#!/bin/bash
# enroll-mac.sh — the one command for a Mac that already has people on it.
#
#   sudo ./enroll-mac.sh --computer-name MEDIA-MAC-01 [--server arise-server] [--ssh-user bradly]
#                        [--only alice,bob] [--skip admin,guest] [--map alice=alice.smith,bob=bob.jones]
#                        [--via ssh|api] [--dashboard http://arise-server:4147]
#                        [--no-migrate] [--dry-run]
#
# What it does, in order, and says so as it goes:
#   1. Binds the Mac to AD.ARISECENLA.CHURCH (mac/bind-mac.sh; skipped if bound).
#   2. Lists the local accounts on this Mac (real people only: uid >= 501,
#      a home folder under /Users, not "admin"/"guest"/anything in --skip).
#   3. For each one, creates the same-named user in the directory on the
#      server. Default: over SSH, `sudo arisectl user add <name> --display "<Full Name>"`.
#      Fallback (--via api): POST /api/directory/users on the dashboard with
#      an admin login. Either way a one-time password is generated here and
#      printed at the end; the person changes it on first login.
#   4. Runs mac/migrate-mac-user.sh for each one (local -> server home).
#      The person must be logged OUT of that account; it skips the ones who are not.
#   5. Installs the two LaunchAgents (mount-home, home-sync) for everyone on this Mac.
#   6. Prints what it did and what is left for a human.
#
# Idempotent: run it again and it skips what is done. --dry-run prints the plan.
# Needs: the ARISE\administrator password (for the bind) and, over SSH, that
# you can `ssh <ssh-user>@<server>` already (ssh-copy-id first).
set -u

HERE=$(cd "$(dirname "$0")" && pwd)
SERVER="arise-server"; SSH_USER="bradly"; COMPUTER=""; ONLY=""; SKIP="admin,guest,administrator,arise,shared"; MAP=""
VIA="ssh"; DASH=""; MIGRATE=1; DRY=0
NETBIOS="ARISE"

die()  { printf '\n  FAILED: %s\n\n' "$*" >&2; exit 1; }
say()  { printf '  %s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
run()  { if [ $DRY -eq 1 ]; then say "would run: $*"; else "$@"; fi; }

while [ $# -gt 0 ]; do
  case "$1" in
    --computer-name) COMPUTER="$2"; shift 2 ;;
    --server)        SERVER="$2"; shift 2 ;;
    --ssh-user)      SSH_USER="$2"; shift 2 ;;
    --only)          ONLY="$2"; shift 2 ;;
    --map)           MAP="$MAP,$2"; shift 2 ;;   # local=directory, e.g. bradly=bradly.dyer (usernames are first.last)
    --skip)          SKIP="$SKIP,$2"; shift 2 ;;
    --via)           VIA="$2"; shift 2 ;;
    --dashboard)     DASH="$2"; shift 2 ;;
    --no-migrate)    MIGRATE=0; shift ;;
    --dry-run)       DRY=1; shift ;;
    -h|--help)       sed -n '2,22p' "$0"; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
done
[ -z "$DASH" ] && DASH="http://${SERVER}:4147"
[ "$(id -u)" -eq 0 ] || die "run with sudo"
[ "$(uname)" = "Darwin" ] || die "this script is for macOS"
[ "$VIA" = "ssh" ] || [ "$VIA" = "api" ] || die "--via must be ssh or api"
for f in bind-mac.sh migrate-mac-user.sh mount-home.sh arise-home-sync.sh com.arisechurch.mounthome.plist com.arisechurch.homesync.plist; do
  [ -f "$HERE/$f" ] || die "$HERE/$f is missing; run this from the mac/ folder of the repo"
done

REPORT=()   # lines for the end
TODO=()     # things a human still has to do
PASSWORDS=() # "name  password"

gen_pw() { # 14 chars, letters and digits, no look-alikes; meets the domain policy (10+, mixed)
  LC_ALL=C tr -dc 'A-HJ-NP-Za-km-z2-9' < /dev/urandom | head -c 11; printf '%s' "$(( RANDOM % 90 + 10 ))x"
}

in_list() { # in_list needle "a,b,c"
  case ",$2," in *",$1,"*) return 0 ;; esac; return 1
}
# The directory name for a local account: --map old=new, else the same name.
# Bradly's rule is first.last (docs/ANSWERS.md 23), so most local names need a map.
dir_name() { local n="$1" pair; IFS=',' read -ra _pairs <<< "$MAP"; for pair in "${_pairs[@]}"; do [ "${pair%%=*}" = "$n" ] && { echo "${pair#*=}"; return; }; done; echo "$n"; }

# ---- 1. bind -------------------------------------------------------------------
step "1/6  Bind to the domain"
if dsconfigad -show 2>/dev/null | grep -q "Active Directory Domain"; then
  say "already bound: $(dsconfigad -show | awk -F'= ' '/Computer Account/{print $2}')"
  REPORT+=("bind: already bound")
else
  [ -n "$COMPUTER" ] || die "--computer-name is required for the bind (the name on the Mac's label)"
  if [ $DRY -eq 1 ]; then say "would run: bind-mac.sh --computer-name $COMPUTER"; REPORT+=("bind: would bind as $COMPUTER")
  else
    bash "$HERE/bind-mac.sh" --computer-name "$COMPUTER" || die "the bind failed; fix what bind-mac.sh printed and run again"
    REPORT+=("bind: bound as $COMPUTER")
  fi
fi

# ---- 2. local accounts --------------------------------------------------------
step "2/6  Local accounts on this Mac"
PEOPLE=()
while IFS= read -r name; do
  [ -n "$name" ] || continue
  uid=$(dscl . -read "/Users/$name" UniqueID 2>/dev/null | awk '{print $2}')
  home=$(dscl . -read "/Users/$name" NFSHomeDirectory 2>/dev/null | awk '{print $2}')
  [ -n "$uid" ] && [ "$uid" -ge 501 ] || continue
  case "$home" in /Users/*) ;; *) continue ;; esac
  if dscl . -read "/Users/$name" OriginalNodeName 2>/dev/null | grep -q "Active Directory"; then say "$name: already a domain (mobile) account; skipped"; continue; fi
  in_list "$name" "$SKIP" && { say "$name: in the skip list"; continue; }
  if [ -n "$ONLY" ] && ! in_list "$name" "$ONLY"; then say "$name: not in --only"; continue; fi
  full=$(dscl . -read "/Users/$name" RealName 2>/dev/null | sed '1d;s/^ *//' | head -1)
  [ -n "$full" ] || full=$(dscl . -read "/Users/$name" RealName 2>/dev/null | awk -F': ' '{print $2}')
  size=$(du -sh "$home" 2>/dev/null | awk '{print $1}')
  say "$name  \"$full\"  $home  $size"
  PEOPLE+=("$name|$full")
done < <(dscl . -list /Users | grep -v '^_')
[ ${#PEOPLE[@]} -gt 0 ] || { say "no local people to enrol"; }

# ---- 3. directory users -----------------------------------------------------
step "3/6  Create the same people in the directory (via $VIA)"
existing=""
if [ "$VIA" = "ssh" ]; then
  if [ $DRY -eq 0 ]; then
    ssh -o BatchMode=yes -o ConnectTimeout=8 "$SSH_USER@$SERVER" true 2>/dev/null || die "cannot ssh to $SSH_USER@$SERVER without a password. On this Mac: ssh-copy-id $SSH_USER@$SERVER, then run again. Or use --via api."
    existing=$(ssh "$SSH_USER@$SERVER" "sudo arisectl user list" 2>/dev/null | awk 'NR>2{print $1}' | tr '\n' ',')
  fi
else
  COOKIE_JAR=$(mktemp)
  if [ $DRY -eq 0 ]; then
    printf '  dashboard admin user: '; read -r ADMIN_USER
    printf '  dashboard password: '; read -rs ADMIN_PW; echo
    code=$(curl -s -o /dev/null -w '%{http_code}' -c "$COOKIE_JAR" -H 'Content-Type: application/json' -d "{\"user\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PW\"}" "$DASH/api/auth/login")
    [ "$code" = "200" ] || die "dashboard login failed ($code) at $DASH/api/auth/login"
    existing=$(curl -s -b "$COOKIE_JAR" "$DASH/api/directory/users" | tr ',' '\n' | awk -F'"' '/"name"/{print $4}' | tr '\n' ',')
  fi
fi
for p in "${PEOPLE[@]}"; do
  name=${p%%|*}; full=${p#*|}; dname=$(dir_name "$name")
  [ "$dname" = "$name" ] || say "$name -> $dname (from --map)"
  case "$dname" in *.*) ;; *) say "$dname: not first.last; add --map $name=first.last if that is the rule"; TODO+=("username $dname is not first.last");; esac
  if in_list "$dname" "$existing"; then say "$dname: already in the directory"; REPORT+=("user $dname: existed"); continue; fi
  pw=$(gen_pw)
  if [ "$VIA" = "ssh" ]; then
    # the password goes over the SSH session, not the command line of this Mac
    if run ssh "$SSH_USER@$SERVER" "sudo arisectl user add '$dname' --display '$full' --password '$pw' --groups Staff"; then
      say "$dname: created (groups: Staff)"; REPORT+=("user $dname: created"); PASSWORDS+=("$dname  $pw")
    else
      say "$dname: arisectl user add FAILED (see above)"; REPORT+=("user $dname: FAILED to create"); TODO+=("create $dname by hand: sudo arisectl user add $dname --display \"$full\"")
    fi
  else
    if [ $DRY -eq 1 ]; then say "would POST $DASH/api/directory/users for $dname"; REPORT+=("user $dname: would create"); continue; fi
    body=$(printf '{"name":"%s","password":"%s","display":"%s","groups":["Staff"]}' "$dname" "$pw" "$full")
    code=$(curl -s -o /tmp/arise-enrol.out -w '%{http_code}' -b "$COOKIE_JAR" -H 'Content-Type: application/json' -d "$body" "$DASH/api/directory/users")
    if [ "$code" = "200" ] && ! grep -q '"ok": *false' /tmp/arise-enrol.out; then
      say "$dname: created (groups: Staff)"; REPORT+=("user $dname: created"); PASSWORDS+=("$dname  $pw")
    else
      say "$dname: API said $code: $(head -c 200 /tmp/arise-enrol.out)"; REPORT+=("user $dname: FAILED to create"); TODO+=("create $dname in Directory > Users > Add")
    fi
  fi
done
[ "$VIA" = "api" ] && rm -f "${COOKIE_JAR:-/nonexistent}"

# ---- 4. migrate ---------------------------------------------------------------
step "4/6  Copy each person's files into their server home"
if [ $MIGRATE -eq 0 ]; then say "skipped (--no-migrate)"; else
  for p in "${PEOPLE[@]}"; do
    name=${p%%|*}; dname=$(dir_name "$name")
    if who | awk '{print $1}' | grep -qx "$name"; then
      say "$name is logged in; skipped. Log them out and run: sudo ./migrate-mac-user.sh --from $name --to $dname"
      TODO+=("migrate $name after they log out: sudo ./migrate-mac-user.sh --from $name --to $dname"); continue
    fi
    if [ $DRY -eq 1 ]; then say "would run: migrate-mac-user.sh --from $name --to $dname"; continue; fi
    say "-- $name -> $dname (you will be asked for $dname's NEW domain password to mount the share)"
    if bash "$HERE/migrate-mac-user.sh" --from "$name" --to "$dname" --server "$SERVER"; then
      REPORT+=("migrate $name: done")
    else
      REPORT+=("migrate $name: finished with warnings (read the manifest on $name's Desktop)")
      TODO+=("check $name's migration manifest, then re-run: sudo ./migrate-mac-user.sh --from $name --to $dname")
    fi
  done
fi

# ---- 5. launch agents -------------------------------------------------------
step "5/6  Install the LaunchAgents (mount the home share at login; sync every 15 minutes)"
run mkdir -p /usr/local/arise
for s in mount-home.sh arise-home-sync.sh; do
  run cp "$HERE/$s" "/usr/local/arise/$s"; run chmod 755 "/usr/local/arise/$s"
done
[ -f /usr/local/arise/sync-folders.txt ] || run sh -c 'printf "# one folder per line, relative to the home. Desktop and Documents are already on the share for domain users.\nDesktop\nDocuments\n" > /usr/local/arise/sync-folders.txt'
for pl in com.arisechurch.mounthome.plist com.arisechurch.homesync.plist; do
  run cp "$HERE/$pl" "/Library/LaunchAgents/$pl"; run chmod 644 "/Library/LaunchAgents/$pl"; run chown root:wheel "/Library/LaunchAgents/$pl"
done
say "installed; they start at the next login of each person"
REPORT+=("launch agents: installed")

# ---- 6. report ----------------------------------------------------------------
step "6/6  Done"
for r in "${REPORT[@]}"; do say "$r"; done
if [ ${#PASSWORDS[@]} -gt 0 ]; then
  echo; say "ONE-TIME PASSWORDS (hand these over in person; the person changes it at first login in the dashboard, flame menu > Change Password):"
  for x in "${PASSWORDS[@]}"; do say "   $x"; done
  umask 077; printf '%s\n' "${PASSWORDS[@]}" > "/var/root/arise-enrol-passwords-$(date +%Y%m%d-%H%M).txt"
  say "   (also written to /var/root/arise-enrol-passwords-<date>.txt, root only; delete it once handed over)"
fi
if [ ${#TODO[@]} -gt 0 ]; then echo; say "LEFT FOR A HUMAN:"; for t in "${TODO[@]}"; do say "   - $t"; done; fi
echo
say "Next: each person logs in on this Mac with their new domain password (Ethernet for the first login)."
say "      Their old local account stays for two weeks; mac/CHECKLIST.md has the rest."
exit 0

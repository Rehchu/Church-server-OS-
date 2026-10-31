#!/bin/bash
# enroll-mac.sh — the one command for a Mac that already has people on it.
#
#   sudo ./enroll-mac.sh --computer-name MEDIA-MAC-01 [--server arise-server] [--ssh-user bradly]
#                        [--only alice,bob] [--skip admin,guest] [--map alice=alice.smith,bob=bob.jones]
#                        [--dns <server ip>] [--via ssh|api] [--dashboard http://arise-server:4147]
#                        [--no-migrate] [--dry-run]
#
# What it does, in order, and says so as it goes:
#   1. Binds the Mac to AD.ARISECENLA.COM (mac/bind-mac.sh; skipped if bound).
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
SERVER="arise-server"; SSH_USER="bradly"; COMPUTER=""; ONLY=""; SKIP="admin,guest,administrator,arise,shared"; MAP=""; DNS_IP=""
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
    --map)           MAP="$MAP,$2"; shift 2 ;;
    --dns)           DNS_IP="$2"; shift 2 ;;   # the server's IP: writes /etc/resolver on this Mac, no router change   # local=directory, e.g. bradly=bradly.dyer (usernames are first.last)
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

gen_pw() { # 15 chars, no look-alikes; always an upper, a lower and a digit (the domain wants 12+ and three kinds)
  LC_ALL=C tr -dc 'A-HJ-NP-Z' < /dev/urandom | head -c 1
  LC_ALL=C tr -dc 'A-HJ-NP-Za-km-z2-9' < /dev/urandom | head -c 11; printf '%s' "$(( RANDOM % 90 + 10 ))x"
}
json_str() { # a JSON string literal: backslash and double quote escaped (passwords may carry either)
  printf '"%s"' "$(printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')"
}

in_list() { # in_list needle "a,b,c"
  case ",$2," in *",$1,"*) return 0 ;; esac; return 1
}
# The directory name for a local account: --map old=new, else the same name.
# Bradly's rule is first.last (docs/ANSWERS.md 23), so most local names need a map.
dir_name() { local n="$1" pair; IFS=',' read -ra _pairs <<< "$MAP"; for pair in ${_pairs[@]+"${_pairs[@]}"}; do [ "${pair%%=*}" = "$n" ] && { echo "${pair#*=}"; return; }; done; echo "$n"; }

# ---- 1. bind -------------------------------------------------------------------
step "1/6  Bind to the domain"
if dsconfigad -show 2>/dev/null | grep -q "Active Directory Domain"; then
  say "already bound: $(dsconfigad -show | awk -F'= ' '/Computer Account/{print $2}')"
  REPORT+=("bind: already bound")
else
  [ -n "$COMPUTER" ] || die "--computer-name is required for the bind (the name on the Mac's label)"
  if [ $DRY -eq 1 ]; then say "would run: bind-mac.sh --computer-name $COMPUTER"; REPORT+=("bind: would bind as $COMPUTER")
  else
    bash "$HERE/bind-mac.sh" --computer-name "$COMPUTER" ${DNS_IP:+--dns "$DNS_IP"} || die "the bind failed; fix what bind-mac.sh printed and run again"
    REPORT+=("bind: bound as $COMPUTER")
  fi
fi

# ---- 1b. the church certificate (round 3, 29): padlock on the dashboard ----------
step "1b   The church certificate"
CA_TMP=$(mktemp /tmp/arise-root.XXXXXX)
if [ $DRY -eq 1 ]; then say "would fetch $DASH/ca.crt and trust it in the System keychain"
elif curl -fsS -m 8 -o "$CA_TMP" "$DASH/ca.crt" && security verify-cert -c "$CA_TMP" >/dev/null 2>&1; then say "already trusted"; REPORT+=("certificate: already trusted")
elif curl -fsS -m 8 -o "$CA_TMP" "$DASH/ca.crt" && grep -q 'BEGIN CERTIFICATE' "$CA_TMP"; then
  if security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain "$CA_TMP"; then say "trusted: this Mac shows the padlock on https://${SERVER}.ad.arisecenla.com"; REPORT+=("certificate: trusted")
  else say "could not add it (security add-trusted-cert failed)"; TODO+=("trust the church certificate by hand: docs/SECURITY.md"); fi
else say "no certificate at $DASH/ca.crt yet (Caddy not running on the server); skipped"; TODO+=("run enroll-mac.sh again once Caddy runs, for the padlock"); fi
rm -f "$CA_TMP"

# ---- 2. local accounts --------------------------------------------------------
step "2/6  Local accounts on this Mac"
PEOPLE=()
while IFS= read -r name; do
  [ -n "$name" ] || continue
  uid=$(dscl . -read "/Users/$name" UniqueID 2>/dev/null | awk '{print $2}')
  home=$(dscl . -read "/Users/$name" NFSHomeDirectory 2>/dev/null | sed -n 's/^NFSHomeDirectory: *//p' | head -1)
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
    code=$(curl -s -o /dev/null -w '%{http_code}' -c "$COOKIE_JAR" -H 'Content-Type: application/json' -d "{\"user\":$(json_str "$ADMIN_USER"),\"password\":$(json_str "$ADMIN_PW")}" "$DASH/api/auth/login")
    [ "$code" = "200" ] || die "dashboard login failed ($code) at $DASH/api/auth/login"
    existing=$(curl -s -b "$COOKIE_JAR" "$DASH/api/directory/users" | tr ',' '\n' | awk -F'"' '/"name"/{print $4}' | tr '\n' ',')
  fi
fi
for p in ${PEOPLE[@]+"${PEOPLE[@]}"}; do
  name=${p%%|*}; full=${p#*|}; dname=$(dir_name "$name")
  [ "$dname" = "$name" ] || say "$name -> $dname (from --map)"
  case "$dname" in *.*) ;; *) say "$dname: not first.last; add --map $name=first.last if that is the rule"; TODO+=("username $dname is not first.last");; esac
  if in_list "$dname" "$existing"; then say "$dname: already in the directory"; REPORT+=("user $dname: existed"); continue; fi
  pw=$(gen_pw)
  if [ "$VIA" = "ssh" ]; then
    # The password goes down the SSH session on stdin: on a command line, sudo would write it to the
    # server's /var/log/auth.log (kept a year). arisectl user add --password-stdin reads one line.
    if [ $DRY -eq 1 ]; then say "would create $dname over ssh"; REPORT+=("user $dname: would create"); continue; fi
    if printf '%s\n' "$pw" | ssh "$SSH_USER@$SERVER" "sudo arisectl user add '$dname' --display '$full' --password-stdin --groups Staff"; then
      say "$dname: created (groups: Staff)"; REPORT+=("user $dname: created"); PASSWORDS+=("$dname  $pw")
    else
      say "$dname: arisectl user add FAILED (see above)"; REPORT+=("user $dname: FAILED to create"); TODO+=("create $dname by hand: sudo arisectl user add $dname --display \"$full\"")
    fi
  else
    if [ $DRY -eq 1 ]; then say "would POST $DASH/api/directory/users for $dname"; REPORT+=("user $dname: would create"); continue; fi
    body=$(printf '{"name":%s,"password":%s,"display":%s,"groups":["Staff"]}' "$(json_str "$dname")" "$(json_str "$pw")" "$(json_str "$full")")
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
  for p in ${PEOPLE[@]+"${PEOPLE[@]}"}; do
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

# ---- 5b. fonts: a first copy of Media/Fonts into /Library/Fonts (every account on this Mac) ----
# The hourly sync keeps each person's own ~/Library/Fonts current afterwards.
step "5b   Fonts from the media share"
if [ $DRY -eq 1 ]; then say "would copy smb://$SERVER/media/Fonts -> /Library/Fonts"; else
  if ! mount | grep -q " on /Volumes/media "; then open "smb://$SERVER/media" >/dev/null 2>&1; t=0; until mount | grep -q " on /Volumes/media "; do t=$((t+1)); [ $t -gt 6 ] && break; sleep 3; done; fi
  if [ -d /Volumes/media/Fonts ]; then
    n=$(rsync -rlt --update --no-perms --no-owner --no-group --include='*/' --include='*.ttf' --include='*.otf' --include='*.ttc' --include='*.TTF' --include='*.OTF' --exclude='*' --stats /Volumes/media/Fonts/ /Library/Fonts/ 2>&1 | awk '/Number of regular files transferred/{print $NF}')
    say "fonts: ${n:-0} installed into /Library/Fonts"; REPORT+=("fonts: ${n:-0} from media/Fonts")
  else
    say "media/Fonts not reachable from this Mac (mount smb://$SERVER/media as someone in the Media group and re-run, or let the hourly sync do it per person)"
    TODO+=("fonts: open smb://$SERVER/media once as a Media member; the hourly sync then installs Media/Fonts for that person")
  fi
fi

# ---- 6. report ----------------------------------------------------------------
step "6/6  Done"
for r in ${REPORT[@]+"${REPORT[@]}"}; do say "$r"; done
if [ ${#PASSWORDS[@]} -gt 0 ]; then
  echo; say "ONE-TIME PASSWORDS (hand these over in person; the person changes it at first login in the dashboard, flame menu > Change Password):"
  for x in ${PASSWORDS[@]+"${PASSWORDS[@]}"}; do say "   $x"; done
  umask 077; printf '%s\n' ${PASSWORDS[@]+"${PASSWORDS[@]}"} > "/var/root/arise-enrol-passwords-$(date +%Y%m%d-%H%M).txt"
  say "   (also written to /var/root/arise-enrol-passwords-<date>.txt, root only; delete it once handed over)"
fi
if [ ${#TODO[@]} -gt 0 ]; then echo; say "LEFT FOR A HUMAN:"; for t in ${TODO[@]+"${TODO[@]}"}; do say "   - $t"; done; fi
echo
say "Next: each person logs in on this Mac with their new domain password (Ethernet for the first login)."
say "      Their old local account stays for two weeks; mac/CHECKLIST.md has the rest."
exit 0

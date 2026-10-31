#!/bin/bash
# nextcloud.sh: the Mac helper's `nextcloud` task (docs/ANSWERS.md round 6, rows 13-19, 39, 40;
# docs/SYNC.md is the plain-words version).
#
# Sets up the Nextcloud desktop client in one macOS account so that:
#   - its Desktop, Documents, Downloads, Pictures and Music sync in full with the server user's
#     home folder (row 13; round 7, 42 and 43), the Photos and Music libraries left out;
#   - the Church, department, Pastors and Shared-with-me folders show in Finder's sidebar,
#     on demand, through the client's File Provider (row 16);
#   - it signs in with a device app password the server issues for that server user, never a
#     domain password (the server asks Nextcloud for it; it is shown to no one);
#   - nothing is ever deleted: the first sync merges what is already on the Mac with what is
#     on the server, and a local APFS snapshot is taken first.
#
# The helper (mac/helper/arise-mac-helper, as root) calls it as
#   nextcloud.sh --user <first.last> --local <short name> --server <https://dashboard>
# and also accepted:
#   nextcloud.sh --server-user <first.last> --local-user <macname> [--server <url>]
# --local is the macOS account to set up: the AD (mobile) account itself, or a LOCAL account an
# admin chose to Link to a server user (the local login itself is left exactly as it is), or a
# department login (row 40: they sync like a person).
#
# Other options:
#   --version 3.14.3       the client version to install (the server's [cloud] client_version)
#   --app-password-file F  read the app password from F (then shredded) instead of asking the server
#   --cloud-url URL        Nextcloud's address, when the server's answer should be overridden
#   --check                say what would happen, change nothing
#   --finish               (internal) run as the user at their next sign-in, when they were not signed in
#   --finish-stdin         (internal) run as the user now, the details on stdin
#
# Exit 0 = done (or staged for the person's next sign-in); the last line says what happened.
# Any other exit = failed; the last line is the reason (the helper reports it).
set -u
umask 077

VERSION_WANTED="3.14.3"
TEAM_ID="NKUJUXUJ3B"     # Nextcloud GmbH's Apple Developer ID team (read from the 3.14.3 pkg's own certificate)
APP="/Applications/Nextcloud.app"
BIN="$APP/Contents/MacOS/Nextcloud"
DOMAIN_ID="com.nextcloud.desktopclient"
DB=/var/db/arise
CONF="$DB/helper.conf"
KEYF="$DB/helper.key"
CACERT="$DB/arise-ca.crt"
SELF="$0"
FIRSTRUN_LABEL="church.arise.nextcloud-firstrun"

S_USER=""; L_USER=""; SERVER=""; CLOUD=""; PWFILE=""; CHECK=0; FINISH=0
FOLDERS="Desktop Documents Downloads Pictures Music"   # round 7, 42 and 43; the server's answer can narrow it
say() { printf '%s\n' "$*"; }
fail() { printf 'FAILED: %s\n' "$*"; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --user|--server-user) S_USER="${2:-}"; shift 2 ;;
    --local|--local-user) L_USER="${2:-}"; shift 2 ;;
    --server|--server-url) SERVER="${2:-}"; shift 2 ;;
    --cloud-url) CLOUD="${2:-}"; shift 2 ;;
    --version) VERSION_WANTED="${2:-}"; shift 2 ;;
    --app-password-file) PWFILE="${2:-}"; shift 2 ;;
    --check) CHECK=1; shift ;;
    --finish) FINISH=1; shift ;;
    --finish-stdin) FINISH=2; shift ;;
    -h|--help) sed -n '2,34p' "$0"; exit 0 ;;
    *) fail "unknown option $1" ;;
  esac
done

# ----- pieces both halves use --------------------------------------------------------------
host_of() { local h="${1#*://}"; h="${h%%/*}"; printf '%s' "${h%%:*}"; }
cfg_file() { printf '%s/Library/Preferences/Nextcloud/nextcloud.cfg' "$1"; }

# The client's own ini (QSettings): which account index holds this server user on this server?
account_index() {   # account_index <cfg> <user> <host>
  [ -f "$1" ] || return 1
  awk -v u="$2" -v h="$3" '
    /^\[/ { sec=$0; next }
    sec=="[Accounts]" && match($0, /^[0-9]+\\dav_user=/) { i=substr($0,1,index($0,"\\")-1); du[i]=substr($0,index($0,"=")+1) }
    sec=="[Accounts]" && match($0, /^[0-9]+\\url=/) { i=substr($0,1,index($0,"\\")-1); ur[i]=substr($0,index($0,"=")+1) }
    END { for (i in du) if (du[i]==u && index(ur[i], h)) { print i; exit 0 } exit 1 }' "$1"
}

# Is a folder pair to this local path already there? (any of the client's folder groups)
has_pair() {   # has_pair <cfg> <index> <local path>
  grep -E "^$2\\\\(Folders|Multifolders|FoldersWithPlaceholders)\\\\[^\\\\]+\\\\localPath=$(printf '%s' "$3" | sed 's/[][\.*^$/]/\\&/g')/?$" "$1" >/dev/null 2>&1
}

# Add a classic (full) folder pair under [Accounts], the way FolderDefinition::save writes one.
# journalPath left empty: the client fills in its default (.sync_<hash>.db) when it loads it.
add_pair() {   # add_pair <cfg> <index> <local path> <remote path>
  local cfg="$1" i="$2" lp="$3" rp="$4" n tmp
  n="$(grep -oE "^$i\\\\Folders\\\\[0-9]+\\\\" "$cfg" | grep -oE '[0-9]+\\$' | tr -d '\\' | sort -n | tail -1)"
  n=$(( ${n:-0} + 1 ))
  tmp="$(mktemp "$cfg.XXXX")" || return 1
  awk -v i="$i" -v n="$n" -v lp="${lp%/}/" -v rp="$rp" '
    { print }
    $0=="[Accounts]" && !done {
      p=i "\\Folders\\" n "\\"
      print p "ignoreHiddenFiles=false"; print p "journalPath="; print p "localPath=" lp
      print p "paused=false"; print p "targetPath=" rp; print p "version=2"; print p "virtualFilesMode=off"
      done=1 }' "$cfg" > "$tmp" && cat "$tmp" > "$cfg"
  rm -f "$tmp"
}

quit_client() {   # as the user
  pgrep -u "$(id -u)" -x Nextcloud >/dev/null 2>&1 || return 0
  osascript -e 'tell application "Nextcloud" to quit' >/dev/null 2>&1
  for _ in $(seq 1 20); do pgrep -u "$(id -u)" -x Nextcloud >/dev/null 2>&1 || return 0; sleep 1; done
  pkill -u "$(id -u)" -x Nextcloud >/dev/null 2>&1; sleep 2
}

# ----- the user's half: runs inside the person's own session (their keychain, their prefs) ------
# Reads "SERVER_USER= CLOUD_URL= APP_PASSWORD=" lines on stdin, never from argv or the environment.
# Round 7, 43: the libraries inside Pictures and Music never sync. Photos' and Music's databases,
# copied file by file while the app has them open, corrupt; they stay on the Mac (Time Machine has
# them). These go in the person's own exclude list, next to the client's settings, where the client
# reads its user-level excludes. The same list is the helper's SKIP_PKGS.
NC_SKIP='*.photoslibrary *.photolibrary *.migratedphotolibrary *.musiclibrary *.tvlibrary *.aplibrary *.imovielibrary *.fcpbundle'
write_excludes() {   # write_excludes <client config dir>: add each pattern once; nothing else is touched
  local dir="$1" f p
  mkdir -p "$dir"; f="$dir/sync-exclude.lst"; touch "$f"
  set -f
  for p in $NC_SKIP; do grep -qxF "$p" "$f" || printf '%s\n' "$p" >> "$f"; done
  set +f
  grep -qxF "Photo Booth Library" "$f" || printf '%s\n' "Photo Booth Library" >> "$f"
}

user_half() {
  local su="" url="" pw="" line h cfg idx folders="Desktop Documents Downloads Pictures Music" f ok=1 note=""
  while IFS= read -r line; do
    case "$line" in SERVER_USER=*) su="${line#*=}" ;; CLOUD_URL=*) url="${line#*=}" ;; APP_PASSWORD=*) pw="${line#*=}" ;; FOLDERS=*) folders="${line#*=}" ;; esac
  done
  [ -n "$su" ] && [ -n "$url" ] && [ -n "$pw" ] || fail "the set-up details did not arrive"
  [ -x "$BIN" ] || fail "the Nextcloud client is not installed"
  h="$(host_of "$url")"; cfg="$(cfg_file "$HOME")"
  write_excludes "$(dirname "$cfg")"
  for f in $folders; do mkdir -p "$HOME/$f"; done
  # File Provider: the shares, on demand, in Finder's sidebar (the client reads this list at start).
  defaults write "$DOMAIN_ID" enabledAccounts -array "$su@$h"
  quit_client
  if ! idx="$(account_index "$cfg" "$su" "$h")"; then
    # The client's own command-line account set-up (3.6+): it stores the app password in this
    # person's login keychain, and makes the first folder pair, Desktop, in full (not virtual).
    "$BIN" --userid "$su" --apppassword "$pw" --serverurl "$url" \
           --localdirpath "$HOME/Desktop" --remotedirpath /Desktop --isvfsenabled 0 >/dev/null 2>&1 &
    for _ in $(seq 1 90); do idx="$(account_index "$cfg" "$su" "$h")" && has_pair "$cfg" "$idx" "$HOME/Desktop" && break; sleep 1; done
    pw=""
    idx="$(account_index "$cfg" "$su" "$h")" || { quit_client; fail "the Nextcloud client did not take the account (is $url reachable, and the church certificate trusted?)"; }
    sleep 3; quit_client
  fi
  pw=""
  # The rest of the folders as full pairs, merged with what is there (nothing on either side is removed).
  for f in $folders; do
    has_pair "$cfg" "$idx" "$HOME/$f" || add_pair "$cfg" "$idx" "$HOME/$f" "/$f" || ok=0
  done
  open -g -a "$APP" >/dev/null 2>&1 || "$BIN" >/dev/null 2>&1 &
  # Did each pair start? The client writes its journal into the folder when it does.
  for _ in $(seq 1 120); do
    note=""
    for f in $folders; do ls "$HOME/$f"/.sync_*.db >/dev/null 2>&1 || note="$note $f"; done
    [ -z "$note" ] && break; sleep 1
  done
  [ "$ok" = 1 ] || fail "could not add the folder pairs to $cfg"
  [ -z "$note" ] || say "note: not syncing yet:$note (Nextcloud → Settings shows why; it carries on in the background)"
  say "OK: Nextcloud signs $(id -un) in as $su on $h; ${folders// /, } sync in full; the shares are in Finder's sidebar"
}

# tests/test_cloud.py sources this file for the functions above, on Linux, and stops here.
if [ "${ARISE_NC_LIB:-}" = 1 ]; then return 0 2>/dev/null || exit 0; fi

# Run in the person's session: now (the root half pipes the details in), or at their next sign-in.
if [ "$FINISH" = 2 ]; then
  [ "$(id -u)" != 0 ] || fail "--finish-stdin runs as the person, not root"
  user_half; exit $?
fi
if [ "$FINISH" = 1 ]; then
  st="$HOME/Library/Application Support/Arise/nextcloud-firstrun"
  [ -f "$st" ] || exit 0
  out="$(user_half < "$st" 2>&1)"; rc=$?
  rm -P "$st" 2>/dev/null || rm -f "$st"
  launchctl bootout "gui/$(id -u)/$FIRSTRUN_LABEL" >/dev/null 2>&1
  rm -f "$HOME/Library/LaunchAgents/$FIRSTRUN_LABEL.plist"
  mkdir -p "$HOME/Library/Logs"; printf '%s %s\n' "$(date '+%F %T')" "$out" >> "$HOME/Library/Logs/arise-nextcloud.log"
  exit $rc
fi

# ----- the root half -------------------------------------------------------------------------
[ "$(id -u)" = 0 ] || fail "run as root (the Mac helper does)"
[[ "$S_USER" =~ ^[a-z0-9][a-z0-9._-]{0,63}$ ]] || fail "--user must be a server user name like first.last"
[ -n "$L_USER" ] || L_USER="$S_USER"
[[ "$L_USER" =~ ^[A-Za-z0-9._-]{1,64}$ ]] || fail "--local must be a macOS short name"
L_UID="$(id -u "$L_USER" 2>/dev/null)" || fail "there is no macOS account $L_USER on this Mac (a domain account appears at its first sign-in here)"
[ "$L_UID" -ge 500 ] || fail "$L_USER is a system account"
L_HOME="$(dscl . -read "/Users/$L_USER" NFSHomeDirectory 2>/dev/null | sed -n 's/^NFSHomeDirectory: *//p' | head -1)"
[ -d "$L_HOME" ] || fail "$L_USER has no home folder on this Mac yet"
case "$L_HOME" in /Users/*) ;; *) fail "$L_USER's home is $L_HOME, not a local folder: Nextcloud syncs a local home only" ;; esac
if [ -d "$L_HOME/Library/Mobile Documents/com~apple~CloudDocs/Desktop" ]; then
  fail "iCloud's Desktop & Documents is on for $L_USER: turn it off in System Settings → Apple ID → iCloud Drive first, or the two would fight over the same folders"
fi
[ -n "$SERVER" ] || SERVER="$(sed -n 's/^SERVER=//p' "$CONF" 2>/dev/null | head -1)"
DEVICE_MODEL="$(sysctl -n hw.model 2>/dev/null)"

installed_version() { defaults read "$APP/Contents/Info.plist" CFBundleShortVersionString 2>/dev/null; }
older() { [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -t. -k1,1n -k2,2n -k3,3n | head -1)" = "$1" ]; }   # older A B: A < B

if [ "$CHECK" = 1 ]; then
  say "would: install Nextcloud $VERSION_WANTED (have: $(installed_version || echo none)), signature by team $TEAM_ID checked"
  say "would: ask $SERVER for a device app password for $S_USER ($L_USER on $(scutil --get ComputerName 2>/dev/null))"
  say "would: set it up in $L_USER's session: ${FOLDERS// /, } in full (the Photos and Music libraries left out), the shares in Finder's sidebar"
  exit 0
fi

# 1. The client: the official signed package, its signature and notarisation checked before it runs.
have="$(installed_version)"
if [ -z "$have" ] || older "$have" "$VERSION_WANTED"; then
  work="$(mktemp -d /tmp/arise-nextcloud.XXXXXX)" || fail "no temporary folder"
  pkg="$work/Nextcloud-$VERSION_WANTED-macOS-vfs.pkg"
  curl -fsSL --max-time 900 -o "$pkg" "https://github.com/nextcloud-releases/desktop/releases/download/v$VERSION_WANTED/Nextcloud-$VERSION_WANTED-macOS-vfs.pkg" \
    || { rm -rf "$work"; fail "could not download Nextcloud $VERSION_WANTED (internet reachable from this Mac?)"; }
  sig="$(pkgutil --check-signature "$pkg" 2>&1)"
  case "$sig" in
    *"Status: signed by a developer certificate issued by Apple"*"Developer ID Installer: Nextcloud GmbH ($TEAM_ID)"*) ;;
    *) rm -rf "$work"; fail "the downloaded package is not signed by Nextcloud GmbH ($TEAM_ID); nothing installed" ;;
  esac
  spctl --assess --type install "$pkg" >/dev/null 2>&1 || { rm -rf "$work"; fail "macOS does not accept the package as notarised; nothing installed"; }
  # Quit any running copy first (an upgrade in place).
  pkill -x Nextcloud >/dev/null 2>&1; sleep 2
  installer -pkg "$pkg" -target / >/dev/null 2>&1 || { rm -rf "$work"; fail "installer refused the Nextcloud package"; }
  rm -rf "$work"
  codesign --verify --deep --strict "$APP" >/dev/null 2>&1 || fail "the installed Nextcloud.app fails its code signature check"
  codesign -dv "$APP" 2>&1 | grep -q "TeamIdentifier=$TEAM_ID" || fail "the installed Nextcloud.app is not Nextcloud GmbH's"
  say "installed Nextcloud $(installed_version)"
fi

# 2. Machine-wide defaults every account on this Mac starts from (/Library/Preferences, read by the
#    client before each person's own settings): no size limit (row 18), no prompt for the shares,
#    ask before a sync would remove everything, deletions from the server go to the Mac's Trash,
#    and updates come through the helper (a standard user cannot install them).
P="/Library/Preferences/$DOMAIN_ID"
defaults write "$P" useNewBigFolderSizeLimit -bool false
defaults write "$P" newBigFolderSizeLimit -int -1
defaults write "$P" notifyExistingFoldersOverLimit -bool false
defaults write "$P" confirmExternalStorage -bool false
defaults write "$P" promptDeleteAllFiles -bool true
defaults write "$P" moveToTrash -bool true
defaults write "$P" skipUpdateCheck -bool true
chmod 644 "$P.plist" 2>/dev/null

# 3. Already set up for this server user? Then nothing more: the client keeps its own password,
#    and a new one is never asked for (issuing one would sign the existing copy out). To set a Mac
#    up again, remove the account in Nextcloud → Settings first, then queue the task again.
L_CFG="$(cfg_file "$L_HOME")"
if grep -q "^[0-9]*\\\\dav_user=$S_USER\$" "$L_CFG" 2>/dev/null; then
  say "OK: Nextcloud already signs $L_USER in as $S_USER"; exit 0
fi

# 4. The device app password, from the server (only for a task an admin queued for this Mac).
PW=""
if [ -n "$PWFILE" ]; then
  [ -f "$PWFILE" ] || fail "no $PWFILE"
  PW="$(head -1 "$PWFILE")"; rm -P "$PWFILE" 2>/dev/null || rm -f "$PWFILE"
else
  MAC_ID="$(sed -n 's/^MAC_ID=//p' "$CONF" 2>/dev/null | head -1)"; KEY="$(cat "$KEYF" 2>/dev/null)"
  [ -n "$SERVER" ] && [ -n "$MAC_ID" ] && [ -n "$KEY" ] || fail "this Mac is not enrolled with the helper (no $CONF)"
  ca=(); case "$SERVER" in https:*) [ -f "$CACERT" ] && ca=(--cacert "$CACERT") ;; esac
  # ${ca[@]+...}: bash 3.2 (macOS) calls an empty "${ca[@]}" unbound under set -u.
  ans="$(curl -fsS --max-time 120 ${ca[@]+"${ca[@]}"} -H @- "$SERVER/api/cloud/agent/app-password" \
          --data-urlencode "user=$S_USER" --data-urlencode "local=$L_USER" --data-urlencode "model=$DEVICE_MODEL" <<< "X-Arise-Mac: $MAC_ID:$KEY" 2>&1)" \
    || fail "the server gave no app password: $(printf '%s' "$ans" | tail -1)"
  case "$ans" in ERROR*) fail "the server refused: ${ans#ERROR }" ;; esac
  PW="$(printf '%s\n' "$ans" | sed -n 's/^APP_PASSWORD=//p' | head -1)"
  [ -n "$CLOUD" ] || CLOUD="$(printf '%s\n' "$ans" | sed -n 's/^CLOUD_URL=//p' | head -1)"
  f="$(printf '%s\n' "$ans" | sed -n 's/^FOLDERS=//p' | head -1)"
  # Only plain folder names in the person's home (Desktop, Documents, ...), never a path.
  case "$f" in *[!A-Za-z\ ]*|"") ;; *) FOLDERS="$f" ;; esac
  ans=""
fi
[ -n "$PW" ] || fail "no app password came back"
[ -n "$CLOUD" ] || CLOUD="https://cloud.ad.arisecenla.com"
case "$CLOUD" in https://*) ;; *) fail "Nextcloud's address must be https ($CLOUD)" ;; esac

# 5. Can this Mac reach it, on the church certificate? (the church network, or Tailscale off-site: row 17)
if ! curl -fsS --max-time 20 "$CLOUD/status.php" >/dev/null 2>&1; then
  if ! curl -fsSk --max-time 20 "$CLOUD/status.php" >/dev/null 2>&1; then
    fail "cannot reach $CLOUD: on the church network or Tailscale? (and is its name in DNS, docs/SYNC.md)"
  fi
  fail "$CLOUD answers but this Mac does not trust the church certificate yet: run the certificate task first"
fi

# 6. Before the first sync touches anything, a local snapshot of the disk (kept by macOS about a day).
tmutil localsnapshot >/dev/null 2>&1 || true

# 7. Into the person's session now, or at their next sign-in.
details() { printf 'SERVER_USER=%s\nCLOUD_URL=%s\nAPP_PASSWORD=%s\nFOLDERS=%s\n' "$S_USER" "$CLOUD" "$PW" "$FOLDERS"; }
if launchctl print "gui/$L_UID" >/dev/null 2>&1 && [ "$(stat -f %Su /dev/console 2>/dev/null)" = "$L_USER" ]; then
  out="$(details | launchctl asuser "$L_UID" sudo -u "$L_USER" -H /bin/bash "$SELF" --finish-stdin 2>&1)"; rc=$?
  PW=""
  printf '%s\n' "$out"
  exit $rc
fi
# Not signed in on the screen: leave the details for them alone (0600, theirs) and a one-time agent.
st_dir="$L_HOME/Library/Application Support/Arise"
mkdir -p "$st_dir" "$L_HOME/Library/LaunchAgents"
details > "$st_dir/nextcloud-firstrun"; PW=""
chown -R "$L_USER" "$st_dir"; chmod 700 "$st_dir"; chmod 600 "$st_dir/nextcloud-firstrun"
install -m 755 -o root -g wheel "$SELF" /usr/local/arise/helper/tasks/nextcloud.sh 2>/dev/null || true
cat > "$L_HOME/Library/LaunchAgents/$FIRSTRUN_LABEL.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$FIRSTRUN_LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>/usr/local/arise/helper/tasks/nextcloud.sh</string><string>--finish</string></array>
  <key>RunAtLoad</key><true/>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
</dict></plist>
PLIST
chown "$L_USER" "$L_HOME/Library/LaunchAgents" "$L_HOME/Library/LaunchAgents/$FIRSTRUN_LABEL.plist"
chmod 644 "$L_HOME/Library/LaunchAgents/$FIRSTRUN_LABEL.plist"
say "OK: staged: Nextcloud finishes setting up when $L_USER next signs in on this Mac (as $S_USER)"

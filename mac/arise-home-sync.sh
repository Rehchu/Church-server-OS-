#!/bin/bash
# arise-home-sync.sh — keep this person's work on the server, whatever else happens.
#
# The fallback (round 6, docs/MACS.md): macOS removed the home sync of mobile accounts
# in 10.12, so on church Macs Desktop and Documents are to sync through the Nextcloud
# client (the helper's nextcloud task). This script keeps doing the job until that is
# in, and on any Mac where Nextcloud is not running.
#
# Run by the LaunchAgent com.arisechurch.homesync: once at login, then every
# 15 minutes. If the person's home share on the server is reachable (on the
# church network, or over Tailscale from anywhere) it copies the chosen
# folders to smb://arise-server/homes/<user>. If the share is not reachable
# it logs one line and waits for the next run. Nothing is ever lost on the
# Mac; nothing is deleted on the server unless --mirror is given.
#
#   /usr/local/arise/arise-home-sync.sh [--dry-run] [--mirror] [--folders "Desktop Documents"] [--max-size 2G] [--server arise-server]
#
# Install for everyone on a Mac (once, as admin) — enroll-mac.sh does this:
#   sudo mkdir -p /usr/local/arise && sudo cp arise-home-sync.sh /usr/local/arise/ && sudo chmod 755 /usr/local/arise/arise-home-sync.sh
#   sudo cp com.arisechurch.homesync.plist /Library/LaunchAgents/ && sudo chmod 644 /Library/LaunchAgents/com.arisechurch.homesync.plist
#
# Which folders: /usr/local/arise/sync-folders.txt, one folder name per line,
# relative to the home. Default when the file is missing: Desktop, Documents.
# A folder that is already a symlink into the share (mount-home.sh did that)
# is skipped: it is on the server already.
#
# Who it runs for:
#   - a domain (mobile) account: always.
#   - a LOCAL account whose short name matches a directory user: also. That is
#     how a Mac nobody has migrated yet still gets its work onto the server.
#     The share is mounted with the saved credential from the first manual
#     mount (Keychain), or with the Kerberos ticket a domain login left behind.
#   - any other local account (a guest, "admin"): skipped, says so in the log.
#
# Why rsync over the mounted share and not an SMB-native copy: macOS has no
# SMB client command that compares by time and size and copies only what
# changed; Finder and cp copy everything every time. rsync does the delta,
# keeps timestamps, handles a dropped connection half way (next run resumes),
# and its --backup lets us keep the older copy of a conflict instead of
# losing it. rsync over a mounted SMB volume is also the one thing Apple
# ships that works the same on every macOS since 10.x. We do not use rsync's
# own network protocol: that would need an rsync daemon or SSH for every
# person on the server, and the share is already there with the right ACLs.
#
# Direction and conflicts: Mac -> server, newest wins. rsync --update skips a
# file whose copy on the server is newer than the one on the Mac (someone
# edited it from the dashboard or another Mac). Every server file that is
# about to be overwritten is first moved to
#   ~/Library/Application Support/Arise/conflicts/<date>/<path>
# on the Mac, so the older version is never gone. Server -> Mac is not done
# here on purpose: pulling into a live home folder while apps have files open
# is how data gets corrupted. The person opens /Volumes/<user> in Finder (or
# the dashboard) for the server's copy.
set -u

SERVER="${ARISE_SERVER:-arise-server}"
DRY=0; MIRROR=0; FOLDERS=""; MAX_SIZE="${ARISE_SYNC_MAX_SIZE:-2G}"
CONF="/usr/local/arise/sync-folders.txt"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)  DRY=1; shift ;;
    --mirror)   MIRROR=1; shift ;;
    --folders)  FOLDERS="$2"; shift 2 ;;
    --max-size) MAX_SIZE="$2"; shift 2 ;;
    --server)   SERVER="$2"; shift 2 ;;
    -h|--help)  sed -n '2,12p' "$0"; exit 0 ;;
    *) printf 'unknown option %s\n' "$1" >&2; exit 2 ;;
  esac
done

USER_NAME=$(id -un)
HOME_DIR="$HOME"
LOG="$HOME_DIR/Library/Logs/arise-home-sync.log"
STATE_DIR="$HOME_DIR/Library/Application Support/Arise"
CONFLICTS="$STATE_DIR/conflicts/$(date +%Y-%m-%d_%H%M)"
LOCK="$STATE_DIR/.sync.lock"
MOUNT="/Volumes/$USER_NAME"
mkdir -p "$(dirname "$LOG")" "$STATE_DIR"
log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; [ -t 1 ] && printf '  %s\n' "$*"; }

# Keep the log from growing forever: 2000 lines is weeks of runs.
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 2500 ]; then tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; fi

# One at a time. A stale lock older than 6 hours is ignored (a crash mid-run).
if [ -f "$LOCK" ]; then
  if [ -n "$(find "$LOCK" -mmin -360 2>/dev/null)" ]; then log "another sync is still running; skipping"; exit 0; fi
  rm -f "$LOCK"
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

# ---- Nextcloud syncs this account now (round 6, docs/SYNC.md)? Then this copy stands down,
# so two programs never write the same folders. mac/helper/tasks/nextcloud.sh sets that up.
if grep -q '^[0-9]*\\dav_user=' "$HOME_DIR/Library/Preferences/Nextcloud/nextcloud.cfg" 2>/dev/null; then
  log "Nextcloud syncs $USER_NAME's Desktop and Documents now; this copy is not needed"
  exit 0
fi

# ---- is this someone with a home on the server? ----------------------------
IS_DOMAIN=0
if dscl . -read "/Users/$USER_NAME" OriginalNodeName 2>/dev/null | grep -q "Active Directory"; then
  IS_DOMAIN=1
elif dscl "/Active Directory/ARISE/All Domains" -read "/Users/$USER_NAME" RecordName >/dev/null 2>&1; then
  # a local account with the same short name as a directory user: sync it too
  IS_DOMAIN=0
else
  log "$USER_NAME is a local account with no matching directory user; nothing to sync"
  exit 0
fi

# ---- is the server reachable right now? -------------------------------------
if ! nc -z -G 3 "$SERVER" 445 >/dev/null 2>&1; then
  log "$SERVER:445 not reachable (off the church network and no VPN?); will try again next run"
  exit 0
fi

# ---- mount the home share if it is not mounted ------------------------------
if ! mount | grep -q " on $MOUNT "; then
  # 'open' asks Finder to mount it. A domain login has a Kerberos ticket, so no
  # prompt. A local account gets a prompt the FIRST time; tick "Remember this
  # password in my keychain" and it never asks again.
  open "smb://${SERVER}/homes/${USER_NAME}" >/dev/null 2>&1
  tries=0
  until mount | grep -q " on $MOUNT "; do
    tries=$((tries+1)); [ $tries -gt 9 ] && break; sleep 5
  done
fi
if ! mount | grep -q " on $MOUNT "; then
  log "could not mount smb://$SERVER/homes/$USER_NAME (no saved password yet? open it once in Finder and tick Remember)"
  exit 0
fi
if ! touch "$MOUNT/.arise-sync-test" 2>/dev/null; then
  log "share mounted but read-only; on the server run: arisectl user homefix $USER_NAME"
  exit 0
fi
rm -f "$MOUNT/.arise-sync-test"

# ---- which folders ----------------------------------------------------------
if [ -z "$FOLDERS" ]; then
  if [ -r "$CONF" ]; then FOLDERS=$(grep -v '^\s*#' "$CONF" | grep -v '^\s*$' | tr '\n' ' '); fi
  [ -n "$FOLDERS" ] || FOLDERS="Desktop Documents"
fi

# Things that must not go to a network share: Apple's library bundles (sqlite
# inside, they corrupt over SMB), caches, cloud-synced folders (they have their
# own sync), the macOS junk.
EXCLUDES=(
  "*.photoslibrary" "*.imovielibrary" "*.fcpbundle" "*.musiclibrary" "*.tvlibrary"
  ".DS_Store" "Icon?" ".localized" ".Trash" ".Trashes" ".Spotlight-V100" ".fseventsd" ".TemporaryItems"
  "*/Library/Caches/*" "*.tmp" "*.part" "*.crdownload" "~$*" ".~lock.*"
  "node_modules" ".git/objects" "*.vmdk" "*.vdi" "*.sparsebundle"
)
RSYNC_EX=(); for e in ${EXCLUDES[@]+"${EXCLUDES[@]}"}; do RSYNC_EX+=(--exclude "$e"); done

# Newest wins only because the server's older copy is moved aside first (--backup-dir). An rsync
# without it (openrsync on some macOS 15 builds) would overwrite instead, so this copy stands down.
case "$(rsync --help 2>&1)" in
  *--backup-dir*) ;;
  *) log "this Mac's rsync has no --backup-dir (openrsync?): nothing synced, so no server copy is overwritten; Nextcloud is the way (docs/SYNC.md)"; exit 0 ;;
esac
RSYNC_OPTS=(-rltD --update --no-perms --no-owner --no-group --max-size="$MAX_SIZE" --timeout=120 --partial
            --backup --backup-dir="$CONFLICTS" ${RSYNC_EX[@]+"${RSYNC_EX[@]}"})
# -rltD not -a: SMB cannot store Unix permissions or owners and -a makes rsync
# complain every run. --update is the newest-wins rule. --backup moves the
# server's older copy aside before it is overwritten (that is the conflict copy).
[ $MIRROR -eq 1 ] && RSYNC_OPTS+=(--delete --delete-after)
[ $DRY -eq 1 ] && RSYNC_OPTS+=(--dry-run)

log "sync start: $USER_NAME -> $MOUNT  folders: $FOLDERS  $([ $DRY -eq 1 ] && echo DRY-RUN) $([ $MIRROR -eq 1 ] && echo MIRROR)"
FAIL=0; TOTAL=0
for f in $FOLDERS; do
  src="$HOME_DIR/$f"
  if [ -L "$src" ]; then log "  $f is a link into the share already; skipped"; continue; fi
  if [ ! -d "$src" ]; then log "  $f does not exist on this Mac; skipped"; continue; fi
  mkdir -p "$MOUNT/$f" 2>/dev/null
  # --backup-dir must be absolute and must NOT be on the share; it is under the
  # Mac's own Library so a conflict copy is never written over SMB.
  out=$(rsync ${RSYNC_OPTS[@]+"${RSYNC_OPTS[@]}"} --stats "$src/" "$MOUNT/$f/" 2>&1)
  rc=$?
  n=$(printf '%s\n' "$out" | awk '/Number of regular files transferred/{print $NF}')
  b=$(printf '%s\n' "$out" | awk '/Total transferred file size/{print $(NF-1)}')
  TOTAL=$((TOTAL + ${n:-0}))
  case $rc in
    0)  log "  $f: ${n:-0} files, ${b:-0} bytes" ;;
    23|24) log "  $f: ${n:-0} files, some skipped (${rc}: vanished or unreadable, usually a file open in an app); fine" ;;
    *)  log "  $f: rsync failed ($rc): $(printf '%s\n' "$out" | grep -i 'error\|failed' | head -2 | tr '\n' ' ')"; FAIL=1 ;;
  esac
done
# Drop an empty conflicts folder so the person only sees ones that hold something.
rmdir "$CONFLICTS" 2>/dev/null
[ -d "$CONFLICTS" ] && log "  older server copies kept in: $CONFLICTS"

# ---- fonts: Media/Fonts on the share -> ~/Library/Fonts (docs/ANSWERS.md round 3, 39) -----
# Every Mac ends up with the same fonts the Proclaim graphics use. Only what is
# newer than this Mac's copy is copied; nothing is ever removed from the Mac.
# A person outside the Media group cannot open that share; that is logged, not an error.
FONTS_MOUNT="/Volumes/media"
if [ $DRY -eq 0 ] && ! mount | grep -q " on $FONTS_MOUNT "; then
  open "smb://${SERVER}/media" >/dev/null 2>&1
  tries=0; until mount | grep -q " on $FONTS_MOUNT "; do tries=$((tries+1)); [ $tries -gt 6 ] && break; sleep 3; done
fi
if [ -d "$FONTS_MOUNT/Fonts" ]; then
  mkdir -p "$HOME_DIR/Library/Fonts"
  fout=$(rsync -rlt --update --no-perms --no-owner --no-group --include='*/' --include='*.ttf' --include='*.otf' --include='*.ttc' --include='*.TTF' --include='*.OTF' --exclude='*' \
         --stats "$FONTS_MOUNT/Fonts/" "$HOME_DIR/Library/Fonts/" 2>&1)
  fn=$(printf '%s\n' "$fout" | awk '/Number of regular files transferred/{print $NF}')
  log "  fonts: ${fn:-0} new or updated from media/Fonts"
else
  log "  fonts: media/Fonts not reachable for $USER_NAME (not in the Media group, or the share is not mounted); skipped"
fi

log "sync done: $TOTAL files$([ $FAIL -eq 1 ] && echo ' WITH ERRORS')"
exit $FAIL

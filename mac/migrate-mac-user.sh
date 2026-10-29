#!/bin/bash
# migrate-mac-user.sh — copy a local Mac account's data into a domain user's server home.
#
#   sudo ./migrate-mac-user.sh --from <localuser> --to <domainuser> [--share smb://arise-server/homes/<domainuser>] [--appsupport Name ...] [--dry-run]
#
# Copies. Never deletes. Re-running copies only what changed. Writes a manifest
# (counts and bytes per folder, before and after) to the local user's Desktop.
set -u

SERVER="arise-server"
FROM=""; TO=""; SHARE=""; DRY=0
APPSUPPORT=(Proclaim StreamYard OBS "OBS Studio" Google Microsoft)
EXCLUDES=(
  "Library/Caches" ".Trash" ".DS_Store" "Icon?" ".localized" ".cache" "node_modules"
  "Library/Mail" "Library/Keychains" "Library/Preferences" "Library/Containers" "Library/Group Containers"
  "Library/Saved Application State" "Library/Logs" "Library/CloudStorage" ".Spotlight-V100" ".fseventsd"
)

die()  { printf '\n  FAILED: %s\n\n' "$*" >&2; exit 1; }
say()  { printf '  %s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --from)       FROM="$2"; shift 2 ;;
    --to)         TO="$2"; shift 2 ;;
    --share)      SHARE="$2"; shift 2 ;;
    --server)     SERVER="$2"; shift 2 ;;
    --appsupport) APPSUPPORT+=("$2"); shift 2 ;;
    --dry-run)    DRY=1; shift ;;
    -h|--help)    sed -n '2,8p' "$0"; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
done

[ "$(id -u)" -eq 0 ] || die "run with sudo"
[ "$(uname)" = "Darwin" ] || die "this script is for macOS"
[ -n "$FROM" ] && [ -n "$TO" ] || die "--from <localuser> and --to <domainuser> are both required"
SRC=$(dscl . -read "/Users/$FROM" NFSHomeDirectory 2>/dev/null | sed -n 's/^NFSHomeDirectory: *//p' | head -1)
[ -n "$SRC" ] && [ -d "$SRC" ] || die "no local user '$FROM' with a home folder"
[ -z "$SHARE" ] && SHARE="smb://${SERVER}/homes/${TO}"
command -v rsync >/dev/null || die "rsync not found (it ships with macOS; something is wrong)"

if who | awk '{print $1}' | grep -qx "$FROM"; then
  die "$FROM is still logged in. Log that account out first (fast user switching counts) so nothing changes while it copies."
fi

STAMP=$(date +%Y-%m-%d_%H%M)
MANIFEST="$SRC/Desktop/ARISE-MIGRATION-$STAMP.txt"
MOUNT="/Volumes/$TO"

step "Plan"
say "from:  $SRC  (local user $FROM)"
say "to:    $SHARE  mounted at $MOUNT  (domain user $TO)"
say "mode:  $([ $DRY -eq 1 ] && echo 'DRY RUN - nothing is copied' || echo 'copy')"

step "Mounting the home share (enter the domain password for $TO when asked)"
if mount | grep -q " on $MOUNT "; then
  say "already mounted"
else
  mkdir -p "$MOUNT" || die "cannot create $MOUNT"
  # mount_smbfs prompts for the password; the share path needs the user in the URL.
  mount_smbfs "//${TO}@${SERVER}/homes/${TO}" "$MOUNT" 2>&1 | sed 's/^/    /'
  mount | grep -q " on $MOUNT " || { rmdir "$MOUNT" 2>/dev/null; die "the share did not mount. Check: the Mac resolves $SERVER, the user $TO exists (arisectl user list), and the password."; }
fi
touch "$MOUNT/.arise-write-test" 2>/dev/null || die "the share mounted read-only. On the server run: arisectl user homefix $TO"
rm -f "$MOUNT/.arise-write-test"
say "mounted and writable"

measure() { # measure <dir> -> "<files>\t<bytes>"
  local d="$1"
  [ -d "$d" ] || { printf '0\t0'; return; }
  local files bytes
  files=$(find "$d" -type f 2>/dev/null | wc -l | tr -d ' ')
  bytes=$(du -sk "$d" 2>/dev/null | awk '{print $1*1024}')
  printf '%s\t%s' "$files" "${bytes:-0}"
}
human() { awk -v b="$1" 'BEGIN{s="B KB MB GB TB"; split(s,u," "); i=1; while(b>=1024 && i<5){b/=1024;i++} printf "%.1f %s", b, u[i]}'; }

FOLDERS=(Desktop Documents Downloads Pictures Movies Music)

step "Sizes before (this takes a minute on a big home)"
{
  echo "ARISE MIGRATION  $STAMP"
  echo "from $FROM ($SRC)  to $TO ($SHARE)"
  echo
  printf '%-34s %10s %12s\n' "BEFORE (on the Mac)" "files" "size"
} > "$MANIFEST"
for f in ${FOLDERS[@]+"${FOLDERS[@]}"}; do
  r=$(measure "$SRC/$f"); n=${r%%	*}; b=${r##*	}
  printf '%-34s %10s %12s\n' "$f" "$n" "$(human "$b")" | tee -a "$MANIFEST" | sed 's/^/  /'
done
for a in ${APPSUPPORT[@]+"${APPSUPPORT[@]}"}; do
  d="$SRC/Library/Application Support/$a"
  [ -d "$d" ] || continue
  r=$(measure "$d"); n=${r%%	*}; b=${r##*	}
  printf '%-34s %10s %12s\n' "App Support/$a" "$n" "$(human "$b")" | tee -a "$MANIFEST" | sed 's/^/  /'
done

for lib in "$SRC/Pictures/Photos Library.photoslibrary" "$SRC/Movies/iMovie Library.imovielibrary"; do
  if [ -d "$lib" ]; then
    sz=$(du -sh "$lib" 2>/dev/null | awk '{print $1}')
    say ""
    say "WARNING: $(basename "$lib") is $sz. It will be copied as a backup but must NOT be used from the share -"
    say "         Photos and iMovie need a local disk. Keep the local copy on the Mac after migration."
  fi
done

[ $DRY -eq 1 ] && say "" && say "dry run: see the plan above, nothing copied. Manifest at $MANIFEST" && exit 0

# -X is rsync 3's flag: Apple's rsync 2.6.9 spells extended attributes -E, and openrsync (macOS
# 15.4 and later) takes neither. So the flags come from what this Mac's rsync says it knows.
RSYNC_HELP="$(rsync --help 2>&1)"
RSYNC_META=(-rlt)
case "$RSYNC_HELP" in *--hard-links*) RSYNC_META+=(-H) ;; esac
case "$RSYNC_HELP" in *--extended-attributes*) RSYNC_META+=(-E) ;; *--xattrs*) RSYNC_META+=(-X) ;; esac
case "$RSYNC_HELP" in *--progress*) RSYNC_META+=(--progress) ;; esac
RSYNC_EX=()
for e in ${EXCLUDES[@]+"${EXCLUDES[@]}"}; do RSYNC_EX+=(--exclude "$e"); done

step "Copying"
FAIL=0
for f in ${FOLDERS[@]+"${FOLDERS[@]}"}; do
  [ -d "$SRC/$f" ] || continue
  say "-- $f"
  mkdir -p "$MOUNT/$f"
  rsync "${RSYNC_META[@]}" ${RSYNC_EX[@]+"${RSYNC_EX[@]}"} "$SRC/$f/" "$MOUNT/$f/" 2>&1 | tail -3 | sed 's/^/    /'
  [ "${PIPESTATUS[0]}" -eq 0 ] || { say "   rsync reported errors in $f (see above)"; FAIL=1; }
done
for a in ${APPSUPPORT[@]+"${APPSUPPORT[@]}"}; do
  d="$SRC/Library/Application Support/$a"
  [ -d "$d" ] || continue
  say "-- Application Support/$a"
  mkdir -p "$MOUNT/Library/Application Support/$a"
  rsync "${RSYNC_META[@]}" ${RSYNC_EX[@]+"${RSYNC_EX[@]}"} "$d/" "$MOUNT/Library/Application Support/$a/" 2>&1 | tail -3 | sed 's/^/    /'
  [ "${PIPESTATUS[0]}" -eq 0 ] || { say "   rsync reported errors in $a"; FAIL=1; }
done

step "Sizes after (on the share)"
{
  echo
  printf '%-34s %10s %12s\n' "AFTER (on the server)" "files" "size"
} >> "$MANIFEST"
MISMATCH=0
for f in ${FOLDERS[@]+"${FOLDERS[@]}"}; do
  [ -d "$SRC/$f" ] || continue
  r1=$(measure "$SRC/$f"); n1=${r1%%	*}
  r2=$(measure "$MOUNT/$f"); n2=${r2%%	*}; b2=${r2##*	}
  flag=""
  # the excludes legitimately remove files, so only flag when the share has FEWER files than the Mac minus nothing we skipped
  [ "$n2" -lt "$n1" ] && flag="  (Mac has $n1 — check the skip list before worrying)"
  printf '%-34s %10s %12s%s\n' "$f" "$n2" "$(human "$b2")" "$flag" | tee -a "$MANIFEST" | sed 's/^/  /'
  [ "$n2" -lt "$((n1 * 9 / 10))" ] && MISMATCH=1
done
cp "$MANIFEST" "$MOUNT/$(basename "$MANIFEST")" 2>/dev/null

echo
if [ $FAIL -eq 1 ]; then
  say "Finished WITH ERRORS. Read the rsync lines above, fix, and re-run (it only copies what changed)."
  exit 2
elif [ $MISMATCH -eq 1 ]; then
  say "Finished, but a folder on the share holds under 90% of the Mac's file count. Compare the manifest before signing off: $MANIFEST"
  exit 3
else
  say "Finished. Nothing was removed from the Mac. Manifest: $MANIFEST (a copy is in the share)."
  say "Next: log in as $TO on this Mac with Ethernet plugged in."
fi

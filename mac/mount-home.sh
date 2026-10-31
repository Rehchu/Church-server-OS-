#!/bin/bash
# mount-home.sh — mount the current user's Arise home share at login and keep
# Desktop and Documents on it. Run by the LaunchAgent com.arisechurch.mounthome.
#
# Install for everyone on a Mac (once, as admin):
#   sudo mkdir -p /usr/local/arise && sudo cp mount-home.sh /usr/local/arise/ && sudo chmod 755 /usr/local/arise/mount-home.sh
#   sudo cp com.arisechurch.mounthome.plist /Library/LaunchAgents/ && sudo chmod 644 /Library/LaunchAgents/com.arisechurch.mounthome.plist
#
# Local (non-domain) accounts are left alone: the script exits if the user is
# not from the ARISE directory. Kerberos from the login supplies the password,
# so nothing is prompted.
SERVER="arise-server"
USER_NAME=$(id -un)
LOG="$HOME/Library/Logs/arise-mount-home.log"
mkdir -p "$(dirname "$LOG")"
log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }

# Only domain users. A mobile account's OriginalNodeName names the AD node.
if ! dscl . -read "/Users/$USER_NAME" OriginalNodeName 2>/dev/null | grep -q "Active Directory"; then
  log "$USER_NAME is a local account; nothing to mount"
  exit 0
fi

MOUNT="/Volumes/$USER_NAME"
tries=0
until mount | grep -q " on $MOUNT "; do
  tries=$((tries+1))
  if [ $tries -gt 12 ]; then log "gave up mounting smb://$SERVER/homes/$USER_NAME after 2 minutes"; exit 1; fi
  # 'open' asks Finder to mount it, which reuses the Kerberos ticket from login.
  open "smb://${SERVER}/homes/${USER_NAME}" >/dev/null 2>&1
  sleep 10
done
log "mounted $MOUNT"

# Point Desktop and Documents at the share. Only done once: if the folder is
# already a link, leave it. If it is a real folder with files in it, keep it
# and note it in the log so nothing is lost -- merging is a person's job.
for f in Desktop Documents; do
  local_dir="$HOME/$f"
  share_dir="$MOUNT/$f"
  mkdir -p "$share_dir" 2>/dev/null
  if [ -L "$local_dir" ]; then
    continue
  elif [ -d "$local_dir" ] && [ -n "$(ls -A "$local_dir" 2>/dev/null)" ]; then
    log "$local_dir has files in it; left as is. Move them to $share_dir and run again, or rename the folder to $f.local"
    continue
  else
    rmdir "$local_dir" 2>/dev/null
    ln -s "$share_dir" "$local_dir" && log "linked $local_dir -> $share_dir"
  fi
done
exit 0

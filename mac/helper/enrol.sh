#!/bin/bash
# enrol.sh: make this Mac a church Mac (round 6, 37; docs/MACS.md).
#
# Nobody runs this by hand. An admin opens Macs on the dashboard, presses "Enrol a Mac",
# and copies the one Terminal line it shows, which looks like:
#
#   curl -fsSL http://192.168.1.20:4147/ca.crt -o /tmp/arise-ca.crt && [ "$(shasum ...)" = "<fingerprint>" ] &&
#   curl -fsSL --cacert /tmp/arise-ca.crt ... https://arise-server.ad.arisecenla.com/mac/enrol.sh |
#   sudo bash -s -- --token <one-time token> --dns 192.168.1.20 --server https://arise-server.ad.arisecenla.com
#
# The token works once, for an hour. Only a Mac enrolled with one is a church Mac; the
# server never touches any other (a personal Mac never runs this).
#
# What it does, in order, and it is safe to run again:
#   1. points this Mac at the server for the church domain only (/etc/resolver; no router change)
#   2. trusts the church certificate (macOS asks for your password once)
#   3. joins the domain with mac/bind-mac.sh (you type the domain administrator password)
#   4. trades the token for this Mac's own key (kept in /var/db/arise, readable by root only)
#   5. installs the helper as a LaunchDaemon (at boot and every five minutes)
#   6. runs it once: the helper then makes everyone's account, the hidden ariseadmin,
#      FileVault, the printers, the bookmarks and Tailscale, as tasks the server hands it
# It never deletes an account. Accounts already on this Mac wait for an admin's choice in
# the Macs app: Convert (becomes the server user), Link (stays, signed in to the server's
# files as the server user) or Leave alone.
set -u

SERVER=""; TOKEN=""; DNS_IP=""; NAME=""
BASE=/usr/local/arise/helper
DB=/var/db/arise
PLIST=/Library/LaunchDaemons/com.arisechurch.helper.plist

die()  { printf '\n  FAILED: %s\n\n' "$*" >&2; exit 1; }
say()  { printf '  %s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --server) SERVER="$2"; shift 2 ;;
    --token)  TOKEN="$2"; shift 2 ;;
    --dns)    DNS_IP="$2"; shift 2 ;;
    --name)   NAME="$2"; shift 2 ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
done

[ "$(id -u)" -eq 0 ] || die "run with sudo (the line from the Macs app does)"
[ "$(uname)" = "Darwin" ] || die "this is for macOS"
[ -n "$SERVER" ] && [ -n "$TOKEN" ] || die "--server and --token are required: copy the whole line from the Macs app"
[ -n "$DNS_IP" ] || die "--dns is required: copy the whole line from the Macs app"
case "$DNS_IP" in *[!0-9.]*) die "--dns wants the server's address, e.g. 192.168.1.20";; esac
case "$TOKEN" in *[!A-Za-z0-9_-]*) die "that token is not one the server makes";; esac

HOSTPART="${SERVER#*://}"; HOSTPART="${HOSTPART%%/*}"; HOST="${HOSTPART%%:*}"
REALM_LC="${HOST#arise-server.}"
[ "$REALM_LC" != "$HOST" ] || REALM_LC="ad.arisecenla.com"

mkdir -p "$DB" "$DB/convert" && chmod 700 "$DB"
TMP="$(mktemp -d /tmp/arise-enrol.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

fetch() {   # fetch <path> <file>: from the server, checking the church certificate when it is https
  local opts=(-fsSL --max-time 60)
  case "$SERVER" in https:*) opts+=(--cacert "$DB/arise-ca.crt" --resolve "$HOST:443:$DNS_IP") ;; esac
  curl "${opts[@]}" "$SERVER$1" -o "$2"
}

step "1. The church domain's DNS (this Mac only; no router change)"
mkdir -p /etc/resolver
printf 'nameserver %s\nsearch_order 1\ntimeout 2\n' "$DNS_IP" > "/etc/resolver/$REALM_LC"
dscacheutil -flushcache; killall -HUP mDNSResponder 2>/dev/null || true
say "names in $REALM_LC are asked of $DNS_IP; everything else is unchanged"

step "2. The church certificate"
if [ -s /tmp/arise-ca.crt ] && grep -q 'BEGIN CERTIFICATE' /tmp/arise-ca.crt; then
  cp /tmp/arise-ca.crt "$DB/arise-ca.crt"      # the line already checked its fingerprint
elif curl -fsS -m 8 -o "$TMP/ca.crt" "http://$DNS_IP:4147/ca.crt" && grep -q 'BEGIN CERTIFICATE' "$TMP/ca.crt"; then
  cp "$TMP/ca.crt" "$DB/arise-ca.crt"
fi
if [ -s "$DB/arise-ca.crt" ]; then
  chmod 644 "$DB/arise-ca.crt"
  if security find-certificate -c "Caddy Local Authority" /Library/Keychains/System.keychain >/dev/null 2>&1; then
    say "already trusted"
  elif security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain "$DB/arise-ca.crt" </dev/tty; then
    say "trusted (the padlock on the dashboard, and the helper checks the server with it)"
  else
    say "macOS did not trust it (the dialog was cancelled?). The helper still checks the server with its own copy."
  fi
else
  case "$SERVER" in https:*) die "no church certificate: cannot reach the server safely over https" ;; esac
  say "the server has no certificate yet (plain http on the church network until it does)"
fi

step "3. The helper's files"
for f in arise-mac-helper com.arisechurch.helper.plist bind-mac.sh; do
  fetch "/mac/$f" "$TMP/$f" || die "could not download $f from $SERVER (is the dashboard up?)"
done
fetch "/mac/nextcloud.sh" "$TMP/nextcloud.sh" 2>/dev/null || rm -f "$TMP/nextcloud.sh"
bash -n "$TMP/arise-mac-helper" || die "the helper did not download whole; run the line again"
say "downloaded"

step "4. Joining the church domain"
if [ -z "$NAME" ]; then
  NAME="$(scutil --get ComputerName 2>/dev/null | tr ' ' '-' | tr -cd 'A-Za-z0-9-' | cut -c1-15)"
fi
[ -n "$NAME" ] || die "this Mac has no name; run the line again with --name MEDIA-MAC-01"
scutil --set ComputerName "$NAME"; scutil --set LocalHostName "$NAME"; scutil --set HostName "$NAME.$REALM_LC"
bash "$TMP/bind-mac.sh" --computer-name "$NAME" --dns "$DNS_IP" </dev/tty || die "the bind did not finish (bind-mac.sh says why, above). Nothing was enrolled; fix that and run the same line again within the hour."

step "5. Enrolling $NAME"
SERIAL="$(ioreg -rd1 -c IOPlatformExpertDevice | awk -F'"' '/IOPlatformSerialNumber/{print $4}')"
FACTS="$(bash "$TMP/arise-mac-helper" --facts)"
ACCTS="$(bash "$TMP/arise-mac-helper" --accounts)"
VER="$(bash "$TMP/arise-mac-helper" --version)"
OUT="$TMP/enrol.out"
opts=(-sS --max-time 60 -o "$OUT" -w '%{http_code}')
case "$SERVER" in https:*) opts+=(--cacert "$DB/arise-ca.crt" --resolve "$HOST:443:$DNS_IP") ;; esac
CODE="$(curl "${opts[@]}" "$SERVER/api/macs/agent/enrol" \
  --data-urlencode "token=$TOKEN" --data-urlencode "name=$NAME" --data-urlencode "serial=$SERIAL" \
  --data-urlencode "model=$(printf '%s\n' "$FACTS" | sed -n 's/^model=//p')" \
  --data-urlencode "macos=$(printf '%s\n' "$FACTS" | sed -n 's/^macos=//p')" \
  --data-urlencode "helper=$VER" --data-urlencode "accounts=$ACCTS")" || die "could not reach $SERVER"
[ "$CODE" = 200 ] || die "the server said no: $(sed 's/^ERROR //' "$OUT" | head -1 | sed 's/%20/ /g;s/%3A/:/g'). Make a new line in the Macs app."
MAC_ID="$(sed -n 's/^MAC_ID=//p' "$OUT")"
umask 077
sed -n 's/^KEY=//p' "$OUT" > "$DB/helper.key"
[ -n "$MAC_ID" ] && [ -s "$DB/helper.key" ] || die "the server's answer was incomplete"
printf 'SERVER=%s\nMAC_ID=%s\n' "$SERVER" "$MAC_ID" > "$DB/helper.conf"
chmod 600 "$DB/helper.key" "$DB/helper.conf"; chown root:wheel "$DB/helper.key" "$DB/helper.conf"
umask 022
say "enrolled as $MAC_ID (its key is in $DB/helper.key, root only)"

step "6. Installing the helper"
mkdir -p "$BASE/tasks"
install -m 755 -o root -g wheel "$TMP/arise-mac-helper" "$BASE/arise-mac-helper"
[ -f "$TMP/nextcloud.sh" ] && install -m 755 -o root -g wheel "$TMP/nextcloud.sh" "$BASE/tasks/nextcloud.sh"
install -m 644 -o root -g wheel "$TMP/com.arisechurch.helper.plist" "$PLIST"
touch /var/log/arise-helper.log && chmod 640 /var/log/arise-helper.log
launchctl bootout system/com.arisechurch.helper 2>/dev/null || true
launchctl bootstrap system "$PLIST" || die "launchctl would not load $PLIST"
say "running at boot and every five minutes"

step "7. The first check-in"
sleep 2
"$BASE/arise-mac-helper" && say "done; the log is /var/log/arise-helper.log" || say "the first check-in failed; the log says why: tail /var/log/arise-helper.log"
tail -n 12 /var/log/arise-helper.log 2>/dev/null | sed 's/^/    /'

LOCALS="$(printf '%s\n' "$ACCTS" | awk -F'|' '$2=="local"{print $1}')"
if [ -n "$LOCALS" ]; then
  step "Accounts already on this Mac"
  printf '%s\n' "$LOCALS" | sed 's/^/    /'
  say "Nothing happens to these until an admin chooses, in Macs on the dashboard:"
  say "Convert (becomes the server user), Link (stays, uses the server's files), or Leave alone."
fi
printf '\n  %s is a church Mac now. Everyone with a server account will appear on its login window within minutes.\n\n' "$NAME"

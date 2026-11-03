#!/bin/bash
# enrol.sh: make this Mac a church Mac (round 6, 37; docs/MACS.md).
#
# Nobody runs this by hand. An admin opens Macs on the dashboard, presses "Enrol a Mac",
# and copies the one Terminal line it shows, which looks like:
#
#   The generated line uses a private temporary CA, verifies its SHA256, then
#   downloads this script over verified HTTPS and passes --ca-sha256 to root.
#   Copy it from the trusted dashboard instead of reconstructing it by hand.
#
# The token works once, for an hour. Only a Mac enrolled with one is a church Mac; the
# server never touches any other (a personal Mac never runs this).
#
# What it does, in order, and it is safe to run again:
#   0. a Time Machine backup first, when this Mac's Time Machine disk answers (round 7, 6);
#      --no-backup skips it, and a Mac with no Time Machine disk goes straight on
#   1. points this Mac at the server for the church domain only (/etc/resolver; no router change)
#   2. trusts the church certificate (macOS asks for your password once)
#   3. joins the domain with mac/bind-mac.sh (you type the domain administrator password)
#   4. trades the token for this Mac's own key (kept in /var/db/arise, readable by root only)
#   5. installs the helper as a LaunchDaemon (at boot and every five minutes)
#   6. runs it once: the helper then makes everyone's account, the hidden ariseadmin,
#      FileVault, the printers, the bookmarks and Tailscale, as tasks the server hands it
# It never deletes an account, and the Mac keeps the name it has (round 7, 35; --name only to
# change it). Accounts already on this Mac are linked to their server user once the helper is
# switched on (round 7, 23): each stays as it is, with its own password, and its files sync.
set -u

SERVER=""; TOKEN=""; DNS_IP=""; NAME=""; BACKUP=1; CA_SHA256=""
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
    --ca-sha256) CA_SHA256="$2"; shift 2 ;;
    --no-backup) BACKUP=0; shift ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
done

[ "$(id -u)" -eq 0 ] || die "run with sudo (the line from the Macs app does)"
[ "$(uname)" = "Darwin" ] || die "this is for macOS"
[ -n "$SERVER" ] && [ -n "$TOKEN" ] || die "--server and --token are required: copy the whole line from the Macs app"
[ -n "$DNS_IP" ] || die "--dns is required: copy the whole line from the Macs app"
case "$DNS_IP" in *[!0-9.]*) die "--dns wants the server's address, e.g. 192.168.1.20";; esac
case "$TOKEN" in *[!A-Za-z0-9_-]*) die "that token is not one the server makes";; esac
case "$SERVER" in https://*) ;; *) die "enrollment requires HTTPS: start Caddy and copy a new enrollment line" ;; esac
[[ "$CA_SHA256" =~ ^[a-f0-9]{64}$ ]] || die "--ca-sha256 must be the fingerprint from the trusted dashboard enrollment line"

HOSTPART="${SERVER#*://}"; HOSTPART="${HOSTPART%%/*}"; HOST="${HOSTPART%%:*}"
REALM_LC="${HOST#arise-server.}"
[ "$REALM_LC" != "$HOST" ] || REALM_LC="ad.arisecenla.com"

mkdir -p "$DB" "$DB/convert" && chmod 700 "$DB"
TMP="$(mktemp -d /tmp/arise-enrol.XXXXXX)" || die "could not make a private temporary directory"
chmod 700 "$TMP"
trap 'rm -rf "$TMP"' EXIT

fetch_pinned_ca() {
  # Fetch again into root's private directory and verify here. Never trust a
  # user-writable /tmp certificate just because an earlier command checked it.
  curl -fsS -m 15 -o "$TMP/ca.crt" "http://$DNS_IP/ca.crt" || return 1
  [ "$(shasum -a 256 "$TMP/ca.crt" | cut -c1-64)" = "$CA_SHA256" ] || return 1
  grep -q 'BEGIN CERTIFICATE' "$TMP/ca.crt"
}

fetch() {   # fetch <path> <file>: from the server, checking the church certificate when it is https
  local opts=(-fsSL --max-time 60)
  case "$SERVER" in https:*) opts+=(--cacert "$DB/arise-ca.crt" --resolve "$HOST:443:$DNS_IP") ;; esac
  curl "${opts[@]}" "$SERVER$1" -o "$2"
}

main() {
fetch_pinned_ca || die "the church certificate could not be verified; no enrollment changes made"
step "0. A Time Machine backup first (round 7, 6)"
if [ "$BACKUP" = 0 ]; then
  say "skipped (--no-backup)"
elif tmutil destinationinfo 2>/dev/null | grep -q '^Name'; then
  say "this Mac has a Time Machine disk: backing up now, before anything changes (this can take a while)"
  if tmutil startbackup --block >/dev/null 2>&1; then say "backed up: $(tmutil latestbackup 2>/dev/null | tail -1)"
  else say "the backup could not run now (is the Synology answering?); going on without it, as Bradly chose"; fi
else
  say "no Time Machine disk on this Mac yet: going on (the Synology's Time Machine share comes later)"
fi

step "1. The church domain's DNS (this Mac only; no router change)"
mkdir -p /etc/resolver
printf 'nameserver %s\nsearch_order 1\ntimeout 2\n' "$DNS_IP" > "/etc/resolver/$REALM_LC"
dscacheutil -flushcache; killall -HUP mDNSResponder 2>/dev/null || true
say "names in $REALM_LC are asked of $DNS_IP; everything else is unchanged"

step "2. The church certificate"
install -m 644 -o root -g wheel "$TMP/ca.crt" "$DB/arise-ca.crt" || die "could not install the verified certificate"
if [ -s "$DB/arise-ca.crt" ]; then
  chmod 644 "$DB/arise-ca.crt"
  # verify-cert asks the trust settings, not just whether the certificate sits in the keychain.
  if security verify-cert -c "$DB/arise-ca.crt" >/dev/null 2>&1; then
    say "already trusted"
  elif security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain "$DB/arise-ca.crt" </dev/tty; then
    say "trusted (the padlock on the dashboard, and the helper checks the server with it)"
  else
    say "macOS did not trust it (the dialog was cancelled?). The helper still checks the server with its own copy."
  fi
else
  die "no verified church certificate"
fi

step "3. The helper's files"
for f in arise-mac-helper com.arisechurch.helper.plist bind-mac.sh; do
  fetch "/mac/$f" "$TMP/$f" || die "could not download $f from $SERVER (is the dashboard up?)"
done
fetch "/mac/nextcloud.sh" "$TMP/nextcloud.sh" 2>/dev/null || rm -f "$TMP/nextcloud.sh"
bash -n "$TMP/arise-mac-helper" || die "the helper did not download whole; run the line again"
say "downloaded"

step "4. Joining the church domain"
# Round 7, 35: the Mac keeps the name it has. Only the domain's computer account needs a short,
# plain form of it (15 letters, digits and dashes); the name people see is left alone.
if [ -n "$NAME" ]; then
  scutil --set ComputerName "$NAME"; scutil --set LocalHostName "$(printf '%s' "$NAME" | tr ' ' '-' | tr -cd 'A-Za-z0-9-')"
  say "renamed to $NAME (--name)"
else
  NAME="$(scutil --get ComputerName 2>/dev/null)"
  say "keeping this Mac's name: $NAME"
fi
ADNAME="$(printf '%s' "$NAME" | tr ' ' '-' | tr -cd 'A-Za-z0-9-' | cut -c1-15)"
[ -n "$ADNAME" ] || die "this Mac's name has no letters or digits; run the line again with --name OFFICE-MAC-02"
bash "$TMP/bind-mac.sh" --computer-name "$ADNAME" --dns "$DNS_IP" --ca-file "$DB/arise-ca.crt" --ca-sha256 "$CA_SHA256" </dev/tty || die "the bind did not finish (bind-mac.sh says why, above). Nothing was enrolled; fix that and run the same line again within the hour."

step "5. Enrolling $NAME"
SERIAL="$(ioreg -rd1 -c IOPlatformExpertDevice | awk -F'"' '/IOPlatformSerialNumber/{print $4}')"
FACTS="$(bash "$TMP/arise-mac-helper" --facts)"
ACCTS="$(bash "$TMP/arise-mac-helper" --accounts)"
VER="$(bash "$TMP/arise-mac-helper" --version)"
OUT="$TMP/enrol.out"
opts=(-sS --max-time 60 -o "$OUT" -w '%{http_code}')
case "$SERVER" in https:*) opts+=(--cacert "$DB/arise-ca.crt" --resolve "$HOST:443:$DNS_IP") ;; esac
CODE="$(curl "${opts[@]}" "$SERVER/api/macs/agent/enrol" \
  --data-urlencode "token=$TOKEN" --data-urlencode "name=$NAME" --data-urlencode "ad_name=$ADNAME" --data-urlencode "serial=$SERIAL" \
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
"$BASE/arise-mac-helper" </dev/null && say "done; the log is /var/log/arise-helper.log" || say "the first check-in failed; the log says why: tail /var/log/arise-helper.log"
tail -n 12 /var/log/arise-helper.log 2>/dev/null | sed 's/^/    /'

step "8. Full Disk Access (once, by hand: Bradly, while enrolling, round 7, 39)"
# macOS lets no script grant this, not even root's. Without it the helper cannot list anyone's
# Desktop or Documents, so it never removes a profile from this Mac (the server refuses).
if ls "/Library/Application Support/com.apple.TCC" >/dev/null 2>&1; then
  say "already granted"
else
  say "In the window that opens: press +, press Cmd-Shift-G, type /usr/local/arise/helper/arise-mac-helper,"
  say "press Open, then do the same for /bin/bash, and make sure both switches are on."
  say "Until then the Macs app shows this Mac as 'no Full Disk Access' and no profile is removed from it."
  # Opened in the signed-in person's session: `open` run as root (sudo) has no window to show.
  CU="$(stat -f %Su /dev/console 2>/dev/null)"
  if [ -n "$CU" ] && [ "$CU" != root ]; then
    launchctl asuser "$(id -u "$CU")" sudo -u "$CU" open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles" >/dev/null 2>&1 || true
  fi
fi

LOCALS="$(printf '%s\n' "$ACCTS" | awk -F'|' '$2=="local"{print $1}')"
if [ -n "$LOCALS" ]; then
  step "Accounts already on this Mac"
  printf '%s\n' "$LOCALS" | sed 's/^/    /'
  say "Each is linked to its server user once the helper is switched on (round 7, 23): it stays as it is,"
  say "with its own password, and its files sync. One that matches nobody gets a new first.last server user."
  say "The Macs app shows what it would do first; Convert or Leave alone are still there per account."
fi
printf '\n  %s is a church Mac now: DNS, certificate trust, domain binding and the helper are installed.\n  Watch mode holds subsequent management tasks until an admin presses Switch on. The Macs app shows the current mode.\n\n' "$NAME"
}

# The whole file is read before anything runs (curl | bash), and nothing below can eat it from stdin.
main "$@" </dev/null

#!/bin/bash
# bind-mac.sh — join this Mac to the Arise Church domain.
#
#   sudo ./bind-mac.sh --computer-name MEDIA-MAC-01 --dns 192.168.1.20 [--ou "OU=Macs,OU=Computers,DC=ad,DC=arisecenla,DC=church"] [--admin administrator] [--test-user jane.smith]
#
# --dns <server ip> writes /etc/resolver/ad.arisecenla.church on this Mac, so
# only names in the church domain are asked of the server; everything else
# keeps using whatever DNS the router hands out. No router is touched: the
# Pineville routers stay exactly as they are (docs/ANSWERS.md, Oct 28).
#
# It checks DNS, the DC's SRV records and the clock first, because those are
# the three things that make a bind fail, and it says exactly which one did.
set -u

REALM="AD.ARISECENLA.CHURCH"
REALM_LC="ad.arisecenla.church"
NETBIOS="ARISE"
DC_HOST="arise-server.${REALM_LC}"
OU="OU=Macs,OU=Computers,DC=ad,DC=arisecenla,DC=church"
ADMIN="administrator"
COMPUTER=""
TEST_USER=""
DNS_IP=""

die()  { printf '\n  FAILED: %s\n\n' "$*" >&2; exit 1; }
say()  { printf '  %s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --computer-name) COMPUTER="$2"; shift 2 ;;
    --ou)            OU="$2"; shift 2 ;;
    --admin)         ADMIN="$2"; shift 2 ;;
    --test-user)     TEST_USER="$2"; shift 2 ;;
    --dns)           DNS_IP="$2"; shift 2 ;;
    -h|--help)       sed -n '2,12p' "$0"; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
done

[ "$(id -u)" -eq 0 ] || die "run with sudo"
[ "$(uname)" = "Darwin" ] || die "this script is for macOS"
[ -n "$COMPUTER" ] || die "--computer-name is required (the name on the Mac's label, e.g. MEDIA-MAC-01)"
case "$COMPUTER" in *[!A-Za-z0-9-]*) die "computer name may only contain letters, digits and dashes";; esac
[ ${#COMPUTER} -le 15 ] || die "computer name must be 15 characters or fewer (NetBIOS limit)"

step "macOS"
say "$(sw_vers -productName) $(sw_vers -productVersion)"

if [ -n "$DNS_IP" ]; then
  step "DNS — per-domain resolver (no router change)"
  case "$DNS_IP" in *[!0-9.]*) die "--dns wants the server's IP address, e.g. 192.168.1.20";; esac
  mkdir -p /etc/resolver
  printf 'nameserver %s\nsearch_order 1\ntimeout 2\n' "$DNS_IP" > "/etc/resolver/${REALM_LC}"
  say "wrote /etc/resolver/${REALM_LC} -> $DNS_IP (only *.${REALM_LC} is asked of the server)"
  dscacheutil -flushcache; killall -HUP mDNSResponder 2>/dev/null || true
fi

step "DNS — does this Mac use the domain controller?"
say "resolvers: $(scutil --dns | awk '/nameserver\[0\]/{print $3}' | sort -u | tr '\n' ' ')"
A=$(dig +short "$DC_HOST" 2>/dev/null | head -1)
[ -n "$A" ] || die "cannot resolve $DC_HOST. This Mac is not using the server for DNS. Run again with --dns <server ip> (writes /etc/resolver/${REALM_LC}; no router change), or set the Mac's DNS to the server in System Settings > Network, then: sudo dscacheutil -flushcache"
say "$DC_HOST -> $A"
SRV=$(dig +short "_ldap._tcp.${REALM_LC}" SRV 2>/dev/null | head -1)
[ -n "$SRV" ] || die "no SRV record for _ldap._tcp.${REALM_LC}. DNS answers but it is not the DC's DNS."
say "_ldap._tcp SRV -> $SRV"
KSRV=$(dig +short "_kerberos._tcp.${REALM_LC}" SRV 2>/dev/null | head -1)
[ -n "$KSRV" ] || die "no SRV record for _kerberos._tcp.${REALM_LC}"
say "_kerberos._tcp SRV -> $KSRV"

step "Clock — Kerberos needs this Mac within 5 minutes of the server"
if command -v sntp >/dev/null 2>&1; then
  OFFSET=$(sntp "$DC_HOST" 2>/dev/null | awk '/[+-][0-9.]+ \+\/-/{print $1}' | head -1)
  if [ -n "$OFFSET" ]; then
    ABS=${OFFSET#-}; ABS=${ABS#+}
    say "offset from DC: ${OFFSET}s"
    awk -v a="$ABS" 'BEGIN{exit (a>300)?0:1}' && die "clock is off by ${OFFSET}s. System Settings > General > Date & Time > set automatically, wait a minute, re-run."
  else
    say "could not measure offset with sntp (the DC may not answer NTP); continuing. If the bind fails with 'authentication server could not be contacted', it is the clock."
  fi
else
  say "sntp not found; skipping the clock check. Make sure automatic time is on."
fi

step "Reachability — LDAP and Kerberos ports on the DC"
for P in 389 88 445; do
  if nc -z -G 3 "$A" "$P" >/dev/null 2>&1; then say "port $P open"; else die "port $P on $A is closed. The server is off, a firewall is in the way, or this is the wrong address."; fi
done

step "Already bound?"
if dsconfigad -show 2>/dev/null | grep -q "Active Directory Domain"; then
  say "this Mac is already bound:"
  dsconfigad -show | sed 's/^/    /'
  say "to re-bind, first: sudo dsconfigad -remove -username $ADMIN"
  exit 0
fi

step "Binding $COMPUTER to $REALM (you will be asked for the $NETBIOS\\$ADMIN password)"
dsconfigad -add "$REALM" \
  -computer "$COMPUTER" \
  -username "$ADMIN" \
  -ou "$OU" \
  -mobile enable -mobileconfirm disable \
  -localhome enable -useuncpath enable -protocol smb \
  -groups "${NETBIOS}\\Domain Admins" \
  -alldomains disable \
  || die "dsconfigad -add failed. The message above is Apple's; the usual causes are the admin password, the OU not existing on the DC, or a computer account by this name already in AD (delete it with: arisectl computer remove $COMPUTER)."

step "Result"
dsconfigad -show | sed 's/^/    /'

step "Search path"
dscl /Search -read / CSPSearchPath 2>/dev/null | sed 's/^/    /'

if [ -n "$TEST_USER" ]; then
  step "Looking up $TEST_USER through the directory"
  sleep 2
  if id "$TEST_USER" >/dev/null 2>&1; then
    id "$TEST_USER" | sed 's/^/    /'
    say "the Mac can see domain users."
  else
    die "id $TEST_USER found nothing. The bind went through but the Mac cannot read users yet. Wait 30 seconds and run: id $TEST_USER. If it still fails, check 'dscl /Active\\ Directory/ARISE/All\\ Domain -list /Users' and the DC's logs."
  fi
fi

printf '\n  Bound. Log out and log in as a domain user (plugged into Ethernet for the first login).\n  Then install the home-share mount: see mac/mount-home.sh\n\n'

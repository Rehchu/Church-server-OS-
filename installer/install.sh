#!/usr/bin/env bash
# =============================================================================
#  Arise Server — installer for Ubuntu Server 24.04 LTS
#
#  Run as root on the church PC after a clean Ubuntu Server install:
#
#      sudo bash installer/install.sh --admin-pass 'YourDomainAdminPassword'
#
#  What it does, in order (every step is idempotent — run it again any time):
#    1. apt packages (Samba AD DC, Kerberos, restic, Docker, Python, git, rsync)
#    2. hostname arise-server, timezone America/Chicago
#    3. copies this repo to /opt/arise, builds the Python venv
#    4. /etc/arise config, /var/lib/arise state, /srv/arise data folders
#    5. provisions the Samba Active Directory domain AD.ARISECENLA.CHURCH
#    6. installs the systemd units and timers, starts the dashboard on :4147
#    7. prints what still needs a human (token.json, restic password, NAS)
#
#  Flags:
#    --admin-pass PASS   Domain Administrator password (prompted if omitted)
#    --skip-domain       do not provision / touch the Samba AD DC
#    --skip-docker       do not install Docker (no app templates)
#    --no-start          install everything but do not start services/timers
#    --with-tailscale    install Tailscale (prints the `tailscale up` line to run yourself)
#    --with-wireguard    native WireGuard server on UDP 51820 (wg0, 10.47.0.0/24)
#    --with-caddy        Caddy HTTPS reverse proxy with an internal CA (config/caddy/Caddyfile)
#    --console           show the arisetui text dashboard on the closet monitor (tty1)
#    --kiosk             show the Arise desktop (Finder, dock, widgets) full screen on the closet monitor (tty1)
#    --no-pin-ip         do NOT pin the address DHCP gave this box (default: pin it, so the DC never moves;
#                        nothing on any router changes, Bradly's rule)
#    --dry-run           print every step, change nothing
#    -h | --help
#
#  Log: /var/log/arise/install.log (every command's output lands there too).
# =============================================================================
set -Eeuo pipefail

# ----------------------------------------------------------------------------
# Fixed names — these match docs/ARCHITECTURE.md. Do not change one without
# changing the others.
# ----------------------------------------------------------------------------
HOSTNAME_WANTED="arise-server"
TIMEZONE="America/Chicago"
REALM="AD.ARISECENLA.CHURCH"
NETBIOS="ARISE"
DNS_FORWARDER="1.1.1.1"
INSTALL_ROOT="/opt/arise"
VENV="$INSTALL_ROOT/venv"
CONF_DIR="/etc/arise"
STATE_DIR="/var/lib/arise"
LOG_DIR="/var/log/arise"
DATA_ROOT="/srv/arise"
WEB_PORT=4147

ADMIN_PASS=""
WITH_TAILSCALE=0
WITH_WIREGUARD=0
WITH_CADDY=0
WITH_CONSOLE=0
WITH_KIOSK=0
PIN_IP=1
SKIP_DOMAIN=0
SKIP_DOCKER=0
NO_START=0
DRY_RUN=0

usage() { sed -n '2,30p' "$0" | sed 's/^#  \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --admin-pass)  ADMIN_PASS="${2:-}"; shift 2 ;;
    --admin-pass=*) ADMIN_PASS="${1#*=}"; shift ;;
    --skip-domain) SKIP_DOMAIN=1; shift ;;
    --skip-docker) SKIP_DOCKER=1; shift ;;
    --no-start)    NO_START=1; shift ;;
    --with-tailscale) WITH_TAILSCALE=1; shift ;;
    --with-wireguard) WITH_WIREGUARD=1; shift ;;
    --with-caddy)  WITH_CADDY=1; shift ;;
    --console)     WITH_CONSOLE=1; shift ;;
    --kiosk)       WITH_KIOSK=1; shift ;;
    --no-pin-ip)   PIN_IP=0; shift ;;
    --dry-run)     DRY_RUN=1; shift ;;
    -h|--help)     usage 0 ;;
    *) echo "unknown flag: $1" >&2; usage 2 ;;
  esac
done

# ----------------------------------------------------------------------------
# Logging. Everything printed also goes to the install log. In --dry-run we
# write the log to /tmp so a dry run never touches /var/log.
# ----------------------------------------------------------------------------
if [ "$DRY_RUN" = 1 ]; then
  LOG_FILE="/tmp/arise-install-dryrun.log"
else
  mkdir -p "$LOG_DIR"
  LOG_FILE="$LOG_DIR/install.log"
fi
exec > >(tee -a "$LOG_FILE") 2>&1

say()  { printf '\n\033[1;31m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
note() { printf '    %s\n' "$*"; }
warn() { printf '    \033[1;33m! %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mFAILED:\033[0m %s\n' "$*" >&2; exit 1; }

# run — execute a command, or print it in --dry-run.
run() {
  if [ "$DRY_RUN" = 1 ]; then
    printf '    [dry-run] %s\n' "$*"
  else
    printf '    $ %s\n' "$*"
    "$@"
  fi
}

trap 'die "step failed at line $LINENO: $BASH_COMMAND  (see $LOG_FILE)"' ERR

echo "============================================================="
echo " Arise Server install — started $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo " flags: admin-pass=$([ -n "$ADMIN_PASS" ] && echo set || echo unset) skip-domain=$SKIP_DOMAIN skip-docker=$SKIP_DOCKER no-start=$NO_START tailscale=$WITH_TAILSCALE wireguard=$WITH_WIREGUARD caddy=$WITH_CADDY console=$WITH_CONSOLE kiosk=$WITH_KIOSK pin-ip=$PIN_IP dry-run=$DRY_RUN"
echo "============================================================="

# ----------------------------------------------------------------------------
# 0. Preflight
# ----------------------------------------------------------------------------
say "Preflight"
if [ "$(id -u)" -ne 0 ]; then
  die "run this as root:  sudo bash installer/install.sh"
fi

if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  note "OS: ${PRETTY_NAME:-unknown}"
  if [ "${ID:-}" != "ubuntu" ] || [ "${VERSION_ID:-}" != "24.04" ]; then
    warn "this installer is written for Ubuntu Server 24.04 LTS; you are on ${ID:-?} ${VERSION_ID:-?}. Continuing, but package names may differ."
  fi
else
  warn "/etc/os-release missing — cannot tell which OS this is."
fi

# The repo is wherever this script lives, one level up.
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
note "repo: $REPO_DIR"
[ -f "$REPO_DIR/docs/ARCHITECTURE.md" ] || die "this script must be run from a checkout of the Church-server-OS repo (docs/ARCHITECTURE.md not found next to it)"

if [ "$SKIP_DOMAIN" = 0 ] && [ "$DRY_RUN" = 0 ] && [ ! -f /var/lib/samba/private/sam.ldb ] && [ -z "$ADMIN_PASS" ]; then
  echo
  echo "    The domain needs an Administrator password (Samba requires: 8+ chars,"
  echo "    upper + lower + digit). It is NOT stored anywhere by this script."
  read -r -s -p "    Domain Administrator password: " ADMIN_PASS; echo
  read -r -s -p "    Again: " ADMIN_PASS2; echo
  [ "$ADMIN_PASS" = "$ADMIN_PASS2" ] || die "passwords did not match"
  [ ${#ADMIN_PASS} -ge 8 ] || die "password must be at least 8 characters"
fi

# A domain controller must not be on Wi-Fi and must have a fixed address.
PRIMARY_IF="$(ip -o route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}' | head -1 || true)"
PRIMARY_IP="$(ip -o route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' | head -1 || true)"
note "primary interface: ${PRIMARY_IF:-unknown}  address: ${PRIMARY_IP:-unknown}"
if [ -n "$PRIMARY_IF" ] && [ -d "/sys/class/net/$PRIMARY_IF/wireless" ]; then
  warn "primary interface $PRIMARY_IF is WIRELESS. A domain controller on Wi-Fi drops Macs off the domain. Plug in Ethernet before going live."
fi

# ----------------------------------------------------------------------------
# 1. Packages
# ----------------------------------------------------------------------------
say "1/7  Packages"
export DEBIAN_FRONTEND=noninteractive
# Kerberos asks three questions during install; answer them up front so apt
# never stops to wait for a keyboard.
if [ "$DRY_RUN" = 0 ]; then
  echo "krb5-config krb5-config/default_realm string $REALM" | debconf-set-selections
  echo "krb5-config krb5-config/kerberos_servers string $HOSTNAME_WANTED.${REALM,,}" | debconf-set-selections
  echo "krb5-config krb5-config/admin_server string $HOSTNAME_WANTED.${REALM,,}" | debconf-set-selections
fi

PKGS=(
  samba winbind krb5-user krb5-config libnss-winbind libpam-winbind
  smbclient ldb-tools acl attr
  cifs-utils nfs-common
  restic rsync git curl jq
  python3 python3-venv python3-pip
  chrony
)
if [ "$SKIP_DOCKER" = 0 ]; then
  PKGS+=(docker.io docker-compose-v2)
fi
run apt-get update -q
run apt-get install -y -q --no-install-recommends "${PKGS[@]}"

# avahi-daemon (mDNS, .local) is deliberately NOT installed. Macs own the
# .local suffix through Bonjour and it fights the domain's DNS.
if dpkg -s avahi-daemon >/dev/null 2>&1; then
  warn "avahi-daemon is installed; removing it (mDNS .local conflicts with the AD realm)"
  run apt-get purge -y -q avahi-daemon
fi

# ----------------------------------------------------------------------------
# 2. Hostname and timezone
# ----------------------------------------------------------------------------
say "2/7  Hostname and timezone"
if [ "$(hostname)" != "$HOSTNAME_WANTED" ]; then
  run hostnamectl set-hostname "$HOSTNAME_WANTED"
else
  note "hostname already $HOSTNAME_WANTED"
fi
FQDN="$HOSTNAME_WANTED.${REALM,,}"
if [ "$DRY_RUN" = 0 ]; then
  # /etc/hosts must resolve the FQDN to the real LAN address, not 127.0.1.1,
  # or Samba's DNS registers the wrong address for the DC.
  sed -i "/[[:space:]]$HOSTNAME_WANTED\([[:space:]]\|$\)/d" /etc/hosts
  if [ -n "$PRIMARY_IP" ]; then
    echo "$PRIMARY_IP $FQDN $HOSTNAME_WANTED" >> /etc/hosts
  else
    warn "no primary IP found; add '<lan-ip> $FQDN $HOSTNAME_WANTED' to /etc/hosts by hand"
  fi
else
  note "[dry-run] would write '$PRIMARY_IP $FQDN $HOSTNAME_WANTED' to /etc/hosts"
fi
if [ "$(timedatectl show -p Timezone --value 2>/dev/null || true)" != "$TIMEZONE" ]; then
  run timedatectl set-timezone "$TIMEZONE"
else
  note "timezone already $TIMEZONE"
fi
run systemctl enable --now chrony >/dev/null 2>&1 || warn "chrony did not start; Kerberos needs the clock within 5 minutes of the Macs"

# ----------------------------------------------------------------------------
# 2b. Keep the address the router gave us, and pin it (docs/ANSWERS.md: no
#     router changes, no IP changes). The box asked Netgear A for an address
#     like any new device; from here on it keeps exactly that address, gateway
#     and interface, written as static in netplan on this box only. Nobody
#     types an IP and nothing on the router changes.
# ----------------------------------------------------------------------------
say "2b/7  Pin this box's address (the one DHCP gave it)"
if [ "$PIN_IP" = 1 ] && [ -n "$PRIMARY_IF" ] && [ -n "$PRIMARY_IP" ]; then
  CIDR="$(ip -o -4 addr show dev "$PRIMARY_IF" 2>/dev/null | awk '{print $4}' | head -1 || true)"
  GW="$(ip -o route show default dev "$PRIMARY_IF" 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="via") print $(i+1)}' | head -1 || true)"
  PINNED="/etc/netplan/60-arise-pinned.yaml"
  if [ -f "$PINNED" ] && grep -q "$PRIMARY_IP/" "$PINNED"; then
    note "already pinned: $PRIMARY_IP on $PRIMARY_IF ($PINNED)"
  elif [ -z "$CIDR" ] || [ -z "$GW" ]; then
    warn "could not read the address/gateway on $PRIMARY_IF; not pinning. INSTALL.md § 5 does it by hand"
  elif [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] write $PINNED: $PRIMARY_IF static $CIDR via $GW, DNS 127.0.0.1 (the DC), search ${REALM,,}; then netplan apply"
  else
    mkdir -p /etc/netplan
    cat > "$PINNED" <<NETPLAN
# Written by Arise Server install.sh. This is the address Netgear A handed
# this box by DHCP, kept for good so the domain controller never moves.
# Nothing on the router was changed. Remove this file and run
# 'netplan apply' to go back to DHCP.
network:
  version: 2
  ethernets:
    $PRIMARY_IF:
      dhcp4: false
      addresses: [$CIDR]
      routes:
        - to: default
          via: $GW
      nameservers:
        addresses: [127.0.0.1]
        search: [${REALM,,}]
NETPLAN
    chmod 600 "$PINNED"
    # the cloud-init netplan still says dhcp4: true for this interface; ours
    # sorts later (60- > 50-) and wins for the keys it sets.
    if netplan generate >/dev/null 2>&1; then
      netplan apply >/dev/null 2>&1 || warn "netplan apply failed; the address stays as DHCP gave it until the next boot"
      note "pinned $CIDR via $GW on $PRIMARY_IF; the router still thinks it is a DHCP lease, which is fine"
    else
      rm -f "$PINNED"; warn "netplan rejected the pin; removed $PINNED and left DHCP alone (INSTALL.md § 5 by hand)"
    fi
  fi
  note "If the router ever hands this address to another device (it can, since the lease is not reserved), arisectl doctor reports the clash; the fix is to run this step again after a reboot."
else
  note "address pinning skipped (--no-pin-ip or no primary interface); the DC's address may change at the router's whim"
fi

# ----------------------------------------------------------------------------
# 3. Code and Python
# ----------------------------------------------------------------------------
say "3/7  Code to $INSTALL_ROOT and the Python venv"
run mkdir -p "$INSTALL_ROOT"
if [ "$DRY_RUN" = 0 ]; then
  if [ "$REPO_DIR" != "$INSTALL_ROOT" ]; then
    rsync -a --delete \
      --exclude '.git' --exclude 'venv' --exclude '__pycache__' --exclude '*.pyc' \
      "$REPO_DIR/" "$INSTALL_ROOT/"
    note "synced repo → $INSTALL_ROOT"
  else
    note "running from $INSTALL_ROOT already"
  fi
else
  note "[dry-run] rsync $REPO_DIR/ → $INSTALL_ROOT/"
fi

if [ ! -x "$VENV/bin/python" ]; then
  run python3 -m venv "$VENV"
else
  note "venv exists"
fi
if [ "$DRY_RUN" = 0 ]; then
  "$VENV/bin/pip" install -q --upgrade pip
  if [ -f "$INSTALL_ROOT/server/requirements.txt" ]; then
    "$VENV/bin/pip" install -q -r "$INSTALL_ROOT/server/requirements.txt"
  else
    warn "server/requirements.txt not found; installing the known set"
    "$VENV/bin/pip" install -q fastapi 'uvicorn[standard]' psutil pyyaml bcrypt itsdangerous python-multipart
  fi
  # The automator's own libraries, so arise_daily.py runs from this venv.
  "$VENV/bin/pip" install -q google-api-python-client google-auth-oauthlib pillow tzdata youtube-transcript-api
  note "python: $("$VENV/bin/python" --version)"
else
  note "[dry-run] pip install server/requirements.txt + automator libs into $VENV"
fi

# Where to read units, templates and examples from. After the sync that is
# $INSTALL_ROOT; in --dry-run nothing was copied, so fall back to the repo.
SRC="$INSTALL_ROOT"
[ -d "$SRC/config" ] || SRC="$REPO_DIR"

# arisectl on the PATH
if [ -f "$SRC/cli/arisectl" ]; then
  run install -m 0755 "$SRC/cli/arisectl" /usr/local/bin/arisectl
  [ -f "$SRC/cli/arisetui" ] && run install -m 0755 "$SRC/cli/arisetui" /usr/local/bin/arisetui
else
  warn "cli/arisectl not in the repo yet; /usr/local/bin/arisectl not installed"
fi

# ----------------------------------------------------------------------------
# 4. Config, state and data folders
# ----------------------------------------------------------------------------
say "4/7  Config ($CONF_DIR), state ($STATE_DIR), data ($DATA_ROOT)"

# The 'arise' service user (uid 1500) owns the app data folders; the Docker
# templates run as it so a container can only touch what that user can.
if id -u arise >/dev/null 2>&1; then
  note "user arise exists (uid $(id -u arise))"
else
  run groupadd -g 1500 arise
  run useradd -u 1500 -g 1500 -M -d "$DATA_ROOT" -s /usr/sbin/nologin arise
fi
run mkdir -p "$CONF_DIR" "$STATE_DIR" "$LOG_DIR"
run mkdir -p "$CONF_DIR/secrets"
run chmod 0700 "$CONF_DIR/secrets"
for d in homes shares automator apps backups backups/github-mirror; do
  run mkdir -p "$DATA_ROOT/$d"
done
run chmod 0755 "$DATA_ROOT" "$DATA_ROOT/homes" "$DATA_ROOT/shares"

if [ ! -f "$CONF_DIR/arise.toml" ]; then
  run cp "$SRC/config/arise.toml.example" "$CONF_DIR/arise.toml"
  note "wrote $CONF_DIR/arise.toml from the example — edit it for the NAS and GitHub list"
else
  note "$CONF_DIR/arise.toml exists, left alone"
fi
if [ ! -f "$CONF_DIR/backups.yaml" ]; then
  run cp "$SRC/config/backups.yaml.example" "$CONF_DIR/backups.yaml"
else
  note "$CONF_DIR/backups.yaml exists, left alone"
fi
run chmod 0640 "$CONF_DIR/arise.toml" "$CONF_DIR/backups.yaml"
run mkdir -p /mnt/synology

# ----------------------------------------------------------------------------
# 5. Samba Active Directory Domain Controller
# ----------------------------------------------------------------------------
say "5/7  Active Directory domain $REALM (NetBIOS $NETBIOS)"
if [ "$SKIP_DOMAIN" = 1 ]; then
  note "--skip-domain: not touching Samba"
elif [ -f /var/lib/samba/private/sam.ldb ]; then
  note "domain already provisioned (sam.ldb exists); not re-provisioning"
  note "   to start over: systemctl stop samba-ad-dc; rm -rf /var/lib/samba/* /etc/samba/smb.conf; re-run"
else
  # On Ubuntu the samba package starts the file-server daemons, which hold
  # the ports the DC needs. They must be stopped and masked first.
  for u in smbd nmbd winbind; do
    run systemctl disable --now "$u" >/dev/null 2>&1 || true
    run systemctl mask "$u" >/dev/null 2>&1 || true
  done
  # samba-tool refuses to provision over an existing smb.conf.
  if [ -f /etc/samba/smb.conf ]; then
    run mv /etc/samba/smb.conf "/etc/samba/smb.conf.pre-arise.$(date +%s)"
  fi
  if [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] samba-tool domain provision --use-rfc2307 --realm=$REALM --domain=$NETBIOS --server-role=dc --dns-backend=SAMBA_INTERNAL --option='dns forwarder = $DNS_FORWARDER' --adminpass=***"
  else
    [ -n "$ADMIN_PASS" ] || die "no --admin-pass and nothing was prompted; cannot provision"
    samba-tool domain provision \
      --use-rfc2307 \
      --realm="$REALM" \
      --domain="$NETBIOS" \
      --server-role=dc \
      --dns-backend=SAMBA_INTERNAL \
      --option="dns forwarder = $DNS_FORWARDER" \
      --adminpass="$ADMIN_PASS"
    note "provisioned. Administrator@$REALM is the domain admin."
  fi
fi

if [ "$SKIP_DOMAIN" = 0 ]; then
  # Merge our [homes] / [shares] / Mac settings into the provisioned smb.conf.
  # See config/samba/README.md. The marker keeps this idempotent.
  TEMPLATE="$SRC/config/samba/smb.conf.template"
  if [ -f /etc/samba/smb.conf ] && [ -f "$TEMPLATE" ]; then
    if grep -q '^# >>> arise-server shares' /etc/samba/smb.conf; then
      note "smb.conf already carries the Arise shares block"
    else
      if [ "$DRY_RUN" = 1 ]; then
        note "[dry-run] append the share block from $TEMPLATE to /etc/samba/smb.conf"
      else
        cp /etc/samba/smb.conf "/etc/samba/smb.conf.bak.$(date +%s)"
        # Everything after the '# >>> arise-server shares' marker in the template.
        awk '/^# >>> arise-server shares/{p=1} p' "$TEMPLATE" >> /etc/samba/smb.conf
        # The Mac (vfs fruit) lines belong in [global]; insert them once.
        if ! grep -q 'fruit:model' /etc/samba/smb.conf; then
          sed -i '/^\[global\]/a\        # arise-server: macOS over SMB (see config/samba/smb.conf.template)\n        vfs objects = acl_xattr fruit streams_xattr\n        fruit:metadata = stream\n        fruit:model = MacSamba\n        fruit:posix_rename = yes\n        fruit:veto_appledouble = no\n        fruit:wipe_intentionally_left_blank_rfork = yes\n        fruit:delete_empty_adfiles = yes' /etc/samba/smb.conf
        fi
        testparm -s >/dev/null 2>&1 || die "smb.conf failed testparm after the merge; restore /etc/samba/smb.conf.bak.* and look at the template"
        note "merged the Arise share block into /etc/samba/smb.conf"
      fi
    fi
  fi

  # Kerberos: use the file the provision wrote.
  if [ -f /var/lib/samba/private/krb5.conf ]; then
    if [ "$DRY_RUN" = 1 ]; then
      note "[dry-run] cp /var/lib/samba/private/krb5.conf /etc/krb5.conf"
    else
      cp /var/lib/samba/private/krb5.conf /etc/krb5.conf
      note "/etc/krb5.conf written from the provision"
    fi
  fi

  # DNS: the DC is its own resolver. systemd-resolved must stop listening on
  # :53 and the box must look at 127.0.0.1 with the realm as search domain.
  if [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] point DNS at 127.0.0.1, search ${REALM,,}; disable systemd-resolved's stub listener"
  else
    mkdir -p /etc/systemd/resolved.conf.d
    cat > /etc/systemd/resolved.conf.d/arise-ad-dc.conf <<RESOLVED
# Written by Arise Server install.sh. The Samba AD DC serves DNS on :53;
# resolved's stub listener on 127.0.0.53 must get out of the way.
[Resolve]
DNS=127.0.0.1
Domains=${REALM,,}
DNSStubListener=no
RESOLVED
    systemctl restart systemd-resolved || true
    # /etc/resolv.conf: a plain file Samba, Kerberos and the Macs' expectations agree with.
    if [ -L /etc/resolv.conf ]; then rm -f /etc/resolv.conf; fi
    printf 'nameserver 127.0.0.1\nsearch %s\n' "${REALM,,}" > /etc/resolv.conf
    note "DNS now 127.0.0.1, search ${REALM,,}"
  fi

  # The local user that the dashboard runs samba-tool as is root (the service
  # runs as root); nothing extra. Start the DC.
  run systemctl unmask samba-ad-dc >/dev/null 2>&1 || true
  if [ "$NO_START" = 0 ]; then
    run systemctl enable --now samba-ad-dc
    if [ "$DRY_RUN" = 0 ]; then
      sleep 3
      if samba-tool domain info 127.0.0.1 >/dev/null 2>&1; then
        note "DC answering: $(samba-tool domain info 127.0.0.1 | tr '\n' ' ' | sed 's/  */ /g')"
      else
        warn "samba-ad-dc started but 'samba-tool domain info 127.0.0.1' failed — journalctl -u samba-ad-dc"
      fi
      # The DC's own DNS record. If this fails the Macs cannot find the domain.
      if host -t SRV "_ldap._tcp.${REALM,,}" 127.0.0.1 >/dev/null 2>&1; then
        note "SRV record _ldap._tcp.${REALM,,} resolves"
      else
        warn "SRV lookup for _ldap._tcp.${REALM,,} failed — the Macs will not find the domain until DNS works"
      fi
    fi
  else
    run systemctl enable samba-ad-dc
    note "--no-start: samba-ad-dc enabled, not started"
  fi
fi

# ----------------------------------------------------------------------------
# 5b. Password policy, groups and shares (docs/ANSWERS.md 25, 26, 27, 37)
# ----------------------------------------------------------------------------
say "5b/7  Password policy, groups and the nine shares"
# Bradly's policy (answer 26): never expires, 12 characters, lockout after 10 failures.
if [ "$SKIP_DOMAIN" = 0 ] && [ "$NO_START" = 0 ]; then
  if [ "$DRY_RUN" = 1 ]; then note "[dry-run] samba-tool domain passwordsettings set --max-pwd-age=0 --min-pwd-length=12 --complexity=on --account-lockout-threshold=10 --account-lockout-duration=15"
  else
    samba-tool domain passwordsettings set --max-pwd-age=0 >/dev/null 2>&1 && \
    samba-tool domain passwordsettings set --min-pwd-length=12 >/dev/null 2>&1 && \
    samba-tool domain passwordsettings set --complexity=on >/dev/null 2>&1 && \
    samba-tool domain passwordsettings set --account-lockout-threshold=10 >/dev/null 2>&1 && \
    samba-tool domain passwordsettings set --account-lockout-duration=15 >/dev/null 2>&1 && \
    note "password policy: no expiry, 12 characters, lockout after 10 failures for 15 minutes" || warn "password policy not applied (is the DC up?); see docs/DIRECTORY.md § Password policy"
  fi
fi
# One security group per share plus the department groups. samba-tool refuses
# to add a group that exists, so every line is safe to run again.
if [ "$SKIP_DOMAIN" = 0 ] && [ "$NO_START" = 0 ]; then
  for g in Staff Leadership Media Kids Childrens-Department Inedge Worship Volunteers Kids-Check-in; do
    if [ "$DRY_RUN" = 1 ]; then note "[dry-run] samba-tool group add $g"; continue; fi
    if samba-tool group list 2>/dev/null | grep -qx "$g"; then note "group $g exists"; else
      samba-tool group add "$g" >/dev/null 2>&1 && note "group $g created" || warn "could not create group $g (is the DC up?)"
    fi
  done
  # Leadership also reads the staff share: nest it. Media reads graphics and worship (in smb.conf).
  if [ "$DRY_RUN" = 0 ]; then samba-tool group addmembers Staff Leadership >/dev/null 2>&1 || true; fi
fi
for sh in staff leadership media graphics kids childrens-department inedge worship; do
  run mkdir -p "$DATA_ROOT/shares/$sh"
done
run mkdir -p "$DATA_ROOT/shares"
if [ "$DRY_RUN" = 0 ] && [ "$SKIP_DOMAIN" = 0 ] && getent group "Domain Users" >/dev/null 2>&1; then
  # Each share folder belongs to its group so the force group in smb.conf matches on disk.
  for pair in staff:Staff leadership:Leadership media:Media graphics:Media kids:Kids childrens-department:Childrens-Department inedge:Inedge worship:Worship; do
    d=${pair%%:*}; g=${pair#*:}
    chgrp "$g" "$DATA_ROOT/shares/$d" 2>/dev/null && chmod 2775 "$DATA_ROOT/shares/$d" || note "chgrp $g on shares/$d skipped (group not visible to the OS yet; run again after the DC is up)"
  done
  chmod 2770 "$DATA_ROOT/shares/leadership" 2>/dev/null || true
fi
note "recordings share lives on the Synology (/mnt/synology/arise/recordings); made by 'arisectl nas mount'"
# The four administrators (docs/ANSWERS.md 25) are added by hand with real passwords:
#   sudo arisectl user add bryant.sanders --display "Bryant Sanders" --groups "Domain Admins,Staff,Leadership"
#   sudo arisectl user add vanessa.sanders --display "Vanessa Sanders" --groups "Domain Admins,Staff,Leadership"
#   sudo arisectl user add kristina.robinson --display "Kristina Robinson" --groups "Domain Admins,Staff"
# bradly.dyer is created by step 5 as the first Domain Admin when --admin-pass is given.

# ----------------------------------------------------------------------------
# 6. Docker (optional) and systemd units
# ----------------------------------------------------------------------------
say "6/7  Docker and the Arise services"
if [ "$SKIP_DOCKER" = 0 ]; then
  run systemctl enable --now docker >/dev/null 2>&1 || warn "docker did not start — app templates will not work until it does"
else
  note "--skip-docker: no Docker"
fi

UNIT_SRC="$SRC/config/systemd"
if [ -d "$UNIT_SRC" ]; then
  for f in "$UNIT_SRC"/*.service "$UNIT_SRC"/*.timer; do
    [ -e "$f" ] || continue
    run install -m 0644 "$f" "/etc/systemd/system/$(basename "$f")"
  done
  run systemctl daemon-reload
else
  die "config/systemd is missing from $SRC"
fi

ENABLE_UNITS=(arise-web.service arise-nas-mount.service arise-automator.timer arise-backup.timer arise-mirror.timer)
for u in "${ENABLE_UNITS[@]}"; do
  if [ -f "/etc/systemd/system/$u" ] || [ -f "$UNIT_SRC/$u" ]; then
    if [ "$NO_START" = 0 ]; then
      run systemctl enable --now "$u" || warn "$u failed to start — journalctl -u ${u%.*}"
    else
      run systemctl enable "$u"
    fi
  else
    warn "unit $u not found in config/systemd; skipped"
  fi
done

if [ "$NO_START" = 0 ] && [ "$DRY_RUN" = 0 ]; then
  sleep 2
  if curl -fsS "http://127.0.0.1:$WEB_PORT/api/overview" >/dev/null 2>&1 || curl -fsS "http://127.0.0.1:$WEB_PORT/" >/dev/null 2>&1; then
    note "dashboard answering on :$WEB_PORT"
  else
    warn "dashboard not answering on :$WEB_PORT yet — journalctl -u arise-web -n 50"
  fi
fi

# ----------------------------------------------------------------------------
# 6b. Remote access: firewall, fail2ban, sshd, notify timer, and the optional
#     Tailscale / WireGuard / Caddy pieces. Every part is idempotent.
#     The LAN subnet is read from [remote] lan_subnet in arise.toml, falling
#     back to the primary interface's own network.
# ----------------------------------------------------------------------------
say "6b/7  Remote access and the firewall"

ADMIN_USER="$(awk -F'"' '/^[[:space:]]*admin_user[[:space:]]*=/{print $2; exit}' "$CONF_DIR/arise.toml" 2>/dev/null || true)"
ADMIN_USER="${ADMIN_USER:-bradly}"
SSH_PORT="$(awk -F'=' '/^[[:space:]]*ssh_port[[:space:]]*=/{gsub(/[^0-9]/,"",$2); print $2; exit}' "$CONF_DIR/arise.toml" 2>/dev/null || true)"
SSH_PORT="${SSH_PORT:-22}"
LAN_SUBNET="$(awk -F'"' '/^[[:space:]]*lan_subnet[[:space:]]*=/{print $2; exit}' "$CONF_DIR/arise.toml" 2>/dev/null || true)"
if [ -z "$LAN_SUBNET" ] && [ -n "${PRIMARY_IP:-}" ]; then
  LAN_SUBNET="$(ip -o -4 route show 2>/dev/null | awk -v ip="$PRIMARY_IP" '$0 ~ ("src " ip) && $1 ~ /\// {print $1; exit}' || true)"
fi
LAN_SUBNET="${LAN_SUBNET:-192.168.1.0/24}"
WG_SUBNET="10.47.0.0/24"
note "admin user $ADMIN_USER · ssh port $SSH_PORT · LAN $LAN_SUBNET"

# --- ufw --------------------------------------------------------------------
if ! command -v ufw >/dev/null 2>&1; then
  run apt-get install -y -q ufw
fi
run ufw --force default deny incoming
run ufw --force default allow outgoing
run ufw allow "$SSH_PORT/tcp" comment 'ssh'
run ufw allow from "$LAN_SUBNET" to any port "$WEB_PORT" proto tcp comment 'arise dashboard'
run ufw allow from "$WG_SUBNET" to any port "$WEB_PORT" proto tcp comment 'arise dashboard (vpn)'
run ufw allow from 100.64.0.0/10 to any port "$WEB_PORT" proto tcp comment 'arise dashboard (tailscale)'
# The domain controller's ports, LAN and VPN only. Nothing of the DC is ever
# reachable from the internet.
for src in "$LAN_SUBNET" "$WG_SUBNET" "100.64.0.0/10"; do
  run ufw allow from "$src" to any port 53 comment 'dns'
  run ufw allow from "$src" to any port 88 comment 'kerberos'
  run ufw allow from "$src" to any port 135 proto tcp comment 'rpc'
  run ufw allow from "$src" to any port 137:139 comment 'netbios'
  run ufw allow from "$src" to any port 389 comment 'ldap'
  run ufw allow from "$src" to any port 445 proto tcp comment 'smb'
  run ufw allow from "$src" to any port 464 comment 'kpasswd'
  run ufw allow from "$src" to any port 636 proto tcp comment 'ldaps'
  run ufw allow from "$src" to any port 3268:3269 proto tcp comment 'global catalog'
  run ufw allow from "$src" to any port 49152:65535 proto tcp comment 'rpc dynamic'
  run ufw allow from "$src" to any port 123 proto udp comment 'ntp'
  run ufw allow from "$src" to any port 8081:8084 proto tcp comment 'arise apps'
done
if [ "$WITH_WIREGUARD" = 1 ]; then
  run ufw allow 51820/udp comment 'wireguard'
fi
if [ "$WITH_CADDY" = 1 ]; then
  for src in "$LAN_SUBNET" "$WG_SUBNET" "100.64.0.0/10"; do
    run ufw allow from "$src" to any port 443 proto tcp comment 'https (caddy)'
  done
fi
run ufw --force enable
note "ufw: deny incoming by default; ssh from anywhere (the VPN keeps 'anywhere' small); DC, dashboard and apps from LAN + VPN only"

# --- fail2ban ---------------------------------------------------------------
if ! command -v fail2ban-client >/dev/null 2>&1; then
  run apt-get install -y -q fail2ban
fi
if [ "$DRY_RUN" = 1 ]; then
  note "[dry-run] write /etc/fail2ban/jail.d/arise-sshd.local (sshd jail, port $SSH_PORT, 5 tries, 10 min ban)"
else
  mkdir -p /etc/fail2ban/jail.d
  cat > /etc/fail2ban/jail.d/arise-sshd.local <<F2B
# Arise Server: ban an address after 5 bad SSH logins for 10 minutes.
[sshd]
enabled = true
port = $SSH_PORT
maxretry = 5
findtime = 10m
bantime = 10m
backend = systemd
F2B
fi
run systemctl enable --now fail2ban >/dev/null 2>&1 || warn "fail2ban did not start — journalctl -u fail2ban"

# --- sshd hardening ---------------------------------------------------------
# Password login is switched off ONLY when the admin user already has a key on
# this box. Otherwise a locked-closet server with no monitor would be
# unreachable the moment this ran.
ADMIN_HOME="$(getent passwd "$ADMIN_USER" | cut -d: -f6 || true)"
KEYS_FILE="${ADMIN_HOME:-/nonexistent}/.ssh/authorized_keys"
HAS_KEYS=0
if [ -s "$KEYS_FILE" ] && grep -qvE '^\s*(#|$)' "$KEYS_FILE"; then HAS_KEYS=1; fi
if [ "$DRY_RUN" = 1 ]; then
  note "[dry-run] write /etc/ssh/sshd_config.d/arise.conf (PasswordAuthentication $([ "$HAS_KEYS" = 1 ] && echo no || echo 'yes — no key for '"$ADMIN_USER"' yet'))"
else
  mkdir -p /etc/ssh/sshd_config.d
  {
    echo "# Arise Server sshd hardening. Written by installer/install.sh; re-run it after ssh-copy-id."
    echo "Port $SSH_PORT"
    echo "PermitRootLogin no"
    echo "PubkeyAuthentication yes"
    echo "MaxAuthTries 4"
    echo "X11Forwarding no"
    echo "ClientAliveInterval 120"
    echo "ClientAliveCountMax 3"
    if [ "$HAS_KEYS" = 1 ]; then
      echo "PasswordAuthentication no"
      echo "KbdInteractiveAuthentication no"
    else
      echo "# PasswordAuthentication left ON: $KEYS_FILE has no key yet."
      echo "# From your Mac:  ssh-copy-id $ADMIN_USER@$HOSTNAME_WANTED   then re-run the installer."
    fi
  } > /etc/ssh/sshd_config.d/arise.conf
  if sshd -t 2>/dev/null; then
    systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
  else
    warn "sshd rejected the new config; removing it so SSH keeps working"
    rm -f /etc/ssh/sshd_config.d/arise.conf
  fi
fi
if [ "$HAS_KEYS" = 1 ]; then
  note "sshd: key-only login for $ADMIN_USER (password login off)"
else
  warn "sshd: PASSWORD LOGIN IS STILL ON because $KEYS_FILE has no key."
  warn "      From your Mac run:  ssh-copy-id $ADMIN_USER@$HOSTNAME_WANTED   and then re-run this installer."
fi

# --- the daily notification timer (unit files come from config/systemd) ------
if [ -f /etc/systemd/system/arise-notify.timer ] || [ -f "$UNIT_SRC/arise-notify.timer" ]; then
  if [ "$NO_START" = 0 ]; then
    run systemctl enable --now arise-notify.timer || warn "arise-notify.timer failed to start"
  else
    run systemctl enable arise-notify.timer
  fi
  note "arise-notify.timer: the morning report goes to [notify] webhook_url in arise.toml once it is set"
else
  note "no arise-notify.timer in config/systemd; skipped"
fi

# --- Tailscale (optional) -----------------------------------------------------
if [ "$WITH_TAILSCALE" = 1 ]; then
  if command -v tailscale >/dev/null 2>&1; then
    note "tailscale already installed ($(tailscale version 2>/dev/null | head -1 || echo '?'))"
  else
    if [ "$DRY_RUN" = 1 ]; then
      note "[dry-run] curl -fsSL https://tailscale.com/install.sh | sh"
    else
      curl -fsSL https://tailscale.com/install.sh | sh || warn "tailscale install script failed — see https://tailscale.com/download/linux"
    fi
  fi
  if [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] sysctl net.ipv4.ip_forward=1 (so the subnet route works)"
  else
    printf 'net.ipv4.ip_forward = 1\nnet.ipv6.conf.all.forwarding = 1\n' > /etc/sysctl.d/99-arise-forward.conf
    sysctl -q --system >/dev/null 2>&1 || true
  fi
  warn "Tailscale needs a browser login, so this is yours to run:"
  warn "    sudo tailscale up --ssh --advertise-routes=$LAN_SUBNET"
  warn "then approve the subnet route in the admin console and set split DNS for ad.arisecenla.church (docs/REMOTE-ACCESS.md)."
fi

# --- WireGuard (optional) -----------------------------------------------------
if [ "$WITH_WIREGUARD" = 1 ]; then
  if ! command -v wg >/dev/null 2>&1; then
    run apt-get install -y -q wireguard
  fi
  WG_CONF=/etc/wireguard/wg0.conf
  WAN_IF="$(ip -o route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}' | head -1 || true)"
  WAN_IF="${WAN_IF:-eth0}"
  if [ -f "$WG_CONF" ]; then
    note "$WG_CONF exists, left alone (peers are kept)"
  elif [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] write $WG_CONF: fresh key, Address 10.47.0.1/24, ListenPort 51820, NAT via $WAN_IF"
  else
    mkdir -p /etc/wireguard/peers
    chmod 0700 /etc/wireguard
    WG_PRIV="$(wg genkey)"
    cat > "$WG_CONF" <<WGC
# Arise Server WireGuard. Written by installer/install.sh --with-wireguard.
# Peers are appended by the dashboard's Remote app / arisectl remote add-peer.
# Forward UDP 51820 on the Pineville router to this server, and set
# [remote] wg_endpoint = "<public name>:51820" in /etc/arise/arise.toml.
[Interface]
Address = 10.47.0.1/24
ListenPort = 51820
PrivateKey = $WG_PRIV
# NAT the tunnel onto the LAN so peers reach the Synology, printers, Macs.
PostUp   = iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -j ACCEPT; iptables -t nat -A POSTROUTING -o $WAN_IF -j MASQUERADE
PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -j ACCEPT; iptables -t nat -D POSTROUTING -o $WAN_IF -j MASQUERADE
WGC
    chmod 0600 "$WG_CONF"
    printf 'net.ipv4.ip_forward = 1\n' > /etc/sysctl.d/99-arise-forward.conf
    sysctl -q --system >/dev/null 2>&1 || true
    note "server public key: $(printf '%s' "$WG_PRIV" | wg pubkey)"
  fi
  # ufw must forward between the tunnel and the LAN
  if [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] ufw: DEFAULT_FORWARD_POLICY=ACCEPT; route allow $WG_SUBNET -> $LAN_SUBNET"
  else
    sed -i 's/^DEFAULT_FORWARD_POLICY=.*/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw 2>/dev/null || true
    ufw route allow from "$WG_SUBNET" to "$LAN_SUBNET" >/dev/null 2>&1 || true
    ufw reload >/dev/null 2>&1 || true
  fi
  if [ "$NO_START" = 0 ]; then
    run systemctl enable --now wg-quick@wg0 || warn "wg-quick@wg0 failed — journalctl -u wg-quick@wg0"
  else
    run systemctl enable wg-quick@wg0
  fi
  note "WireGuard on UDP 51820, tunnel $WG_SUBNET. Add devices: dashboard → Remote → Add peer, or: sudo arisectl remote add-peer <name>"
  warn "Do not also deploy the wg-easy template: same port."
fi

# --- Caddy (optional) ---------------------------------------------------------
if [ "$WITH_CADDY" = 1 ]; then
  if ! command -v caddy >/dev/null 2>&1; then
    if [ "$DRY_RUN" = 1 ]; then
      note "[dry-run] add the official Caddy apt repo (cloudsmith) and apt-get install caddy"
    else
      apt-get install -y -q debian-keyring debian-archive-keyring apt-transport-https curl gnupg >/dev/null
      curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
      curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
      apt-get update -q >/dev/null
      apt-get install -y -q caddy
    fi
  else
    note "caddy already installed"
  fi
  if [ -f "$SRC/config/caddy/Caddyfile" ]; then
    if [ -f /etc/caddy/Caddyfile ] && ! grep -q 'Arise Server' /etc/caddy/Caddyfile 2>/dev/null; then
      run cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.before-arise
    fi
    run install -m 0644 "$SRC/config/caddy/Caddyfile" /etc/caddy/Caddyfile
  else
    warn "config/caddy/Caddyfile missing from the repo; caddy left with its default config"
  fi
  if [ "$NO_START" = 0 ]; then
    run systemctl enable --now caddy || warn "caddy failed to start — journalctl -u caddy"
    if command -v caddy >/dev/null 2>&1 && [ "$DRY_RUN" = 0 ]; then
      systemctl reload caddy >/dev/null 2>&1 || true
    fi
  else
    run systemctl enable caddy
  fi
  note "HTTPS on https://$HOSTNAME_WANTED.ad.arisecenla.church (internal CA). Trust the root once per device: docs/REMOTE-ACCESS.md (e)"
  note "DNS records still needed:  sudo samba-tool dns add 127.0.0.1 ad.arisecenla.church vault A ${PRIMARY_IP:-<lan-ip>}   (and remote)"
fi

# ----------------------------------------------------------------------------
# 6c. The closet monitor: pre-login banner, login message, optional tty1 dashboard
# ----------------------------------------------------------------------------
say "6c/7  Console: banner, login message$( [ "$WITH_CONSOLE" = 1 ] && echo ', arisetui on tty1' )"
if [ -f "$SRC/config/console/issue" ]; then
  run install -m 0644 "$SRC/config/console/issue" /etc/issue
  note "/etc/issue: the Arise banner before login"
fi
if [ -f "$SRC/config/console/50-arise-motd" ] && [ -d /etc/update-motd.d ]; then
  run install -m 0755 "$SRC/config/console/50-arise-motd" /etc/update-motd.d/50-arise-motd
  # Ubuntu's own ad lines have no place on a church server's login
  for f in 10-help-text 50-motd-news 90-updates-available 91-contract-ua-esm-status; do
    [ -x "/etc/update-motd.d/$f" ] && run chmod -x "/etc/update-motd.d/$f"
  done
  note "login message: the Arise flame + arisectl info"
fi
if [ "$WITH_CONSOLE" = 1 ]; then
  if [ -f "$SRC/config/systemd/arise-console.service" ]; then
    run install -m 0644 "$SRC/config/systemd/arise-console.service" /etc/systemd/system/arise-console.service
    run systemctl daemon-reload
    if [ "$NO_START" = 0 ]; then
      run systemctl enable --now arise-console.service
      note "tty1 now shows arisetui (read only). Alt+F2 is a normal login."
    else
      run systemctl enable arise-console.service
    fi
  else
    warn "config/systemd/arise-console.service not in the repo; tty1 left as a login prompt"
  fi
fi

if [ "$WITH_KIOSK" = 1 ]; then
  say "6d/7  Kiosk: the Arise desktop on the closet monitor"
  # cage (a Wayland kiosk compositor) + Epiphany (GTK WebKit) are plain apt
  # packages: no snaps, no X, no desktop environment. ~250 MB.
  run apt-get install -y -q cage epiphany-browser
  if id -u arise-kiosk >/dev/null 2>&1; then
    note "user arise-kiosk exists"
  else
    run useradd -u 1501 -m -d /var/lib/arise/kiosk-home -s /usr/sbin/nologin -G video,input,render arise-kiosk
  fi
  run mkdir -p /var/lib/arise/kiosk
  run chown -R arise-kiosk: /var/lib/arise/kiosk /var/lib/arise/kiosk-home
  if [ -f "$SRC/config/systemd/arise-kiosk.service" ]; then
    run install -m 0644 "$SRC/config/systemd/arise-kiosk.service" /etc/systemd/system/arise-kiosk.service
    run systemctl daemon-reload
    if [ "$WITH_CONSOLE" = 1 ]; then
      warn "--console and --kiosk both given: the desktop takes tty1; arisetui is still 'arisetui' in any terminal"
      run systemctl disable --now arise-console.service || true
    fi
    if [ "$NO_START" = 0 ]; then
      run systemctl enable --now arise-kiosk.service
      note "tty1 now shows the Arise desktop. Alt+F2 is a normal login."
    else
      run systemctl enable arise-kiosk.service
    fi
  fi
  if ! lspci 2>/dev/null | grep -qi 'vga\|display'; then
    warn "no display adapter seen by lspci; the kiosk needs a GPU and a monitor plugged in at boot"
  fi
fi

# ----------------------------------------------------------------------------
# 7. Summary — what still needs a human
# ----------------------------------------------------------------------------
say "7/7  Done. What still needs you"
AUTOMATOR_DIR="$DATA_ROOT/automator/ARISE_YouTube_Updater"
cat <<SUMMARY

    Dashboard      http://$HOSTNAME_WANTED:$WEB_PORT   (or http://${PRIMARY_IP:-<lan-ip>}:$WEB_PORT)
    Domain         $REALM   NetBIOS $NETBIOS   admin: Administrator
    Code           $INSTALL_ROOT        Config  $CONF_DIR/arise.toml
    Data           $DATA_ROOT          Log     $LOG_FILE

    Still needs a human — in this order:

    1. Dashboard password:        sudo arisectl admin set-password
    2. The automator checkout:    git clone https://github.com/Rehchu/arise-youtube-automation.git "$AUTOMATOR_DIR"
       then copy token.json and client_secret.json into "$AUTOMATOR_DIR/"
       (they are never in git — bring them from the old PC or run authorize.py there)
    3. restic password:           openssl rand -base64 32 | sudo tee $CONF_DIR/secrets/restic-password >/dev/null
                                  sudo chmod 0600 $CONF_DIR/secrets/restic-password
       KEEP A COPY OF THAT PASSWORD OFF THE SERVER. Without it the backups cannot be read.
    4. Synology credentials:      sudo nano $CONF_DIR/secrets/synology.cred   (username=… / password=… / domain=$NETBIOS)
                                  sudo chmod 0600 $CONF_DIR/secrets/synology.cred ; sudo arisectl nas mount
    5. Then:                      sudo arisectl doctor
    6. Remote access (docs/REMOTE-ACCESS.md):
       ssh key from your Mac:     ssh-copy-id $ADMIN_USER@$HOSTNAME_WANTED   then re-run this installer (turns password login off)
$( [ "$WITH_TAILSCALE" = 1 ] && echo "       tailscale (needs a browser): sudo tailscale up --ssh --advertise-routes=$LAN_SUBNET" || echo "       VPN not installed yet: re-run with --with-tailscale (recommended) or --with-wireguard" )
$( [ "$WITH_WIREGUARD" = 1 ] && echo "       wireguard: forward UDP 51820 on the router; set [remote] wg_endpoint in $CONF_DIR/arise.toml; add devices from the Remote app" )
$( [ "$WITH_CADDY" = 1 ] && echo "       https: trust the Caddy root on each Mac; add the vault/remote DNS records (config/caddy/Caddyfile)" )
       remote desktop:            sudo arisectl app deploy guacamole   (see templates/guacamole/template.yaml for the one-time initdb)

$( [ "$SKIP_DOMAIN" = 1 ] && echo "    (domain skipped: no Active Directory on this box; re-run without --skip-domain to provision it)" )
$( [ "$NO_START" = 1 ] && echo "    (--no-start: nothing is running yet;  sudo systemctl start arise-web samba-ad-dc  when ready)" )
$( [ "$DRY_RUN" = 1 ] && echo "    (dry run: NOTHING WAS CHANGED)" )
SUMMARY
echo " Arise Server install — finished $(date '+%Y-%m-%d %H:%M:%S %Z')"

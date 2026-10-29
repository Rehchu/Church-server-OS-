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
#    5. provisions the Samba Active Directory domain AD.ARISECENLA.COM
#    6. installs the systemd units and timers, starts the dashboard on :4147
#    7. prints what still needs a human (token.json, restic password, NAS)
#
#  Flags:
#    --admin-pass PASS   Domain Administrator password (prompted if omitted)
#    --owner NAME        Bradly's own Linux account (default: the account that ran sudo). It runs the 02:05
#                        YouTube job and gets sudo without a password, so his Claude can change anything (Oct 28)
#    --skip-domain       do not provision / touch the Samba AD DC
#    --skip-docker       do not install Docker (no app templates)
#    --no-start          install everything but do not start services/timers
#    --with-tailscale    (default ON) install Tailscale; --no-tailscale to skip. `tailscale up` is still yours to run
#    --apps "a,b"        only these apps at install (default: every template, started within the memory budget); --no-apps for none
#    --with-wireguard    native WireGuard server on UDP 51820 (wg0, 10.47.0.0/24)
#    --with-caddy        (default ON since v0.8; --no-caddy to skip) Caddy in front of the dashboard with the box's own
#                        certificate authority: the church certificate every enrolled Mac trusts (round 3, 29)
#    --no-tpm            do not bind the encrypted disk to the TPM (default: if the disk is LUKS and a TPM is there, bind it)
#    --restore REPO      REINSTALL: on a fresh Ubuntu, pull /etc/arise, /etc/samba, the domain's offline backup and the
#                        pinned address back from this restic repository first, then install around them (docs/REINSTALL.md)
#    --with-cockpit      (default ON; --no-cockpit to skip) Cockpit (Red Hat's web console) on :9090: disks, services, logs, a terminal, a second door
#                        into the box when the dashboard is what is broken
#    --console           show the arisetui text dashboard on the closet monitor (tty1)
#    --kiosk             show the Arise desktop (Finder, dock, widgets) full screen on the closet monitor (tty1)
#    --staging           installing somewhere that is NOT the church (Bradly's house): the domain listens
#                        on this box only, no address is pinned, no network scan, no DC ports open.
#                        At the church run install.sh again WITHOUT --staging and it switches over.
#    --with-claude       (default ON; --no-claude to skip) Claude Code on the box (Node 20 LTS + the npm package),
#                        signed in with Bradly's claude.ai account: run `claude`, then /login. No API key anywhere.
#    --no-hardening      skip the care an old PC needs: security updates (no auto-reboot), a year of logs,
#                        SMART monitoring, needrestart, fstrim, logrotate. Default ON.
#    --no-safety         skip step 6j, the safety basics: arise-rescue, clamav, timeshift, clevis/TPM, the safe card
#    --ssh-key "ssh-ed25519 AAAA… name"   the admin's public key, enrolled into the admin user's authorized_keys
#                        (or --ssh-key-file FILE). SSH is keys only (Bradly): password login is off; the closet
#                        monitor and arise-rescue are the way in without a key.
#    --no-splash         skip the ariseOS boot splash (Plymouth theme, quiet kernel, 1 s GRUB menu)
#    --no-ups            skip NUT (the UPS daemon; shuts the box down cleanly on low battery once the model is set)
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
REALM="AD.ARISECENLA.COM"
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
WITH_TAILSCALE=1
WITH_WIREGUARD=0
WITH_CADDY=1
WITH_TPM=1
WITH_SAFETY=1
RESTORE_REPO=""
SSH_KEY=""
WITH_CONSOLE=0
WITH_KIOSK=0
WITH_COCKPIT=1
WITH_CLAUDE=1
WITH_HARDENING=1
WITH_SPLASH=1
WITH_UPS=1
PIN_IP=1
# Every template deployed after the OS install (Bradly, round 3, 5: "The 24 app
# templates should already be preinstalled"). Started only within the memory
# budget: each template.yaml says autostart and ram_mb; the heavy ones are
# deployed and left stopped, one click in the Store away. `--apps "a b c"`
# narrows it to a list; `--no-apps` skips the step.
DEFAULT_APPS="all"
APPS="$DEFAULT_APPS"
STAGING=0
STAGING_MARK="/etc/arise/staging"
SKIP_DOMAIN=0
SKIP_DOCKER=0
# Bradly's account: --owner, else whoever ran `sudo bash install.sh`.
OWNER="${OWNER:-}"
NO_START=0
DRY_RUN=0

usage() { sed -n '2,30p' "$0" | sed 's/^#  \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --admin-pass)  ADMIN_PASS="${2:-}"; shift 2 ;;
    --owner)       OWNER="${2:-}"; shift 2 ;;
    --admin-pass=*) ADMIN_PASS="${1#*=}"; shift ;;
    --skip-domain) SKIP_DOMAIN=1; shift ;;
    --skip-docker) SKIP_DOCKER=1; shift ;;
    --no-start)    NO_START=1; shift ;;
    --with-tailscale) WITH_TAILSCALE=1; shift ;;
    --with-wireguard) WITH_WIREGUARD=1; shift ;;
    --with-caddy)  WITH_CADDY=1; shift ;;
    --no-caddy)    WITH_CADDY=0; shift ;;
    --no-tpm)      WITH_TPM=0; shift ;;
    --no-safety)   WITH_SAFETY=0; shift ;;
    --restore)     RESTORE_REPO="${2:-}"; shift 2 ;;
    --restore=*)   RESTORE_REPO="${1#*=}"; shift ;;
    --ssh-key)     SSH_KEY="${2:-}"; shift 2 ;;
    --ssh-key-file) SSH_KEY="$(cat "${2:-/dev/null}" 2>/dev/null || true)"; shift 2 ;;
    --with-cockpit) WITH_COCKPIT=1; shift ;;
    --no-cockpit)  WITH_COCKPIT=0; shift ;;
    --with-claude) WITH_CLAUDE=1; shift ;;
    --no-claude)   WITH_CLAUDE=0; shift ;;
    --no-hardening) WITH_HARDENING=0; shift ;;
    --no-splash)   WITH_SPLASH=0; shift ;;
    --no-ups)      WITH_UPS=0; shift ;;
    --no-tailscale) WITH_TAILSCALE=0; shift ;;
    --apps)        APPS="${2//,/ }"; shift 2 ;;
    --no-apps)     APPS=""; shift ;;
    --console)     WITH_CONSOLE=1; shift ;;
    --kiosk)       WITH_KIOSK=1; shift ;;
    --no-pin-ip)   PIN_IP=0; shift ;;
    --staging)     STAGING=1; PIN_IP=0; shift ;;
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
# A random password, letters and digits. Not `tr </dev/urandom | head`: under
# pipefail tr dies of SIGPIPE when head closes, the pipeline returns 141 and the
# ERR trap ends the install (found by the install rehearsal).
rand_pw() { python3 -c 'import secrets, string, sys; a = string.ascii_letters + string.digits; print("".join(secrets.choice(a) for _ in range(int(sys.argv[1]))))' "${1:-24}"; }

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
echo " flags: admin-pass=$([ -n "$ADMIN_PASS" ] && echo set || echo unset) skip-domain=$SKIP_DOMAIN skip-docker=$SKIP_DOCKER no-start=$NO_START tailscale=$WITH_TAILSCALE wireguard=$WITH_WIREGUARD caddy=$WITH_CADDY tpm=$WITH_TPM safety=$WITH_SAFETY restore=${RESTORE_REPO:-no} cockpit=$WITH_COCKPIT claude=$WITH_CLAUDE hardening=$WITH_HARDENING apps=[$APPS] console=$WITH_CONSOLE kiosk=$WITH_KIOSK splash=$WITH_SPLASH ups=$WITH_UPS pin-ip=$PIN_IP staging=$STAGING dry-run=$DRY_RUN"
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

# Staging (at home) vs the church. The marker file remembers which this box
# last ran as, so a plain run at the church knows it is relocating.
if [ "$STAGING" = 1 ]; then
  note "STAGING: this box is not at the church. The domain will listen on this box only (interfaces = lo),"
  note "         no address is pinned, no network scan runs, no DC port is opened, timers stay enabled but idle."
elif [ -f "$STAGING_MARK" ]; then
  RELOCATING=1
  note "RELOCATING: this box was staged elsewhere (${STAGING_MARK}). Switching it to the church network:"
  note "            address pinned here, domain on the wire, DNS records refreshed, scans on."
fi
RELOCATING="${RELOCATING:-0}"

# --- 0b. REINSTALL from the Synology's backup (round 3, 24; docs/REINSTALL.md) ----
# Before the domain is provisioned or a config written, the box's own files come
# back from the restic repository: /etc/arise (config + secrets), /etc/samba,
# the domain's OFFLINE backup (/var/lib/arise/samba-backup), the pinned address.
# Step 5 then RESTORES the domain from that offline backup instead of
# provisioning a new one, and the rest of the install finds its config in place.
RESTORED_DOMAIN=0
if [ -n "$RESTORE_REPO" ]; then
  say "0b  Reinstall: restoring this box's own files from $RESTORE_REPO"
  [ -f /var/lib/samba/private/sam.ldb ] && [ "$DRY_RUN" = 0 ] && die "this box already has a domain database (/var/lib/samba/private/sam.ldb). --restore is for a FRESH Ubuntu. Stop."
  RESTIC_PW_FILE="$CONF_DIR/secrets/restic-password"
  if [ ! -s "$RESTIC_PW_FILE" ] && [ "$DRY_RUN" = 0 ]; then
    mkdir -p "$CONF_DIR/secrets"; chmod 0711 "$CONF_DIR/secrets"
    read -r -s -p "    The restic password (from the closet card): " RPW; echo
    [ -n "$RPW" ] || die "no restic password; nothing can be read from the repository"
    printf '%s\n' "$RPW" > "$RESTIC_PW_FILE"; chmod 600 "$RESTIC_PW_FILE"; unset RPW
  fi
  if [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] apt-get install -y restic"
    note "[dry-run] restic -r $RESTORE_REPO snapshots --latest 1 --tag system"
    note "[dry-run] restic -r $RESTORE_REPO restore latest --tag system --target / --include /etc/arise --include /etc/samba --include /var/lib/arise/samba-backup --include /etc/netplan/60-arise-pinned.yaml"
    note "[dry-run] (the newest /var/lib/arise/samba-backup/samba-backup-*.tar.bz2 is what step 5 restores the domain from)"
  else
    command -v restic >/dev/null 2>&1 || apt-get install -y -q restic >>"$LOG_FILE" 2>&1
    export RESTIC_REPOSITORY="$RESTORE_REPO" RESTIC_PASSWORD_FILE="$RESTIC_PW_FILE"
    restic snapshots --latest 1 --tag system >>"$LOG_FILE" 2>&1 || die "cannot read $RESTORE_REPO (is the Synology mounted? is the password the one on the safe card?)"
    restic restore latest --tag system --target / --include /etc/arise --include /etc/samba --include /var/lib/arise/samba-backup --include /etc/netplan/60-arise-pinned.yaml >>"$LOG_FILE" 2>&1 \
      || die "restic restore failed (see $LOG_FILE)"
    note "restored: $CONF_DIR, /etc/samba, /var/lib/arise/samba-backup, the pinned address"
    SAMBA_TAR="$(ls -1t /var/lib/arise/samba-backup/samba-backup-*.tar.bz2 2>/dev/null | head -1 || true)"
    if [ -n "$SAMBA_TAR" ]; then
      note "domain backup to restore in step 5: $SAMBA_TAR"
    else
      warn "no samba offline backup in the repository; step 5 will PROVISION a new domain (users and passwords will not come back). docs/REINSTALL.md explains the live-copy fallback."
    fi
    # The restored smb.conf would make step 5 think the domain exists; step 5 handles it.
    chmod 0711 "$CONF_DIR/secrets" 2>/dev/null || true   # traverse only (step 4)
  fi
fi

# A domain controller must not be on Wi-Fi and must have a fixed address.
PRIMARY_IF="$(ip -o route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}' | head -1 || true)"
PRIMARY_IP="$(ip -o route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' | head -1 || true)"
# The LAN subnet, read from the box itself (no router page needed): the
# firewall and the Docker allow-list use it. Override with LAN_SUBNET=... in the environment.
if [ -z "${LAN_SUBNET:-}" ] && [ -n "$PRIMARY_IF" ] && command -v python3 >/dev/null 2>&1; then
  _CIDR="$(ip -o -4 addr show dev "$PRIMARY_IF" 2>/dev/null | awk '{print $4}' | head -1 || true)"
  [ -n "$_CIDR" ] && LAN_SUBNET="$(python3 -c "import ipaddress,sys; print(ipaddress.ip_interface(sys.argv[1]).network)" "$_CIDR" 2>/dev/null || true)"
fi
LAN_SUBNET="${LAN_SUBNET:-192.168.1.0/24}"
WG_SUBNET="10.47.0.0/24"
note "primary interface: ${PRIMARY_IF:-unknown}  address: ${PRIMARY_IP:-unknown}  subnet: $LAN_SUBNET"
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
  samba samba-ad-dc samba-ad-provision samba-dsdb-modules samba-vfs-modules
  winbind krb5-user krb5-config libnss-winbind libpam-winbind
  smbclient ldb-tools acl attr quota auditd inotify-tools
  cifs-utils nfs-common
  restic rsync git curl jq arp-scan nmap ffmpeg bind9-host
  openssh-server
  ca-certificates gnupg
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
      --exclude '.git' --exclude 'venv' --exclude '__pycache__' --exclude '*.pyc' --exclude '/.mcp.json' \
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
run chmod 0711 "$CONF_DIR/secrets"   # 0711: no listing, but the owner (youtube/) and arise-kb (archive/) reach their own subfolders
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
# arise.toml holds no secrets, but stays closed: root, plus the group arise-conf, which the
# service users join (arise-git, arise-kb) and the owner, so their arisectl calls can read it.
getent group arise-conf >/dev/null 2>&1 || run groupadd -g 1504 arise-conf 2>/dev/null || run groupadd arise-conf
run chgrp arise-conf "$CONF_DIR/arise.toml"
run mkdir -p /mnt/synology

# ----------------------------------------------------------------------------
# 5. Samba Active Directory Domain Controller
# ----------------------------------------------------------------------------
say "5/7  Active Directory domain $REALM (NetBIOS $NETBIOS)"
# REINSTALL (step 0b): a domain comes back from its offline backup, never re-provisioned.
if [ -n "$RESTORE_REPO" ] && [ "$SKIP_DOMAIN" = 0 ]; then
  SAMBA_TAR="${SAMBA_TAR:-$(ls -1t /var/lib/arise/samba-backup/samba-backup-*.tar.bz2 2>/dev/null | head -1 || true)}"
  if [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] systemctl stop samba-ad-dc smbd nmbd winbind; mv /var/lib/samba /var/lib/samba.fresh; mv /etc/samba/smb.conf /etc/samba/smb.conf.restored"
    note "[dry-run] samba-tool domain backup restore --backup-file=<newest samba-backup-*.tar.bz2> --targetdir=/var/lib/samba --newservername=$HOSTNAME_WANTED"
    note "[dry-run] cp /var/lib/samba/etc/smb.conf /etc/samba/smb.conf; testparm -s; systemctl enable --now samba-ad-dc"
    RESTORED_DOMAIN=1
  elif [ -n "$SAMBA_TAR" ]; then
    systemctl stop samba-ad-dc smbd nmbd winbind >/dev/null 2>&1 || true
    systemctl disable --now smbd nmbd winbind >/dev/null 2>&1 || true
    [ -d /var/lib/samba ] && mv /var/lib/samba "/var/lib/samba.fresh.$(date +%s)"
    [ -f /etc/samba/smb.conf ] && mv /etc/samba/smb.conf /etc/samba/smb.conf.restored
    if samba-tool domain backup restore --backup-file="$SAMBA_TAR" --targetdir=/var/lib/samba --newservername="$HOSTNAME_WANTED" >>"$LOG_FILE" 2>&1; then
      # the restore writes its own smb.conf inside the target; put it where Samba reads it, then our shares file beside it
      [ -f /var/lib/samba/etc/smb.conf ] && cp /var/lib/samba/etc/smb.conf /etc/samba/smb.conf
      if testparm -s >/dev/null 2>&1; then
        systemctl unmask samba-ad-dc >/dev/null 2>&1 || true
        systemctl enable --now samba-ad-dc >/dev/null 2>&1 || warn "samba-ad-dc did not start after the restore: journalctl -u samba-ad-dc"
        RESTORED_DOMAIN=1
        note "domain restored from $SAMBA_TAR (every user, group and password came back)"
      else
        warn "the restored smb.conf fails testparm; the domain is NOT up. Compare /etc/samba/smb.conf with /etc/samba/smb.conf.restored"
      fi
    else
      warn "samba-tool domain backup restore failed (see $LOG_FILE). The domain will be provisioned fresh below; users will need to be re-created."
    fi
  fi
fi

if [ "$SKIP_DOMAIN" = 1 ]; then
  note "--skip-domain: not touching Samba"
elif [ "$RESTORED_DOMAIN" = 1 ] || [ -f /var/lib/samba/private/sam.ldb ]; then
  note "domain already $([ "$RESTORED_DOMAIN" = 1 ] && echo restored || echo provisioned) (sam.ldb exists); not re-provisioning"
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
        # Round 5, row 12: [storage] homes_on = "synology" moves the homes to <nas mount>/arise/homes.
        HOMES_ON="$(python3 -c 'import sys,tomllib; print((tomllib.load(open(sys.argv[1],"rb")).get("storage") or {}).get("homes_on","server"))' "$CONF_DIR/arise.toml" 2>/dev/null || echo server)"
        if [ "$HOMES_ON" = synology ]; then
          awk '/^# >>> arise-server shares/{p=1} p' "$TEMPLATE" | sed "s#/srv/arise/homes/#/mnt/synology/arise/homes/#g" >> /etc/samba/smb.conf
          note "homes on the Synology (/mnt/synology/arise/homes), from [storage] homes_on"
        else
          awk '/^# >>> arise-server shares/{p=1} p' "$TEMPLATE" >> /etc/samba/smb.conf
        fi
        # The Mac (vfs fruit) lines belong in [global]; insert them once.
        if ! grep -q 'fruit:model' /etc/samba/smb.conf; then
          sed -i '/^\[global\]/a\        # arise-server: macOS over SMB (see config/samba/smb.conf.template)\n        vfs objects = dfs_samba4 acl_xattr fruit streams_xattr\n        fruit:metadata = stream\n        fruit:model = MacSamba\n        fruit:posix_rename = yes\n        fruit:veto_appledouble = no\n        fruit:wipe_intentionally_left_blank_rfork = yes\n        fruit:delete_empty_adfiles = yes' /etc/samba/smb.conf
        fi
        testparm -s >/dev/null 2>&1 || die "smb.conf failed testparm after the merge; restore /etc/samba/smb.conf.bak.* and look at the template"
        note "merged the Arise share block into /etc/samba/smb.conf"
      fi
    fi
  fi
  # Staging: the DC listens on loopback only, so nothing on a home network ever
  # sees the domain, its DNS or its shares. Relocating: take that back out.
  if [ -f /etc/samba/smb.conf ] && [ "$DRY_RUN" = 0 ]; then
    sed -i '/^\s*# arise-server: staging$/,/^\s*bind interfaces only = yes$/d' /etc/samba/smb.conf
    if [ "$STAGING" = 1 ]; then
      sed -i '/^\[global\]/a\        # arise-server: staging\n        interfaces = lo\n        bind interfaces only = yes' /etc/samba/smb.conf
      testparm -s >/dev/null 2>&1 || die "smb.conf failed testparm after the staging lines"
      note "staging: Samba bound to loopback only (interfaces = lo)"
    elif [ "$RELOCATING" = 1 ]; then
      note "relocating: Samba now listens on the wire"
    fi
  elif [ "$DRY_RUN" = 1 ] && [ "$STAGING" = 1 ]; then
    note "[dry-run] would bind Samba to loopback only (interfaces = lo, bind interfaces only = yes)"
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

  # DNS, in two moves (the rehearsal found the old order broke every later
  # download: the box was pointed at 127.0.0.1 before the DC answered, so with
  # --no-start, or a DC that failed to start, apt could resolve nothing).
  #  1. Free :53 for Samba (resolved's stub listener off) but keep the box
  #     resolving through the upstream servers it already had.
  #  2. Start the DC; only when it answers BOTH the domain's SRV record and an
  #     outside name (through its forwarder) does the box switch to 127.0.0.1.
  if [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] resolved: stub listener off, upstream DNS kept; switch to 127.0.0.1 (search ${REALM,,}) only once the DC answers"
  else
    mkdir -p /etc/systemd/resolved.conf.d
    cat > /etc/systemd/resolved.conf.d/arise-ad-dc.conf <<RESOLVED
# Written by Arise Server install.sh. The Samba AD DC serves DNS on :53;
# resolved's stub listener on 127.0.0.53 must get out of the way.
[Resolve]
DNSStubListener=no
RESOLVED
    systemctl restart systemd-resolved >/dev/null 2>&1 || true
    # Until the DC answers, resolve through the upstream servers directly.
    if [ -f /run/systemd/resolve/resolv.conf ] && grep -q '^nameserver' /run/systemd/resolve/resolv.conf; then
      if [ -L /etc/resolv.conf ] || ! grep -q '^nameserver 127\.0\.0\.1' /etc/resolv.conf 2>/dev/null; then
        ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf
      fi
    fi
  fi
  dns_switch_to_dc() {
    if [ -L /etc/resolv.conf ]; then rm -f /etc/resolv.conf; fi
    printf 'nameserver 127.0.0.1\nsearch %s\n' "${REALM,,}" > /etc/resolv.conf
    printf '[Resolve]\nDNS=127.0.0.1\nDomains=%s\nDNSStubListener=no\n' "${REALM,,}" > /etc/systemd/resolved.conf.d/arise-ad-dc.conf
    systemctl restart systemd-resolved >/dev/null 2>&1 || true
    note "DNS now 127.0.0.1 (the DC), search ${REALM,,}"
  }

  # The local user that the dashboard runs samba-tool as is root (the service
  # runs as root); nothing extra. Start the DC.
  run systemctl unmask samba-ad-dc >/dev/null 2>&1 || true
  if [ "$NO_START" = 0 ]; then
    run systemctl enable --now samba-ad-dc
    if [ "$DRY_RUN" = 0 ]; then
      DC_OK=0
      for _ in 1 2 3 4 5 6 7 8 9 10; do
        if host -W 2 -t SRV "_ldap._tcp.${REALM,,}" 127.0.0.1 >/dev/null 2>&1; then DC_OK=1; break; fi
        sleep 2
      done
      if samba-tool domain info 127.0.0.1 >/dev/null 2>&1; then
        note "DC answering: $(samba-tool domain info 127.0.0.1 | tr '\n' ' ' | sed 's/  */ /g')"
      else
        warn "samba-ad-dc started but 'samba-tool domain info 127.0.0.1' failed — journalctl -u samba-ad-dc"
      fi
      if [ "$DC_OK" = 1 ]; then
        note "SRV record _ldap._tcp.${REALM,,} resolves"
        if host -W 3 archive.ubuntu.com 127.0.0.1 >/dev/null 2>&1; then
          dns_switch_to_dc
        else
          warn "the DC answers for ${REALM,,} but not for outside names (dns forwarder $DNS_FORWARDER?); the box keeps its upstream DNS so the install can go on. Fix the forwarder, then: sudo arisectl doctor"
        fi
      else
        warn "SRV lookup for _ldap._tcp.${REALM,,} failed — the Macs will not find the domain until DNS works; the box keeps its upstream DNS for now (journalctl -u samba-ad-dc)"
      fi
    fi
  else
    run systemctl enable samba-ad-dc
    note "--no-start: samba-ad-dc enabled, not started; the box keeps its upstream DNS. After 'systemctl start samba-ad-dc', re-run the installer to switch DNS to the DC"
  fi
fi

# ----------------------------------------------------------------------------
# 5b. Password policy, groups and shares (docs/ANSWERS.md 25, 26, 27, 37)
# ----------------------------------------------------------------------------
say "5b/7  Password policy, groups and the nine shares"
# Bradly's policy (answer 26): never expires, 12 characters. NO lockout (round 3, 27):
# everything is behind Tailscale or inside the building, and a locked-out pastor
# on a Sunday morning is worse than a guesser who never reaches the box.
if [ "$SKIP_DOMAIN" = 0 ] && [ "$NO_START" = 0 ]; then
  if [ "$DRY_RUN" = 1 ]; then note "[dry-run] samba-tool domain passwordsettings set --max-pwd-age=0 --min-pwd-length=12 --complexity=on --account-lockout-threshold=0"
  else
    samba-tool domain passwordsettings set --max-pwd-age=0 >/dev/null 2>&1 && \
    samba-tool domain passwordsettings set --min-pwd-length=12 >/dev/null 2>&1 && \
    samba-tool domain passwordsettings set --complexity=on >/dev/null 2>&1 && \
    samba-tool domain passwordsettings set --account-lockout-threshold=0 >/dev/null 2>&1 && \
    note "password policy: no expiry, 12 characters, no lockout (round 3, 27)" || warn "password policy not applied (is the DC up?); see docs/DIRECTORY.md § Password policy"
  fi
fi
# One security group per share plus the department groups. samba-tool refuses
# to add a group that exists, so every line is safe to run again.
if [ "$SKIP_DOMAIN" = 0 ] && [ "$NO_START" = 0 ]; then
  for g in Staff Leadership Media Kids Childrens-Department Inedge Worship Volunteers Kids-Check-in Alexandria Pastors; do
    if [ "$DRY_RUN" = 1 ]; then note "[dry-run] samba-tool group add $g"; continue; fi
    if samba-tool group list 2>/dev/null | grep -qx "$g"; then note "group $g exists"; else
      samba-tool group add "$g" >/dev/null 2>&1 && note "group $g created" || warn "could not create group $g (is the DC up?)"
    fi
  done
  # Leadership also reads the staff share: nest it. Media reads graphics and worship (in smb.conf).
  if [ "$DRY_RUN" = 0 ]; then samba-tool group addmembers Staff Leadership >/dev/null 2>&1 || true; fi
  # The OUs the Macs and PCs bind into (docs/DIRECTORY.md). bind-mac.sh's default is
  # OU=Macs,OU=Computers and windows/join-arise.ps1 uses OU=PCs,OU=Computers: without
  # these, every bind fails with "OU does not exist". OU=Computers sits beside the
  # built-in CN=Computers container; they are different objects.
  BASE_DN="DC=$(echo "${REALM,,}" | sed 's/\./,DC=/g')"
  for ou in "OU=Computers" "OU=Macs,OU=Computers" "OU=PCs,OU=Computers"; do
    if [ "$DRY_RUN" = 1 ]; then note "[dry-run] samba-tool ou add '$ou,$BASE_DN'"; continue; fi
    if samba-tool ou list 2>/dev/null | grep -qix "$ou"; then note "$ou exists"; else
      samba-tool ou add "$ou,$BASE_DN" >/dev/null 2>&1 && note "$ou created" || warn "could not create $ou (is the DC up?): sudo samba-tool ou add '$ou,$BASE_DN'"
    fi
  done
fi
for sh in staff leadership media graphics kids childrens-department inedge worship church alexandria; do
  run mkdir -p "$DATA_ROOT/shares/$sh"
done
# Round 5: the Pastors folder sits outside shares/ so no share above it reaches it; shared/ holds
# each person's Shared-with-me links (the [shared] share).
run mkdir -p "$DATA_ROOT/pastors" "$DATA_ROOT/shared"
run chmod 0700 "$DATA_ROOT/pastors"
run chmod 0755 "$DATA_ROOT/shared"
# Media/Fonts (docs/ANSWERS.md round 3, 39): the Proclaim fonts live here and every
# enrolled Mac installs what it finds on its hourly sync (mac/arise-home-sync.sh).
run mkdir -p "$DATA_ROOT/shares/media/Fonts"
if [ "$DRY_RUN" = 0 ] && [ ! -f "$DATA_ROOT/shares/media/Fonts/README.txt" ]; then
  printf '%s\n' "Fonts for the Proclaim graphics. Drop .ttf / .otf / .ttc files here;" "every enrolled Mac installs them on its hourly sync (mac/arise-home-sync.sh)." "Keep the licence file beside a bought font." > "$DATA_ROOT/shares/media/Fonts/README.txt"
fi
run mkdir -p "$DATA_ROOT/shares"
if [ "$DRY_RUN" = 0 ] && [ "$SKIP_DOMAIN" = 0 ] && getent group "Domain Users" >/dev/null 2>&1; then
  # Each share folder belongs to its group so the force group in smb.conf matches on disk.
  # The department folders, the Church folder and the Pastors folder get their permissions from
  # `arisectl share folders` below (round 5); these three keep the plain group rule.
  for pair in staff:Staff leadership:Leadership graphics:Media; do
    d=${pair%%:*}; g=${pair#*:}
    chgrp "$g" "$DATA_ROOT/shares/$d" 2>/dev/null && chmod 2775 "$DATA_ROOT/shares/$d" || note "chgrp $g on shares/$d skipped (group not visible to the OS yet; run again after the DC is up)"
  done
  chmod 2770 "$DATA_ROOT/shares/leadership" 2>/dev/null || true
fi
note "recordings share lives on the Synology (/mnt/synology/arise/recordings); made by 'arisectl nas mount'"
# ---- Round 5 (docs/ANSWERS.md rows 16-18, 36): the Church, department, Pastors and Shared-with-me
# shares, generated from arise.toml [storage] with the ACLs that make them true on disk. Macs reach
# them over SMB, so the ACLs are the rule; the dashboard checks the same rule (server/arise_server/sharing.py).
if [ "$SKIP_DOMAIN" = 0 ]; then
  if [ "$DRY_RUN" = 1 ]; then note "[dry-run] arisectl share folders (arise-folders.conf + ACLs)"
  elif [ -x /usr/local/bin/arisectl ] && getent group "Domain Users" >/dev/null 2>&1; then
    /usr/local/bin/arisectl share folders --yes >>"$LOG_FILE" 2>&1 && note "Church, department, Pastors and Shared-with-me shares written (arise-folders.conf)" \
      || warn "arisectl share folders failed (see $LOG_FILE); run it again once the DC is up"
  else note "run 'sudo arisectl share folders' once the DC is up (the groups must be visible to the OS)"; fi
fi
# Row 18: root reading the Pastors folder is logged by auditd (ausearch -k arise-pastors).
if [ "$DRY_RUN" = 1 ]; then note "[dry-run] /etc/audit/rules.d/arise-pastors.rules: -w $DATA_ROOT/pastors -p rwxa -k arise-pastors"
elif command -v auditctl >/dev/null 2>&1; then
  install -d /etc/audit/rules.d
  printf '%s\n' "# ariseOS (round 5, row 18): every read or write of the Pastors folder, by anyone, root included" "-w $DATA_ROOT/pastors -p rwxa -k arise-pastors" > /etc/audit/rules.d/arise-pastors.rules
  (augenrules --load >/dev/null 2>&1 || auditctl -w "$DATA_ROOT/pastors" -p rwxa -k arise-pastors >/dev/null 2>&1) && note "auditd watches the Pastors folder (ausearch -k arise-pastors)" || warn "auditd rule written but not loaded; reboot or: sudo augenrules --load"
else warn "auditd is not installed; the Pastors folder is not watched (apt install auditd, then run the installer again)"; fi
# Row 13: 50 GB a home. The dashboard enforces it on uploads; the filesystem enforces it for
# the Macs when the homes' filesystem has user quotas on (docs/FINDER.md, "The home quota").
if [ "$DRY_RUN" = 0 ] && command -v quotaon >/dev/null 2>&1; then
  if quotaon -pu "$DATA_ROOT/homes" 2>/dev/null | grep -q 'is on'; then
    /usr/local/bin/arisectl quota apply >>"$LOG_FILE" 2>&1 && note "home quotas set (setquota)" || warn "arisectl quota apply failed (see $LOG_FILE)"
  else note "user quotas are off on $DATA_ROOT/homes: the dashboard still refuses uploads past the quota; to make the Macs' copies stop too, add usrquota to that filesystem in /etc/fstab, remount, quotacheck -cum, quotaon, then: sudo arisectl quota apply"; fi
fi
# The four administrators (docs/ANSWERS.md 25) are added by hand with real passwords:
#   sudo arisectl user add bryant.sanders --display "Bryant Sanders" --groups "Domain Admins,Staff,Leadership,Pastors"
#   sudo arisectl user add vanessa.sanders --display "Vanessa Sanders" --groups "Domain Admins,Staff,Leadership,Pastors"
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

# Bradly's own account owns the box (Oct 28): every ariseOS group, sudo without a
# password (his Claude edits anything), and the 02:05 job runs as him (next step).
OWNER="${OWNER:-${SUDO_USER:-}}"
if [ -z "$OWNER" ] || [ "$OWNER" = root ]; then
  warn "no owner account: run install.sh with sudo from your own account, or pass --owner NAME (then: sudo arisectl owner setup)"
elif [ "$DRY_RUN" = 1 ]; then
  bash "$SRC/scripts/arise-owner-setup" --dry-run --owner "$OWNER" --src "$SRC" || warn "owner setup (dry run) reported a problem"
else
  bash "$SRC/scripts/arise-owner-setup" --owner "$OWNER" --src "$SRC" || warn "owner setup did not finish (above): sudo arisectl owner setup $OWNER"
fi

# The YouTube automator: ready, never the runner (SERVER_HANDOFF.md in the automator
# repo; docs/AUTOMATOR.md). Its user, folders, env file, read-only deploy key and
# checkout; the timer below may run from day one, because while runner.json names
# the PC each night only writes a "not the runner" report.
if [ "$DRY_RUN" = 1 ]; then
  bash "$SRC/scripts/arise-automator-setup" --dry-run --src "$SRC" ${OWNER:+--owner "$OWNER"} || warn "automator setup (dry run) reported a problem"
else
  bash "$SRC/scripts/arise-automator-setup" --src "$SRC" ${OWNER:+--owner "$OWNER"} || warn "automator setup did not finish (above): sudo arisectl automator setup"
fi

# The Arise repos, two-way with GitHub every 15 minutes (docs/REPOS.md).
if [ "$DRY_RUN" = 1 ]; then
  bash "$SRC/scripts/arise-repos-setup" --dry-run --src "$SRC" || warn "repos setup (dry run) reported a problem"
else
  bash "$SRC/scripts/arise-repos-setup" --src "$SRC" || warn "repos setup did not finish (above): sudo arisectl repos setup"
fi

# The searchable archive of the automator repo and ProjectBackups, for Claude on the box (docs/ARCHIVE.md).
if [ "$DRY_RUN" = 1 ]; then
  bash "$SRC/scripts/arise-archive-setup" --dry-run --src "$SRC" || warn "archive setup (dry run) reported a problem"
else
  bash "$SRC/scripts/arise-archive-setup" --src "$SRC" || warn "archive setup incomplete (docs/ARCHIVE.md)"
fi

ENABLE_UNITS=(arise-web.service arise-nas-mount.service arise-automator.timer arise-backup.timer arise-mirror.timer arise-repos.timer arise-archive.timer arise-archive-rebuild.timer)
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
# --- Docker's published ports bypass ufw. The DOCKER-USER chain does not. ---
# A tiny unit rewrites that chain at boot and now: containers answer only the
# sources in /etc/arise/docker-allow (the LAN, the VPN). Staging writes an
# empty list, so at Bradly's house no container is reachable from the house.
if [ "$SKIP_DOCKER" = 0 ]; then
  if [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] write /etc/arise/docker-allow ($([ "$STAGING" = 1 ] && echo 'empty: staging' || echo "$LAN_SUBNET $WG_SUBNET 100.64.0.0/10")), /usr/local/sbin/arise-docker-firewall, arise-docker-firewall.service"
  else
    mkdir -p /etc/arise
    if [ "$STAGING" = 1 ]; then : > /etc/arise/docker-allow; else printf '%s\n' "$LAN_SUBNET" "$WG_SUBNET" "100.64.0.0/10" > /etc/arise/docker-allow; fi
    cat > /usr/local/sbin/arise-docker-firewall <<'DFW'
#!/bin/sh
# Arise Server: containers answer only the networks listed in /etc/arise/docker-allow.
# Docker inserts its own ACCEPT rules ahead of ufw; DOCKER-USER runs before them.
set -e
iptables -N DOCKER-USER 2>/dev/null || true
iptables -F DOCKER-USER
iptables -A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
iptables -A DOCKER-USER -i lo -j RETURN
iptables -A DOCKER-USER -i docker0 -j RETURN
iptables -A DOCKER-USER -i 'br-+' -j RETURN
while read -r net; do
  [ -n "$net" ] && iptables -A DOCKER-USER -s "$net" -j RETURN
done < /etc/arise/docker-allow
# traffic the containers start (image pulls, YouTube) leaves through the host and returns as ESTABLISHED
iptables -A DOCKER-USER -m conntrack --ctstate NEW -j DROP
iptables -A DOCKER-USER -j RETURN
DFW
    chmod 755 /usr/local/sbin/arise-docker-firewall
    cat > /etc/systemd/system/arise-docker-firewall.service <<UNIT
[Unit]
Description=Arise Server: containers answer the LAN and the VPN only (DOCKER-USER chain)
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/arise-docker-firewall
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable arise-docker-firewall.service >/dev/null 2>&1 || true
    if [ "$NO_START" = 0 ]; then systemctl restart arise-docker-firewall.service || warn "docker firewall unit failed; containers may answer any source"; fi
    note "containers answer: $([ "$STAGING" = 1 ] && echo 'nobody (staging)' || echo "$LAN_SUBNET, $WG_SUBNET, Tailscale")"
  fi
fi

# ----------------------------------------------------------------------------
# 6a. The apps: deployed, started, ready (DEFAULT_APPS, or --apps)
# ----------------------------------------------------------------------------
say "6a/7  Apps: $([ -n "$APPS" ] && echo "$APPS" || echo none)"
if [ -n "$APPS" ] && [ "$SKIP_DOCKER" = 0 ] && [ "$NO_START" = 0 ]; then
  # The recordings/media mounts Jellyfin and Frigate bind must exist or Docker
  # makes them as root-owned dirs on the mount point; create them explicitly.
  for d in /mnt/synology/arise/recordings /mnt/synology/arise/media /mnt/synology/arise/cameras; do [ -d "$d" ] || run mkdir -p "$d"; done
  APPS_OK=""; APPS_BAD=""
  if [ "$APPS" = "all" ]; then
    # Every template, capped (mem_limit/cpus from its manifest), started only while
    # RAM minus 2 GB (the domain, the dashboard, the kiosk) allows; the rest wait, stopped.
    if [ "$DRY_RUN" = 1 ]; then
      note "[dry-run] arisectl app install-all   (every template deployed; autostart ones started within RAM - 2 GB; heavy ones left stopped)"
    elif /usr/local/bin/arisectl app install-all >>"$LOG_FILE" 2>&1; then
      note "apps: every template deployed; see 'arisectl app list' for what runs and what waits (the Store shows the same)"
    else
      warn "some apps did not deploy (see $LOG_FILE); arisectl app install-all to retry, or arisectl app deploy <name> one at a time"
    fi
    APPS=""
  fi
  for a in $APPS; do
    if [ "$DRY_RUN" = 1 ]; then note "[dry-run] arisectl app deploy $a"; continue; fi
    if [ -d "$SRC/templates/$a" ]; then
      if /usr/local/bin/arisectl app deploy "$a" >>"$LOG_FILE" 2>&1; then APPS_OK="$APPS_OK $a"; note "app $a: up"; else APPS_BAD="$APPS_BAD $a"; warn "app $a: deploy failed (see $LOG_FILE); arisectl app deploy $a to retry"; fi
    else
      warn "no template called $a"; APPS_BAD="$APPS_BAD $a"
    fi
  done
  [ -z "$APPS_BAD" ] || note "apps that did not come up:$APPS_BAD"
  note "generated passwords: /etc/arise/secrets/apps/<app>.env (root only)"
elif [ -n "$APPS" ]; then
  note "apps skipped ($([ "$SKIP_DOCKER" = 1 ] && echo --skip-docker || echo --no-start)); later: arisectl app deploy <name>"
fi

# --- 6a-sync. Mac and phone syncing: Nextcloud over the homes and shares (round 6, docs/SYNC.md) ---
# Nextcloud starts by default (row 14). `arisectl cloud setup` makes it ariseOS's: the domain
# sign-in (its own read-only directory account), the mounts, the theme, each home linked.
if [ "$SKIP_DOCKER" = 0 ] && [ "$NO_START" = 0 ]; then
  if [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] arisectl app deploy nextcloud (if not yet); arisectl cloud setup; cloud CNAME in the domain's DNS; arise-cloud-watch + the hourly conflicts timer"
  else
    [ -f /srv/arise/apps/nextcloud/compose.yaml ] || /usr/local/bin/arisectl app deploy nextcloud >>"$LOG_FILE" 2>&1 || warn "nextcloud did not deploy (see $LOG_FILE): arisectl app deploy nextcloud"
    # inotify for the watcher: one watch per folder in every home and share
    printf 'fs.inotify.max_user_watches=1048576\nfs.inotify.max_user_instances=512\n' > /etc/sysctl.d/60-arise-cloud.conf
    sysctl -q -p /etc/sysctl.d/60-arise-cloud.conf >/dev/null 2>&1 || true
    if [ -f /srv/arise/apps/nextcloud/compose.yaml ]; then
      # The first start of Nextcloud installs itself (a minute or two) before occ answers.
      for _ in $(seq 1 60); do docker exec -u www-data arise-app-nextcloud php occ status >/dev/null 2>&1 && break; sleep 5; done
      if /usr/local/bin/arisectl cloud setup >>"$LOG_FILE" 2>&1; then
        note "sync: Nextcloud is set up (https://cloud.${REALM,,}); every church Mac's helper installs the client"
      else
        warn "sync: arisectl cloud setup had failures (see $LOG_FILE); run it again once Nextcloud is up"
      fi
    fi
    if samba-tool dns query 127.0.0.1 "${REALM,,}" cloud ALL -P >/dev/null 2>&1; then
      note "sync: cloud.${REALM,,} is already in the domain's DNS"
    elif samba-tool dns add 127.0.0.1 "${REALM,,}" cloud CNAME "$HOSTNAME_WANTED.${REALM,,}" -P >>"$LOG_FILE" 2>&1; then
      note "sync: cloud.${REALM,,} added to the domain's DNS (a CNAME to this box)"
    else
      warn "sync: could not add cloud.${REALM,,} to DNS: sudo samba-tool dns add 127.0.0.1 ${REALM,,} cloud CNAME $HOSTNAME_WANTED.${REALM,,} -U administrator"
    fi
  fi
  for u in arise-cloud-watch.service arise-cloud-conflicts.timer; do
    [ -f "$UNIT_SRC/$u" ] && { run systemctl enable --now "$u" || warn "$u did not start"; }
  done
  note "sync: arise-cloud-watch (SMB changes reach the clients), arise-cloud-conflicts.timer hourly (newest wins, the older copy to the Trash)"
else
  note "sync: Nextcloud skipped with the apps; later: arisectl app deploy nextcloud && sudo arisectl cloud setup"
fi

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
# reachable from the internet. Staging: none of them, the DC is on loopback.
DC_SRCS=("$LAN_SUBNET" "$WG_SUBNET" "100.64.0.0/10")
if [ "$STAGING" = 1 ]; then DC_SRCS=(); note "staging: only ssh and the dashboard are reachable; no DC port is opened"; fi
for src in "${DC_SRCS[@]}"; do
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
  run ufw allow from "$src" to any port 8081:8096 proto tcp comment 'arise apps'
  run ufw allow from "$src" to any port 8000 proto tcp comment 'icecast'
  run ufw allow from "$src" to any port 8008 proto tcp comment 'synapse'
  run ufw allow from "$src" to any port 8065 proto tcp comment 'mattermost'
  run ufw allow from "$src" to any port 1935:1936 proto tcp comment 'rtmp'
  run ufw allow from "$src" to any port 9443 proto tcp comment 'portainer'
  run ufw allow from "$src" to any port 19999 proto tcp comment 'netdata'
  run ufw allow from "$src" to any port 20211 proto tcp comment 'netalertx'
  run ufw allow from "$src" to any port 8384 proto tcp comment 'syncthing ui'
  run ufw allow from "$src" to any port 22000 comment 'syncthing'
  run ufw allow from "$src" to any port 8554 proto tcp comment 'frigate rtsp'
  run ufw allow from "$src" to any port 8971 proto tcp comment 'frigate'
done
if [ "$WITH_WIREGUARD" = 1 ]; then
  run ufw allow 51820/udp comment 'wireguard'
fi
if [ "$WITH_CADDY" = 1 ]; then
  for src in "$LAN_SUBNET" "$WG_SUBNET" "100.64.0.0/10"; do
    run ufw allow from "$src" to any port 443 proto tcp comment 'https (caddy)'
  done
fi
if [ "$WITH_COCKPIT" = 1 ]; then
  # Cockpit is apt, not Docker: it is the door that still opens when Docker
  # or the dashboard is what broke. Logs in with the box's own accounts.
  # Not cockpit-networkmanager: it brings NetworkManager, a second owner for the network that
  # netplan and 60-arise-pinned.yaml run (rule 2: the network stays as it is).
  run apt-get install -y -q --no-install-recommends cockpit cockpit-storaged cockpit-packagekit || warn "cockpit did not install (the mirror?); the dashboard does not need it; re-run later"
  if [ "$NO_START" = 0 ]; then run systemctl enable --now cockpit.socket || warn "cockpit.socket did not start"; else run systemctl enable cockpit.socket || warn "cockpit.socket not enabled (not installed?)"; fi
  for src in "$LAN_SUBNET" "$WG_SUBNET" "100.64.0.0/10"; do
    run ufw allow from "$src" to any port 9090 proto tcp comment 'cockpit'
  done
  note "Cockpit on https://arise-server:9090 (its own certificate; sign in as ${OWNER:-your own account})"
fi
run ufw --force enable
note "ufw: deny incoming by default; ssh from anywhere (the VPN keeps 'anywhere' small); DC, dashboard and apps from LAN + VPN only"

# --- no fail2ban (round 3, 27) ------------------------------------------------
# Bradly chose no sign-in lockout of any kind. An earlier version installed
# fail2ban here; this removes it if it is present, so the decision holds.
if command -v fail2ban-client >/dev/null 2>&1; then
  run systemctl disable --now fail2ban >/dev/null 2>&1 || true
  run apt-get remove -y -q fail2ban
  note "fail2ban removed: no address or account is ever locked out (docs/ANSWERS.md round 3, 27)"
else
  note "no fail2ban, by Bradly's decision (round 3, 27)"
fi
[ -f /etc/fail2ban/jail.d/arise-sshd.local ] && run rm -f /etc/fail2ban/jail.d/arise-sshd.local

# --- sshd: keys only (Bradly, Oct 28) ----------------------------------------
# Password login over SSH is OFF, always. The admin's key is enrolled here from
# --ssh-key / --ssh-key-file (or already in authorized_keys from ssh-copy-id).
# No key yet? SSH is closed until one is added; the closet monitor still signs
# in, and arise-rescue (round 3, 21) works there too: at the console ONLY,
# never over SSH (DenyUsers).
# The key goes to Bradly's own Linux account (the owner, the one he SSHes in as), falling back
# to the dashboard admin's name when no owner is known.
KEY_USER="${OWNER:-$ADMIN_USER}"
ADMIN_HOME="$(getent passwd "$KEY_USER" | cut -d: -f6 || true)"
KEYS_FILE="${ADMIN_HOME:-/nonexistent}/.ssh/authorized_keys"
if [ -n "$SSH_KEY" ] && [ -z "$ADMIN_HOME" ]; then
  warn "--ssh-key given but the admin user $KEY_USER has no home on this box yet (step 5 makes it); re-run after the domain is up"
fi
if [ -n "$SSH_KEY" ] && [ -n "$ADMIN_HOME" ]; then
  case "$SSH_KEY" in ssh-ed25519\ *|ssh-rsa\ *|ecdsa-sha2-*|sk-ssh-ed25519*) ;; *) die "--ssh-key does not look like a public key (ssh-ed25519 AAAA… or ssh-rsa AAAA…)";; esac
  if [ "$DRY_RUN" = 1 ]; then note "[dry-run] append the --ssh-key to $KEYS_FILE (0600, owned by $KEY_USER)"
  else
    mkdir -p "$ADMIN_HOME/.ssh"; chmod 700 "$ADMIN_HOME/.ssh"
    touch "$KEYS_FILE"; grep -qxF "$SSH_KEY" "$KEYS_FILE" || printf '%s\n' "$SSH_KEY" >> "$KEYS_FILE"
    chmod 600 "$KEYS_FILE"; chown -R "$KEY_USER:" "$ADMIN_HOME/.ssh" 2>/dev/null || true
    note "ssh key enrolled for $KEY_USER"
  fi
fi
HAS_KEYS=0
if [ -s "$KEYS_FILE" ] && grep -qvE '^\s*(#|$)' "$KEYS_FILE"; then HAS_KEYS=1; fi
if [ "$DRY_RUN" = 1 ]; then
  note "[dry-run] write /etc/ssh/sshd_config.d/00-arise.conf (keys only: PasswordAuthentication no; DenyUsers arise-rescue; key for $KEY_USER: $([ "$HAS_KEYS" = 1 ] && echo present || echo 'NONE yet'))"
else
  mkdir -p /etc/ssh/sshd_config.d
  rm -f /etc/ssh/sshd_config.d/arise.conf   # the old name (sorted after 50-cloud-init.conf, so it lost)
  {
    echo "# Arise Server sshd: keys only (Bradly, Oct 28). Written by installer/install.sh."
    echo "# Add a key: install.sh --ssh-key '...' or ssh-copy-id from the closet monitor's session."
    echo "Port $SSH_PORT"
    echo "PermitRootLogin no"
    echo "PubkeyAuthentication yes"
    echo "PasswordAuthentication no"
    echo "KbdInteractiveAuthentication no"
    echo "MaxAuthTries 4"
    echo "X11Forwarding no"
    echo "ClientAliveInterval 120"
    echo "ClientAliveCountMax 3"
    echo "# The break-glass admin signs in at the closet monitor only (round 3, 21)."
    echo "DenyUsers arise-rescue"
  } > /etc/ssh/sshd_config.d/00-arise.conf
  # Ubuntu 24.04 starts sshd by socket activation, so /run/sshd only exists once
  # sshd has run; without it 'sshd -t' fails and the keys-only file was removed as
  # "rejected" (found by the rehearsal). ssh.service makes it the same way.
  mkdir -p /run/sshd && chmod 0755 /run/sshd
  if sshd -t 2>/dev/null; then
    systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
  else
    warn "sshd rejected the new config; removing it so SSH keeps working"
    rm -f /etc/ssh/sshd_config.d/00-arise.conf
  fi
fi
if [ "$HAS_KEYS" = 1 ]; then
  note "sshd: keys only; $ADMIN_USER has a key; arise-rescue is console-only"
else
  warn "sshd: keys only and $KEYS_FILE has NO key yet, so SSH is closed until one is added."
  warn "      Re-run with --ssh-key 'ssh-ed25519 AAAA…' (from your Mac: cat ~/.ssh/id_ed25519.pub), or sign in on the closet monitor."
fi

# --- the daily notification timer (unit files come from config/systemd) ------
if [ -f "$UNIT_SRC/arise-devices.timer" ] && [ "$STAGING" = 1 ]; then
  run systemctl disable --now arise-devices.timer >/dev/null 2>&1 || true
  note "staging: the hourly network scan is off (it would scan the house)"
elif [ -f "$UNIT_SRC/arise-devices.timer" ]; then
  if [ "$NO_START" = 0 ]; then
    run systemctl enable --now arise-devices.timer || warn "arise-devices.timer failed to start"
  else
    run systemctl enable arise-devices.timer
  fi
fi
if [ -f "$UNIT_SRC/arise-trash.timer" ]; then
  if [ "$NO_START" = 0 ]; then
    run systemctl enable --now arise-trash.timer || warn "arise-trash.timer failed to start"
  else
    run systemctl enable arise-trash.timer
  fi
  note "arise-trash.timer: 04:30 daily, removes what has sat in a share's Trash for 30 days (arisectl trash)"
fi
if [ -f "$UNIT_SRC/arise-offboard.timer" ]; then
  if [ "$NO_START" = 0 ]; then
    run systemctl enable --now arise-offboard.timer || warn "arise-offboard.timer failed to start"
  else
    run systemctl enable arise-offboard.timer
  fi
  note "arise-offboard.timer: 05:15 daily, disables a leaver's login on their day and moves their files on (arisectl offboard)"
fi
if [ -f "$UNIT_SRC/arise-drill.timer" ]; then
  if [ "$NO_START" = 0 ]; then
    run systemctl enable --now arise-drill.timer || warn "arise-drill.timer failed to start"
  else
    run systemctl enable arise-drill.timer
  fi
  note "arise-drill.timer: once a month one file comes back from last night's backup and is compared (arisectl backup drill)"
fi
# Software Update (round 3, 4 and 25): security patches stay unattended (6f);
# everything Bradly queues in the dashboard installs Saturday 03:30 after a
# system snapshot, and a reboot happens only if the kernel asks and no service is on.
if [ -f "$UNIT_SRC/arise-update.timer" ]; then
  if [ "$NO_START" = 0 ]; then
    run systemctl enable --now arise-update.timer || warn "arise-update.timer failed to start"
  else
    run systemctl enable arise-update.timer
  fi
  note "arise-update.timer: Saturday 03:30, installs only what is queued in Software Update (arisectl update)"
fi
# Round 7: the hourly upkeep checks (64, 82, 137/138), the January report (63, 139) and the
# staff mail forwarding (155; it does nothing until [mailfwd] enabled = true).
for t in arise-upkeep.timer arise-january.timer arise-mailfwd.timer; do
  [ -f "$UNIT_SRC/$t" ] || continue
  if [ "$NO_START" = 0 ]; then run systemctl enable --now "$t" || warn "$t failed to start"; else run systemctl enable "$t"; fi
done
note "upkeep: arise-upkeep.timer hourly (Discord #alerts once per item), arise-january.timer Jan 5, arise-mailfwd.timer every 5 min (off until [mailfwd] enabled)"
# Desktop programs from the Store (GIMP, LibreOffice...) stop themselves after an hour with nobody connected.
if [ -f "$UNIT_SRC/arise-idle-apps.timer" ]; then
  if [ "$NO_START" = 0 ]; then run systemctl enable --now arise-idle-apps.timer || warn "arise-idle-apps.timer failed to start"; else run systemctl enable arise-idle-apps.timer; fi
fi
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
  warn "then approve the subnet route in the admin console and set split DNS for ad.arisecenla.com (docs/REMOTE-ACCESS.md)."
fi

# --- WireGuard (optional) -----------------------------------------------------
if [ "$WITH_WIREGUARD" = 1 ]; then
  if ! command -v wg >/dev/null 2>&1; then
    run apt-get install -y -q wireguard || warn "wireguard did not install; Tailscale covers remote access; re-run later"
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
      # Caddy's own repository first (current releases); if it cannot be reached (the
      # church internet is down, Cloudsmith is down) fall back to Ubuntu's caddy, which
      # does everything the Caddyfile asks (tls internal, default_bind). An unreachable
      # repository used to kill the whole install here (found by the install rehearsal).
      CADDY_KEY=/usr/share/keyrings/caddy-stable-archive-keyring.gpg
      CADDY_LIST=/etc/apt/sources.list.d/caddy-stable.list
      apt-get install -y -q debian-keyring debian-archive-keyring apt-transport-https curl gnupg >/dev/null 2>&1 || true
      if curl -1sLf -m 30 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' -o /tmp/caddy-key.asc \
         && gpg --dearmor --yes -o "$CADDY_KEY" /tmp/caddy-key.asc \
         && curl -1sLf -m 30 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' -o "$CADDY_LIST.tmp" \
         && grep -q '^deb ' "$CADDY_LIST.tmp"; then
        mv "$CADDY_LIST.tmp" "$CADDY_LIST"
        note "Caddy's apt repository added"
      else
        rm -f "$CADDY_LIST.tmp" "$CADDY_KEY"
        warn "Caddy's repository (dl.cloudsmith.io) did not answer; using Ubuntu's caddy package instead"
      fi
      rm -f /tmp/caddy-key.asc
      apt-get update -q >/dev/null 2>&1 || true
      apt-get install -y -q caddy || warn "caddy did not install; the dashboard stays on http://$HOSTNAME_WANTED:4147 until it does (re-run the installer)"
    fi
  else
    note "caddy already installed"
  fi
  if ! command -v caddy >/dev/null 2>&1 && [ "$DRY_RUN" = 0 ]; then
    warn "no caddy on this box: HTTPS and the church certificate are skipped for now"
  elif [ -f "$SRC/config/caddy/Caddyfile" ]; then
    if [ -f /etc/caddy/Caddyfile ] && ! grep -q 'Arise Server' /etc/caddy/Caddyfile 2>/dev/null; then
      run cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.before-arise
    fi
    if [ "$STAGING" = 1 ]; then
      # Staging: Caddy answers on this box only, like the domain (nothing at Bradly's house sees it).
      if [ "$DRY_RUN" = 1 ]; then note "[dry-run] write /etc/caddy/Caddyfile = { default_bind 127.0.0.1 } + config/caddy/Caddyfile"
      else { printf '{\n\tdefault_bind 127.0.0.1\n}\n\n'; cat "$SRC/config/caddy/Caddyfile"; } > /etc/caddy/Caddyfile; chmod 0644 /etc/caddy/Caddyfile; fi
    else
      run install -m 0644 "$SRC/config/caddy/Caddyfile" /etc/caddy/Caddyfile
    fi
  else
    warn "config/caddy/Caddyfile missing from the repo; caddy left with its default config"
  fi
  if [ "$NO_START" = 0 ]; then
    run systemctl enable --now caddy || warn "caddy failed to start — journalctl -u caddy"
    if command -v caddy >/dev/null 2>&1 && [ "$DRY_RUN" = 0 ]; then
      systemctl reload caddy >/dev/null 2>&1 || true
    fi
  else
    run systemctl enable caddy || warn "caddy not enabled (not installed?)"
  fi
  note "HTTPS on https://$HOSTNAME_WANTED.ad.arisecenla.com with the church certificate. enroll-mac.sh / bind-mac.sh --dns trust it; by hand: http://$HOSTNAME_WANTED:4147/ca.crt (docs/SECURITY.md)"
  note "DNS records still needed:  sudo samba-tool dns add 127.0.0.1 ad.arisecenla.com vault A ${PRIMARY_IP:-<lan-ip>}   (and remote)"
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
  # cage (a Wayland kiosk compositor) is a plain apt package: no X, no desktop
  # environment. Firefox comes next from packages.mozilla.org (not the snap);
  # Epiphany (GTK WebKit) is the small fallback browser.
  run apt-get install -y -q cage epiphany-browser || warn "cage/epiphany did not install; the monitor shows the text console until they do (re-run with --kiosk)"
  if id -u arise-kiosk >/dev/null 2>&1; then
    note "user arise-kiosk exists"
  else
    run useradd -u 1501 -m -d /var/lib/arise/kiosk-home -s /usr/sbin/nologin -G video,input,render arise-kiosk
  fi
  run mkdir -p /var/lib/arise/kiosk
  run chown -R arise-kiosk: /var/lib/arise/kiosk /var/lib/arise/kiosk-home
  # The browser is Firefox from Mozilla's own apt repository, in the house theme
  # (docs/BROWSER.md). Epiphany stays installed as the fallback the launcher uses
  # if Firefox is ever missing, so the monitor is never blank.
  if [ "$DRY_RUN" = 1 ]; then
    bash "$SRC/scripts/arise-browser-setup" --dry-run --src "$SRC" || warn "Firefox setup (dry run) reported a problem"
  else
    bash "$SRC/scripts/arise-browser-setup" --src "$SRC" || warn "Firefox setup did not finish (above); the monitor uses Epiphany until it does: sudo bash $SRC/scripts/arise-browser-setup"
  fi
  # Claude Desktop (Linux beta), opened from the dashboard by Bradly only (docs/CLAUDE-ON-THE-BOX.md).
  if [ "$WITH_CLAUDE" = 1 ]; then
    if [ "$DRY_RUN" = 1 ]; then
      bash "$SRC/scripts/arise-claude-desktop-setup" --dry-run --src "$SRC" || true
    else
      bash "$SRC/scripts/arise-claude-desktop-setup" --src "$SRC" || warn "Claude Desktop did not install (above); Claude is still in Firefox and the claude command"
    fi
  fi
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

  # 6d-2. The panel's hours and Screen Sharing (round 3, 30 and 17).
  # wlr-randr drives cage's output (off 23:00, on 06:00); wayvnc shares that
  # display to Guacamole only, with a password and TLS, for Bradly alone.
  say "6d-2/7  Closet monitor: off 23:00, on 06:00; Screen Sharing"
  run apt-get install -y -q wlr-randr wayvnc || warn "wlr-randr/wayvnc not installed: the panel will not sleep on schedule and Screen Sharing is off (apt install wlr-randr wayvnc later)"
  for t in arise-monitor-off.timer arise-monitor-on.timer; do
    if [ -f "$UNIT_SRC/$t" ]; then
      if [ "$NO_START" = 0 ]; then run systemctl enable --now "$t" || warn "$t failed to start"; else run systemctl enable "$t"; fi
    fi
  done
  note "the panel sleeps at 23:00 and wakes at 06:00 (arisectl monitor on|off|status); after a scheduled off, a key does not wake it - the 06:00 timer does"
  if [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] arisectl monitor share on   (wayvnc for Guacamole only; a 'Closet monitor' connection for $ADMIN_USER)"
  elif [ "$NO_START" = 0 ] && [ -d "$DATA_ROOT/apps/guacamole" ]; then
    if /usr/local/bin/arisectl monitor share on >>"$LOG_FILE" 2>&1; then
      note "Screen Sharing on: Guacamole → 'Closet monitor', sign in as $ADMIN_USER (password in /etc/arise/secrets/guacamole-$ADMIN_USER, root only)"
    else
      warn "Screen Sharing not set up (see $LOG_FILE); later: sudo arisectl monitor share on"
    fi
  else
    note "Screen Sharing waits for Guacamole: sudo arisectl monitor share on once it is deployed"
  fi
fi

# ----------------------------------------------------------------------------
# 7. Summary — what still needs a human
# ----------------------------------------------------------------------------
# Staging marker, and the relocation refresh.
if [ "$STAGING" = 1 ]; then
  if [ "$DRY_RUN" = 0 ]; then mkdir -p /etc/arise; date -Is > "$STAGING_MARK"; fi
  note "staging marker written: $STAGING_MARK. At the church: sudo bash install.sh (same flags, without --staging)"
elif [ "$RELOCATING" = 1 ] && [ "$DRY_RUN" = 0 ]; then
  rm -f "$STAGING_MARK"
  if command -v samba_dnsupdate >/dev/null 2>&1 && [ "$SKIP_DOMAIN" = 0 ]; then
    systemctl restart samba-ad-dc >/dev/null 2>&1 || true; sleep 4
    samba_dnsupdate --use-samba-tool >/dev/null 2>&1 && note "domain DNS records now carry this box's church address" || warn "samba_dnsupdate failed; run: sudo samba_dnsupdate --use-samba-tool --verbose"
  fi
  note "relocation done: staging marker removed"
fi

# ----------------------------------------------------------------------------
# 6e. Claude Code on the box (Bradly's claude.ai account; no API key)
# ----------------------------------------------------------------------------
if [ "$WITH_CLAUDE" = 1 ]; then
  say "6e/7  Claude Code"
  # Node from NodeSource, not Ubuntu's archive: Ubuntu 24.04 ships Node 18,
  # which Claude Code has already moved past; NodeSource tracks the 20 LTS line
  # and updates with apt like everything else. The setup script only adds a
  # signed apt source; the package itself comes through apt.
  if command -v node >/dev/null 2>&1 && [ "$(node -v | sed 's/^v//' | cut -d. -f1)" -ge 22 ] 2>/dev/null; then
    note "node $(node -v) already present"
  elif [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] curl -fsSL https://deb.nodesource.com/setup_22.x | bash -; apt-get install -y nodejs"
  else
    if curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >>"$LOG_FILE" 2>&1 && apt-get install -y -q nodejs >>"$LOG_FILE" 2>&1; then
      note "node $(node -v) installed from NodeSource"
    else
      warn "NodeSource failed (no internet, or the proxy); trying Ubuntu's nodejs"
      apt-get install -y -q nodejs npm >>"$LOG_FILE" 2>&1 || warn "no Node at all; Claude Code skipped. Later: install Node 22 and 'npm install -g @anthropic-ai/claude-code'"
    fi
  fi
  if command -v npm >/dev/null 2>&1; then
    if [ "$DRY_RUN" = 1 ]; then
      note "[dry-run] npm install -g @anthropic-ai/claude-code"
    elif command -v claude >/dev/null 2>&1; then
      note "claude $(claude --version 2>/dev/null | head -1) already installed; npm update -g @anthropic-ai/claude-code to move it"
    elif npm install -g @anthropic-ai/claude-code >>"$LOG_FILE" 2>&1; then
      note "claude installed: $(claude --version 2>/dev/null | head -1 || echo ok)"
    else
      warn "npm install of @anthropic-ai/claude-code failed (see $LOG_FILE)"
    fi
    # The global npm bin is on root's PATH; make sure bradly's login shell sees it too.
    NPM_BIN="$(npm bin -g 2>/dev/null || npm prefix -g 2>/dev/null | sed 's|$|/bin|')"
    if [ -n "$NPM_BIN" ] && [ "$NPM_BIN" != "/usr/bin" ] && [ "$NPM_BIN" != "/usr/local/bin" ] && [ "$DRY_RUN" = 0 ]; then
      printf 'PATH="%s:$PATH"\n' "$NPM_BIN" > /etc/profile.d/arise-npm.sh
    fi
  fi
  note "sign in later, as bradly: claude   then type /login (opens a claude.ai page on your phone or Mac; paste the code back). Works over SSH and in the dashboard's Terminal."
fi

# ----------------------------------------------------------------------------
# 6f. The care an old PC needs (each line idempotent)
# ----------------------------------------------------------------------------
if [ "$WITH_HARDENING" = 1 ]; then
  say "6f/7  Care: security updates, a year of logs, disk health"
  run apt-get install -y -q --no-install-recommends unattended-upgrades smartmontools needrestart logrotate || warn "some care packages did not install (the mirror?); re-run later"
  if [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] unattended-upgrades: security origin only, Automatic-Reboot false, daily timer on"
    note "[dry-run] journald SystemMaxUse=4G MaxRetentionSec=1year; smartd enabled; needrestart list mode; fstrim.timer on; logrotate for $LOG_DIR/*.log weekly keep 52"
  else
    # Security updates only, applied daily, NEVER a reboot by themselves: a
    # domain controller that reboots at 06:00 on a Sunday is a bad morning.
    cat > /etc/apt/apt.conf.d/52-arise-unattended <<'APT'
// Arise Server: security updates only, no automatic reboot. Kernel updates
// wait for a person (needrestart lists what wants a restart; arisectl doctor says so).
Unattended-Upgrade::Allowed-Origins { "${distro_id}:${distro_codename}-security"; "${distro_id}ESMApps:${distro_codename}-apps-security"; "${distro_id}ESM:${distro_codename}-infra-security"; };
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT
    systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true
    note "unattended-upgrades: security only, daily, no automatic reboot"
    # journald: a year of logs (round 3, 26), capped at 4 GB so a 256 GB disk never fills with them.
    mkdir -p /etc/systemd/journald.conf.d
    printf '[Journal]\nSystemMaxUse=4G\nMaxRetentionSec=1year\nCompress=yes\n' > /etc/systemd/journald.conf.d/arise.conf
    systemctl restart systemd-journald >/dev/null 2>&1 || true
    note "journald: a year kept, 4 GB cap"
    # SMART: the disk says it is dying before it dies. smartd watches; doctor reports.
    if [ -f /etc/smartd.conf ] && ! grep -q '^# arise' /etc/smartd.conf; then
      printf '# arise: scan every disk, email nothing (no mail here), log to journal\nDEVICESCAN -a -o on -S on -n standby,q -W 4,45,55\n' > /etc/smartd.conf
    fi
    systemctl enable --now smartmontools >/dev/null 2>&1 || systemctl enable --now smartd >/dev/null 2>&1 || warn "smartd did not start (a VM, or no SMART-capable disk)"
    note "smartd watching the disks; arisectl doctor shows the SMART verdict"
    # needrestart: never a prompt on this box; it lists, it does not ask.
    mkdir -p /etc/needrestart/conf.d
    printf "# arise: list, never prompt\n\$nrconf{restart} = 'l';\n\$nrconf{kernelhints} = -1;\n" > /etc/needrestart/conf.d/arise.conf
    note "needrestart in list mode"
    systemctl enable --now fstrim.timer >/dev/null 2>&1 && note "fstrim weekly (SSD care)" || true
    cat > /etc/logrotate.d/arise <<LR
$LOG_DIR/*.log {
    weekly
    rotate 52
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
LR
    note "logrotate: $LOG_DIR/*.log weekly, 52 kept (a year)"
  fi
fi

# ----------------------------------------------------------------------------
# 6g. The boot splash: ariseOS boots like a product (answer 1: splash, no sound)
# ----------------------------------------------------------------------------
if [ "$WITH_SPLASH" = 1 ]; then
  say "6g/7  Boot splash: ariseOS"
  THEME_DIR="/usr/share/plymouth/themes/ariseos"
  if [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] apt-get install plymouth plymouth-themes; copy $SRC/config/plymouth/ariseos -> $THEME_DIR; python3 $SRC/scripts/gen-plymouth-art.py $THEME_DIR"
    note "[dry-run] plymouth-set-default-theme -R ariseos; /etc/default/grub.d/60-ariseos.cfg: quiet splash loglevel=3, GRUB_TIMEOUT=1, GRUB_GFXPAYLOAD_LINUX=keep; update-grub"
  else
    apt-get install -y -q --no-install-recommends plymouth plymouth-themes plymouth-label >/dev/null 2>&1 || warn "plymouth did not install; the box boots with text"
    if command -v plymouth-set-default-theme >/dev/null 2>&1; then
      mkdir -p "$THEME_DIR"
      cp "$SRC/config/plymouth/ariseos/ariseos.plymouth" "$SRC/config/plymouth/ariseos/ariseos.script" "$THEME_DIR/"
      python3 "$SRC/scripts/gen-plymouth-art.py" "$THEME_DIR" >/dev/null 2>&1 || warn "could not draw the splash pictures (python3 zlib?)"
      mkdir -p /etc/default/grub.d
      cat > /etc/default/grub.d/60-ariseos.cfg <<GRUB
# ariseOS: a quiet boot with the splash, a one-second menu, the framebuffer kept
# for Plymouth. Delete this file and run update-grub to see the text again.
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash loglevel=3"
GRUB_TIMEOUT=1
GRUB_TIMEOUT_STYLE=hidden
GRUB_GFXPAYLOAD_LINUX=keep
GRUB
      if [ "$(plymouth-set-default-theme 2>/dev/null)" = "ariseos" ]; then
        note "plymouth theme already ariseos"
      else
        plymouth-set-default-theme -R ariseos >/dev/null 2>&1 && note "plymouth theme: ariseos (initramfs rebuilt)" || warn "plymouth-set-default-theme failed; run it by hand: sudo plymouth-set-default-theme -R ariseos"
      fi
      update-grub >/dev/null 2>&1 && note "grub: quiet splash, 1 s menu" || warn "update-grub failed; the splash shows once grub is updated"
    fi
  fi
fi

# ----------------------------------------------------------------------------
# 6h. The UPS: NUT, shutting down cleanly on LOW BATTERY (answer 48: when nearly flat)
# ----------------------------------------------------------------------------
if [ "$WITH_UPS" = 1 ]; then
  say "6h/7  UPS: NUT installed; the driver waits for the model"
  if [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] apt-get install nut; /etc/nut/{nut.conf MODE=none until the model is known, ups.conf [arise] usbhid-ups commented, upsd.users, upsmon.conf MONITOR ... SHUTDOWNCMD}"
  else
    apt-get install -y -q --no-install-recommends nut >/dev/null 2>&1 || warn "nut did not install"
    if [ -d /etc/nut ]; then
      UPS_PW="$(rand_pw 20)"
      [ -f /etc/nut/ups.conf ] && grep -q '^# arise' /etc/nut/ups.conf || cat > /etc/nut/ups.conf <<UPS
# arise: the Pineville UPS. The model is not known yet (docs/ANSWERS.md 8), so
# the stanza is commented. Most USB UPSes (APC, CyberPower, Eaton, Tripp Lite)
# work with usbhid-ups and port = auto. Uncomment, set MODE=standalone in
# nut.conf, then: sudo systemctl restart nut-server nut-monitor; sudo arisectl ups
#[arise]
#  driver = usbhid-ups
#  port = auto
#  desc = "Pineville closet UPS"
UPS
      if ! grep -q '^MODE=standalone' /etc/nut/nut.conf 2>/dev/null; then
        sed -i 's/^MODE=.*/MODE=none/' /etc/nut/nut.conf 2>/dev/null || true
        grep -q '^MODE=' /etc/nut/nut.conf 2>/dev/null || echo "MODE=none" >> /etc/nut/nut.conf
      fi
      if ! grep -q '^\[monuser\]' /etc/nut/upsd.users 2>/dev/null; then
        printf '\n# arise: upsmon login\n[monuser]\n  password = %s\n  upsmon primary\n' "$UPS_PW" >> /etc/nut/upsd.users
        if ! grep -q '^MONITOR arise@localhost' /etc/nut/upsmon.conf 2>/dev/null; then
          printf '\n# arise: shut down cleanly when the UPS says LOW BATTERY (its own threshold); nothing earlier (answer 48)\nMONITOR arise@localhost 1 monuser %s primary\nSHUTDOWNCMD "/sbin/shutdown -h +0"\nPOWERDOWNFLAG /etc/killpower\n' "$UPS_PW" >> /etc/nut/upsmon.conf
        fi
        chmod 640 /etc/nut/upsd.users /etc/nut/upsmon.conf 2>/dev/null || true
      fi
      note "nut: installed, MODE=none until the UPS model is known; then uncomment /etc/nut/ups.conf [arise], MODE=standalone, restart nut-server nut-monitor"
    fi
  fi
fi

# ----------------------------------------------------------------------------
# 6j. The safety basics (round 3): the break-glass admin, ClamAV, Timeshift,
#     the TPM binding for an encrypted disk, the safe card. Each line idempotent.
# ----------------------------------------------------------------------------
if [ "$WITH_SAFETY" = 1 ]; then
  say "6j/7  Safety: arise-rescue, virus scan, system snapshots, encryption"
  run apt-get install -y -q --no-install-recommends clamav clamav-freshclam timeshift || warn "clamav/timeshift did not install (the mirror?); the scan and the snapshots wait until a re-run"
  # --- the break-glass admin (round 3, 21) ---
  # A LOCAL account that signs in on the console or over SSH when the domain
  # itself is down. Never the dashboard: the dashboard checks the domain only.
  # Its password lives in /etc/arise/secrets/rescue-password (root) and on the
  # SAFE card (/etc/arise/SAFE-CARD.txt, printed by `arisectl rescue card`),
  # which goes in the safe, never on the closet door. Every sign-in is pushed.
  set_rescue_pw() {
    RESCUE_PW="$(rand_pw 24)"
    echo "arise-rescue:$RESCUE_PW" | chpasswd
    mkdir -p "$CONF_DIR/secrets"; chmod 0711 "$CONF_DIR/secrets"
    printf '%s\n' "$RESCUE_PW" > "$CONF_DIR/secrets/rescue-password"; chmod 600 "$CONF_DIR/secrets/rescue-password"; unset RESCUE_PW
  }
  if id arise-rescue >/dev/null 2>&1; then
    if [ "$DRY_RUN" = 0 ] && [ ! -s "$CONF_DIR/secrets/rescue-password" ]; then
      # An earlier run made the account but stopped before its password was set: finish it.
      set_rescue_pw
      note "arise-rescue existed without a recorded password; a new one is in $CONF_DIR/secrets/rescue-password"
    else
      note "arise-rescue exists"
    fi
  elif [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] useradd -m -s /bin/bash -G sudo -c 'ariseOS break-glass admin' arise-rescue; a 24-character password into $CONF_DIR/secrets/rescue-password (0600)"
  else
    # No ':' in a comment: it is /etc/passwd's field separator and useradd refuses it (found by the rehearsal).
    useradd -m -s /bin/bash -G sudo -c "ariseOS break-glass admin - console only" arise-rescue
    set_rescue_pw
    note "arise-rescue created; password in $CONF_DIR/secrets/rescue-password (root only) and on the safe card"
  fi
  # --- the weekly virus scan (round 3, 28): Sunday 23:30, quarantine, a report ---
  if [ "$DRY_RUN" = 0 ]; then
    systemctl stop clamav-freshclam >/dev/null 2>&1 || true
    freshclam >>"$LOG_FILE" 2>&1 || warn "freshclam could not fetch signatures yet (no internet?); the timer retries"
    systemctl enable --now clamav-freshclam >/dev/null 2>&1 || true
    mkdir -p /srv/arise/.quarantine; chmod 700 /srv/arise/.quarantine
  else
    note "[dry-run] freshclam; systemctl enable --now clamav-freshclam; mkdir /srv/arise/.quarantine (0700)"
  fi
  if [ -f "$UNIT_SRC/arise-clamscan.timer" ]; then
    run install -m 0644 "$UNIT_SRC/arise-clamscan.service" "$UNIT_SRC/arise-clamscan.timer" /etc/systemd/system/
    run systemctl daemon-reload
    if [ "$NO_START" = 0 ]; then run systemctl enable --now arise-clamscan.timer || warn "arise-clamscan.timer failed to start"; else run systemctl enable arise-clamscan.timer; fi
    note "arise-clamscan.timer: Sunday 23:30, the shares scanned, video skipped, found files to /srv/arise/.quarantine, a push to Bradly"
  fi
  # --- system snapshots before updates (round 3, 23): Timeshift, rsync mode, 5 kept ---
  if [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] write /etc/timeshift/timeshift.json (rsync mode, schedule off, exclude /srv/arise /mnt /var/lib/docker /var/lib/arise /var/log); timeshift --create --comments 'install' --tags O"
  else
    ROOT_UUID="$(findmnt -no UUID / 2>/dev/null || true)"
    mkdir -p /etc/timeshift
    cat > /etc/timeshift/timeshift.json <<TS
{
  "backup_device_uuid" : "$ROOT_UUID",
  "parent_device_uuid" : "",
  "do_first_run" : "false",
  "btrfs_mode" : "false",
  "include_btrfs_home_for_backup" : "false",
  "include_btrfs_home_for_restore" : "false",
  "stop_cron_emails" : "true",
  "schedule_monthly" : "false",
  "schedule_weekly" : "false",
  "schedule_daily" : "false",
  "schedule_hourly" : "false",
  "schedule_boot" : "false",
  "count_monthly" : "2",
  "count_weekly" : "3",
  "count_daily" : "5",
  "count_hourly" : "6",
  "count_boot" : "5",
  "snapshot_size" : "0",
  "snapshot_count" : "0",
  "date_format" : "%Y-%m-%d %H:%M:%S",
  "exclude" : [ "/srv/arise/**", "/mnt/**", "/var/lib/docker/**", "/var/lib/arise/**", "/var/log/**", "/home/*/.cache/**", "/root/.cache/**", "/var/cache/apt/archives/**" ],
  "exclude-apps" : []
}
TS
    if command -v timeshift >/dev/null 2>&1 && [ "$NO_START" = 0 ]; then
      timeshift --create --comments "install $(date +%F)" --tags O --scripted >>"$LOG_FILE" 2>&1 && note "first system snapshot taken (timeshift, rsync mode; church files excluded, they are in the backup)" || warn "timeshift could not take the first snapshot (see $LOG_FILE); arisectl snapshot create to retry"
    fi
  fi
  # --- encryption: bind the LUKS disk to the TPM so the box boots alone (round 3, 22) ---
  LUKS_DEV="$(lsblk -rno NAME,FSTYPE 2>/dev/null | awk '$2=="crypto_LUKS"{print "/dev/"$1; exit}' || true)"
  if [ -z "$LUKS_DEV" ]; then
    warn "the disk is NOT encrypted (no LUKS volume). Bradly chose encryption (round 3, 22); it is picked in the Ubuntu installer, not later. docs/SECURITY.md"
  elif [ "$WITH_TPM" = 0 ]; then
    note "LUKS on $LUKS_DEV; --no-tpm: the passphrase is typed at every boot"
  elif [ ! -e /dev/tpmrm0 ] && [ ! -e /dev/tpm0 ] && [ "$DRY_RUN" = 0 ]; then
    warn "LUKS on $LUKS_DEV but no TPM 2.0 found: enable it in the Dell's BIOS (Security > TPM 2.0 / PTT), then: sudo arisectl encrypt tpm. Until then the passphrase is typed at every boot."
  else
    run apt-get install -y -q --no-install-recommends clevis clevis-luks clevis-tpm2 clevis-initramfs tpm2-tools || warn "clevis did not install; the disk still asks for its passphrase at boot until a re-run"
    if [ "$DRY_RUN" = 1 ]; then
      note "[dry-run] clevis luks bind -d $LUKS_DEV tpm2 '{\"pcr_bank\":\"sha256\",\"pcr_ids\":\"7\"}' (asks the disk passphrase once); update-initramfs -u"
    elif clevis luks list -d "$LUKS_DEV" 2>/dev/null | grep -q tpm2; then
      note "$LUKS_DEV is already bound to the TPM"
    else
      echo
      echo "    The disk is encrypted. To let the TPM unlock it at boot, clevis needs the"
      echo "    disk passphrase ONCE now (it is not stored). Leave empty to skip; later: sudo arisectl encrypt tpm"
      read -r -s -p "    Disk passphrase: " LUKS_PW; echo
      if [ -n "$LUKS_PW" ]; then
        if printf '%s' "$LUKS_PW" | clevis luks bind -d "$LUKS_DEV" -k - tpm2 '{"pcr_bank":"sha256","pcr_ids":"7"}' >>"$LOG_FILE" 2>&1 && update-initramfs -u >>"$LOG_FILE" 2>&1; then
          note "$LUKS_DEV bound to the TPM (PCR 7): the box boots alone; the passphrase on the safe card still works"
        else
          warn "clevis bind failed (see $LOG_FILE); the passphrase is typed at boot until: sudo arisectl encrypt tpm"
        fi
      else
        note "skipped; the passphrase is typed at every boot until: sudo arisectl encrypt tpm"
      fi
      unset LUKS_PW
    fi
  fi
  # --- the safe card: the two things that must never be on the closet door ---
  if [ "$DRY_RUN" = 1 ]; then
    note "[dry-run] write $CONF_DIR/SAFE-CARD.txt (0600): the arise-rescue password and the disk passphrase line to fill in by hand (the restic password goes on the closet card, by hand)"
  else
    {
      echo "ariseOS SAFE CARD  -  Arise Church, Pineville LA  -  printed $(date '+%Y-%m-%d')"
      echo "Root only. The same password is on the closet card taped inside the closet (round 7, 57 and 73) and with Kristina."
      echo
      echo "Break-glass admin (works when the domain is down; at the closet monitor ONLY: never SSH, never the dashboard)"
      echo "  user      arise-rescue"
      echo "  password  $(cat "$CONF_DIR/secrets/rescue-password" 2>/dev/null || echo '(not set: sudo arisectl rescue rotate)')"
      echo "  rotate    sudo arisectl rescue rotate     (every use is logged and pushed to Bradly)"
      echo
      echo "Backups (restic on the Synology)"
      echo "  password  NOT here. Bradly's rule: the restic password lives on the CLOSET card only (written by hand) and in /etc/arise/secrets/restic-password."
      echo "  rebuild   sudo arisectl reinstall /mnt/synology/arise-backups/restic     (docs/REINSTALL.md)"
      echo
      echo "Disk encryption (LUKS)"
      echo "  passphrase  ________________________________   (write it here by hand; the TPM unlocks the disk at boot, this is the fallback)"
      echo "  bound to TPM: $(command -v clevis >/dev/null 2>&1 && [ -n "$LUKS_DEV" ] && clevis luks list -d "$LUKS_DEV" 2>/dev/null | grep -q tpm2 && echo yes || echo no)"
    } > "$CONF_DIR/SAFE-CARD.txt"
    chmod 600 "$CONF_DIR/SAFE-CARD.txt"
    note "SAFE-CARD.txt written (root only); the printed card is the closet card: sudo arisectl rescue card"
  fi
fi

# ----------------------------------------------------------------------------
# 6i. The closet card: one printable page for the closet door (answer 46)
# ----------------------------------------------------------------------------
say "6i/7  The closet card"
CARD_BODY="$(cat <<CARD
<!doctype html><html lang="en"><head><meta charset="utf-8"><title>ariseOS: if the server dies</title>
<style>@page{margin:14mm}body{font-family:Oswald,"Helvetica Neue",Arial,sans-serif;color:#0A0A0C;margin:0;max-width:760px}
.hd{background:#0A0A0C;color:#fff;padding:18px 24px;border-top:6px solid #D6222D}.hd h1{font-family:Anton,Impact,"Arial Black",sans-serif;font-size:30px;margin:0;letter-spacing:.04em;text-transform:uppercase}
.hd p{margin:4px 0 0;font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#bbb}h2{font-size:13px;letter-spacing:.16em;text-transform:uppercase;color:#D6222D;margin:22px 24px 6px;border-bottom:2px solid #D6222D;padding-bottom:4px}
table{border-collapse:collapse;margin:0 24px;width:calc(100% - 48px)}td{padding:6px 0;border-bottom:1px solid #e4e1dd;font-size:14px;vertical-align:top}td:first-child{width:200px;color:#6A6A6E;text-transform:uppercase;letter-spacing:.08em;font-size:11px;padding-top:9px}
code{font-family:Menlo,Consolas,monospace;font-size:13px;background:#F4F2F0;padding:1px 5px}.ft{margin:26px 24px 0;font-size:11px;color:#6A6A6E}</style></head><body>
<div class="hd"><h1>ariseOS: if the server dies</h1><p>Tape this inside the closet. This copy has no passwords: sudo arisectl rescue card writes the one that does.</p></div>
<h2>This box</h2><table><tr><td>Name</td><td>$HOSTNAME_WANTED &nbsp;(<code>$FQDN</code>)</td></tr><tr><td>Address on the wire</td><td><code>${PRIMARY_IP:-see arisectl info}</code> &nbsp;pinned on the box, not on the router</td></tr>
<tr><td>Dashboard</td><td><code>http://$HOSTNAME_WANTED:4147</code> &nbsp;and the desktop on this monitor</td></tr><tr><td>Over Tailscale</td><td><code>http://$HOSTNAME_WANTED:4147</code> from any signed-in laptop, anywhere</td></tr>
<tr><td>Cockpit (second door)</td><td><code>https://$HOSTNAME_WANTED:9090</code> &nbsp;sign in as $ADMIN_USER</td></tr></table>
<h2>Three commands (Alt+F2 for a text login, or SSH)</h2><table><tr><td>What is wrong?</td><td><code>sudo arisectl doctor</code></td></tr><tr><td>Dashboard stuck</td><td><code>sudo systemctl restart arise-web</code> &nbsp;(logins and shares keep working meanwhile)</td></tr><tr><td>Everything stuck</td><td><code>sudo reboot</code> &nbsp;about a minute; the desktop comes back by itself; Macs keep working on cached accounts</td></tr></table>
<h2>Where things are</h2><table><tr><td>Backups</td><td>restic on the Synology: <code>$(grep -E '^restic_repo' "$CONF_DIR/arise.toml" 2>/dev/null | sed 's/.*= *"\(.*\)"/\1/' || echo /mnt/synology/arise-backups/restic)</code> &nbsp;nightly 03:00; restore: <code>sudo arisectl backup restore latest --target /srv/arise/restore</code></td></tr>
<tr><td>Passwords and keys</td><td><code>/etc/arise/secrets/</code> &nbsp;root only: restic, Resend, the apps' generated passwords (<code>apps/</code>). Never on this card.</td></tr>
<tr><td>Domain down?</td><td>The break-glass login <code>arise-rescue</code> works on this monitor (Alt+F2), never over SSH. Its password is on the <b>safe card</b> (in the safe; <code>sudo arisectl rescue card</code> prints it again). Every use is logged.</td></tr>
<tr><td>Backup password (restic)</td><td>Write it here by hand: ______________________________ &nbsp;This card is its only paper copy (Bradly's rule); on the box it is <code>/etc/arise/secrets/restic-password</code>, root only.</td></tr>
<tr><td>Disk encrypted</td><td>The TPM unlocks it at boot. If the box asks for a passphrase, it is on the safe card too. Rebuild from the Synology: <code>sudo arisectl reinstall</code> (docs/REINSTALL.md).</td></tr>
<tr><td>Config</td><td><code>/etc/arise/arise.toml</code> &nbsp;·&nbsp; code <code>/opt/arise</code> &nbsp;·&nbsp; data <code>/srv/arise</code> &nbsp;·&nbsp; logs <code>/var/log/arise</code>, <code>journalctl -u arise-web</code></td></tr>
<tr><td>The docs</td><td><code>/opt/arise/docs/</code>, start with SETUP-GUIDE.md; MOVING-DAY.md for the move to the Hub</td></tr>
<tr><td>Staging marker</td><td>If <code>/etc/arise/staging</code> exists the box thinks it is NOT at the church (domain on loopback, nothing scanned). Fix: <code>sudo bash /opt/arise/installer/install.sh --kiosk</code></td></tr></table>
<h2>Who to call</h2><table><tr><td>Bradly Dyer</td><td>media and IT &nbsp;·&nbsp; phone: ______________________</td></tr><tr><td>Minister Kristina Robinson</td><td>follows this card when Bradly cannot be reached (round 7, 59) &nbsp;·&nbsp; phone: ______________________</td></tr><tr><td>Ronnie</td><td>when neither answers &nbsp;·&nbsp; phone: ______________________</td></tr></table>
<p class="ft">Printed by install.sh on $(date '+%Y-%m-%d'). Nothing on this page changes a router. Arise Church · Pineville, LA.</p></body></html>
CARD
)"
if [ "$DRY_RUN" = 1 ]; then
  note "[dry-run] write $CONF_DIR/CLOSET-CARD.html and $DATA_ROOT/shares/staff/CLOSET-CARD.html (print and tape to the closet door)"
else
  mkdir -p "$CONF_DIR" "$DATA_ROOT/shares/staff"
  # Round 7, 57/73: one card, taped INSIDE the closet, with arise-rescue's password on it, and a
  # copy on the staff share with the password left out. arisectl writes both (and again after a
  # rotate); this page is only the fallback when arisectl cannot run yet.
  if [ -x /usr/local/bin/arisectl ] && /usr/local/bin/arisectl rescue card >>"$LOG_FILE" 2>&1; then
    note "closet card: print $CONF_DIR/CLOSET-CARD.html at the closet monitor (root only: it has arise-rescue's password), tape it INSIDE the closet, give Kristina a copy"
  else
    printf '%s\n' "$CARD_BODY" > "$CONF_DIR/CLOSET-CARD.html"
    printf '%s\n' "$CARD_BODY" > "$DATA_ROOT/shares/staff/CLOSET-CARD.html"
    chmod 600 "$CONF_DIR/CLOSET-CARD.html"; chmod 644 "$DATA_ROOT/shares/staff/CLOSET-CARD.html"
    warn "closet card written without the password (arisectl rescue card failed): run it again once the box is up"
  fi
fi

say "7/7  Done. What still needs you"
AUTOMATOR_DIR="$DATA_ROOT/automator/ARISE_YouTube_Updater"
cat <<SUMMARY

    Dashboard      http://$HOSTNAME_WANTED:$WEB_PORT   (or http://${PRIMARY_IP:-<lan-ip>}:$WEB_PORT)
    Domain         $REALM   NetBIOS $NETBIOS   admin: Administrator
    Code           $INSTALL_ROOT        Config  $CONF_DIR/arise.toml
    Data           $DATA_ROOT          Log     $LOG_FILE

    Still needs a human — in this order:

    1. Dashboard password:        sudo arisectl admin set-password
    2. The YouTube automator (docs/AUTOMATOR.md; the PC stays the runner until you switch runner.json there):
       a. GitHub: add the deploy key printed above to Rehchu/arise-youtube-automation, READ-ONLY;
          then: sudo arisectl automator setup
       b. Cloud Console (project iconic-vine-505702-i5): OAuth consent screen -> Audience -> Publish app;
          Credentials -> Create OAuth client ID -> Desktop app, named "ariseOS server"; download the JSON
       c. scp it to /etc/arise/secrets/youtube/client_secret.json; chown it to your account; chmod 600
       d. sudo arisectl automator signin        (once; paste the localhost address back)
       e. sudo arisectl automator cutover       (what is left before you hand the job over)
    3. restic password:           openssl rand -base64 32 | sudo tee $CONF_DIR/secrets/restic-password >/dev/null
                                  sudo chmod 0600 $CONF_DIR/secrets/restic-password
       KEEP A COPY OF THAT PASSWORD OFF THE SERVER. Without it the backups cannot be read.
    4. Synology credentials:      sudo nano $CONF_DIR/secrets/synology.cred   (username=… / password=… / domain=$NETBIOS)
                                  sudo chmod 0600 $CONF_DIR/secrets/synology.cred ; sudo arisectl nas mount
    5. Then:                      sudo arisectl doctor
    6. Remote access (docs/REMOTE-ACCESS.md):
       ssh is keys only: no key yet? re-run with --ssh-key 'ssh-ed25519 AAAA…' (cat ~/.ssh/id_ed25519.pub on your Mac)
$( [ "$WITH_TAILSCALE" = 1 ] && echo "       tailscale (needs a browser): sudo tailscale up --ssh --advertise-routes=$LAN_SUBNET" || echo "       VPN not installed yet: re-run with --with-tailscale (recommended) or --with-wireguard" )
$( [ "$WITH_WIREGUARD" = 1 ] && echo "       wireguard: forward UDP 51820 on the router; set [remote] wg_endpoint in $CONF_DIR/arise.toml; add devices from the Remote app" )
$( [ "$WITH_CADDY" = 1 ] && echo "       https: every church Mac enrolled from the Macs app trusts the church certificate; by hand: http://$HOSTNAME_WANTED:4147/ca.crt" )
$( [ "$WITH_SAFETY" = 1 ] && echo "    6b. The closet card:            sudo arisectl rescue card   (print $CONF_DIR/CLOSET-CARD.html: it has arise-rescue's password; write the restic password and disk passphrase on it by hand; a copy to Kristina)" )
$( [ "$WITH_SAFETY" = 1 ] && echo "        Encryption check:           sudo arisectl encrypt status   (LUKS + TPM; docs/SECURITY.md if the disk is not encrypted)" )
    7. Apps, up and waiting (passwords in $CONF_DIR/secrets/apps/):
       Cockpit  https://$HOSTNAME_WANTED:9090   Netdata  http://$HOSTNAME_WANTED:19999   Uptime Kuma  http://$HOSTNAME_WANTED:8082
       NetAlertX :20211   Portainer https://:9443   BookStack :8085   Jellyfin :8096   Syncthing :8384
       Vaultwarden :8083  Guacamole :8084/guacamole   Owncast :8087   Icecast :8000
       Trilium (Notes) :8090   Immich (Photos) :2283
       The other templates are deployed and stopped (memory): the Store starts them. arisectl app list
    7b. The church Macs (docs/MACS.md): Macs app -> Enrol a Mac -> paste the one line into Terminal on each church Mac
        (never a personal one). Then, on that Mac, once by hand: System Settings > Privacy & Security >
        Full Disk Access > add /usr/local/arise/helper/arise-mac-helper and /bin/bash (no profile is removed without it).
    7c. Sync (docs/SYNC.md): Nextcloud at https://cloud.ad.arisecenla.com for Desktop, Documents, Downloads, Pictures and Music; the Macs app's
        Convert or Link sets each Mac up; phones: the Nextcloud app and a device password from the Sync app.
    8. Tape the printed closet card INSIDE the closet (never on the door); write the phone numbers on it by hand
    9. The UPS: when the model is known, uncomment [arise] in /etc/nut/ups.conf, MODE=standalone in nut.conf, restart nut-server nut-monitor; sudo arisectl ups
   10. The restore drill runs monthly by itself (arise-drill.timer); try it once now: sudo arisectl backup drill
$( [ "$WITH_CLAUDE" = 1 ] && printf '%s\n' "   11. Claude on the box (your claude.ai account, no API key):" "       as ${OWNER:-your own account}:  claude        then type  /login" "       it prints a claude.ai address: open it on your phone or Mac, sign in, paste the code back." "       Works over SSH and in the dashboard's Terminal app. /opt/arise/CLAUDE.md tells it the house rules." )

$( [ "$SKIP_DOMAIN" = 1 ] && echo "    (domain skipped: no Active Directory on this box; re-run without --skip-domain to provision it)" )
$( [ "$NO_START" = 1 ] && echo "    (--no-start: nothing is running yet;  sudo systemctl start arise-web samba-ad-dc  when ready)" )
$( [ "$DRY_RUN" = 1 ] && echo "    (dry run: NOTHING WAS CHANGED)" )
SUMMARY
echo " Arise Server install — finished $(date '+%Y-%m-%d %H:%M:%S %Z')"

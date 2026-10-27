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
SKIP_DOMAIN=0
SKIP_DOCKER=0
NO_START=0
DRY_RUN=0

usage() { sed -n '2,27p' "$0" | sed 's/^#  \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --admin-pass)  ADMIN_PASS="${2:-}"; shift 2 ;;
    --admin-pass=*) ADMIN_PASS="${1#*=}"; shift ;;
    --skip-domain) SKIP_DOMAIN=1; shift ;;
    --skip-docker) SKIP_DOCKER=1; shift ;;
    --no-start)    NO_START=1; shift ;;
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
echo " flags: admin-pass=$([ -n "$ADMIN_PASS" ] && echo set || echo unset) skip-domain=$SKIP_DOMAIN skip-docker=$SKIP_DOCKER no-start=$NO_START dry-run=$DRY_RUN"
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

$( [ "$SKIP_DOMAIN" = 1 ] && echo "    (domain skipped: no Active Directory on this box; re-run without --skip-domain to provision it)" )
$( [ "$NO_START" = 1 ] && echo "    (--no-start: nothing is running yet;  sudo systemctl start arise-web samba-ad-dc  when ready)" )
$( [ "$DRY_RUN" = 1 ] && echo "    (dry run: NOTHING WAS CHANGED)" )
SUMMARY
echo " Arise Server install — finished $(date '+%Y-%m-%d %H:%M:%S %Z')"

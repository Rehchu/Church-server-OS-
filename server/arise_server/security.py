"""The safety basics (round 3, Oct 28): the break-glass admin, disk encryption
and the TPM, system snapshots before updates, the weekly virus scan, the
church certificate, and the Security app that reads them all.

Every function answers with sample data when the tool behind it is missing,
and says so with "demo": true. Nothing here deletes a church file: the virus
scan moves a found file aside, it never removes it.
"""
from __future__ import annotations

import json
import hashlib
import ipaddress
import os
import re
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from .config import load
from . import maintenance
from .util import now_iso, read_json, run, which, write_json

RESCUE_USER = "arise-rescue"
RESCUE_LOG = "/var/log/arise/rescue.log"
RESCUE_CURSOR = "rescue-cursor"
CADDY_ROOT = "/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt"
QUARANTINE = "/srv/arise/.quarantine"
SCAN_PATHS = ["/srv/arise/homes", "/srv/arise/shares"]
# Video and audio are never carriers worth hours of CPU on a Sunday night; the Trash is already on its way out.
SCAN_SKIP_EXT = ["mp4", "mov", "mkv", "m4v", "avi", "webm", "mp3", "wav", "m4a", "aac", "flac", "aiff", "iso", "img"]
SCAN_SKIP_DIRS = [".Trash", ".quarantine", "Library/Caches", "node_modules"]
SNAPSHOT_KEEP = 5
SNAPSHOT_EXCLUDE = ["/srv/arise/**", "/mnt/**", "/var/lib/docker/**", "/var/lib/arise/**", "/var/log/**", "/home/*/.cache/**", "/root/.cache/**"]
SERVICE_HOURS = 2.5


# ---- never during a service ---------------------------------------------------------
def in_service(now: datetime | None = None, services: list | None = None, hours: float = SERVICE_HOURS) -> dict | None:
    """Pure: the service running right now (from [church] services), or None."""
    from .church import DAYS, info
    now = now or datetime.now()
    for s in services if services is not None else info()["services"]:
        try:
            day = DAYS.index(s["day"])
            hh, mm = [int(x) for x in str(s["time"]).split(":")[:2]]
        except (ValueError, KeyError):
            continue
        for back in (0, 1):  # a Monday 19:00 service still runs at 00:30 Tuesday? no, but keep the window honest across midnight
            d = now - timedelta(days=back)
            if d.weekday() != day:
                continue
            start = d.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if start <= now < start + timedelta(hours=hours):
                return {"name": s["name"], "site": s.get("site", ""), "until": (start + timedelta(hours=hours)).isoformat(timespec="minutes")}
    return None


def _refuse_in_service(what: str) -> dict | None:
    s = in_service()
    if s:
        return {"ok": False, "err": f"not during a service: {s['name']} ({s['site']}) is on until {s['until'][11:16]}. {what} waits."}
    return None


# ---- the break-glass admin -----------------------------------------------------------
_RESCUE_RE = re.compile(r"session opened for user " + re.escape(RESCUE_USER) + r"(?:\(uid=\d+\))?\s+by\s+(?:\S+)?\(uid=\d+\)")
_FROM_RE = re.compile(r"Accepted (?:password|publickey) for " + re.escape(RESCUE_USER) + r" from (\S+) port (\d+)")


def parse_rescue_line(line: str) -> dict | None:
    """Pure: one journal line -> {via, from} when it is arise-rescue signing in, else None.
    sshd logs 'Accepted password for arise-rescue from 10.0.0.5 port 50112'; a console
    login logs 'pam_unix(login:session): session opened for user arise-rescue(uid=1001) by LOGIN(uid=0)'."""
    m = _FROM_RE.search(line)
    if m:
        return {"via": "ssh", "from": m.group(1)}
    m = _RESCUE_RE.search(line)
    if m:
        via = "ssh" if "sshd" in line else "console"
        return {"via": via, "from": "the closet monitor" if via == "console" else "ssh"}
    return None


def rescue_status() -> dict:
    cfg = load()
    if cfg.demo:
        return {"demo": True, "user": RESCUE_USER, "exists": True, "uses": [], "last": None, "note": "never used"}
    exists = False
    try:
        import pwd
        pwd.getpwnam(RESCUE_USER)
        exists = True
    except KeyError:
        pass
    uses = []
    try:
        for line in Path(RESCUE_LOG).read_text(encoding="utf-8").splitlines()[-50:]:
            try:
                uses.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    except OSError:
        pass
    last = uses[-1] if uses else None
    return {"user": RESCUE_USER, "exists": exists, "uses": uses[-10:], "last": last,
            "note": "never used" if not uses else f"last used {last['when']} by {last['via']} from {last['from']}",
            "password_file": "/etc/arise/secrets/rescue-password (root only; a copy on the safe card)", "where": "the closet monitor only (sshd: DenyUsers arise-rescue)"}


def rescue_check() -> list[dict]:
    """Reads the journal since the last cursor for arise-rescue logins; logs and pushes each.
    Called by the watcher thread every minute; safe to call by hand."""
    if load().demo or not which("journalctl"):
        return []
    cur_p = load().state_dir / RESCUE_CURSOR
    cursor = ""
    try:
        cursor = cur_p.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    args = ["journalctl", "-o", "short-iso", "--no-pager", "--show-cursor", "-g", RESCUE_USER]
    args += ["--after-cursor", cursor] if cursor else ["--since", "-10min"]
    r = run(args, timeout=30)
    found = []
    new_cursor = ""
    for line in r["out"].splitlines():
        if line.startswith("-- cursor:"):
            new_cursor = line.split(":", 1)[1].strip()
            continue
        hit = parse_rescue_line(line)
        if hit:
            row = {"when": line[:19], **hit, "line": line[-160:]}
            found.append(row)
    if new_cursor:
        try:
            cur_p.parent.mkdir(parents=True, exist_ok=True)
            cur_p.write_text(new_cursor, encoding="utf-8")
        except OSError:
            pass
    if found:
        try:
            os.makedirs(os.path.dirname(RESCUE_LOG), exist_ok=True)
            with open(RESCUE_LOG, "a", encoding="utf-8") as f:
                for row in found:
                    f.write(json.dumps(row) + "\n")
        except OSError:
            pass
        from . import push
        last = found[-1]
        push.send("arise-rescue signed in", f"{RESCUE_USER} signed in by {last['via']} from {last['from']} at {last['when']}. If that was not you, change its password: sudo arisectl rescue rotate", "/#security", tag="rescue", throttle_s=60)
    return found


def rescue_watch(every_s: int = 60):
    def loop():
        time.sleep(45)
        while True:
            try:
                rescue_check()
            except Exception:
                pass
            time.sleep(every_s)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


def rescue_rotate() -> dict:
    """A new 24-character password for arise-rescue, written to the secrets file only."""
    import secrets
    import string
    if load().demo:
        return {"ok": True, "demo": True, "out": "(sample) rotated; on the card"}
    if not which("chpasswd"):
        return {"ok": False, "err": "chpasswd is not installed; nothing was changed"}
    alphabet = string.ascii_letters + string.digits
    pw = "".join(secrets.choice(alphabet) for _ in range(24))
    r = run(["chpasswd"], timeout=10, input_text=f"{RESCUE_USER}:{pw}\n")
    if not r["ok"]:
        return {"ok": False, "err": (r["err"] or r["out"]).strip() or "chpasswd failed (does the user exist? install.sh step 6j makes it)"}
    p = Path("/etc/arise/secrets/rescue-password")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(pw + "\n", encoding="utf-8")
        os.chmod(p, 0o600)
    except OSError as e:
        return {"ok": False, "err": f"password set but could not write {p}: {e}"}
    return {"ok": True, "out": "rotated; the new password is in /etc/arise/secrets/rescue-password. Print the safe card again: sudo arisectl rescue card"}


# ---- encryption and the TPM ----------------------------------------------------------
def parse_lsblk(doc: dict | str) -> dict:
    """Pure: lsblk -J output -> {luks: [devices], root_encrypted: bool, root_device}."""
    if isinstance(doc, str):
        try:
            doc = json.loads(doc)
        except json.JSONDecodeError:
            doc = {}
    luks, root_enc, root_dev, root_luks = [], False, None, []

    def walk(nodes, parent_luks=False, ancestors=()):
        nonlocal root_enc, root_dev, root_luks
        for n in nodes or []:
            is_luks = (n.get("fstype") == "crypto_LUKS")
            if is_luks:
                dev = "/dev/" + n["name"] if not str(n.get("name", "")).startswith("/") else n["name"]
                if dev not in luks:
                    luks.append(dev)
            chain = (*ancestors, dev) if is_luks else ancestors
            mps = [n.get("mountpoint")] + list(n.get("mountpoints") or [])
            if "/" in mps:
                root_dev = n.get("name")
                root_enc = parent_luks or n.get("type") == "crypt"
                root_luks = list(chain)
            walk(n.get("children"), parent_luks or is_luks or n.get("type") == "crypt", chain)
    walk(doc.get("blockdevices"))
    return {"luks": luks, "root_encrypted": root_enc, "root_device": root_dev, "root_luks": root_luks}


def encrypt_status() -> dict:
    if load().demo:
        return {"demo": True, "known": True, "luks": ["/dev/sda3"], "root_luks": ["/dev/sda3"],
                "root_encrypted": True, "tpm": False, "tpm_version": 1, "tpm_bound": False,
                "needs_passphrase": True, "ssh_unlock": False, "clevis": False,
                "note": "the disk is encrypted; type the passphrase at the closet keyboard at each boot"}
    unknown = {"known": False, "luks": [], "root_encrypted": False, "tpm": False,
               "tpm_bound": False, "clevis": False, "needs_passphrase": True, "ssh_unlock": False,
               "note": "disk encryption could not be checked; automatic restart is blocked"}
    if not which("lsblk"):
        return unknown
    r = run(["lsblk", "-J", "-o", "NAME,TYPE,FSTYPE,MOUNTPOINT"], timeout=10)
    if not r["ok"]:
        return unknown
    try:
        st = parse_lsblk(r["out"])
    except (KeyError, TypeError, AttributeError):
        return unknown
    if not st["root_device"]:
        return unknown
    st["known"] = True
    st["tpm_version"] = tpm_version()
    st["tpm"] = st["tpm_version"] == 2   # clevis-tpm2 needs a 2.0 chip; the EliteDesk 800 G1's is 1.2 (Oct 30, H6)
    st["clevis"] = bool(which("clevis"))
    bound_devices = []
    if st["clevis"] and st["tpm"]:
        for dev in st["luks"]:
            l = run(["clevis", "luks", "list", "-d", dev], timeout=15)
            if l["ok"] and re.search(r'^\s*\d+:\s+tpm2\s+', l["out"], re.M):
                bound_devices.append(dev)
    st["tpm_bound_devices"] = bound_devices
    # A binding on a different disk must never authorize a reboot of an unbound root.
    bound = bool(st["luks"]) and set(st["luks"]) <= set(bound_devices)
    st["tpm_bound"] = bound
    st["needs_passphrase"] = (bool(st["luks"]) and not bound) or (st["root_encrypted"] and not st["root_luks"])
    st["ssh_unlock"] = ssh_unlock_ready()
    if not st["luks"]:
        st["note"] = "no LUKS volume: the disk is not encrypted (pick 'Encrypt the new installation' in the Ubuntu installer; docs/SECURITY.md)"
    elif not st["tpm"]:
        st["note"] = ("encrypted, no TPM 2.0 (Bradly, Oct 30: the passphrase at boot): type it at the closet keyboard, "
                      + ("or over early-boot SSH at the server's LAN boot address" if st["ssh_unlock"] else "or opt in to early-boot SSH (docs/SECURITY.md)"))
    elif not bound:
        st["note"] = "encrypted and a TPM is present, but not bound yet: sudo arisectl encrypt tpm"
    else:
        st["note"] = "encrypted; the TPM unlocks it at boot; the passphrase on the safe card is the fallback"
    return st


@maintenance.guarded("TPM boot setup")
def encrypt_tpm(passphrase: str | None = None) -> dict:
    """Bind the LUKS volume to the TPM with clevis so the box boots alone."""
    if load().demo:
        return {"ok": True, "demo": True}
    st = encrypt_status()
    if not st["luks"]:
        return {"ok": False, "err": "no LUKS volume on this box; nothing to bind"}
    if not st["tpm"]:
        return {"ok": False, "err": ("this TPM is version 1.2, which clevis can't use" if st.get("tpm_version") == 1 else "no TPM 2.0 found")
                + ". The passphrase is typed at boot instead (Oct 30, H3); sudo arisectl encrypt ssh lets you type it from a church computer"}
    if not which("clevis"):
        return {"ok": False, "err": "clevis missing: apt install clevis clevis-luks clevis-tpm2 clevis-initramfs tpm2-tools"}
    if st["tpm_bound"]:
        return {"ok": True, "out": "already bound"}
    root_luks = st.get("root_luks", [])
    if len(root_luks) != 1:
        return {"ok": False, "err": "cannot identify one LUKS device containing the root filesystem; bind it manually after checking the storage layout"}
    dev = root_luks[0]
    if dev in st.get("tpm_bound_devices", []):
        return {"ok": True, "out": "root is already bound; other encrypted volumes may still need a passphrase"}
    cmd = ["clevis", "luks", "bind", "-d", dev, "tpm2", '{"pcr_bank":"sha256","pcr_ids":"7"}']
    if passphrase:
        r = run(cmd + ["-k", "-"], timeout=120, input_text=passphrase)
    else:
        r = run(cmd, timeout=120)
    if not r["ok"]:
        return {"ok": False, "err": (r["err"] or r["out"]).strip()[-400:]}
    u = run(["update-initramfs", "-u"], timeout=600)
    if not u["ok"]:
        return {"ok": False, "err": "bound, but update-initramfs failed: " + (u["err"] or u["out"]).strip()[-300:]}
    return {"ok": True, "out": f"{dev} is bound to the TPM (PCR 7). Test a supervised boot; other encrypted volumes may still need a passphrase. The safe-card passphrase still works."}


# ---- no TPM 2.0: the passphrase at boot, typed at the closet or over SSH (Bradly, Oct 30) ----
DROPBEAR_DIR = "/etc/dropbear/initramfs"          # Ubuntu 22.04+ (dropbear-initramfs)
UNLOCK_PORT = 2222                                # the early-boot SSH only; the real sshd stays on 22
UNLOCK_OPTS = 'no-port-forwarding,no-agent-forwarding,no-X11-forwarding,command="/usr/bin/cryptroot-unlock"'
DROPBEAR_HOOK = "/usr/share/initramfs-tools/hooks/dropbear"
CRYPTROOT_HOOK = "/usr/share/initramfs-tools/hooks/cryptroot"
UNLOCK_NETWORK = "/etc/initramfs-tools/conf.d/arise-unlock"
UNLOCK_BOOT = "/boot"


def tpm_version(sysfs: str = "/sys/class/tpm") -> int:
    """0 (none), 1 (TPM 1.2) or 2. /dev/tpm0 alone also exists for a 1.2 chip, which clevis can't use."""
    try:
        with open(os.path.join(sysfs, "tpm0", "tpm_version_major"), encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except (OSError, ValueError):
        pass
    if os.path.exists("/dev/tpmrm0"):
        return 2
    return 1 if os.path.exists("/dev/tpm0") else 0


def unlock_keys(authorized_keys: str) -> list[str]:
    """Validate bare public keys, then restrict each to the unlock command.

    Never strip an existing from=/command=/expiry restriction: doing so could grant
    a formerly restricted key new access. Use an explicitly chosen .pub file instead.
    Ubuntu 24.04 Dropbear supports RSA, ECDSA and Ed25519, but not FIDO sk-* keys.
    """
    from cryptography.exceptions import UnsupportedAlgorithm
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    out = []
    for number, line in enumerate(authorized_keys.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not re.fullmatch(r'(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(?:256|384|521)) +[A-Za-z0-9+/]+={0,2}(?: +[^\x00-\x1f\x7f]*)?', line):
            raise ValueError(f"line {number}: use a bare RSA, ECDSA or Ed25519 public key; options, certificates and FIDO keys are not accepted")
        try:
            key = serialization.load_ssh_public_key(line.encode("utf-8"))
        except (ValueError, UnsupportedAlgorithm) as exc:
            raise ValueError(f"line {number}: malformed SSH public key") from exc
        if isinstance(key, rsa.RSAPublicKey) and key.key_size < 2048:
            raise ValueError(f"line {number}: RSA keys must have at least 2048 bits")
        canonical = key.public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode("ascii")
        entry = f"{UNLOCK_OPTS} {canonical}"
        if entry not in out:
            out.append(entry)
    return out


def unlock_network(value: str) -> str:
    """Accept explicit DHCP or a conservative IPv4 kernel ip= specification."""
    if value == "dhcp":
        return value
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,14}:dhcp", value):
        return ":::::" + value
    fields = value.split(":")
    if len(fields) == 7:
        addr, server, gateway, mask, host, device, mode = fields
        try:
            ipaddress.IPv4Address(addr)
            for ip in (server, gateway):
                if ip:
                    ipaddress.IPv4Address(ip)
            ipaddress.IPv4Network("0.0.0.0/" + mask)
            if (mode == "none" and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,14}", device)
                    and (not host or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,62}", host))):
                return value
        except ValueError:
            pass
    raise ValueError("set --network dhcp, INTERFACE:dhcp, or IPv4:server:gateway:netmask:hostname:interface:none")


def _unlock_files() -> list[Path]:
    return [Path(DROPBEAR_DIR) / "authorized_keys", Path(DROPBEAR_DIR) / "dropbear.conf", Path(UNLOCK_NETWORK)]


def _unlock_manifest() -> dict:
    images = sorted(Path(UNLOCK_BOOT).glob("initrd.img-*"))
    if not images:
        raise OSError("no boot initramfs images found")
    host_keys = [p for p in Path(DROPBEAR_DIR).glob("dropbear_*_host_key") if p.is_file()]
    if not host_keys:
        raise OSError("no Dropbear host keys found")
    return {"files": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [*_unlock_files(), *host_keys]},
            "images": {str(p): [p.stat().st_size, p.stat().st_mtime_ns] for p in images}}


def ssh_unlock_ready() -> bool:
    """Configured into the current boot images, not proof of network reachability."""
    try:
        if not all(Path(p).is_file() for p in (DROPBEAR_HOOK, CRYPTROOT_HOOK)):
            return False
        manifest = read_json(load().state_dir / "ssh-unlock-ready.json", {})
        return bool(manifest) and manifest == _unlock_manifest()
    except (OSError, ValueError, TypeError):
        return False


@maintenance.guarded("early-boot SSH setup")
def encrypt_ssh(user: str = "", *, network: str = "", authorized_keys: str = "") -> dict:
    """Let the passphrase be typed over SSH while the box waits at boot (dropbear in the initramfs).
    Explicitly enables early-boot networking. The main OS firewall and Tailscale
    are unavailable here: the connected LAN and its router define reachability.
    """
    if load().demo:
        return {"ok": True, "demo": True, "out": f"(sample) early-boot SSH on port {UNLOCK_PORT}"}
    try:
        network = unlock_network(network)
    except ValueError as exc:
        return {"ok": False, "err": str(exc)}
    st = encrypt_status()
    if not st.get("root_encrypted") or not st.get("known"):
        return {"ok": False, "err": "cannot verify a LUKS-encrypted root filesystem; no boot configuration was changed"}
    user = user or str(load().owner.user or "") or "bradly"
    src = authorized_keys or os.path.join(os.path.expanduser(f"~{user}"), ".ssh", "authorized_keys")
    try:
        with open(src, encoding="utf-8") as f:
            keys = unlock_keys(f.read())
    except (OSError, ValueError) as exc:
        return {"ok": False, "err": f"could not use SSH keys from {src}: {exc}. Choose a bare public key using --authorized-keys FILE"}
    if not keys:
        return {"ok": False, "err": f"no SSH key in {src}; copy the owner's public .pub key to the server, then use --authorized-keys FILE. The closet keyboard works meanwhile"}
    if not which("dropbear") or not Path(DROPBEAR_HOOK).is_file() or not Path(CRYPTROOT_HOOK).is_file():
        r = run(["apt-get", "install", "-y", "-q", "dropbear-initramfs", "cryptsetup-initramfs"], timeout=600)
        if not r["ok"]:
            return {"ok": False, "err": "dropbear-initramfs did not install: " + (r["err"] or r["out"]).strip()[-300:]}
    if not all(Path(p).is_file() for p in (DROPBEAR_HOOK, CRYPTROOT_HOOK)) or not which("update-initramfs") or not which("lsinitramfs"):
        return {"ok": False, "err": "required initramfs hooks/tools are still missing; no unlock keys were installed"}
    marker = load().state_dir / "ssh-unlock-ready.json"
    try:
        marker.unlink(missing_ok=True)
        contents = ["# ariseOS: command-only early-boot public keys\n" + "\n".join(keys) + "\n",
                    f'DROPBEAR_OPTIONS="-p {UNLOCK_PORT} -s -j -k -I 300"\n',
                    f"# ariseOS: explicit early-boot network, independent of netplan/Tailscale\nIP={network}\n"]
        for dest, content in zip(_unlock_files(), contents):
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                # Preserve custom configuration for the operator before taking ownership.
                backup = dest.with_name(dest.name + ".before-arise")
                if not backup.exists():
                    shutil.copy2(dest, backup)
            dest.write_text(content, encoding="utf-8")
            dest.chmod(0o600)
        u = run(["update-initramfs", "-u", "-k", "all"], timeout=600)
        if not u["ok"]:
            return {"ok": False, "err": "boot configuration written, but update-initramfs failed; use the closet keyboard. " + (u["err"] or u["out"]).strip()[-300:]}
        manifest = _unlock_manifest()
        for image in manifest["images"]:
            listing = run(["lsinitramfs", image], timeout=60)
            files = {p.removeprefix("./") for p in listing.get("out", "").splitlines()}
            # Noble uses a randomized root-XXXXXXXXXX home in the initramfs.
            has_keys = any(re.fullmatch(r"root(?:-[A-Za-z0-9]{10})?/.ssh/authorized_keys", p) for p in files)
            has_hostkey = any(re.fullmatch(r"etc/dropbear/dropbear_(?:rsa|ecdsa|ed25519)_host_key", p) for p in files)
            if not listing["ok"] or not any(p in files for p in ("usr/bin/cryptroot-unlock", "bin/cryptroot-unlock")) or "usr/sbin/dropbear" not in files or not has_keys or not has_hostkey:
                return {"ok": False, "err": f"unlock program, server or keys missing from {image}; use the closet keyboard"}
        write_json(marker, manifest)
    except OSError as exc:
        return {"ok": False, "err": f"early-boot SSH setup incomplete: {exc}; use the closet keyboard"}
    return {"ok": True, "out": f"{len(keys)} command-only key(s) installed into the boot images. Test ssh -p {UNLOCK_PORT} root@<boot-LAN-IP> with someone at the closet keyboard. "
            "Verify the separate Dropbear host-key fingerprint there first. Tailscale, the OS firewall and server DNS do not run before disk unlock; use a trusted LAN, with no router port forwarding. No supervised boot test has been performed."}


# ---- system snapshots (Timeshift) ------------------------------------------------------
def parse_timeshift_list(out: str) -> list[dict]:
    """Pure: `timeshift --list` -> [{num, name, tags, note}] newest last.
    Rows look like:  0    >  2026-10-28_03-30-01  O     before update"""
    rows = []
    for line in out.splitlines():
        m = re.match(r"^\s*(\d+)\s+>?\s+(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\s+([A-Z ]*?)\s*(?:\s{2,}(.*))?$", line)
        if m:
            rows.append({"num": int(m.group(1)), "name": m.group(2), "tags": m.group(3).strip(), "note": (m.group(4) or "").strip()})
    return rows


def _sample_snapshots() -> list[dict]:
    return [{"num": 0, "name": "2026-10-25_03-30-02", "tags": "O", "note": "before update"}, {"num": 1, "name": "2026-10-28_03-30-01", "tags": "O", "note": "before update"}]


def snapshot_list() -> dict:
    if not load().demo and not which("timeshift"):
        return {"demo": False, "snapshots": [], "error": "timeshift is not installed (install.sh step 6j installs it)"}
    if load().demo:
        from . import demo_state
        return {"demo": True, "snapshots": demo_state.get("snapshots", _sample_snapshots)[-SNAPSHOT_KEEP:], "keep": SNAPSHOT_KEEP, "note": "sample: timeshift not installed here"}
    r = run(["timeshift", "--list"], timeout=60)
    return {"snapshots": parse_timeshift_list(r["out"]), "keep": SNAPSHOT_KEEP, "error": None if r["ok"] else (r["err"] or r["out"]).strip()[-300:]}


def snapshot_create(note: str = "") -> dict:
    """A system snapshot (rsync mode) before an update; the last five kept. Refused during a service."""
    bad = _refuse_in_service("The snapshot")
    if bad:
        return bad
    if load().demo:
        from . import demo_state
        name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        demo_state.get("snapshots", _sample_snapshots).append({"num": len(demo_state.get("snapshots", _sample_snapshots)), "name": name, "tags": "O", "note": note or "arisectl snapshot"})
        return {"ok": True, "demo": True, "name": name}
    if not which("timeshift"):
        return {"ok": False, "err": "timeshift is not installed (install.sh step 6j installs it); no snapshot was taken"}
    note = (note or "arisectl snapshot")[:80]
    r = run(["timeshift", "--create", "--comments", note, "--tags", "O", "--scripted"], timeout=3600)
    if not r["ok"]:
        return {"ok": False, "err": (r["err"] or r["out"]).strip()[-400:]}
    pruned = snapshot_prune()
    rows = parse_timeshift_list(run(["timeshift", "--list"], timeout=60)["out"])
    return {"ok": True, "name": rows[-1]["name"] if rows else "", "pruned": pruned.get("removed", []), "out": r["out"][-300:]}


def snapshot_prune(keep: int = SNAPSHOT_KEEP) -> dict:
    if load().demo:
        return {"ok": True, "demo": True, "removed": []}
    if not which("timeshift"):
        return {"ok": False, "err": "timeshift is not installed"}
    rows = [x for x in parse_timeshift_list(run(["timeshift", "--list"], timeout=60)["out"]) if "O" in x["tags"]]
    removed = []
    for x in rows[:-keep] if len(rows) > keep else []:
        d = run(["timeshift", "--delete", "--snapshot", x["name"], "--scripted"], timeout=600)
        if d["ok"]:
            removed.append(x["name"])
    return {"ok": True, "removed": removed}


def snapshot_restore(name: str) -> dict:
    bad = _refuse_in_service("The restore")
    if bad:
        return bad
    if load().demo:
        return {"ok": True, "demo": True, "out": f"(sample) would roll the system back to {name}"}
    if not which("timeshift"):
        return {"ok": False, "err": "timeshift is not installed; nothing to restore from"}
    if not re.match(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$", name or ""):
        return {"ok": False, "err": "give the snapshot's name as listed, e.g. 2026-10-28_03-30-01"}
    r = run(["timeshift", "--restore", "--snapshot", name, "--scripted", "--yes"], timeout=3600)
    return {"ok": r["ok"], "out": r["out"][-600:], "err": None if r["ok"] else (r["err"] or r["out"]).strip()[-400:]}


# ---- the weekly virus scan (ClamAV) ----------------------------------------------------
def parse_clamscan(out: str) -> dict:
    """Pure: clamscan output -> {scanned, infected, found: [{file, sig}], seconds}."""
    found = []
    scanned = infected = 0
    seconds = None
    for line in out.splitlines():
        m = re.match(r"^(.*?): (\S.*) FOUND$", line)
        if m:
            found.append({"file": m.group(1), "sig": m.group(2)})
            continue
        m = re.match(r"^Scanned files:\s*(\d+)", line)
        if m:
            scanned = int(m.group(1))
        m = re.match(r"^Infected files:\s*(\d+)", line)
        if m:
            infected = int(m.group(1))
        m = re.match(r"^Time:\s*([\d.]+) sec", line)
        if m:
            seconds = float(m.group(1))
    return {"scanned": scanned, "infected": infected or len(found), "found": found, "seconds": seconds}


def scan_args(paths: list[str] | None = None, quarantine: str | None = None) -> list[str]:
    """Pure: the clamscan command line (video and audio skipped, the Trash skipped, found files moved aside)."""
    args = ["clamscan", "-r", "-i", "--no-summary=no", "--max-filesize=200M", "--max-scansize=400M"]
    for d in SCAN_SKIP_DIRS:
        args.append(f"--exclude-dir={re.escape(d)}")
    args.append(r"--exclude=\.(" + "|".join(SCAN_SKIP_EXT) + r")$")
    if quarantine:
        args.append(f"--move={quarantine}")
    return args + list(paths or SCAN_PATHS)


def _reports_dir() -> Path:
    return Path("/var/log/arise")


def _sample_scan() -> dict:
    from . import demo_state
    return demo_state.get("scan", lambda: {"last": {"when": "2026-10-26T23:31", "scanned": 18420, "infected": 1, "found": [{"file": "/srv/arise/shares/staff/USB import/invoice.pdf.exe", "sig": "Win.Trojan.Agent-1234 (sample)", "moved_to": QUARANTINE + "/2026-10-26/invoice.pdf.exe"}], "seconds": 1912.4, "ok": True},
                                           "quarantined": [{"batch": "2026-10-26", "file": "/srv/arise/shares/staff/USB import/invoice.pdf.exe", "sig": "Win.Trojan.Agent-1234 (sample)", "moved_to": QUARANTINE + "/2026-10-26/invoice.pdf.exe"}]})


def scan_status() -> dict:
    if load().demo:
        st = _sample_scan()
        return {"demo": True, "last": st["last"], "next": "Sunday 23:30", "quarantine": QUARANTINE, "installed": True, "quarantined": st["quarantined"]}
    reports = sorted(_reports_dir().glob("clamscan-*.json"))
    last = read_json(reports[-1], default=None) if reports else None
    q = []
    try:
        for d in sorted(Path(QUARANTINE).iterdir()):
            man = read_json(d / "manifest.json", default=None)
            for row in (man or {}).get("found", []):
                q.append({"batch": d.name, **row})
    except OSError:
        pass
    return {"last": last, "next": "Sunday 23:30", "quarantine": QUARANTINE, "installed": bool(which("clamscan")), "quarantined": q,
            "note": None if which("clamscan") else "clamav is not installed (install.sh step 6j)"}


def scan_run() -> dict:
    """The weekly scan: Sunday 23:30 by arise-clamscan.timer, or `arisectl scan run`."""
    bad = _refuse_in_service("The virus scan")
    if bad:
        return bad
    if load().demo:
        from . import demo_state
        st = _sample_scan()
        st["last"] = {"when": now_iso()[:16], "scanned": 18431, "infected": 0, "found": [], "seconds": 1890.0, "ok": True}
        return {"ok": True, "demo": True, **st["last"]}
    if not which("clamscan"):
        return {"ok": False, "err": "clamav is not installed (install.sh step 6j); nothing was scanned"}
    stamp = datetime.now().strftime("%Y-%m-%d")
    qdir = Path(QUARANTINE) / stamp
    qdir.mkdir(parents=True, exist_ok=True)
    os.chmod(QUARANTINE, 0o700)
    paths = [p for p in SCAN_PATHS if os.path.isdir(p)]
    if not paths:
        return {"ok": False, "err": "nothing to scan: neither /srv/arise/homes nor /srv/arise/shares exists"}
    r = run(scan_args(paths, str(qdir)), timeout=8 * 3600)
    rep = parse_clamscan(r["out"])
    # clamscan exits 1 when something was found, 2 on an error; both carry output
    rep.update({"when": now_iso(), "ok": r["code"] in (0, 1), "error": None if r["code"] in (0, 1) else (r["err"] or r["out"]).strip()[-400:], "paths": paths, "quarantine": str(qdir)})
    for row in rep["found"]:
        row["moved_to"] = str(qdir / os.path.basename(row["file"]))
    write_json(_reports_dir() / f"clamscan-{stamp}.json", rep)
    if rep["found"]:
        write_json(qdir / "manifest.json", {"when": rep["when"], "found": rep["found"]})
        from . import push
        push.send("Virus scan found something", f"{len(rep['found'])} file{'s' if len(rep['found']) != 1 else ''} moved to quarantine. Open Security to see the list.", "/#security", tag="clamscan", throttle_s=60)
    else:
        try:
            qdir.rmdir()
        except OSError:
            pass
    return {"ok": rep["ok"], **rep}


def scan_restore(name: str, confirm: str) -> dict:
    """Put a quarantined file back where it was. The name is typed, never clicked."""
    if confirm != name:
        return {"ok": False, "err": "type the file's name to confirm"}
    if load().demo:
        st = _sample_scan()
        row = next((q for q in st["quarantined"] if os.path.basename(q["file"]) == name), None)
        if not row:
            return {"ok": False, "err": f"{name} is not in quarantine"}
        st["quarantined"].remove(row)
        return {"ok": True, "demo": True, "out": f"(sample) {name} put back at {row['file']}"}
    for d in sorted(Path(QUARANTINE).glob("*")):
        man = read_json(d / "manifest.json", default=None) or {}
        for row in man.get("found", []):
            if os.path.basename(row["file"]) == name:
                src = Path(row.get("moved_to") or d / name)
                if not src.exists():
                    return {"ok": False, "err": f"{src} is no longer in quarantine"}
                dest = Path(row["file"])
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
                man["found"] = [x for x in man["found"] if x is not row]
                write_json(d / "manifest.json", man)
                return {"ok": True, "out": f"{name} put back at {dest}"}
    return {"ok": False, "err": f"{name} is not in quarantine"}


# ---- the church certificate (Caddy's internal CA) -------------------------------------
def ca_cert() -> str | None:
    """The root certificate's PEM text, or None when Caddy has not made one."""
    if load().demo:
        return "-----BEGIN CERTIFICATE-----\n(sample: the church root certificate appears here once Caddy runs on the box)\n-----END CERTIFICATE-----\n"
    try:
        t = Path(CADDY_ROOT).read_text(encoding="utf-8")
        return t if "BEGIN CERTIFICATE" in t else None
    except OSError:
        return None


def ca_info() -> dict:
    if load().demo:
        return {"demo": True, "present": True, "path": CADDY_ROOT, "subject": "Caddy Local Authority - 2026 ECC Root", "not_after": "2036-10-28", "days_left": 3652, "caddy_running": True}
    present = Path(CADDY_ROOT).exists()
    info = {"present": present, "path": CADDY_ROOT, "subject": None, "not_after": None, "days_left": None,
            "caddy_running": run(["systemctl", "is-active", "caddy"], timeout=5)["out"].strip() == "active" if which("systemctl") else False}
    if present and which("openssl"):
        r = run(["openssl", "x509", "-in", CADDY_ROOT, "-noout", "-subject", "-enddate"], timeout=10)
        for line in r["out"].splitlines():
            if line.startswith("subject="):
                info["subject"] = line.split("=", 1)[1].strip()
            if line.startswith("notAfter="):
                raw = line.split("=", 1)[1].strip()
                try:
                    dt = datetime.strptime(raw, "%b %d %H:%M:%S %Y %Z")
                    info["not_after"] = dt.date().isoformat()
                    info["days_left"] = (dt - datetime.now()).days
                except ValueError:
                    info["not_after"] = raw
    return info


# ---- the Security app -----------------------------------------------------------------
def _apt_pending() -> int | None:
    if not which("apt"):
        return None
    r = run(["sh", "-c", "apt list --upgradable 2>/dev/null | grep -c '/'"], timeout=30)
    try:
        return int(r["out"].strip() or 0)
    except ValueError:
        return None


def facts() -> dict:
    """Everything the Security app needs, gathered once. Sample when demo."""
    from . import twofa
    cfg = load()
    if cfg.demo:
        return {"demo": True, "encrypt": encrypt_status(), "scan": scan_status(), "ca": ca_info(), "twofa": twofa.who_has(),
                "rescue": rescue_status(), "firewall": True, "tailscale": "up", "updates": 3, "snapshot": snapshot_list()["snapshots"][-1],
                "lockout": "none (round 3, 27)", "logs_days": 365, "caddy_default": True}
    fw = run(["ufw", "status"], timeout=10)["out"] if which("ufw") else ""
    ts = run(["tailscale", "status", "--json"], timeout=10) if which("tailscale") else {"ok": False, "out": ""}
    ts_state = "not installed"
    if ts["ok"]:
        try:
            ts_state = "up" if json.loads(ts["out"]).get("BackendState") == "Running" else "down"
        except json.JSONDecodeError:
            ts_state = "down"
    snaps = snapshot_list().get("snapshots") or []
    return {"demo": False, "encrypt": encrypt_status(), "scan": scan_status(), "ca": ca_info(), "twofa": twofa.who_has(),
            "rescue": rescue_status(), "firewall": "Status: active" in fw, "tailscale": ts_state, "updates": _apt_pending(),
            "snapshot": snaps[-1] if snaps else None, "lockout": "none (round 3, 27)", "logs_days": 365}


def rows(f: dict) -> list[dict]:
    """Pure: facts -> rows for the Security app. Each: {id, label, level ok|warn|bad, text, fix}."""
    out = []
    e = f.get("encrypt") or {}
    if e.get("known") is False:
        out.append({"id": "encrypt", "label": "Encryption", "level": "warn", "text": e.get("note") or "Could not check disk encryption; automatic restart is blocked.", "fix": "sudo arisectl encrypt status"})
    elif e.get("luks") and e.get("tpm_bound"):
        out.append({"id": "encrypt", "label": "Encryption", "level": "ok", "text": "The disk is encrypted and the TPM unlocks it at boot. The passphrase on the safe card is the fallback.", "fix": ""})
    elif e.get("luks") and e.get("tpm"):
        out.append({"id": "encrypt", "label": "Encryption", "level": "warn", "text": e.get("note") or "Encrypted; a TPM 2.0 is here but not bound, so a reboot waits for a passphrase.", "fix": "sudo arisectl encrypt tpm"})
    elif e.get("luks"):
        # The closet keyboard meets H3; networking is an explicit optional setup.
        ssh = e.get("ssh_unlock")
        out.append({"id": "encrypt", "label": "Encryption", "level": "ok",
                    "text": "The disk is encrypted; the passphrase is typed at every boot, at the closet keyboard" + (" or over SSH to the tested early-boot LAN address." if ssh else ". Early-boot SSH is optional and has not been verified."),
                    "fix": ""})
    else:
        out.append({"id": "encrypt", "label": "Encryption", "level": "warn", "text": "The disk is not encrypted. Bradly chose LUKS with the passphrase at boot (Oct 30, H3); it is ticked on Ubuntu's disk screen at install, not later.", "fix": "docs/SECURITY.md, 'Encryption'"})
    s = f.get("scan") or {}
    last = s.get("last")
    if not s.get("installed", True):
        out.append({"id": "scan", "label": "Virus scan", "level": "warn", "text": "ClamAV is not installed.", "fix": "sudo bash /opt/arise/installer/install.sh (step 6j)"})
    elif not last:
        out.append({"id": "scan", "label": "Virus scan", "level": "warn", "text": "No scan has run yet. The first one is Sunday 23:30.", "fix": "sudo arisectl scan run"})
    elif last.get("found"):
        out.append({"id": "scan", "label": "Virus scan", "level": "bad", "text": f"{len(last['found'])} file(s) found on {last.get('when', '')[:10]} and moved to quarantine.", "fix": "sudo arisectl scan status"})
    else:
        age = _days_since(last.get("when"))
        lvl = "ok" if age is not None and age <= 8 else "warn"
        out.append({"id": "scan", "label": "Virus scan", "level": lvl, "text": f"Last scan {last.get('when', '')[:10]}: {last.get('scanned', 0):,} files, nothing found." + ("" if lvl == "ok" else " That is more than a week ago."), "fix": "" if lvl == "ok" else "sudo systemctl status arise-clamscan.timer"})
    c = f.get("ca") or {}
    if c.get("present") and c.get("caddy_running", True):
        out.append({"id": "ca", "label": "The church certificate", "level": "ok", "text": f"Padlock on: Caddy's root certificate is present (expires {c.get('not_after') or 'unknown'}). Enrolled Macs trust it; phones on Tailscale use Tailscale's.", "fix": ""})
    elif c.get("present"):
        out.append({"id": "ca", "label": "The church certificate", "level": "warn", "text": "The certificate exists but Caddy is not running; the dashboard is plain http on the LAN.", "fix": "sudo systemctl start caddy"})
    else:
        out.append({"id": "ca", "label": "The church certificate", "level": "warn", "text": "No certificate yet: Caddy has not run on this box.", "fix": "sudo bash /opt/arise/installer/install.sh (Caddy is on by default)"})
    tf = f.get("twofa") or []
    out.append({"id": "twofa", "label": "Two-step sign-in", "level": "ok" if tf else "warn", "text": (f"{len(tf)} {'person has' if len(tf) == 1 else 'people have'} it on: {', '.join(tf)}." if tf else "Nobody has it on. It is optional; anyone turns it on from the flame menu with Microsoft Authenticator."), "fix": ""})
    r = f.get("rescue") or {}
    if not r.get("exists", True):
        out.append({"id": "rescue", "label": "Break-glass admin", "level": "warn", "text": f"{RESCUE_USER} does not exist yet.", "fix": "sudo bash /opt/arise/installer/install.sh (step 6j)"})
    elif r.get("last"):
        out.append({"id": "rescue", "label": "Break-glass admin", "level": "warn", "text": f"{RESCUE_USER} was used {r['last'].get('when', '')} by {r['last'].get('via', '')} from {r['last'].get('from', '')}. If that was not you, rotate its password.", "fix": "sudo arisectl rescue rotate"})
    else:
        out.append({"id": "rescue", "label": "Break-glass admin", "level": "ok", "text": f"{RESCUE_USER} exists and has never been used. It signs in at the closet monitor only; its password is on the safe card.", "fix": ""})
    out.append({"id": "firewall", "label": "Firewall", "level": "ok" if f.get("firewall") else "bad", "text": "ufw is on; Docker's ports go through the same gate." if f.get("firewall") else "ufw is OFF.", "fix": "" if f.get("firewall") else "sudo ufw enable"})
    ts = f.get("tailscale")
    out.append({"id": "tailscale", "label": "Tailscale", "level": "ok" if ts == "up" else "warn", "text": {"up": "Up: the only way in from outside the building.", "down": "Installed but down: nothing reaches the box from outside until it is up.", "not installed": "Not installed."}.get(ts, str(ts)), "fix": "" if ts == "up" else "sudo tailscale up --ssh"})
    u = f.get("updates")
    if u is None:
        out.append({"id": "updates", "label": "Updates", "level": "warn", "text": "Could not count pending updates.", "fix": "sudo arisectl update check"})
    else:
        out.append({"id": "updates", "label": "Updates", "level": "ok" if u == 0 else "warn", "text": "Nothing pending; security updates install themselves." if u == 0 else f"{u} package update{'s' if u != 1 else ''} waiting for your click (installed Saturday 03:30 after a snapshot).", "fix": "" if u == 0 else "Software Update"})
    sn = f.get("snapshot")
    out.append({"id": "snapshot", "label": "System snapshot", "level": "ok" if sn else "warn", "text": f"Last snapshot {sn['name'].replace('_', ' ')} ({sn.get('note') or 'no note'}); the last {SNAPSHOT_KEEP} are kept." if sn else "No system snapshot yet.", "fix": "" if sn else "sudo arisectl snapshot create \"first\""})
    out.append({"id": "lockout", "label": "Sign-in lockout", "level": "ok", "text": "None, by Bradly's decision (round 3, 27): no fail2ban, no domain lockout. Everything is behind Tailscale or inside the building.", "fix": ""})
    out.append({"id": "logs", "label": "Logs", "level": "ok", "text": f"The journal and the arise logs are kept {f.get('logs_days', 365)} days.", "fix": ""})
    return out


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        return (datetime.now() - datetime.fromisoformat(iso[:16])).days
    except ValueError:
        return None


def overview() -> dict:
    f = facts()
    r = rows(f)
    worst = "bad" if any(x["level"] == "bad" for x in r) else "warn" if any(x["level"] == "warn" for x in r) else "ok"
    return {"demo": f.get("demo", False), "rows": r, "worst": worst, "twofa": f.get("twofa"), "rescue": f.get("rescue"), "scan": f.get("scan"), "ca": f.get("ca"), "encrypt": f.get("encrypt")}

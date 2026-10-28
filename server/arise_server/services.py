"""systemd units of interest, and the Logs app's readers. Falls back to demo data when systemctl is absent."""
from __future__ import annotations

import os
import re

from . import demo
from .config import load
from .util import run, which

UNITS = [
    ("arise-web.service", "Arise dashboard"),
    ("samba-ad-dc.service", "Active Directory"),
    ("docker.service", "Docker"),
    ("arise-automator.timer", "YouTube automator (02:05)"),
    ("arise-backup.timer", "Backups (03:00)"),
    ("arise-mirror.timer", "GitHub mirror (04:00)"),
    ("arise-nas-mount.service", "Synology mount"),
    ("ssh.service", "SSH"),
]
ALLOWED_ACTIONS = {"start", "stop", "restart"}

# The Logs app's unit picker, grouped, in plain words (round 3, 7).
LOG_GROUPS = [
    ("Arise", [("arise-web.service", "the dashboard"), ("arise-automator.service", "the nightly YouTube job"), ("arise-backup.service", "backups"), ("arise-mirror.service", "GitHub mirror"), ("arise-devices.service", "network scan"), ("arise-drill.service", "restore drill"), ("arise-update.service", "software updates"), ("arise-nas-mount.service", "Synology mount"), ("arise-kiosk.service", "the closet monitor (cage)"), ("arise-wayvnc.service", "screen sharing"), ("arise-notify.service", "the daily note")]),
    ("The box", [("samba-ad-dc.service", "the domain"), ("docker.service", "Docker"), ("ssh.service", "SSH"), ("caddy.service", "HTTPS (Caddy)"), ("nut-monitor.service", "the UPS"), ("smartd.service", "disk health"), ("unattended-upgrades.service", "security patches"), ("systemd-networkd.service", "the network"), ("tailscaled.service", "Tailscale")]),
]
READABLE_RE = re.compile(r"^(arise-[a-z-]+\.(service|timer)|samba-ad-dc\.service|docker\.service|ssh\.service|caddy\.service|nut-[a-z]+\.service|smartd\.service|unattended-upgrades\.service|systemd-networkd\.service|tailscaled\.service|cockpit\.service|apt-daily(-upgrade)?\.service|fstrim\.service)$")
ERROR_RE = re.compile(r"\b(error|failed|fatal|traceback|exception|denied|refused|timed? ?out|unreachable|critical|panic)\b", re.I)
FILE_RE = re.compile(r"^[A-Za-z0-9._-]+\.(log|txt|md)$")


def available() -> bool:
    return bool(which("systemctl")) and not load().demo


def list_services() -> dict:
    if load().demo:
        from . import demo_state
        return {"demo": True, "services": demo_state.get("services", demo.SERVICES)}
    if not available():
        return {"demo": False, "services": [], "error": "systemctl is not here"}
    names = [u for u, _ in UNITS]
    r = run(["systemctl", "show", "--no-pager", "-p", "Id,ActiveState,SubState,ActiveEnterTimestamp,Description", *names], timeout=15)
    out, cur = [], {}
    for line in r["out"].splitlines() + [""]:
        if not line.strip():
            if cur:
                out.append(cur)
            cur = {}
            continue
        k, _, v = line.partition("=")
        cur[k] = v
    label = dict(UNITS)
    services = [{
        "unit": c.get("Id", ""), "name": label.get(c.get("Id", ""), c.get("Description", "")),
        "active": c.get("ActiveState", "unknown"), "sub": c.get("SubState", ""), "since": c.get("ActiveEnterTimestamp", ""),
    } for c in out if c.get("Id")]
    return {"demo": False, "services": services}


def act(unit: str, action: str) -> dict:
    if action not in ALLOWED_ACTIONS:
        return {"ok": False, "err": f"action must be one of {sorted(ALLOWED_ACTIONS)}"}
    if unit not in dict(UNITS):
        return {"ok": False, "err": "that unit is not managed here"}
    if load().demo:
        from . import demo, demo_state
        row = next((x for x in demo_state.get("services", demo.SERVICES) if x["unit"] == unit), None)
        if row is not None and action in ("start", "restart"):
            row.update({"active": "active", "sub": "running" if unit.endswith(".service") else "waiting"})
        elif row is not None and action == "stop":
            row.update({"active": "inactive", "sub": "dead"})
        return {"ok": True, "demo": True, "out": f"(sample) systemctl {action} {unit}"}
    if not available():
        return {"ok": False, "err": "systemctl is not here; nothing was done"}
    r = run(["systemctl", action, unit], timeout=60)
    if not r["ok"]:
        return {"ok": False, "err": f"systemctl {action} {unit}: " + ((r["err"] or r["out"]).strip()[:300] or f"exit {r['code']}")}
    return {"ok": True, "out": f"{action} {unit}: done"}


def last_error_index(lines: list[str]) -> int | None:
    """The index of the last line that looks like an error, else None. Pure."""
    for i in range(len(lines) - 1, -1, -1):
        if ERROR_RE.search(lines[i] or ""):
            return i
    return None


def _with_error(res: dict) -> dict:
    lines = (res.get("text") or "").splitlines()
    idx = last_error_index(lines)
    res["lines"] = len(lines)
    res["last_error_line"] = idx
    res["last_error"] = lines[idx][:300] if idx is not None else None
    return res


def journal(unit: str, lines: int = 200) -> dict:
    if not available():
        return _with_error({"demo": True, "unit": unit, "text": demo.LOGS.get(unit, f"(demo) no sample log for {unit}")})
    if unit not in dict(UNITS) and not READABLE_RE.match(unit or ""):
        return {"unit": unit, "text": "that unit is not readable here"}
    r = run(["journalctl", "-u", unit, "-n", str(min(max(int(lines), 10), 2000)), "--no-pager", "-o", "short"], timeout=20)
    return _with_error({"demo": False, "unit": unit, "text": r["out"] or r["err"]})


def log_sources() -> dict:
    """What the Logs app can read: the grouped units, the arise log files, the apps."""
    cfg = load()
    files = []
    if cfg.demo:
        files = [{"name": "install.log", "size": 184_220, "mtime": "2026-10-26T14:02"}, {"name": "backup.log", "size": 61_004, "mtime": "2026-10-28T03:16"}, {"name": "automator.log", "size": 402_118, "mtime": "2026-10-28T02:09"}, {"name": "updates.log", "size": 2_208, "mtime": "2026-10-25T03:31"}, {"name": "drill.log", "size": 1_020, "mtime": "2026-10-01T03:40"}]
    else:
        d = cfg.paths.log_dir
        try:
            from datetime import datetime
            for n in sorted(os.listdir(d)):
                p = os.path.join(d, n)
                if FILE_RE.match(n) and os.path.isfile(p):
                    st = os.stat(p)
                    files.append({"name": n, "size": st.st_size, "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes")})
        except OSError:
            pass
    apps_ = []
    try:
        from . import apps as _apps
        apps_ = [{"name": a["name"], "status": a["status"]} for a in _apps.list_apps()["apps"]]
    except Exception:  # noqa: BLE001
        pass
    return {"demo": cfg.demo, "groups": [{"name": g, "units": [{"unit": u, "what": w} for u, w in us]} for g, us in LOG_GROUPS], "files": files, "apps": apps_, "log_dir": cfg.paths.log_dir}


def log_file(name: str, lines: int = 300) -> dict:
    cfg = load()
    if not FILE_RE.match(name or "") or "/" in name:
        return {"name": name, "text": "that is not a log file name"}
    if cfg.demo:
        samples = {"install.log": "2026-10-26 14:02:11 ==> Preflight\n2026-10-26 14:02:12     OS: Ubuntu 24.04.1 LTS\n2026-10-26 14:03:40 ==> 5/7 Active Directory domain AD.ARISECENLA.COM\n2026-10-26 14:09:02 ==> 6a/7 Apps\n2026-10-26 14:31:55     app netdata: up\n2026-10-26 14:33:10     app guacamole: up\n2026-10-26 14:40:00 ==> 7/7 Done.",
                   "updates.log": "2026-10-18T03:30:04-05:00 ok 3 packages, 0 apps, no reboot needed\n2026-10-25T03:30:02-05:00 ok 2 packages, 1 apps, reboot needed\n",
                   "backup.log": "2026-10-28 03:00:01 job automator: started\n2026-10-28 03:02:35 job automator: ok, 797.1 MB added\n2026-10-28 03:04:00 job homes: started\n2026-10-28 03:11:12 job homes: ok, 451.3 MB added\n2026-10-28 03:16:30 prune: kept 30 daily, 12 weekly, 24 monthly"}
        return _with_error({"demo": True, "name": name, "text": samples.get(name, f"(demo) no sample for {name}")})
    p = os.path.join(cfg.paths.log_dir, name)
    try:
        with open(p, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 400_000))
            text = f.read().decode("utf-8", "replace")
    except OSError as e:
        return {"name": name, "text": f"cannot read {p}: {e}"}
    tail = text.splitlines()[-min(max(int(lines), 10), 2000):]
    return _with_error({"demo": False, "name": name, "text": "\n".join(tail)})

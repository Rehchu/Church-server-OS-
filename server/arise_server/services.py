"""systemd units of interest. Falls back to demo data when systemctl is absent."""
from __future__ import annotations

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


def available() -> bool:
    return bool(which("systemctl")) and not load().demo


def list_services() -> dict:
    if not available():
        return {"demo": True, "services": demo.SERVICES}
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
    if not available():
        return {"ok": True, "demo": True, "out": f"(demo) systemctl {action} {unit}"}
    return run(["systemctl", action, unit], timeout=60)


def journal(unit: str, lines: int = 200) -> dict:
    if not available():
        return {"demo": True, "unit": unit, "text": demo.LOGS.get(unit, f"(demo) no sample log for {unit}")}
    if unit not in dict(UNITS) and not unit.startswith("arise-"):
        return {"unit": unit, "text": "that unit is not readable here"}
    r = run(["journalctl", "-u", unit, "-n", str(min(lines, 2000)), "--no-pager", "-o", "short"], timeout=20)
    return {"demo": False, "unit": unit, "text": r["out"] or r["err"]}

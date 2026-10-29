"""The box itself: updates, reboot, shutdown, the daily notification, the web terminal."""
from __future__ import annotations

import asyncio
import fcntl
import json
import os
import pty
import signal
import struct
import termios
import urllib.request
from datetime import datetime

from .config import load
from .util import read_text, now_iso, read_json, run, which, write_json

ARISE_HOME = "/opt/arise"


# Round 7, 135/136: any admin installs ariseOS updates, and they arrive in two steps. Arise-Home
# (Bradly's house, the test box) takes a new version the day it lands; Arise-Pineville takes only
# what has been out a week, so a bad version shows itself at the house first.
RING_DAYS = {"home": 0, "pineville": 7}


def ring() -> str:
    raw = load().raw
    r = str(((raw.get("updates") if isinstance(raw, dict) else None) or {}).get("ring", "pineville")).lower()
    return r if r in RING_DAYS else "pineville"


def stage_args(ring_name: str) -> list[str]:
    """Pure: the git rev-list arguments naming the newest commit this box may take."""
    days = RING_DAYS.get(ring_name, 7)
    return ["rev-list", "-1"] + ([f"--before={days} days ago"] if days else []) + ["origin/main"]


def _stage_ref() -> tuple[str | None, int]:
    """(the commit this box may move to, how many newer commits wait for the week to pass)."""
    r = run(["git", "-C", ARISE_HOME, *stage_args(ring())], timeout=10)
    ref = r["out"].strip() if r["ok"] and r["out"].strip() else None
    waiting = 0
    if ref:
        w = run(["git", "-C", ARISE_HOME, "rev-list", "--count", f"{ref}..origin/main"], timeout=10)
        waiting = int(w["out"].strip() or 0) if w["ok"] else 0
    return ref, waiting


def updates() -> dict:
    cfg = load()
    if cfg.demo or not which("apt-get"):
        return {"demo": True, "apt_upgradable": 3, "arise_behind": 0, "arise_waiting": 0, "ring": ring(), "last_check": now_iso(), "security": 1}
    r = run(["apt", "list", "--upgradable"], timeout=60)
    rows = [l for l in r["out"].splitlines() if "/" in l and "upgradable" in l]
    sec = sum(1 for l in rows if "security" in l)
    behind = waiting = None
    if os.path.isdir(os.path.join(ARISE_HOME, ".git")):
        run(["git", "-C", ARISE_HOME, "fetch", "-q", "origin"], timeout=60)
        ref, waiting = _stage_ref()
        if ref:
            b = run(["git", "-C", ARISE_HOME, "rev-list", "--count", f"HEAD..{ref}"], timeout=10)
            behind = int(b["out"].strip() or 0) if b["ok"] else None
        else:
            behind = 0
    return {"demo": False, "apt_upgradable": len(rows), "security": sec, "arise_behind": behind, "arise_waiting": waiting,
            "ring": ring(), "last_check": now_iso()}


def update_arise() -> dict:
    """Move to the newest version this box's ring allows (a merge, never a rebase), pip install,
    restart. The timers keep running throughout."""
    if load().demo:
        return {"ok": True, "demo": True, "out": f"(sample) git merge --ff-only <the newest {ring()} version> && pip install -r server/requirements.txt && systemctl restart arise-web"}
    if not os.path.isdir(os.path.join(ARISE_HOME, ".git")):
        return {"ok": False, "err": f"{ARISE_HOME} is not a git checkout, so there is nothing to pull; reinstall from the repo"}
    run(["git", "-C", ARISE_HOME, "fetch", "-q", "origin"], timeout=120)
    ref, waiting = _stage_ref()
    if not ref:
        return {"ok": True, "out": f"nothing has been out long enough for {ring()} yet ({waiting} newer version(s) wait for the week)"}
    steps = [
        ["git", "-C", ARISE_HOME, "merge", "--ff-only", ref],
        [os.path.join(ARISE_HOME, "venv", "bin", "pip"), "install", "-q", "-r", os.path.join(ARISE_HOME, "server", "requirements.txt")],
        ["install", "-m", "0755", os.path.join(ARISE_HOME, "cli", "arisectl"), "/usr/local/bin/arisectl"],
        ["cp", "-f"] + [os.path.join(ARISE_HOME, "config", "systemd", f) for f in os.listdir(os.path.join(ARISE_HOME, "config", "systemd"))] + ["/etc/systemd/system/"],
        ["systemctl", "daemon-reload"],
    ]
    log = []
    for s in steps:
        r = run(s, timeout=900)
        log.append(f"$ {' '.join(s)[:120]}\n{(r['out'] or r['err']).strip()[-400:]}")
        if not r["ok"]:
            return {"ok": False, "err": r["err"] or r["out"], "log": "\n".join(log)}
    run(["systemctl", "restart", "arise-web.service"], timeout=30)  # restarts us; the response may not arrive
    return {"ok": True, "log": "\n".join(log), "waiting": waiting}


def apt_upgrade() -> dict:
    if load().demo:
        return {"ok": True, "demo": True, "out": "(sample) apt-get upgrade"}
    if not which("apt-get"):
        return {"ok": False, "err": "apt-get is not here; this is not an Ubuntu box"}
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    import subprocess
    p = subprocess.run(["apt-get", "-y", "-q", "upgrade"], capture_output=True, text=True, timeout=3600, env=env)
    return {"ok": p.returncode == 0, "out": p.stdout[-1500:], "err": p.stderr[-800:]}


def power(action: str, confirm: str) -> dict:
    if action not in ("reboot", "poweroff"):
        return {"ok": False, "err": "action must be reboot or poweroff"}
    if confirm != action:
        return {"ok": False, "err": f"type {action} to confirm"}
    if load().demo:
        return {"ok": True, "demo": True, "out": f"(sample) systemctl {action}"}
    if not which("systemctl"):
        return {"ok": False, "err": "systemctl is not here; nothing was done"}
    r = run(["systemctl", action], timeout=10)
    if not r["ok"]:
        return {"ok": False, "err": f"systemctl {action}: " + ((r["err"] or r["out"]).strip()[:300] or f"exit {r['code']}")}
    return {"ok": True, "out": f"{'restarting' if action == 'reboot' else 'shutting down'} now"}


# ----- the daily notification -------------------------------------------------
def notify_config() -> dict:
    cfg = load()
    n = dict(cfg.raw.get("notify", {}) if isinstance(cfg.raw, dict) else {})
    n.setdefault("webhook_url", "")
    n.setdefault("hour", 7)
    n.setdefault("only_when_attention", True)
    return n


def send_webhook(text: str, url: str | None = None) -> dict:
    url = url or notify_config()["webhook_url"]
    if not url:
        return {"ok": False, "err": "no webhook_url in [notify]"}
    body = {"content": text[:1900]} if "discord" in url else {"text": text[:3000]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return {"ok": 200 <= r.status < 300}
    except Exception as e:
        return {"ok": False, "err": str(e)[:200]}


def daily_report(attention: list[dict], summary: dict) -> dict:
    """Called by `arisectl notify send` from arise-notify.timer. Writes a state row either way."""
    cfg = load()
    n = notify_config()
    lines = [f"Arise Server · {datetime.now():%a %b %d, %I:%M %p}"]
    if attention:
        lines += [f"{'🔴' if a['level'] == 'bad' else '🟡'} {a['text']}" for a in attention]
    else:
        lines.append("✅ All clear: services up, last automator run clean, backups ok, Synology mounted.")
    lines.append(f"Automator: {summary.get('automator', '')} · Backups: {summary.get('backup', '')}")
    # Round 7, 145: a failed 02:05 run, in the report's own words, job by job.
    if summary.get("automator_failed"):
        try:
            from . import automator, reports
            why = reports.explain_failure(read_text(automator._paths()["latest"], ""))
            if why:
                lines.append("What the 02:05 report says went wrong:")
                lines += [f"  · {w}" for w in why]
        except Exception:  # noqa: BLE001
            pass
    text = "\n".join(lines)
    result = {"when": now_iso(), "sent": False, "text": text}
    if attention or not n["only_when_attention"]:
        r = send_webhook(text) if n["webhook_url"] and not cfg.demo else {"ok": False, "err": "no webhook / demo"}
        result.update({"sent": r.get("ok", False), "error": r.get("err")})
    if not cfg.demo:
        sp = cfg.state_dir / "state.json"
        st = read_json(sp, default={})
        st["last_notify"] = result
        write_json(sp, st)
    return result


# ----- web terminal (a pty over a websocket) ---------------------------------
def spawn_shell(cols: int = 100, rows: int = 30):
    """Returns (pid, fd). Runs a login shell as the user the service runs as."""
    shell = os.environ.get("SHELL") or ("/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh")
    pid, fd = pty.fork()
    if pid == 0:
        env = dict(os.environ, TERM="xterm-256color", COLUMNS=str(cols), LINES=str(rows), ARISE_TERMINAL="1")
        os.chdir(os.environ.get("HOME", "/"))
        os.execvpe(shell, [shell, "-l"], env)
    resize(fd, cols, rows)
    return pid, fd


def resize(fd: int, cols: int, rows: int):
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except OSError:
        pass


def kill(pid: int):
    try:
        os.kill(pid, signal.SIGHUP)
    except OSError:
        pass


DEMO_BANNER = "\x1b[31m   ▲\x1b[0m  Arise Server \x1b[2mv0.2.0 “Pineville”\x1b[0m  ·  preview terminal\r\n   This is a sample shell. On the real server this is a root shell on the box.\r\n\r\n"
DEMO_COMMANDS = {
    "help": "arisectl info · arisectl doctor · arisectl backup status · arisectl user list · uptime · df -h · clear",
    "arisectl info": "Arise Server v0.2.0 “Pineville”\r\n  host      arise-server  (Ubuntu 24.04, 4 cores, 16 GB RAM)\r\n  realm     AD.ARISECENLA.COM / ARISE   directory on\r\n  web       http://arise-server:4147   password set\r\n  automator /srv/arise/automator/ARISE_YouTube_Updater  at 02:05\r\n  backups   /mnt/synology/arise-backups/restic  at 03:00",
    "arisectl doctor": "arisectl doctor\r\n  \x1b[32m✓\x1b[0m config /etc/arise/arise.toml\r\n  \x1b[32m✓\x1b[0m Samba AD DC answers\r\n  \x1b[32m✓\x1b[0m DNS SRV for ad.arisecenla.com resolves\r\n  \x1b[32m✓\x1b[0m token.json present\r\n  \x1b[32m✓\x1b[0m restic installed\r\n  \x1b[32m✓\x1b[0m Synology /mnt/synology mounted\r\n  \x1b[33m!\x1b[0m 3 apt packages upgradable (1 security)\r\n  \x1b[32m✓\x1b[0m clock synchronised",
    "arisectl backup status": "repository /mnt/synology/arise-backups/restic\r\n  \x1b[32m✓\x1b[0m 53 snapshots, 296.2 GB stored\r\n  JOB        LAST              RESULT  ADDED\r\n  automator  2026-10-27T03:00  ok      797.1 MB\r\n  homes      2026-10-27T03:04  ok      451.3 MB\r\n  config     2026-10-27T03:16  ok      739.5 MB",
    "arisectl user list": "  USER          NAME             ENABLED  GROUPS\r\n  bradly        Bradly Dyer      yes      Domain Admins, Media, Staff\r\n  media-mac     Media Booth Mac  yes      Media\r\n  office        Church Office    yes      Staff\r\n  kids-checkin  Kids Check-in    yes      Kids-Check-in",
    "uptime": " 09:41:12 up 14 days,  3:07,  1 user,  load average: 0.42, 0.58, 0.61",
    "df -h": "Filesystem      Size  Used Avail Use% Mounted on\r\n/dev/sda2       224G   66G  147G  31% /\r\n/dev/sdb1       894G  242G  607G  29% /srv/arise\r\n//synology/arise  15T  4.5T   10T  31% /mnt/synology",
    "whoami": "root",
    "hostname": "arise-server",
}

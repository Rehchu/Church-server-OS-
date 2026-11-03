"""One Firefox profile per admin on the closet monitor (round 6, 29-33).

The monitor's Firefox runs as arise-kiosk. Each admin has a profile of their own
under /var/lib/arise/browser/profiles/<user>: their history, sign-ins, saved
passwords and add-ons. At rest every admin profile belongs to root (0700), so the
kiosk cannot open one; scripts/arise-browser-profile lends it to the kiosk only
while that admin is signed in at the monitor, and takes it back when the screen
locks. Locked, the monitor runs a neutral profile made fresh each time (no
history).

The switch restarts Firefox, so the admin's dashboard session has to cross into
the new profile: the page that signed in asks for a switch, the server keeps the
session for one minute behind a one-time handoff token, and the restarted
Firefox opens /?kiosk=1&handoff=<token>, which trades it back for the cookie.
"""
from __future__ import annotations

import os
import re
import secrets
import subprocess
import threading
import time
from pathlib import Path

from .config import load

TOOL = "/usr/local/sbin/arise-browser-profile"
STATE = Path("/run/arise-kiosk")
HANDOFF_SECONDS = 60
USER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

_lock = threading.Lock()
_handoffs: dict[str, tuple[str, str, float]] = {}   # token -> (session cookie, user, expires)
_demo_current = {"user": "neutral"}


def on_monitor(host: str, forwarded: str = "") -> bool:
    """Only the monitor itself may switch the monitor's browser: a request from this box that did
    not come through Caddy (Caddy proxies from 127.0.0.1 too, and always adds X-Forwarded-For;
    the kiosk talks to http://127.0.0.1:4147 directly)."""
    if load().demo:
        return True
    return host in ("127.0.0.1", "::1", "localhost") and not (forwarded or "").strip()


def current() -> str:
    if load().demo:
        return _demo_current["user"]
    try:
        v = (STATE / "current").read_text().strip()
    except OSError:
        return "neutral"
    return v if USER_RE.match(v) else "neutral"


def handoff_make(session: str, user: str, now: float | None = None) -> str:
    now = now if now is not None else time.time()
    tok = secrets.token_urlsafe(24)
    with _lock:
        for k, (_, _, exp) in list(_handoffs.items()):
            if exp < now:
                _handoffs.pop(k, None)
        _handoffs[tok] = (session, user, now + HANDOFF_SECONDS)
    return tok


def handoff_take(tok: str, now: float | None = None) -> tuple[str, str] | None:
    """(session cookie, user) once, within a minute; then never again."""
    now = now if now is not None else time.time()
    with _lock:
        got = _handoffs.pop(tok or "", None)
    if not got or got[2] < now:
        return None
    return got[0], got[1]


def _run(args: list[str]) -> dict:
    try:
        r = subprocess.run([TOOL, *args], capture_output=True, text=True, timeout=40)
    except FileNotFoundError:
        return {"ok": False, "err": "the monitor's profile switcher is not installed (sudo bash /opt/arise/scripts/arise-browser-setup)"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "err": "the monitor's browser did not restart in time"}
    out = (r.stdout or r.stderr).strip()
    return {"ok": r.returncode == 0, **({} if r.returncode == 0 else {"err": out[-300:] or f"exit {r.returncode}"})}


def switch(user: str, session: str) -> dict:
    """Restart the monitor's Firefox into this admin's own profile, signed in."""
    if not USER_RE.match(user or ""):
        return {"ok": False, "err": "not a user name"}
    if current() == user:
        return {"ok": True, "already": True, "user": user}
    tok = handoff_make(session, user)
    url = f"http://127.0.0.1:{load().web.port}/?kiosk=1&handoff={tok}"
    if load().demo:
        _demo_current["user"] = user
        return {"ok": True, "demo": True, "user": user, "note": "Sample: on the monitor Firefox restarts into your own profile"}
    r = _run(["switch", user, url])
    return {**r, "user": user}


def neutral() -> dict:
    """The screen locked: back to a fresh profile with no history; the admin's profile is put away."""
    if load().demo:
        _demo_current["user"] = "neutral"
        return {"ok": True, "demo": True, "user": "neutral"}
    if current() == "neutral":
        return {"ok": True, "already": True, "user": "neutral"}
    return {**_run(["neutral"]), "user": "neutral"}


# ----- after a restart, the owner's desktop (round 7, 107) -----------------------------
# "After a restart, the monitor shows: Your desktop." Once per boot, within the first
# AUTOLOGIN_MINUTES of it, only from the monitor (the route checks on_monitor). The marker in
# /run (a tmpfs, empty at every boot) makes it once. It still locks after ten idle minutes.
# [kiosk] autologin = "owner" (the default) means the dashboard's admin user; "" or "off" turns it off.
AUTOLOGIN_MINUTES = 15


def autologin_user() -> str | None:
    cfg = load()
    k = (cfg.raw.get("kiosk") if isinstance(cfg.raw, dict) else None) or {}
    v = str(k.get("autologin", "owner") or "").strip().lower()
    if v in ("", "off", "none", "no", "false"):
        return None
    user = cfg.web.admin_user if v == "owner" else v
    return user if USER_RE.match(user or "") else None


def autologin_take(now: float | None = None, boot: float | None = None) -> tuple[str, str] | None:
    """(session token, user) once per boot, or None."""
    user = autologin_user()
    if not user:
        return None
    now = now if now is not None else time.time()
    if boot is None:
        try:
            import psutil
            boot = psutil.boot_time()
        except Exception:  # noqa: BLE001
            return None
    if now - boot > AUTOLOGIN_MINUTES * 60:
        return None
    mark = STATE / "autologin-used"
    with _lock:
        if not load().demo:
            try:
                STATE.mkdir(parents=True, exist_ok=True)
                fd = os.open(str(mark), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
            except FileExistsError:
                return None
            except OSError:
                return None
    from .auth import _serializer
    return _serializer().dumps({"u": user, "r": "admin", "v": "local", "t": int(now)}), user

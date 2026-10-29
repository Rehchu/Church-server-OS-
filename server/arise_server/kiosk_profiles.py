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

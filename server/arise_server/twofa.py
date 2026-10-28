"""Two-step sign-in, optional per person (Bradly, Oct 28: "2fa is optional,
but if they do opt in, then it uses Microsoft Authenticator").

Plain TOTP (RFC 6238), which Microsoft Authenticator scans like any other
authenticator; no Microsoft account is involved. Each person's secret lives
in /etc/arise/secrets/totp/<user>.json, root-only. It is shown exactly once,
at setup, as a QR code and as text for manual entry, and never leaves the box
again. Nobody is forced; an admin can see who has it on and switch it off for
someone who lost their phone (`arisectl twofa reset <user>`).

Login: /api/auth/login answers {need_code: true, pending: <token>} for an
enrolled person; /api/auth/login/code finishes it. The pending token is
signed, lives five minutes, and dies after three wrong codes.
"""
from __future__ import annotations

import json
import re
import os
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

from .config import load

ISSUER = "ariseOS"
PENDING_SECONDS = 300
MAX_WRONG = 3
DEMO_ON = ["bradly"]  # the sample: Bradly has it on, nobody else

_lock = threading.Lock()
_wrong: dict[str, int] = {}       # pending nonce -> wrong codes so far
_dead: set[str] = set()           # nonces that spent their three tries


def _dir() -> Path:
    cfg = load()
    base = Path(cfg.web.get("secret_file", "/etc/arise/secrets/web-secret")).parent
    return base / "totp"


def _path(user: str) -> Path:
    safe = "".join(c for c in (user or "").lower() if c.isalnum() or c in "._-")
    return _dir() / f"{safe}.json"


def _read(user: str) -> dict | None:
    try:
        return json.loads(_path(user).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write(user: str, d: dict) -> bool:
    p = _path(user)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(p.parent, 0o700)
        tmp = p.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, p)
        return True
    except OSError:
        return False


# ---- the pure parts (tested) ---------------------------------------------------
def verify_code(secret: str, code: str, at: float | None = None, window: int = 1) -> bool:
    """Does this six-digit code match this secret now (or one step either side)?"""
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != 6 or not secret:
        return False
    try:
        import pyotp
    except ImportError:
        return False
    t = pyotp.TOTP(secret)
    return bool(t.verify(code, for_time=at, valid_window=window))


def code_at(secret: str, at: float) -> str:
    """The code a phone would show at this moment (for the tests)."""
    import pyotp
    return pyotp.TOTP(secret).at(at)


def provisioning_uri(secret: str, user: str) -> str:
    import pyotp
    return pyotp.TOTP(secret).provisioning_uri(name=user, issuer_name=ISSUER)


def qr_svg(uri: str) -> str:
    """The QR as inline SVG; empty when segno is missing (the text secret still works)."""
    try:
        import io
        import segno
        buf = io.BytesIO()
        segno.make(uri, error="m").save(buf, kind="svg", scale=5, dark="#0A0A0C", light="#FFFFFF", xmldecl=False, svgns=True, border=2)
        return buf.getvalue().decode("utf-8")
    except Exception:
        return ""


def pending_attempt(nonce: str, correct: bool, wrong: dict | None = None, dead: set | None = None) -> dict:
    """Pure: the three-strikes rule on a pending login. Returns {ok, left, dead}."""
    wrong = _wrong if wrong is None else wrong
    dead = _dead if dead is None else dead
    if nonce in dead:
        return {"ok": False, "left": 0, "dead": True}
    if correct:
        wrong.pop(nonce, None)
        return {"ok": True, "left": MAX_WRONG, "dead": False}
    n = wrong.get(nonce, 0) + 1
    wrong[nonce] = n
    if n >= MAX_WRONG:
        dead.add(nonce)
        wrong.pop(nonce, None)
        return {"ok": False, "left": 0, "dead": True}
    return {"ok": False, "left": MAX_WRONG - n, "dead": False}


# ---- state -------------------------------------------------------------------------
def _demo_on() -> set:
    from . import demo_state
    return demo_state.get("twofa.on", lambda: set(DEMO_ON))


def enrolled(user: str) -> bool:
    if load().demo:
        return user in _demo_on()
    d = _read(user)
    return bool(d and d.get("on"))


def status(user: str) -> dict:
    if load().demo:
        on = user in _demo_on()
        return {"demo": True, "user": user, "on": on, "since": "2026-10-28T20:10" if on else None, "available": True}
    try:
        import pyotp  # noqa: F401
        avail = True
    except ImportError:
        avail = False
    d = _read(user) or {}
    return {"user": user, "on": bool(d.get("on")), "since": d.get("since"), "available": avail,
            "note": None if avail else "pip install pyotp segno (server/requirements.txt), then restart arise-web"}


def who_has() -> list[str]:
    """Everyone with two-step on. Names only; no secrets."""
    if load().demo:
        return sorted(_demo_on())
    out = []
    try:
        for p in sorted(_dir().glob("*.json")):
            try:
                if json.loads(p.read_text(encoding="utf-8")).get("on"):
                    out.append(p.stem)
            except (json.JSONDecodeError, OSError):
                pass
    except OSError:
        pass
    return out


def setup(user: str) -> dict:
    """A new secret, shown once. Not on until enable() sees a correct code."""
    try:
        import pyotp
    except ImportError:
        return {"ok": False, "err": "pyotp is not installed on the server (server/requirements.txt)"}
    if load().demo:
        secret = "ARISEOSSAMPLESECRETX"  # the sample: never a real key
        uri = provisioning_uri(secret, user)
        from . import demo_state
        demo_state.get("twofa.pending", dict)[user] = secret
        return {"ok": True, "demo": True, "secret": secret, "uri": uri, "qr": qr_svg(uri), "on": user in _demo_on()}
    d = _read(user) or {}
    if d.get("on"):
        return {"ok": False, "err": "Two-step is already on. Turn it off first (it asks for your password and a code)."}
    secret = pyotp.random_base32()
    if not _write(user, {"secret": secret, "on": False, "made": datetime.now().isoformat(timespec="minutes")}):
        return {"ok": False, "err": "could not write the secret under /etc/arise/secrets/totp (is arise-web running as root?)"}
    uri = provisioning_uri(secret, user)
    return {"ok": True, "secret": secret, "uri": uri, "qr": qr_svg(uri), "on": False}


def enable(user: str, code: str) -> dict:
    if load().demo:
        from . import demo_state
        if user in _demo_on():
            return {"ok": True, "demo": True, "on": True}
        if user not in demo_state.get("twofa.pending", dict):
            return {"ok": False, "err": "scan the code first (Two-step sign-in… in the flame menu)"}
        if not re.fullmatch(r"\d{6}", (code or "").replace(" ", "")):
            return {"ok": False, "err": "six digits from Microsoft Authenticator"}
        demo_state.get("twofa.pending", dict).pop(user, None)
        _demo_on().add(user)
        return {"ok": True, "demo": True, "on": True, "since": datetime.now().isoformat(timespec="minutes")}
    d = _read(user)
    if not d or not d.get("secret"):
        return {"ok": False, "err": "scan the code first (Two-step sign-in… in the flame menu)"}
    if d.get("on"):
        return {"ok": True, "on": True}
    if not verify_code(d["secret"], code):
        return {"ok": False, "err": "that code did not match; wait for the next one and try again"}
    d["on"] = True
    d["since"] = datetime.now().isoformat(timespec="minutes")
    _write(user, d)
    return {"ok": True, "on": True, "since": d["since"]}


def disable(user: str, password: str, code: str, by_admin: bool = False) -> dict:
    """Off again: the person's password and a current code, or an admin on the box (arisectl)."""
    if load().demo:
        if not by_admin and not (password or "").strip():
            return {"ok": False, "err": "wrong password"}
        _demo_on().discard(user)
        return {"ok": True, "demo": True, "on": False}
    d = _read(user)
    if not d:
        return {"ok": True, "on": False}
    if not by_admin:
        from . import directory
        from .auth import verify_password
        cfg = load()
        ok_pw = directory.authenticate(user, password) or (user == cfg.web.admin_user and cfg.web.admin_password_hash and verify_password(password, cfg.web.admin_password_hash))
        if not ok_pw:
            time.sleep(0.8)
            return {"ok": False, "err": "wrong password"}
        if d.get("on") and not verify_code(d["secret"], code):
            return {"ok": False, "err": "that code did not match"}
    try:
        _path(user).unlink()
    except OSError:
        pass
    return {"ok": True, "on": False}


# ---- the pending login ------------------------------------------------------------
def _serializer():
    from itsdangerous import URLSafeTimedSerializer
    from .auth import _secret
    return URLSafeTimedSerializer(_secret(load()), salt="arise-2fa-pending")


def pending_token(session_token: str, user: str) -> str:
    """Wraps the finished session token so it is handed out only after a code."""
    return _serializer().dumps({"t": session_token, "u": user, "n": secrets.token_urlsafe(8)})


def finish(pending: str, code: str, max_age: int = PENDING_SECONDS) -> dict:
    """{ok, token, user} or {ok: False, err, left}."""
    from itsdangerous import BadSignature, SignatureExpired
    try:
        d = _serializer().loads(pending or "", max_age=max_age)
    except SignatureExpired:
        return {"ok": False, "err": "That took more than five minutes. Sign in again.", "left": 0, "expired": True}
    except BadSignature:
        return {"ok": False, "err": "Sign in again.", "left": 0, "expired": True}
    user, nonce = d.get("u", ""), d.get("n", "")
    rec = _read(user) or {}
    with _lock:
        if nonce in _dead:
            return {"ok": False, "err": "Three wrong codes. Sign in again.", "left": 0, "expired": True}
        good = bool(rec.get("on")) and verify_code(rec.get("secret", ""), code)
        a = pending_attempt(nonce, good)
    if not a["ok"]:
        if a["dead"]:
            return {"ok": False, "err": "Three wrong codes. Sign in again.", "left": 0, "expired": True}
        return {"ok": False, "err": f"That code did not match ({a['left']} more {'try' if a['left'] == 1 else 'tries'}).", "left": a["left"], "expired": False}
    return {"ok": True, "token": d["t"], "user": user}

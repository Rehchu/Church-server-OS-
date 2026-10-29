"""Logins: the admin (bcrypt hash in arise.toml) and every directory user (Kerberos), signed session cookie.

- No hash set and not demo  → every API call answers 401 with setup=True; the
  dashboard shows "run `arisectl admin set-password`" instead of a login box.
- Demo mode                 → no login at all.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from pathlib import Path

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .config import load

COOKIE = "arise_session"


def _secret(cfg) -> str:
    env = os.environ.get("ARISE_WEB_SECRET")
    if env:
        return env
    p = Path(cfg.web.get("secret_file", ""))
    try:
        s = p.read_text().strip()
        if s:
            return s
    except OSError:
        pass
    s = secrets.token_urlsafe(32)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(s)
        os.chmod(p, 0o600)
    except OSError:
        pass  # ephemeral secret: sessions end on restart, which is fine
    return s


def _serializer():
    cfg = load()
    return URLSafeTimedSerializer(_secret(cfg), salt="arise-session")


def verify_password(password: str, hashed: str) -> bool:
    try:
        import bcrypt
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def hash_password(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


MEMBER_OK = ("/api/auth/", "/api/me", "/api/files/", "/api/search", "/api/links", "/api/sermons", "/api/bible", "/api/sites", "/api/health", "/api/church", "/api/sunday", "/api/kiosk/open", "/api/public/", "/api/push/", "/api/about/week", "/api/about/whatsnew", "/api/calendar", "/api/weather", "/api/help", "/api/people", "/api/checklist/")


def login(user: str, password: str) -> tuple[str | None, dict] | None:
    """Returns (token, who) or None. The admin user is checked against the bcrypt
    hash in arise.toml; everyone else against the directory (Kerberos). A right but
    expired (temporary) password returns (None, {"user", "expired": True})."""
    from . import directory
    cfg = load()
    user = (user or "").strip().lower()
    who = None
    if user == cfg.web.admin_user and cfg.web.admin_password_hash and verify_password(password, cfg.web.admin_password_hash):
        who = {"user": user, "role": "admin", "via": "local"}
    elif cfg.web.get("member_login", True):
        state = directory.check_login(user, password)
        if state == "expired":   # the right password, but a temporary one: choose their own first (round 5, 5)
            return None, {"user": user, "expired": True}
        if state == "ok":
            who = {"user": user, "role": "admin" if directory.is_admin(user) else "member", "via": "directory"}
    if not who:
        return None
    # "fp": the full password was typed for this session (a PIN session has none), so setting a
    # PIN right after a password sign-in needs no second password (round 7, 162).
    now = int(time.time())
    return _serializer().dumps({"u": who["user"], "r": who["role"], "v": who["via"], "t": now, "fp": now}), who


def pin_token(user: str, scope: str) -> tuple[str, dict] | None:
    """A session from a PIN (round 7, 160 and 162). The same session as a password sign-in,
    except: no "fp" and never an "ra" (the password-again clicks still ask the password, 161),
    and a staff PIN ("checklist") reaches the phone checklist only."""
    from . import directory
    cfg = load()
    user = (user or "").strip().lower()
    if user == cfg.web.admin_user:
        who = {"user": user, "role": "admin", "via": "local"}
    else:
        if not cfg.demo:
            live = live_state(user)
            if live is not None and not live[0]:
                return None   # a disabled account: no PIN gets it in
        who = {"user": user, "role": "admin" if directory.is_admin(user) else "member", "via": "directory"}
    if who["role"] != "admin":
        scope = "checklist"
    who["pin"] = scope
    return _serializer().dumps({"u": who["user"], "r": who["role"], "v": who["via"], "t": int(time.time()), "pin": scope}), who


def current_user(request: Request) -> dict:
    cfg = load()
    tok = request.cookies.get(COOKIE)
    if cfg.demo:
        who = {"user": "demo", "role": "admin", "demo": True}
        if tok:
            try:
                d = _serializer().loads(tok, max_age=int(cfg.web.session_hours) * 3600)
                who = {"user": d["u"], "role": d.get("r", "admin"), "demo": True}
                if d.get("pin"):
                    who["pin"] = d["pin"]
            except BadSignature:
                pass
        _check_path(request, who)
        return who
    if not cfg.web.admin_password_hash:
        raise HTTPException(401, {"setup": True, "message": "No admin password yet. On the server run: sudo arisectl admin set-password"})
    if not tok:
        raise HTTPException(401, {"message": "Sign in"})
    try:
        data = _serializer().loads(tok, max_age=int(cfg.web.session_hours) * 3600)
    except BadSignature:
        raise HTTPException(401, {"message": "Session expired, sign in again"})
    if not session_current(data, valid_after(data["u"])):
        raise HTTPException(401, {"message": "Signed out: the password changed or the account was disabled. Sign in again"})
    role = data.get("r", "admin")
    if data.get("v") == "directory":
        live = live_state(data["u"])
        if live is not None:
            enabled, is_adm = live
            if not enabled:
                raise HTTPException(401, {"message": "This account is disabled"})
            role = "admin" if is_adm else "member"
    who = {"user": data["u"], "role": role, "demo": False}
    if data.get("pin"):
        who["pin"] = data["pin"]
    _check_path(request, who)
    return who


# ---- sessions that end when they should (round 7 security review) --------------------
# A session lasts a year (round 3, 38), so the role it was signed in with, a disabled account
# and a changed password must not ride along for that year. Each token carries when it was
# issued ("t"); a password change, a reset, disabling or deleting the account moves the
# person's "valid after" mark, and older tokens stop working. The role and the enabled flag
# are read back from the directory every two minutes, not trusted from the token.
_SESS_LOCK = threading.Lock()
LIVE_SECONDS = 120
_live: dict[str, tuple[float, bool, bool]] = {}


def _sessions_file() -> Path:
    return load().state_dir / "sessions.json"


def _valid_after_all() -> dict:
    try:
        return json.loads(_sessions_file().read_text())
    except (OSError, ValueError):
        return {}


def valid_after(user: str) -> float:
    return float(_valid_after_all().get((user or "").lower(), 0))


def session_current(token_data: dict, after: float) -> bool:
    """Pure: was this token issued after the person's last sign-out-everywhere mark?
    A token from before "t" existed counts as issued at 0."""
    return not after or float(token_data.get("t", 0)) > after


def revoke_sessions(user: str, now: float | None = None) -> None:
    """Every session of this person issued before now stops working (all their devices).
    Their PIN, if they have one, waits for their next full-password sign-in (round 7, 160)."""
    if not user:
        return
    try:
        from . import pins
        pins.switch_off(user, "the password changed or the account was switched off")
    except Exception:  # noqa: BLE001 - a PIN record never blocks a sign-out
        pass
    if load().demo:
        return
    with _SESS_LOCK:
        d = _valid_after_all()
        d[user.lower()] = float(now or time.time())
        p = _sessions_file()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(d))
            os.chmod(tmp, 0o600)
            os.replace(tmp, p)
        except OSError:
            pass
        _live.pop(user.lower(), None)


def live_state(user: str, now: float | None = None) -> tuple[bool, bool] | None:
    """(enabled, admin) from the directory, cached two minutes; None when the directory cannot
    say (samba down): then the token's role stands, so an outage does not lock admins out of
    the page they would fix it from."""
    from . import directory
    now = now or time.time()
    key = (user or "").lower()
    hit = _live.get(key)
    if hit and now - hit[0] < LIVE_SECONDS:
        return hit[1], hit[2]
    if not directory.available():
        return None
    d = directory._user_detail(key)
    if d.get("error"):
        return None
    adm = directory.is_admin(key)
    _live[key] = (now, bool(d.get("enabled", True)), bool(adm))
    return _live[key][1], _live[key][2]


def fresh_token(request: Request) -> str | None:
    """The current session re-issued now (after the person changed their own password,
    which signs out every other device)."""
    tok = request.cookies.get(COOKIE)
    if not tok:
        return None
    try:
        d = _serializer().loads(tok, max_age=int(load().web.session_hours) * 3600)
    except BadSignature:
        return None
    d["t"] = int(time.time()) + 1
    return _serializer().dumps(d)


# ---- too many wrong passwords ----------------------------------------------------------
# Samba's own lockout is off by default, and the dashboard was only slowed by 0.8 s a try
# (with forty worker threads, about fifty guesses a second). Ten wrong tries in fifteen
# minutes from one address, and that device waits. Never per account: anyone could lock
# someone else out that way, and round 4, 27 says no lockout.
FAIL_MAX, FAIL_WINDOW = 10, 900
_fails: dict[str, list[float]] = {}


def limited(hist: list[float], now: float, n: int = FAIL_MAX, window: int = FAIL_WINDOW) -> bool:
    """Pure: n or more failures inside the window."""
    return sum(1 for t in hist if now - t < window) >= n


def too_many(keys: list[str], now: float | None = None) -> bool:
    now = now or time.time()
    return any(limited(_fails.get(k, []), now) for k in keys if k)


def note_failure(keys: list[str], now: float | None = None) -> None:
    now = now or time.time()
    for k in keys:
        if k:
            _fails[k] = [t for t in _fails.get(k, []) if now - t < FAIL_WINDOW][-50:] + [now]


def clear_failures(keys: list[str]) -> None:
    for k in keys:
        _fails.pop(k, None)


def _check_path(request: Request, who: dict):
    """Members reach only the portal routes; everything else is the admin's.
    With [web] staff_access = "none" (the default since round 5) they reach only
    the sign-in routes: the dashboard shows them the 'your files are on your Mac' page.
    A staff PIN session (round 7, 162) reaches the phone checklist only, whatever staff_access says."""
    if who.get("pin") == "checklist" and not member_ok(request.url.path, "member", "none"):
        raise HTTPException(403, {"message": "A PIN opens the checklist only. Sign in with your password for the rest"})
    if who.get("role") == "admin":
        return
    path = request.url.path
    if not member_ok(path, who.get("role", "member"), staff_access()):
        raise HTTPException(403, {"message": "That part of the dashboard is for the administrator", "staff_access": staff_access()})


# ---- staff and member web access (Bradly, after round 5) ----------------------------
# "staff shouldn't have access to the actual server OS; the staff and volunteers use
# the Mac as normal, with everything syncing. Admins, Kristina, and myself will use the
# OS directly in the closet." So: "none" (the default) or "portal" (the member portal).
STAFF_ACCESS = ("none", "portal")
NONE_OK = ("/api/auth/", "/api/public/", "/api/health", "/api/checklist/")   # round 7, 89: the phone checklist page


def staff_access() -> str:
    v = os.environ.get("ARISE_STAFF_ACCESS") or str(load().web.get("staff_access", "none") or "none")
    return v if v in STAFF_ACCESS else "none"


REAUTH_SECONDS = 300


def reauth_token(request: Request) -> str | None:
    """A fresh session token with a 'recently typed the password' stamp (ra)."""
    tok = request.cookies.get(COOKIE)
    if not tok:
        return None
    try:
        d = _serializer().loads(tok, max_age=int(load().web.session_hours) * 3600)
    except BadSignature:
        return None
    d["ra"] = int(__import__("time").time())
    return _serializer().dumps(d)


FULL_PW_SECONDS = 600


def full_password_recent(request: Request, within: int = FULL_PW_SECONDS) -> bool:
    """Was this session signed in with the full password in the last ten minutes? Setting a
    PIN right after a password sign-in needs no second password; a PIN session never has it."""
    try:
        d = _serializer().loads(request.cookies.get(COOKIE) or "", max_age=int(load().web.session_hours) * 3600)
    except BadSignature:
        return False
    fp = d.get("fp")
    return bool(fp) and not d.get("pin") and 0 <= __import__("time").time() - float(fp) <= within


def recent_auth_ok(token_data: dict, now: float, within: int = REAUTH_SECONDS) -> bool:
    """Pure: was the password typed again within the last five minutes?"""
    ra = token_data.get("ra")
    return bool(ra) and 0 <= now - float(ra) <= within


def require_recent_auth(request: Request) -> dict:
    """A signed-in person who typed their password again in the last five minutes.
    For the dangerous clicks: delete a user, empty a Trash, shut the box down.
    Otherwise 403 with reauth: true, which the dashboard turns into a password box."""
    who = current_user(request)
    cfg = load()
    if cfg.demo:
        return who
    try:
        d = _serializer().loads(request.cookies.get(COOKIE) or "", max_age=int(cfg.web.session_hours) * 3600)
    except BadSignature:
        raise HTTPException(401, {"message": "Sign in"})
    if not recent_auth_ok(d, __import__("time").time()):
        raise HTTPException(403, {"reauth": True, "message": "Type your password again for this"})
    return who


def check_password_for(user: str, password: str) -> bool:
    """The same check the sign-in uses, for one person: the local admin hash or the directory."""
    cfg = load()
    if user == cfg.web.admin_user and cfg.web.admin_password_hash and verify_password(password, cfg.web.admin_password_hash):
        return True
    from . import directory
    return bool(password) and directory.authenticate(user, password)


def require_admin(request: Request) -> dict:
    who = current_user(request)
    if who.get("role") != "admin":
        raise HTTPException(403, {"message": "Administrator only"})
    return who


def member_ok(path: str, role: str, access: str = "portal") -> bool:
    """Pure helper for the tests: may this role call this path? A prefix matches only at a
    "/" boundary: "/api/me" lets members reach /api/me/... but never a later /api/media."""
    if role == "admin":
        return True
    allowed = NONE_OK if access == "none" else MEMBER_OK
    return any(path == m.rstrip("/") or path.startswith(m if m.endswith("/") else m + "/") for m in allowed)


def origin_ok(origin: str | None, host: str | None) -> bool:
    """Pure: may a request with this Origin act with the session cookie? The cookie is
    SameSite=Lax, which still lets a sibling site (vault., cloud., any app on
    *.ad.arisecenla.com) send it, so a change, and the root terminal, also needs the page
    that asked to be this dashboard. No Origin at all is a non-browser client (curl, the
    tests); a browser always sends one on a POST and on a websocket."""
    if origin is None:
        return True
    if not host or origin == "null":
        return False
    from urllib.parse import urlsplit
    o = urlsplit(origin)
    return bool(o.netloc) and o.netloc.lower() == host.lower()

"""Logins: the admin (bcrypt hash in arise.toml) and every directory user (Kerberos), signed session cookie.

- No hash set and not demo  → every API call answers 401 with setup=True; the
  dashboard shows "run `arisectl admin set-password`" instead of a login box.
- Demo mode                 → no login at all.
"""
from __future__ import annotations

import os
import secrets
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


MEMBER_OK = ("/api/auth/", "/api/me", "/api/files/", "/api/search", "/api/links", "/api/sermons", "/api/bible", "/api/sites", "/api/health", "/api/church", "/api/sunday", "/api/kiosk/open", "/api/public/", "/api/push/", "/api/about/week", "/api/about/whatsnew", "/api/calendar", "/api/weather", "/api/help", "/api/people")


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
    return _serializer().dumps({"u": who["user"], "r": who["role"], "v": who["via"]}), who


def current_user(request: Request) -> dict:
    cfg = load()
    tok = request.cookies.get(COOKIE)
    if cfg.demo:
        who = {"user": "demo", "role": "admin", "demo": True}
        if tok:
            try:
                d = _serializer().loads(tok, max_age=int(cfg.web.session_hours) * 3600)
                who = {"user": d["u"], "role": d.get("r", "admin"), "demo": True}
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
    who = {"user": data["u"], "role": data.get("r", "admin"), "demo": False}
    _check_path(request, who)
    return who


def _check_path(request: Request, who: dict):
    """Members reach only the portal routes; everything else is the admin's.
    With [web] staff_access = "none" (the default since round 5) they reach only
    the sign-in routes: the dashboard shows them the 'your files are on your Mac' page."""
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
NONE_OK = ("/api/auth/", "/api/public/", "/api/health")


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
    """Pure helper for the tests: may this role call this path?"""
    if role == "admin":
        return True
    allowed = NONE_OK if access == "none" else MEMBER_OK
    return any(path == m.rstrip("/") or path.startswith(m) for m in allowed)

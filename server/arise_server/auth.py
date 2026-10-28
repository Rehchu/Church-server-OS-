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


MEMBER_OK = ("/api/auth/", "/api/me", "/api/files/", "/api/search", "/api/links", "/api/sermons", "/api/bible", "/api/sites", "/api/health")


def login(user: str, password: str) -> tuple[str, dict] | None:
    """Returns (token, who) or None. The admin user is checked against the bcrypt
    hash in arise.toml; everyone else against the directory (Kerberos)."""
    from . import directory
    cfg = load()
    user = (user or "").strip().lower()
    who = None
    if user == cfg.web.admin_user and cfg.web.admin_password_hash and verify_password(password, cfg.web.admin_password_hash):
        who = {"user": user, "role": "admin", "via": "local"}
    elif cfg.web.get("member_login", True) and directory.authenticate(user, password):
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
    """Members reach only the portal routes; everything else is the admin's."""
    if who.get("role") == "admin":
        return
    path = request.url.path
    if not any(path == m.rstrip("/") or path.startswith(m) for m in MEMBER_OK):
        raise HTTPException(403, {"message": "That part of the dashboard is for the administrator"})


def require_admin(request: Request) -> dict:
    who = current_user(request)
    if who.get("role") != "admin":
        raise HTTPException(403, {"message": "Administrator only"})
    return who


def member_ok(path: str, role: str) -> bool:
    """Pure helper for the tests: may this role call this path?"""
    if role == "admin":
        return True
    return any(path == m.rstrip("/") or path.startswith(m) for m in MEMBER_OK)

"""Admin login: one admin user, bcrypt hash in arise.toml, signed session cookie.

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


def login(user: str, password: str) -> str | None:
    cfg = load()
    if user != cfg.web.admin_user or not cfg.web.admin_password_hash:
        return None
    if not verify_password(password, cfg.web.admin_password_hash):
        return None
    return _serializer().dumps({"u": user})


def current_user(request: Request) -> dict:
    cfg = load()
    if cfg.demo:
        return {"user": "demo", "demo": True}
    if not cfg.web.admin_password_hash:
        raise HTTPException(401, {"setup": True, "message": "No admin password yet. On the server run: sudo arisectl admin set-password"})
    tok = request.cookies.get(COOKIE)
    if not tok:
        raise HTTPException(401, {"message": "Sign in"})
    try:
        data = _serializer().loads(tok, max_age=int(cfg.web.session_hours) * 3600)
    except BadSignature:
        raise HTTPException(401, {"message": "Session expired, sign in again"})
    return {"user": data["u"], "demo": False}

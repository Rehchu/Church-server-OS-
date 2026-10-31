"""Share links: a public URL for one file or folder, living until removed (or until a chosen date).

Stored in <state_dir>/links.json as {token: {root, path, name, user, created, expires, note, downloads}}.
The link serves the file (or a zip of the folder) at GET /s/<token> with no login.
Members may link only what they can browse (files.roots scopes that); admins anything.
"""
from __future__ import annotations

import json
import os
import secrets
import tempfile
import time
from datetime import datetime, timedelta

from . import files
from .config import load

_DEMO: dict = {}


def _path() -> str:
    cfg = load()
    return str(cfg.state_dir / "links.json")


def _load() -> dict:
    cfg = load()
    if cfg.demo:
        if not _DEMO:
            _DEMO.update({"demo7x2k9q": {"root": "home", "path": "/Documents/Sunday setlist 2026-10-26.pdf", "name": "Sunday setlist 2026-10-26.pdf", "user": "bradly",
                                         "created": _iso(-2 * 86400), "expires": _iso(5 * 86400), "note": "for the worship team", "downloads": 3, "dir": False}})
        return _DEMO
    try:
        with open(_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(d: dict):
    if load().demo:
        return
    p = _path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, p)


def _iso(offset_s: float = 0) -> str:
    return (datetime.now() + timedelta(seconds=offset_s)).isoformat(timespec="minutes")


def link_refused(root: str) -> str:
    """Pure: the places a no-login link never reaches. Something shared with you is the
    owner's to hand out (round 5, 19: Share with... is the way to share); the Pastors folder is
    the two pastors' only (round 5, 18)."""
    if root.startswith("shared:"):
        return "that was shared with you: ask its owner to make the link"
    if root == "pastors":
        return "the Pastors folder never gets a link that works without signing in"
    return ""


def life(days: int | None, default: int, most: int) -> int:
    """Pure: a link's life in days (round 7, 47: each ends after 7 days). 0 = never, only where
    [links] max_days is 0 too (the old behaviour, by hand in arise.toml)."""
    days = default if days is None else int(days)
    if most > 0:
        return max(1, min(days if days > 0 else most, most))
    return max(0, days)


def create(root: str, rel: str, who: dict, days: int | None = None, note: str = "") -> dict:
    cfg = load()
    # Round 7, 47: only admins make a link that works without signing in, and each ends after 7 days.
    if cfg.links.get("admins_only", True) and who.get("role") != "admin":
        return {"ok": False, "err": "only an administrator makes an outside link; use Share with… for people at church"}
    days = life(days, int(cfg.links.days), int(cfg.links.max_days))
    expires = None if days <= 0 else _iso(days * 86400)
    rs = {r["id"]: r for r in files.roots(who)}
    if root not in rs:
        return {"ok": False, "err": "not a place you can share from"}
    why = link_refused(root)
    if why:
        return {"ok": False, "err": why}
    rel = "/" + rel.strip("/")
    name = os.path.basename(rel) or rs[root]["name"]
    is_dir = False
    if cfg.demo:
        from . import sharing
        key = files._demo_rel(root, rel, who)
        hit = files.demo_find(key) if key and key != "/" and not sharing.hidden_demo(key, who) else None
        if key and key != "/" and not hit:
            return {"ok": False, "err": "no such file"}
        is_dir = bool(hit[1]) if hit else True
    else:
        target = files._resolve(rs[root], rel, who, "share link")
        if not target or not os.path.exists(target):
            return {"ok": False, "err": "no such file"}
        is_dir = os.path.isdir(target)
    tok = secrets.token_urlsafe(9)
    d = _load()
    d[tok] = {"root": root, "path": rel, "name": name, "user": who["user"], "role": who.get("role", "member"), "created": _iso(),
              "expires": expires, "note": note[:120], "downloads": 0, "dir": is_dir}
    _save(d)
    return {"ok": True, "token": tok, "link": d[tok], "demo": cfg.demo}


def mine(who: dict) -> dict:
    d = _load()
    now = _iso()
    out = []
    for tok, l in d.items():
        if who.get("role") == "admin" or l["user"] == who["user"]:
            out.append(dict(l, token=tok, expired=bool(l.get("expires")) and l["expires"] < now))
    out.sort(key=lambda l: l["created"], reverse=True)
    return {"links": out, "demo": load().demo}


def revoke(token: str, who: dict) -> dict:
    d = _load()
    l = d.get(token)
    if not l:
        return {"ok": False, "err": "no such link"}
    if who.get("role") != "admin" and l["user"] != who["user"]:
        return {"ok": False, "err": "not your link"}
    del d[token]
    _save(d)
    return {"ok": True}


def resolve(token: str) -> dict | None:
    """The file behind a live token, as {"path", "name", "dir"}; None if unknown or expired."""
    d = _load()
    l = d.get(token)
    if not l or (l.get("expires") and l["expires"] < _iso()):
        return None
    if load().demo:
        return {"path": None, "name": l["name"], "dir": l["dir"], "demo": True}
    if link_refused(l["root"]):
        return None
    # The owner's places as they are now, not when the link was made: a person who left, was
    # disabled or lost the group that let them see a share takes their links with them.
    owner = {"user": l["user"], "role": _owner_role(l)}
    if owner["role"] is None:
        return None
    rs = {r["id"]: r for r in files.roots(owner)}
    base = rs.get(l["root"])
    if base is None:
        return None
    target = files._resolve(base["path"], l["path"])
    if not target or not os.path.exists(target):
        return None
    l["downloads"] = int(l.get("downloads", 0)) + 1
    _save(d)
    return {"path": target, "name": l["name"], "dir": os.path.isdir(target)}


def _owner_role(l: dict) -> str | None:
    """admin / member for the link's owner today, or None when the account is gone or disabled.
    The local dashboard admin is not a directory account and stays admin."""
    from . import directory
    user = l["user"]
    if user == load().web.admin_user:
        return "admin"
    if not directory.available():
        return l.get("role") or "admin"   # no directory to ask (Windows profile): as it was
    d = directory._user_detail(user)
    if d.get("error") or not d.get("enabled", True):
        return None
    return "admin" if directory.is_admin(user) else "member"


def zip_folder(path: str) -> str | None:
    """Zip a folder into a temp file; None if it is over the configured limit."""
    cfg = load()
    files_in = zip_members(path)
    if sum(n for _, _, n in files_in) > int(cfg.links.max_zip_bytes):
        return None
    import zipfile
    tmp = tempfile.mkdtemp(prefix="arise-link-")
    out = os.path.join(tmp, (os.path.basename(path) or "folder") + ".zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for full, arc, _ in files_in:
            z.write(full, arc)
    return out


def zip_members(path: str) -> list[tuple[str, str, int]]:
    """(file, name in the zip, size) for every regular file inside the folder. A link that
    points outside it (Shared with me holds links to other people's things) is left out:
    a share link hands over this folder, nothing it points at."""
    base = os.path.realpath(path)
    out = []
    for dp, dirs, fs in os.walk(base):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(dp, d))]
        for f in fs:
            full = os.path.join(dp, f)
            real = os.path.realpath(full)
            if not (real == base or real.startswith(base + os.sep)) or not os.path.isfile(real):
                continue
            try:
                size = os.path.getsize(real)
            except OSError:
                continue
            out.append((real, os.path.relpath(full, base), size))
    return out


def sweep() -> int:
    """Drop expired links; returns how many."""
    d = _load()
    now = _iso()
    dead = [t for t, l in d.items() if l.get("expires") and l["expires"] < now]
    for t in dead:
        del d[t]
    if dead:
        _save(d)
    return len(dead)

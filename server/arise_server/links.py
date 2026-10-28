"""Share links: a public URL for one file or folder, living until removed (or until a chosen date).

Stored in <state_dir>/links.json as {token: {root, path, name, user, created, expires, note, downloads}}.
The link serves the file (or a zip of the folder) at GET /s/<token> with no login.
Members may link only what they can browse (files.roots scopes that); admins anything.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
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


def create(root: str, rel: str, who: dict, days: int | None = None, note: str = "") -> dict:
    cfg = load()
    # Bradly (Oct 28): a link lives until it is removed unless a life is picked for it.
    days = int(cfg.links.days) if days is None else int(days)
    expires = None if days <= 0 else _iso(max(1, min(days, int(cfg.links.max_days))) * 86400)
    rs = {r["id"]: r for r in files.roots(who)}
    if root not in rs:
        return {"ok": False, "err": "not a place you can share from"}
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
    d[tok] = {"root": root, "path": rel, "name": name, "user": who["user"], "created": _iso(), "expires": expires, "note": note[:120], "downloads": 0, "dir": is_dir}
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
    owner = {"user": l["user"], "role": "admin"}  # the owner's roots at creation; admin roots cover every path
    rs = {r["id"]: r for r in files.roots(owner)}
    base = rs.get(l["root"]) or ({"path": os.path.join(load().directory.homes_path, l["user"])} if l["root"] == "home" else None)
    if base is None:
        from . import shares
        for sh in shares.list_shares().get("shares", []):
            if l["root"] == "share:" + sh["name"]:
                base = {"path": sh["path"]}
    if base is None:
        return None
    target = files._resolve(base["path"], l["path"])
    if not target or not os.path.exists(target):
        return None
    l["downloads"] = int(l.get("downloads", 0)) + 1
    _save(d)
    return {"path": target, "name": l["name"], "dir": os.path.isdir(target)}


def zip_folder(path: str) -> str | None:
    """Zip a folder into a temp file; None if it is over the configured limit."""
    cfg = load()
    total = 0
    for dp, _, fs in os.walk(path):
        for f in fs:
            try:
                total += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
            if total > int(cfg.links.max_zip_bytes):
                return None
    tmp = tempfile.mkdtemp(prefix="arise-link-")
    return shutil.make_archive(os.path.join(tmp, os.path.basename(path) or "folder"), "zip", path)


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

"""The wallpaper's icons (round 5, 24): the signed-in person's Desktop folder,
shown like a Mac. Listing, opening, moving and the Trash go through the usual
files routes; this module only says where the folder is and keeps where each
icon was dragged to (per person, <state_dir>/desktop/<user>.json).
"""
from __future__ import annotations

import json
import os
import re

from .config import load

MAX_ICONS = 300


def location(who: dict) -> dict:
    """Where this person's Desktop folder is, as a (root, path) the files routes understand."""
    user = who.get("user", "")
    if who.get("role") == "admin":
        return {"root": "data", "path": f"/homes/{user}/Desktop"}
    return {"root": "home", "path": "/Desktop"}


def _path(user: str) -> str:
    return str(load().state_dir / "desktop" / f"{user}.json")


def _ok_user(user: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._-]{1,64}", user or "")) and not user.startswith(".")


def positions(user: str) -> dict:
    if not _ok_user(user):
        return {}
    if load().demo:
        from . import demo_state
        return demo_state.get(f"desktop.pos.{user}", lambda: dict(DEMO_POSITIONS) if user == "bradly" else {})
    try:
        with open(_path(user), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def clean_positions(raw: dict) -> dict:
    """Pure: {name: [x, y]} with sane numbers only (0 to 10000 px), at most MAX_ICONS names."""
    out = {}
    for k, v in list((raw or {}).items())[:MAX_ICONS]:
        if not isinstance(k, str) or not k or "/" in k or len(k) > 255:
            continue
        if isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(n, (int, float)) for n in v):
            x, y = int(v[0]), int(v[1])
            if 0 <= x <= 10000 and 0 <= y <= 10000:
                out[k] = [x, y]
    return out


def save_positions(user: str, raw: dict) -> dict:
    if not _ok_user(user):
        return {"ok": False, "err": "bad user"}
    pos = clean_positions(raw)
    if load().demo:
        from . import demo_state
        demo_state.put(f"desktop.pos.{user}", pos)
        return {"ok": True, "demo": True, "count": len(pos)}
    p = _path(user)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(pos, f)
    os.replace(p + ".tmp", p)
    return {"ok": True, "count": len(pos)}


def move(root_id: str, rel: str, to_dir: str, who: dict) -> dict:
    """Move a file or folder to another folder in the same place (Finder onto the Desktop, a
    desktop icon into a folder). Never across places, never over an existing name, never into itself."""
    from . import audit, files
    cfg = load()
    rs = {r["id"]: r for r in files.roots(who)}
    if root_id not in rs:
        return {"ok": False, "err": "not a place you can change"}
    if rs[root_id].get("writable", True) is False:
        return {"ok": False, "err": "that share is read-only for you"}
    src_rel = "/" + rel.strip("/")
    dst_dir = "/" + to_dir.strip("/") if to_dir.strip("/") else "/"
    name = src_rel.rsplit("/", 1)[-1]
    if not name or name.startswith(".") or src_rel == "/":
        return {"ok": False, "err": "bad name"}
    if dst_dir == src_rel or dst_dir.startswith(src_rel + "/"):
        return {"ok": False, "err": "a folder cannot go inside itself"}
    if dst_dir == (src_rel.rsplit("/", 1)[0] or "/"):
        return {"ok": True, "unchanged": True}
    if cfg.demo:
        sk, dk = files._demo_rel(root_id, src_rel, who), files._demo_rel(root_id, dst_dir, who)
        if sk is None or dk is None or dk not in files.tree():
            return {"ok": False, "err": "the sample has nothing there"}
        if any(e[0] == name for e in files.tree().get(dk, [])):
            return {"ok": False, "err": f"{name} already exists there"}
        taken = files.demo_take(sk)
        if not taken:
            return {"ok": False, "err": "no such file"}
        files.demo_put(dk, taken)
        return {"ok": True, "demo": True, "path": dst_dir.rstrip("/") + "/" + name}
    base = rs[root_id]["path"]
    src, dst = files._resolve(base, src_rel), files._resolve(base, dst_dir)
    if not src or not os.path.exists(src):
        return {"ok": False, "err": "no such file"}
    if not dst or not os.path.isdir(dst):
        return {"ok": False, "err": "folder not found"}
    target = os.path.join(dst, name)
    if os.path.exists(target):
        return {"ok": False, "err": f"{name} already exists there"}
    os.rename(src, target)
    audit.record(who.get("user", ""), "files.move", f"{root_id}:{src_rel}", detail=f"to {dst_dir}")
    return {"ok": True, "path": dst_dir.rstrip("/") + "/" + name}


DEMO_POSITIONS = {}

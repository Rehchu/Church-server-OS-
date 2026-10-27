"""A read-mostly file browser over the data root (homes, shares, automator, apps).

Listing and download only, inside /srv/arise and the NAS mount. No delete:
deleting is Bradly's click, in Finder. Upload lands in the chosen folder.
"""
from __future__ import annotations

import os
import stat
from datetime import datetime

from .config import load

DEMO_TREE = {
    "/": [("homes", True), ("shares", True), ("automator", True), ("apps", True), ("backups", True)],
    "/homes": [("bradly", True), ("media-mac", True), ("office", True), ("kids-checkin", True)],
    "/homes/bradly": [("Desktop", True), ("Documents", True), ("Pictures", True)],
    "/homes/bradly/Documents": [("Sunday setlist 2026-10-26.pdf", False, 182_000), ("Proclaim backgrounds", True), ("THUMB_2026-10-26_whose_hand.jpg", False, 412_000)],
    "/shares": [("media", True), ("staff", True), ("leadership", True), ("kids", True), ("graphics", True)],
    "/shares/graphics": [("lower-thirds", True), ("loops", True), ("ARISE_BRAND_KIT.md", False, 14_000), ("flame-logo.png", False, 88_000)],
    "/automator": [("ARISE_YouTube_Updater", True)],
    "/automator/ARISE_YouTube_Updater": [("automator", True), ("transcripts", True), ("thumbnails", True), ("song_bank.json", False, 240_000), ("speakers.json", False, 2_100), ("youtube_updater.py", False, 61_000)],
    "/automator/ARISE_YouTube_Updater/automator": [("reports", True), ("arise_daily.py", False, 23_000), ("holds.json", False, 1_800), ("worklist.json", False, 3_400), ("LATEST_REPORT.md", False, 2_900), ("quota_ledger.json", False, 9_200)],
    "/apps": [("filebrowser", True), ("uptime-kuma", True), ("syncthing", True)],
    "/backups": [("github-mirror", True)],
    "/backups/github-mirror": [("Church-server-OS-.git", True), ("arise-youtube-automation.git", True), ("arisechurch.git", True), ("arisehub.git", True)],
}


def roots() -> list[dict]:
    cfg = load()
    out = [{"id": "data", "name": "Server", "path": cfg.system.data_root}]
    if cfg.nas.enabled:
        out.append({"id": "nas", "name": "Synology", "path": cfg.nas.mount})
    return out


def _resolve(root: str, rel: str) -> str | None:
    base = os.path.realpath(root)
    target = os.path.realpath(os.path.join(base, rel.lstrip("/")))
    if target != base and not target.startswith(base + os.sep):
        return None
    return target


def listing(root_id: str, rel: str = "/") -> dict:
    cfg = load()
    rs = {r["id"]: r for r in roots()}
    if root_id not in rs:
        return {"error": "unknown root"}
    root = rs[root_id]["path"]
    rel = "/" + rel.strip("/") if rel.strip("/") else "/"
    if cfg.demo or not os.path.isdir(root):
        entries = DEMO_TREE.get(rel, [])
        return {"demo": True, "root": root_id, "path": rel, "entries": [{"name": e[0], "dir": e[1], "size": (e[2] if len(e) > 2 else None), "mtime": "2026-10-26T14:02"} for e in entries]}
    target = _resolve(root, rel)
    if not target or not os.path.isdir(target):
        return {"error": "not a folder", "root": root_id, "path": rel}
    entries = []
    try:
        with os.scandir(target) as it:
            for e in it:
                if e.name.startswith("."):
                    continue
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                entries.append({"name": e.name, "dir": e.is_dir(follow_symlinks=False), "size": None if e.is_dir() else st.st_size, "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes")})
    except PermissionError:
        return {"error": "no permission", "root": root_id, "path": rel}
    entries.sort(key=lambda x: (not x["dir"], x["name"].lower()))
    return {"demo": False, "root": root_id, "path": rel, "entries": entries[:2000], "truncated": len(entries) > 2000}


def file_path(root_id: str, rel: str) -> str | None:
    rs = {r["id"]: r for r in roots()}
    if root_id not in rs:
        return None
    t = _resolve(rs[root_id]["path"], rel)
    return t if t and os.path.isfile(t) else None


def save_upload(root_id: str, rel: str, filename: str, data: bytes) -> dict:
    cfg = load()
    rs = {r["id"]: r for r in roots()}
    if root_id not in rs or cfg.demo:
        return {"ok": True, "demo": True}
    name = os.path.basename(filename or "").replace("\x00", "")
    if not name or name.startswith("."):
        return {"ok": False, "err": "bad file name"}
    folder = _resolve(rs[root_id]["path"], rel)
    if not folder or not os.path.isdir(folder):
        return {"ok": False, "err": "folder not found"}
    dest = os.path.join(folder, name)
    if os.path.exists(dest):
        return {"ok": False, "err": f"{name} already exists here; rename one of them first"}
    with open(dest, "wb") as f:
        f.write(data)
    return {"ok": True, "path": dest, "bytes": len(data)}

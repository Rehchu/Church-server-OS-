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
    "/homes/office": [("Desktop", True), ("Documents", True)],
    "/homes/office/Documents": [("Bulletin 2026-11-01.docx", False, 96_000), ("Visitor cards October.xlsx", False, 41_000), ("Letters", True)],
    "/shares": [("media", True), ("staff", True), ("leadership", True), ("kids", True), ("graphics", True)],
    "/shares/staff": [("Calendar 2026-27.pdf", False, 310_000), ("Forms", True), ("Phone list.xlsx", False, 22_000)],
    "/shares/media": [("sermons", True), ("thumbnails", True), ("loops", True), ("Sunday 2026-10-26 program.mp4", False, 6_420_000_000)],
    "/shares/graphics": [("lower-thirds", True), ("loops", True), ("ARISE_BRAND_KIT.md", False, 14_000), ("flame-logo.png", False, 88_000)],
    "/automator": [("ARISE_YouTube_Updater", True)],
    "/automator/ARISE_YouTube_Updater": [("automator", True), ("transcripts", True), ("thumbnails", True), ("song_bank.json", False, 240_000), ("speakers.json", False, 2_100), ("youtube_updater.py", False, 61_000)],
    "/automator/ARISE_YouTube_Updater/automator": [("reports", True), ("arise_daily.py", False, 23_000), ("holds.json", False, 1_800), ("worklist.json", False, 3_400), ("LATEST_REPORT.md", False, 2_900), ("quota_ledger.json", False, 9_200)],
    "/apps": [("filebrowser", True), ("uptime-kuma", True), ("syncthing", True)],
    "/backups": [("github-mirror", True)],
    "/backups/github-mirror": [("Church-server-OS-.git", True), ("arise-youtube-automation.git", True), ("arisechurch.git", True), ("arisehub.git", True)],
}


def roots(who: dict | None = None) -> list[dict]:
    """What this person may browse. The admin sees the whole data root and the
    NAS; a member sees their own home folder and the shares their groups allow."""
    cfg = load()
    if who is None or who.get("role", "admin") == "admin":
        out = [{"id": "data", "name": "Server", "path": cfg.system.data_root}]
        if cfg.nas.enabled:
            out.append({"id": "nas", "name": "Synology", "path": cfg.nas.mount})
        return out
    from . import directory, shares
    user = who["user"]
    out = [{"id": "home", "name": "My files", "path": os.path.join(cfg.directory.homes_path, user), "home": True}]
    groups = directory.user_groups(user)
    for sh in shares.list_shares().get("shares", []):
        if sh["name"] in ("homes", "sysvol", "netlogon") or not sh.get("browseable", True):
            continue
        if shares.can_use(sh, user, groups):
            out.append({"id": "share:" + sh["name"], "name": sh["name"], "path": sh["path"], "share": True,
                        "writable": bool(sh.get("writable")) and (not sh.get("write_list") or shares.can_use({"valid_users": sh["write_list"]}, user, groups))})
    return out


def _demo_rel(root_id: str, rel: str, who: dict | None) -> str | None:
    """Map a member's root onto the sample tree (which is keyed from the data root)."""
    if root_id == "data":
        return rel
    if root_id == "home" and who:
        return ("/homes/" + who["user"] + ("" if rel == "/" else rel))
    if root_id.startswith("share:"):
        return ("/shares/" + root_id[6:] + ("" if rel == "/" else rel))
    return None


def _resolve(root: str, rel: str) -> str | None:
    base = os.path.realpath(root)
    target = os.path.realpath(os.path.join(base, rel.lstrip("/")))
    if target != base and not target.startswith(base + os.sep):
        return None
    return target


def listing(root_id: str, rel: str = "/", who: dict | None = None) -> dict:
    cfg = load()
    rs = {r["id"]: r for r in roots(who)}
    if root_id not in rs:
        return {"error": "unknown root"}
    root = rs[root_id]["path"]
    rel = "/" + rel.strip("/") if rel.strip("/") else "/"
    if cfg.demo or not os.path.isdir(root):
        entries = DEMO_TREE.get(_demo_rel(root_id, rel, who) or "", [])
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


def file_path(root_id: str, rel: str, who: dict | None = None) -> str | None:
    rs = {r["id"]: r for r in roots(who)}
    if root_id not in rs:
        return None
    t = _resolve(rs[root_id]["path"], rel)
    return t if t and os.path.isfile(t) else None


def _writable(rs: dict, root_id: str) -> bool:
    r = rs.get(root_id) or {}
    return r.get("writable", True) is not False


def save_upload(root_id: str, rel: str, filename: str, data: bytes, who: dict | None = None) -> dict:
    cfg = load()
    rs = {r["id"]: r for r in roots(who)}
    if root_id in rs and not _writable(rs, root_id):
        return {"ok": False, "err": "that share is read-only for you"}
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


def make_folder(root_id: str, rel: str, name: str, who: dict | None = None) -> dict:
    cfg = load()
    rs = {r["id"]: r for r in roots(who)}
    if root_id in rs and not _writable(rs, root_id):
        return {"ok": False, "err": "that share is read-only for you"}
    if root_id not in rs or cfg.demo:
        return {"ok": True, "demo": True}
    name = os.path.basename(name or "").strip()
    if not name or name.startswith(".") or "/" in name:
        return {"ok": False, "err": "bad folder name"}
    folder = _resolve(rs[root_id]["path"], rel)
    if not folder or not os.path.isdir(folder):
        return {"ok": False, "err": "folder not found"}
    dest = os.path.join(folder, name)
    if os.path.exists(dest):
        return {"ok": False, "err": f"{name} already exists"}
    os.makedirs(dest)
    return {"ok": True, "path": dest}


_search_cache: dict = {}


def search(q: str, limit: int = 40, who: dict | None = None) -> dict:
    """Name search over what this person may browse, bounded and cached (admin: the whole index)."""
    import time
    q = (q or "").strip().lower()
    if len(q) < 2:
        return {"hits": []}
    cfg = load()
    member = who is not None and who.get("role") != "admin"
    if cfg.demo:
        hits = []
        for path, entries in DEMO_TREE.items():
            for e in entries:
                if q in e[0].lower():
                    hits.append({"root": "data", "path": (path.rstrip("/") + "/" + e[0]), "name": e[0], "dir": e[1], "size": e[2] if len(e) > 2 else None})
        if member:  # re-key the sample hits onto the member's roots
            out = []
            for h in hits:
                for r in roots(who):
                    pref = _demo_rel(r["id"], "/", who)
                    if pref and h["path"].startswith(pref + "/"):
                        out.append(dict(h, root=r["id"], path=h["path"][len(pref):]))
            hits = out
        return {"demo": True, "hits": hits[:limit]}
    if member:  # a member's roots are small: walk them now, no shared index
        hits = []
        for r in roots(who):
            base = r["path"]
            if not os.path.isdir(base):
                continue
            n = 0
            for dirpath, dirs, fs in os.walk(base):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                rel = dirpath[len(base):] or "/"
                for nm in dirs + [f for f in fs if not f.startswith(".")]:
                    if q in nm.lower():
                        hits.append({"root": r["id"], "path": rel.rstrip("/") + "/" + nm, "name": nm, "dir": nm in dirs, "size": None})
                n += len(dirs) + len(fs)
                if n > 20000 or len(hits) >= limit:
                    break
        return {"demo": False, "hits": hits[:limit]}
    now = time.time()
    if now - _search_cache.get("t", 0) > 120:
        index = []
        for r in roots():
            base = r["path"]
            if not os.path.isdir(base):
                continue
            n = 0
            for dirpath, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", "@eaDir", "#recycle")]
                rel = dirpath[len(base):] or "/"
                for d in dirs:
                    index.append((r["id"], rel.rstrip("/") + "/" + d, d, True, None))
                for f in files:
                    if not f.startswith("."):
                        index.append((r["id"], rel.rstrip("/") + "/" + f, f, False, None))
                n += len(dirs) + len(files)
                if n > 60000 or time.time() - now > 8:
                    break
        _search_cache.update({"t": now, "index": index})
    hits = [{"root": a, "path": b, "name": c, "dir": d, "size": e} for a, b, c, d, e in _search_cache.get("index", []) if q in c.lower()]
    hits.sort(key=lambda h: (not h["name"].lower().startswith(q), h["dir"] is False, h["name"].lower()))
    return {"demo": False, "hits": hits[:limit]}

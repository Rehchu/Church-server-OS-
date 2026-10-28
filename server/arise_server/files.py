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
    "/homes/bradly": [("Desktop", True), ("Documents", True), ("Photos", True), ("Videos", True), ("Music", True), ("Downloads", True)],
    "/homes/bradly/Photos": [("2026-10-19 baptisms", True), ("stage-wide.jpg", False, 3_900_000)],
    "/homes/bradly/Downloads": [("proclaim-6.4.dmg", False, 310_000_000)],
    "/homes/bradly/Documents": [("Sunday setlist 2026-10-26.pdf", False, 182_000), ("Proclaim backgrounds", True), ("THUMB_2026-10-26_whose_hand.jpg", False, 412_000)],
    "/homes/office": [("Desktop", True), ("Documents", True), ("Photos", True), ("Videos", True), ("Music", True), ("Downloads", True)],
    "/homes/office/Photos": [("Fall festival 2026", True)],
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


# Sample contents for the editor (demo mode). Nothing here is a church record.
DEMO_TEXT = {
    "ARISE_BRAND_KIT.md": "# Arise brand kit\n\nThe house look for every graphic: ink background, the red flame, Anton for titles, Oswald for everything else.\n\n## Colours\n\n| Name | Hex |\n|---|---|\n| Ink | #0A0A0C |\n| Red | #D6222D |\n| Bone | #F4F2F0 |\n\n## Rules\n\n- Titles in Anton, all caps.\n- The flame never stretches.\n- Sunday Service thumbnails keep red; Glory Night matches the stage.\n",
    "LATEST_REPORT.md": "# Arise YouTube - automated run\n\n3 jobs done - 0 failed - 1 skipped\n",
    "holds.json": "{\n  \"holds\": []\n}\n",
}

# Every home starts with these (Bradly, Oct 28): made at first sign-in, by the
# dashboard (ensure_home) and by Samba's root preexec on the [homes] share.
HOME_FOLDERS = ("Documents", "Photos", "Videos", "Music", "Downloads")


def ensure_home(user: str) -> dict:
    """Make <homes>/<user> and its five folders if missing; chown to the user when
    the OS knows them (a domain user through winbind). Never touches what exists."""
    cfg = load()
    if cfg.demo or not user or "/" in user or user.startswith("."):
        return {"ok": True, "demo": cfg.demo, "made": []}
    home = os.path.join(cfg.directory.homes_path, user)
    made = []
    try:
        if not os.path.isdir(home):
            os.makedirs(home, mode=0o700); made.append(home)
        for f in HOME_FOLDERS:
            d = os.path.join(home, f)
            if not os.path.isdir(d):
                os.makedirs(d, mode=0o700); made.append(d)
        try:
            import pwd
            pw = pwd.getpwnam(user)
            for d in made:
                os.chown(d, pw.pw_uid, pw.pw_gid)
        except (KeyError, OSError):
            pass
    except OSError as e:
        return {"ok": False, "err": str(e), "made": made}
    return {"ok": True, "demo": False, "made": made}


def all_of(folder: str, who: dict | None = None) -> dict:
    """The administrator's merged view: everyone's <folder> (Documents, Photos, …)
    side by side, each entry labelled with its owner. Admin only; a member never
    sees another person's folder (files.roots keeps them in their own)."""
    cfg = load()
    if who is not None and who.get("role", "admin") != "admin":
        return {"error": "administrator only", "entries": []}
    if folder not in HOME_FOLDERS:
        return {"error": "not one of the home folders", "entries": []}
    entries = []
    if cfg.demo:
        t = tree()
        for path, es in t.items():
            parts = path.split("/")
            if len(parts) == 4 and parts[1] == "homes" and parts[3] == folder:
                for e in es:
                    entries.append({"owner": parts[2], **entry_dict(e), "root": "data", "path": f"{path}/{e[0]}"})
        owners = sorted({p.split("/")[2] for p in t if p.startswith("/homes/") and len(p.split("/")) == 3})
        return {"demo": True, "folder": folder, "owners": owners, "entries": entries}
    homes = cfg.directory.homes_path
    owners = []
    if os.path.isdir(homes):
        for u in sorted(os.listdir(homes)):
            d = os.path.join(homes, u, folder)
            if u.startswith(".") or not os.path.isdir(d):
                continue
            owners.append(u)
            try:
                with os.scandir(d) as it:
                    for e in it:
                        if e.name.startswith("."):
                            continue
                        try:
                            st = e.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        entries.append({"owner": u, "name": e.name, "dir": e.is_dir(follow_symlinks=False), "size": None if e.is_dir() else st.st_size,
                                        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes"), "root": "data", "path": f"/homes/{u}/{folder}/{e.name}"})
            except PermissionError:
                continue
            if len(entries) > 5000:
                break
    entries.sort(key=lambda x: (x["owner"].lower(), not x["dir"], x["name"].lower()))
    return {"demo": False, "folder": folder, "owners": owners, "entries": entries[:5000], "truncated": len(entries) > 5000}


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


# ---- the sample file system (demo mode) ------------------------------------------
# DEMO_TREE is the seed. tree() is the live copy a sample server's clicks change:
# New Folder, Upload, Trash, Put Back, Save in the editor. In memory only.
def tree() -> dict:
    from . import demo_state
    return demo_state.get("files.tree", DEMO_TREE)


def _now_min() -> str:
    return datetime.now().isoformat(timespec="minutes")


def entry_dict(e: tuple) -> dict:
    return {"name": e[0], "dir": e[1], "size": (e[2] if len(e) > 2 else None), "mtime": (e[3] if len(e) > 3 else "2026-10-26T14:02")}


def _split(key: str) -> tuple[str, str]:
    key = "/" + key.strip("/")
    parent, _, name = key.rpartition("/")
    return (parent or "/"), name


def _join(parent: str, name: str) -> str:
    return parent.rstrip("/") + "/" + name


def demo_find(key: str) -> tuple | None:
    parent, name = _split(key)
    return next((e for e in tree().get(parent, []) if e[0] == name), None)


def demo_add(parent: str, name: str, is_dir: bool, size: int | None = None) -> dict:
    t = tree()
    es = t.setdefault(parent, [])
    if any(e[0] == name for e in es):
        return {"ok": False, "err": f"{name} already exists here"}
    es.append((name, bool(is_dir), None if is_dir else int(size or 0), _now_min()))
    if is_dir:
        t.setdefault(_join(parent, name), [])
    return {"ok": True}


def demo_take(key: str) -> dict | None:
    """Take an entry, and everything under it, out of the sample tree (for the Trash)."""
    t = tree()
    key = "/" + key.strip("/")
    parent, name = _split(key)
    e = next((x for x in t.get(parent, []) if x[0] == name), None)
    if not e:
        return None
    t[parent].remove(e)
    sub = {k: t.pop(k) for k in list(t) if k == key or k.startswith(key + "/")}
    from . import demo_state
    txt = demo_state.get("files.text", dict)
    texts = {k: txt.pop(k) for k in list(txt) if k == key or k.startswith(key + "/")}
    return {"key": key, "entry": e, "sub": sub, "texts": texts}


def demo_put(parent: str, taken: dict, name: str | None = None) -> str:
    """Put a taken entry back under `parent` (as `name`); returns its new key."""
    t = tree()
    e = taken["entry"]
    name = name or e[0]
    new_key = _join(parent, name)
    t.setdefault(parent, []).append((name, *e[1:]))
    old = taken["key"]
    for k, v in taken["sub"].items():
        t[new_key + k[len(old):]] = v
    from . import demo_state
    txt = demo_state.get("files.text", dict)
    for k, v in taken.get("texts", {}).items():
        txt[new_key + k[len(old):]] = v
    return new_key


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
    if cfg.demo:
        entries = sorted(tree().get(_demo_rel(root_id, rel, who) or "", []), key=lambda e: (not e[1], e[0].lower()))
        return {"demo": True, "root": root_id, "path": rel, "entries": [entry_dict(e) for e in entries]}
    if not os.path.isdir(root):
        return {"error": f"{root} is not on this server yet", "root": root_id, "path": rel, "entries": []}
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
    if root_id not in rs:
        return {"ok": False, "err": "not a place you can upload to"}
    if not _writable(rs, root_id):
        return {"ok": False, "err": "that share is read-only for you"}
    name = os.path.basename(filename or "").replace("\x00", "")
    if not name or name.startswith("."):
        return {"ok": False, "err": "bad file name"}
    if cfg.demo:
        key = _demo_rel(root_id, "/" + rel.strip("/") if rel.strip("/") else "/", who)
        if key is None:
            return {"ok": False, "err": "the sample has nothing there"}
        r = demo_add(key, name, False, len(data))
        return {**r, "demo": True, "bytes": len(data)} if r["ok"] else r
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
    if root_id not in rs:
        return {"ok": False, "err": "not a place you can make a folder in"}
    if not _writable(rs, root_id):
        return {"ok": False, "err": "that share is read-only for you"}
    name = os.path.basename(name or "").strip()
    if not name or name.startswith(".") or "/" in name:
        return {"ok": False, "err": "bad folder name"}
    if cfg.demo:
        key = _demo_rel(root_id, "/" + rel.strip("/") if rel.strip("/") else "/", who)
        if key is None:
            return {"ok": False, "err": "the sample has nothing there"}
        r = demo_add(key, name, True)
        return {**r, "demo": True} if r["ok"] else r
    folder = _resolve(rs[root_id]["path"], rel)
    if not folder or not os.path.isdir(folder):
        return {"ok": False, "err": "folder not found"}
    dest = os.path.join(folder, name)
    if os.path.exists(dest):
        return {"ok": False, "err": f"{name} already exists"}
    os.makedirs(dest)
    return {"ok": True, "path": dest}


_search_cache: dict = {}


def search_transcripts(q: str, limit: int = 8) -> list[dict]:
    """Sermon transcripts the automator keeps (<automator>/transcripts/*.txt|*.json|*.srt):
    a case-insensitive phrase search with a short snippet. Spotlight shows these
    under Sermons. No sung words are ever returned: lines in [brackets] are skipped."""
    q = (q or "").strip().lower()
    if len(q) < 3:
        return []
    cfg = load()
    if cfg.demo:
        return [{"id": "dhy1VW5ZnpQ", "title": "Glory Night | October 5, 2026", "snippet": "…the kind of faith that moves when it cannot see, " + q + " is where it starts…", "file": "transcripts/dhy1VW5ZnpQ.txt"}] if q in "faith moves see starts the kind of" else []
    root = os.path.join(cfg.automator.path, "transcripts")
    if not os.path.isdir(root):
        return []
    hits = []
    for name in sorted(os.listdir(root)):
        if not name.endswith((".txt", ".srt", ".json")):
            continue
        p = os.path.join(root, name)
        try:
            if os.path.getsize(p) > 5_000_000:
                continue
            text = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        low = text.lower()
        i = low.find(q)
        if i < 0:
            continue
        start = max(0, i - 80); end = min(len(text), i + len(q) + 80)
        snippet = " ".join(text[start:end].split())
        if "[" in snippet and "]" in snippet:
            snippet = snippet.split("]")[-1].strip() or "(match inside a bracketed line)"
        hits.append({"id": name.rsplit(".", 1)[0], "title": name.rsplit(".", 1)[0], "snippet": "…" + snippet + "…", "file": "transcripts/" + name})
        if len(hits) >= limit:
            break
    return hits


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
        for path, entries in tree().items():
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

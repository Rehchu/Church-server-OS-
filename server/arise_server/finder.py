"""The Finder's everyday pieces (v0.8 "Exodus", docs/ANSWERS.md round 3):

Trash          a delete in the portal MOVES the file into <share>/.Trash/<user>/...,
               the same place Samba's recycle module puts a Mac's delete, so one
               Trash holds both. Put Back returns it; the daily sweep removes what
               is older than 30 days; Empty is an admin's typed click (1).
Get Info       kind, size, owner, dates, the SMB address, who can open it (16).
Recents        what changed in the last seven days across what you may browse (16).
Text           read and write small text files in place; Markdown preview (15).
Compress       a zip of a file or folder to download (16).
Open on my Mac the smb:// address of the folder you are looking at (18).

Everything is scoped by files.roots(who): a member only ever reaches their own
home and the shares their groups allow. Nothing here unlinks a file except the
Trash sweep and Empty, and those only inside a .Trash folder.
"""
from __future__ import annotations

import html
import os
import pwd
import grp
import re
import shutil
import tempfile
import time
import zipfile
from datetime import datetime, timedelta

from . import files
from .config import load
from .util import read_json, write_json

TRASH_DAYS = 30
TEXT_EXT = (".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".toml", ".log")
TEXT_MAX = 1_000_000
ZIP_MAX = 2 * 1024 ** 3
COPY_RE = re.compile(r"^Copy #(\d+) of (.+)$")   # Samba recycle:versions naming, reused for ours


# ---- shared helpers ----------------------------------------------------------
def _rs(who):
    return {r["id"]: r for r in files.roots(who)}


def _abs(root_id: str, rel: str, who) -> tuple[str, str] | None:
    """(root path, absolute target) for a path this person may reach, or None."""
    rs = _rs(who)
    if root_id not in rs:
        return None
    rel = "/" + rel.strip("/")
    t = files._resolve(rs[root_id]["path"], rel)
    return (rs[root_id]["path"], t) if t else None


def is_text(name: str) -> bool:
    return name.lower().endswith(TEXT_EXT)


def _share_paths(who=None) -> list[tuple[str, str]]:
    """[(share name, path)] for the shares that exist, homes left out (it has %U)."""
    from . import shares
    out = []
    for sh in shares.list_shares().get("shares", []):
        p = (sh.get("path") or "").rstrip("/")
        if sh["name"] in ("homes", "sysvol", "netlogon") or not p or "%" in p:
            continue
        out.append((sh["name"], p))
    out.sort(key=lambda x: -len(x[1]))   # longest path first
    return out


def smb_path(root_id: str, rel: str, who=None, host: str | None = None) -> str | None:
    """The smb:// address a Mac opens for this folder, or None when no share reaches it.

    A home is reached as smb://<host>/<user> (Samba's [homes] answers to the
    person's own name); a share as smb://<host>/<share>/<sub>; anything under
    /srv/arise/shares as smb://<host>/shares/<sub> when no narrower share has it.
    Pure, so the tests pin it."""
    cfg = load()
    host = host or f"{cfg.system.hostname}.{cfg.directory.realm.lower()}"
    rel = "/" + rel.strip("/")
    sub = rel.strip("/")
    if root_id == "home" and who:
        return f"smb://{host}/{who['user']}" + (f"/{sub}" if sub else "")
    if root_id.startswith("share:"):
        return f"smb://{host}/{root_id[6:]}" + (f"/{sub}" if sub else "")
    rs = _rs(who)
    if root_id not in rs:
        return None
    absolute = os.path.normpath(os.path.join(rs[root_id]["path"], sub))
    homes = cfg.directory.homes_path.rstrip("/")
    if absolute.startswith(homes + "/"):
        parts = absolute[len(homes) + 1:].split("/")
        return f"smb://{host}/{parts[0]}" + ("/" + "/".join(parts[1:]) if parts[1:] else "")
    for name, p in _share_paths(who):
        if absolute == p or absolute.startswith(p + "/"):
            tail = absolute[len(p):].strip("/")
            return f"smb://{host}/{name}" + (f"/{tail}" if tail else "")
    return None


def _owner(st) -> tuple[str, str]:
    try:
        u = pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        u = str(st.st_uid)
    try:
        g = grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        g = str(st.st_gid)
    return u, g


def folder_size(path: str, limit_seconds: float = 3.0) -> tuple[int, int, bool]:
    """(bytes, files, complete). Stops at the time limit and says so."""
    t0 = time.time(); total = 0; n = 0
    for dp, dirs, fs in os.walk(path):
        for f in fs:
            try:
                total += os.lstat(os.path.join(dp, f)).st_size; n += 1
            except OSError:
                pass
        if time.time() - t0 > limit_seconds:
            return total, n, False
    return total, n, True


# ---- Get Info ------------------------------------------------------------------
def info(root_id: str, rel: str, who=None) -> dict:
    cfg = load()
    rel = "/" + rel.strip("/")
    name = os.path.basename(rel) or (_rs(who).get(root_id) or {}).get("name") or root_id
    out = {"name": name, "root": root_id, "path": rel, "smb": smb_path(root_id, rel, who)}
    out["access"] = _access(root_id, rel, who)
    if cfg.demo:
        d = not ("." in name and not name.startswith("."))
        sample = next((e for es in files.DEMO_TREE.values() for e in es if e[0] == name and len(e) > 2), None)
        out.update({"demo": True, "dir": d, "kind": "Folder" if d else None, "size": 4_600_000_000 if d else (sample[2] if sample else 182_000), "files": 1240 if d else None,
                    "size_complete": not d, "owner": who["user"] if who else "bradly", "group": "Domain Users",
                    "created": "2026-09-14T10:02:00", "modified": "2026-10-26T14:02:00", "abs": None})
        return out
    got = _abs(root_id, rel, who)
    if not got or not os.path.exists(got[1]):
        return {"error": "no such file", **out}
    t = got[1]
    st = os.lstat(t)
    u, g = _owner(st)
    out.update({"demo": False, "dir": os.path.isdir(t), "owner": u, "group": g, "abs": t if (who or {}).get("role", "admin") == "admin" else None,
                "created": datetime.fromtimestamp(getattr(st, "st_birthtime", st.st_ctime)).isoformat(timespec="seconds"),
                "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    if out["dir"]:
        b, n, complete = folder_size(t)
        out.update({"size": b, "files": n, "size_complete": complete})
    else:
        out.update({"size": st.st_size, "files": None, "size_complete": True})
    return out


def _access(root_id: str, rel: str, who) -> dict:
    """Who can open this: the share's valid users and write list, in words."""
    from . import shares
    cfg = load()
    rs = _rs(who)
    r = rs.get(root_id) or {}
    if root_id == "home" or (root_id == "data" and ("/" + rel.strip("/")).startswith("/homes/")):
        owner = who["user"] if root_id == "home" else (rel.strip("/").split("/") + [""])[1]
        return {"share": owner or "homes", "who": [owner] if owner else [], "write": [owner] if owner else [], "note": "a home folder: only this person, and the administrators"}
    absolute = os.path.normpath(os.path.join(r.get("path", "/"), rel.strip("/"))) if r else ""
    for sh in sorted(shares.list_shares().get("shares", []), key=lambda x: -len(x.get("path") or "")):
        p = (sh.get("path") or "").rstrip("/")
        if not p or "%" in p:
            continue
        if root_id == "share:" + sh["name"] or (absolute and (absolute == p or absolute.startswith(p + "/"))):
            vu = sh.get("valid_users") or []
            return {"share": sh["name"], "who": [v.lstrip("@") for v in vu] or ["everyone in the domain"],
                    "write": [v.lstrip("@") for v in (sh.get("write_list") or [])] or ([v.lstrip("@") for v in vu] if sh.get("writable") else []),
                    "read_only": not sh.get("writable"), "note": sh.get("comment", "")}
    return {"share": None, "who": ["administrators"], "write": ["administrators"], "note": "not on any share: the server's own folders"}


# ---- Recents ---------------------------------------------------------------------
_recent_cache: dict = {}


def recent(who=None, days: int = 7, limit: int = 200) -> dict:
    cfg = load()
    key = (who or {}).get("user", "admin")
    now = time.time()
    c = _recent_cache.get(key)
    if c and now - c["t"] < 60:
        return c["out"]
    since = now - days * 86400
    hits = []
    if cfg.demo:
        for path, entries in files.DEMO_TREE.items():
            for e in entries:
                if not e[1] and len(e) > 2:
                    hits.append({"root": "data", "path": path.rstrip("/") + "/" + e[0], "name": e[0], "size": e[2], "mtime": "2026-10-26T14:02", "where": path})
        if who and who.get("role") != "admin":
            out = []
            for h in hits:
                for r in files.roots(who):
                    pref = files._demo_rel(r["id"], "/", who)
                    if pref and h["path"].startswith(pref + "/"):
                        out.append(dict(h, root=r["id"], path=h["path"][len(pref):], where=r["name"] + os.path.dirname(h["path"][len(pref):])))
            hits = out
        res = {"demo": True, "days": days, "hits": hits[:limit]}
    else:
        t0 = time.time()
        for r in files.roots(who):
            base = r["path"]
            if not os.path.isdir(base):
                continue
            for dp, dirs, fs in os.walk(base):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", "@eaDir", "#recycle")]
                for f in fs:
                    if f.startswith("."):
                        continue
                    try:
                        st = os.lstat(os.path.join(dp, f))
                    except OSError:
                        continue
                    if st.st_mtime >= since:
                        relp = dp[len(base):] or "/"
                        hits.append({"root": r["id"], "path": relp.rstrip("/") + "/" + f, "name": f, "size": st.st_size, "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes"), "where": r["name"] + relp})
                if time.time() - t0 > 6:
                    break
        hits.sort(key=lambda h: h["mtime"], reverse=True)
        res = {"demo": False, "days": days, "hits": hits[:limit], "truncated": len(hits) > limit or time.time() - t0 > 6}
    _recent_cache[key] = {"t": now, "out": res}
    return res


# ---- text files ------------------------------------------------------------------
def read_text(root_id: str, rel: str, who=None) -> dict:
    cfg = load()
    name = os.path.basename(rel)
    if not is_text(name):
        return {"ok": False, "err": "only text files open in the editor: " + " ".join(TEXT_EXT)}
    if cfg.demo:
        sample = files.DEMO_TEXT.get(name) or f"# {name}\n\nSample text. On the server this is the real file, editable in place.\n"
        return {"ok": True, "demo": True, "name": name, "text": sample, "bytes": len(sample), "mtime": "2026-10-26T14:02"}
    got = _abs(root_id, rel, who)
    if not got or not os.path.isfile(got[1]):
        return {"ok": False, "err": "no such file"}
    st = os.stat(got[1])
    if st.st_size > TEXT_MAX:
        return {"ok": False, "err": f"{name} is {st.st_size:,} bytes; the editor stops at 1 MB. Download it instead."}
    try:
        text = open(got[1], encoding="utf-8").read()
    except UnicodeDecodeError:
        return {"ok": False, "err": f"{name} is not UTF-8 text"}
    return {"ok": True, "demo": False, "name": name, "text": text, "bytes": st.st_size, "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}


def write_text(root_id: str, rel: str, text: str, who=None, expect_mtime: str | None = None) -> dict:
    cfg = load()
    name = os.path.basename(rel)
    if not is_text(name):
        return {"ok": False, "err": "only text files are saved by the editor"}
    if len(text.encode("utf-8")) > TEXT_MAX:
        return {"ok": False, "err": "over 1 MB; not saved"}
    rs = _rs(who)
    if root_id in rs and not files._writable(rs, root_id):
        return {"ok": False, "err": "that share is read-only for you"}
    if cfg.demo or root_id not in rs:
        return {"ok": True, "demo": True}
    got = _abs(root_id, rel, who)
    if not got or not os.path.isfile(got[1]):
        return {"ok": False, "err": "no such file"}
    cur = datetime.fromtimestamp(os.stat(got[1]).st_mtime).isoformat(timespec="seconds")
    if expect_mtime and cur != expect_mtime:
        return {"ok": False, "err": "someone changed this file since you opened it; reopen it and paste your changes in"}
    tmp = got[1] + ".arise-save"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, got[1])
    return {"ok": True, "demo": False, "bytes": len(text.encode("utf-8")), "mtime": datetime.fromtimestamp(os.stat(got[1]).st_mtime).isoformat(timespec="seconds")}


_BAD_HREF = re.compile(r'href="\s*(javascript|data|vbscript):[^"]*"', re.I)


def render_markdown(text: str) -> str:
    """Markdown to HTML for the preview. Raw HTML in the source never reaches the
    page: every '<' is escaped before the parser sees it, and script-ish links
    are stripped after. Falls back to escaped paragraphs without the library."""
    src = (text or "").replace("<", "&lt;")
    try:
        import markdown  # type: ignore
        out = markdown.markdown(src, extensions=["tables", "fenced_code", "sane_lists"])
    except ImportError:
        paras = [p.strip() for p in re.split(r"\n\s*\n", src) if p.strip()]
        out = "".join(f"<p>{html.escape(p, quote=False).replace('&amp;lt;', '&lt;')}</p>" for p in paras)
    return _BAD_HREF.sub('href="#"', out)


# ---- Compress ----------------------------------------------------------------------
def zip_path(root_id: str, rel: str, who=None) -> dict:
    """A zip of a file or folder in a temp dir; {"ok", "zip", "name"} or an error."""
    cfg = load()
    name = os.path.basename("/" + rel.strip("/")) or (_rs(who).get(root_id) or {}).get("name", "folder")
    if cfg.demo:
        return {"ok": True, "demo": True, "name": name + ".zip"}
    got = _abs(root_id, rel, who)
    if not got or not os.path.exists(got[1]):
        return {"ok": False, "err": "no such file"}
    t = got[1]
    total = os.path.getsize(t) if os.path.isfile(t) else folder_size(t, limit_seconds=20)[0]
    if total > ZIP_MAX:
        return {"ok": False, "err": f"{name} is over 2 GB ({total / 1024 ** 3:.1f} GB); too big to zip here. Open it on the share instead."}
    tmp = tempfile.mkdtemp(prefix="arise-zip-")
    out = os.path.join(tmp, name + ".zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.isfile(t):
            z.write(t, name)
        else:
            for dp, dirs, fs in os.walk(t):
                dirs[:] = [d for d in dirs if d != ".Trash"]
                for f in fs:
                    p = os.path.join(dp, f)
                    z.write(p, os.path.join(name, os.path.relpath(p, t)))
    return {"ok": True, "demo": False, "zip": out, "name": name + ".zip", "bytes": os.path.getsize(out)}


# ---- Trash -----------------------------------------------------------------------------
def trash_base(absolute: str, who=None) -> str | None:
    """The folder whose .Trash takes this path: the enclosing share, else the
    enclosing home, else the data root. Matches where Samba's recycle puts a
    Mac's delete (recycle:repository = .Trash/%U under the share's path)."""
    cfg = load()
    absolute = os.path.normpath(absolute)
    for _name, p in _share_paths(who):
        if absolute == p or absolute.startswith(p + "/"):
            return p
    homes = cfg.directory.homes_path.rstrip("/")
    if absolute.startswith(homes + "/"):
        return homes + "/" + absolute[len(homes) + 1:].split("/")[0]
    data = cfg.system.data_root.rstrip("/")
    if absolute == data or absolute.startswith(data + "/"):
        return data
    nas = (cfg.nas.mount or "").rstrip("/")
    if nas and absolute.startswith(nas + "/"):
        return nas
    return None


def trash_rel(base: str, absolute: str) -> str:
    """Where inside .Trash/<user>/ a file goes: its path relative to the base
    (Samba's recycle:keeptree), so Put Back knows the way home."""
    return os.path.relpath(absolute, base)


def versioned_name(name: str, taken) -> str:
    """'x.pdf' -> 'Copy #1 of x.pdf', 'Copy #2 of x.pdf'... until taken(name) is False.
    The same scheme Samba's recycle:versions uses, so the two never collide."""
    if not taken(name):
        return name
    n = 1
    while taken(f"Copy #{n} of {name}"):
        n += 1
    return f"Copy #{n} of {name}"


def put_back_name(name: str, taken) -> str:
    """The name a file returns under: its own, or 'name (put back).ext' and so on."""
    m = COPY_RE.match(name)
    if m:
        name = m.group(2)
    if not taken(name):
        return name
    stem, ext = os.path.splitext(name)
    cand = f"{stem} (put back){ext}"
    n = 2
    while taken(cand):
        cand = f"{stem} (put back {n}){ext}"; n += 1
    return cand


def expired(when_iso: str | None, now: datetime, days: int = TRASH_DAYS) -> bool:
    if not when_iso:
        return False
    try:
        when = datetime.fromisoformat(when_iso)
    except ValueError:
        return False
    return now - when > timedelta(days=days)


def _manifest_path(base: str, user: str) -> str:
    return os.path.join(base, ".Trash", user, ".arise-trash.json")


def _bases_for(who) -> list[tuple[str, str]]:
    """[(label, base path)] this person may see a Trash in."""
    cfg = load()
    out = []
    if who is None or who.get("role", "admin") == "admin":
        for name, p in _share_paths(who):
            out.append((name, p))
        homes = cfg.directory.homes_path
        if os.path.isdir(homes):
            for d in sorted(os.listdir(homes)):
                if not d.startswith(".") and os.path.isdir(os.path.join(homes, d)):
                    out.append(("home of " + d, os.path.join(homes, d)))
        out.append(("server", cfg.system.data_root.rstrip("/")))
        if cfg.nas.enabled:
            out.append(("Synology", cfg.nas.mount.rstrip("/")))
    else:
        for r in files.roots(who):
            out.append((r["name"], r["path"].rstrip("/")))
    return out


def _label_for(base: str, who) -> str:
    for label, p in _bases_for(who):
        if p == base:
            return label
    return os.path.basename(base)


def trash_list(who=None) -> dict:
    cfg = load()
    admin = who is None or who.get("role", "admin") == "admin"
    user = (who or {}).get("user", "bradly")
    if cfg.demo:
        rows = [
            {"base": "/srv/arise/shares/media", "label": "media", "user": user, "rel": "loops/old intro loop.mov", "name": "old intro loop.mov", "original": "loops/old intro loop.mov", "dir": False, "size": 412_000_000, "when": (datetime.now() - timedelta(days=2)).isoformat(timespec="minutes"), "from": "portal"},
            {"base": "/srv/arise/shares/staff", "label": "staff", "user": user, "rel": "Forms/Copy #1 of Visitor card 2025.docx", "name": "Copy #1 of Visitor card 2025.docx", "original": "Forms/Visitor card 2025.docx", "dir": False, "size": 38_000, "when": (datetime.now() - timedelta(days=12)).isoformat(timespec="minutes"), "from": "mac"},
            {"base": "/srv/arise/shares/graphics", "label": "graphics", "user": "media-mac", "rel": "lower-thirds/draft", "name": "draft", "original": "lower-thirds/draft", "dir": True, "size": None, "when": (datetime.now() - timedelta(days=27)).isoformat(timespec="minutes"), "from": "mac"},
        ]
        if not admin:
            rows = [r for r in rows if r["user"] == user and any(r["base"] == b for _l, b in _bases_for(who))]
        return {"demo": True, "days": TRASH_DAYS, "items": rows, "admin": admin}
    rows = []
    now = datetime.now()
    for label, base in _bases_for(who):
        tdir = os.path.join(base, ".Trash")
        if not os.path.isdir(tdir):
            continue
        users = sorted(os.listdir(tdir)) if admin else [user]
        for u in users:
            udir = os.path.join(tdir, u)
            if not os.path.isdir(udir):
                continue
            man = read_json(_manifest_path(base, u), default={}) or {}
            for dp, dirs, fs in os.walk(udir):
                # a folder deleted whole is one entry; do not descend into it
                here = os.path.relpath(dp, udir)
                entries = [(d, True) for d in dirs] + [(f, False) for f in fs if f != ".arise-trash.json"]
                keep = []
                for nm, is_dir in entries:
                    rel = nm if here == "." else os.path.join(here, nm)
                    m = man.get(rel)
                    if is_dir and not m:
                        keep.append(nm)   # a tree Samba kept: descend, its files are the entries
                        continue
                    p = os.path.join(dp, nm)
                    try:
                        st = os.lstat(p)
                    except OSError:
                        continue
                    when = (m or {}).get("when") or datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes")
                    rows.append({"base": base, "label": label, "user": u, "rel": rel, "name": nm, "original": (m or {}).get("original") or (COPY_RE.sub(r"\2", rel) if COPY_RE.match(nm) else rel),
                                 "dir": is_dir, "size": None if is_dir else st.st_size, "when": when, "from": "portal" if m else "mac", "expires_in_days": max(0, TRASH_DAYS - (now - datetime.fromisoformat(when)).days)})
                dirs[:] = keep
    rows.sort(key=lambda r: r["when"], reverse=True)
    return {"demo": False, "days": TRASH_DAYS, "items": rows[:2000], "admin": admin}


def trash_put(root_id: str, rel: str, who=None, confirm: str = "") -> dict:
    """Move a file or folder into the Trash. The caller typed its name (confirm)."""
    cfg = load()
    rel = "/" + rel.strip("/")
    name = os.path.basename(rel)
    if not name:
        return {"ok": False, "err": "pick a file or folder, not the whole place"}
    if confirm != name:
        return {"ok": False, "err": "type the name to confirm"}
    rs = _rs(who)
    if root_id in rs and not files._writable(rs, root_id):
        return {"ok": False, "err": "that share is read-only for you"}
    if cfg.demo or root_id not in rs:
        return {"ok": True, "demo": True, "trash": f".Trash/{(who or {}).get('user', 'bradly')}/{name}"}
    got = _abs(root_id, rel, who)
    if not got or not os.path.lexists(got[1]):
        return {"ok": False, "err": "no such file"}
    t = got[1]
    if "/.Trash/" in t + "/" or os.path.basename(t) == ".Trash":
        return {"ok": False, "err": "that is already in the Trash"}
    base = trash_base(t, who)
    if not base or not (t.startswith(base + "/")):
        return {"ok": False, "err": "no Trash covers that place"}
    user = (who or {}).get("user", "admin")
    udir = os.path.join(base, ".Trash", user)
    relp = trash_rel(base, t)
    dest_dir = os.path.join(udir, os.path.dirname(relp))
    os.makedirs(dest_dir, exist_ok=True)
    try:
        os.chmod(os.path.join(base, ".Trash"), 0o771)
    except OSError:
        pass
    final = versioned_name(name, lambda n: os.path.lexists(os.path.join(dest_dir, n)))
    dest = os.path.join(dest_dir, final)
    shutil.move(t, dest)
    try:
        os.utime(dest, None)   # like recycle:touch - the mtime is the delete time, the sweep reads it
    except OSError:
        pass
    key = os.path.relpath(dest, udir)
    man = read_json(_manifest_path(base, user), default={}) or {}
    man[key] = {"original": relp, "who": user, "when": datetime.now().isoformat(timespec="seconds"), "dir": os.path.isdir(dest), "root": root_id}
    write_json(_manifest_path(base, user), man)
    return {"ok": True, "demo": False, "trash": key, "base": base, "expires_in_days": TRASH_DAYS}


def _check_base(base: str, who) -> bool:
    return any(os.path.normpath(base) == os.path.normpath(b) for _l, b in _bases_for(who))


def trash_restore(base: str, user: str, rel: str, who=None) -> dict:
    cfg = load()
    me = (who or {}).get("user", "admin")
    admin = who is None or who.get("role", "admin") == "admin"
    if not admin and user != me:
        return {"ok": False, "err": "not your file"}
    if cfg.demo:
        return {"ok": True, "demo": True, "restored": put_back_name(os.path.basename(rel), lambda n: False)}
    if not _check_base(base, who):
        return {"ok": False, "err": "no Trash there for you"}
    udir = os.path.join(base, ".Trash", user)
    src = os.path.realpath(os.path.join(udir, rel))
    if not src.startswith(os.path.realpath(udir) + os.sep) or not os.path.lexists(src):
        return {"ok": False, "err": "that item is not in the Trash any more"}
    man = read_json(_manifest_path(base, user), default={}) or {}
    m = man.get(rel)
    original = (m or {}).get("original") or rel
    dest_dir = os.path.join(base, os.path.dirname(original))
    os.makedirs(dest_dir, exist_ok=True)
    final = put_back_name(os.path.basename(original) if m else os.path.basename(rel), lambda n: os.path.lexists(os.path.join(dest_dir, n)))
    dest = os.path.join(dest_dir, final)
    shutil.move(src, dest)
    if rel in man:
        del man[rel]
        write_json(_manifest_path(base, user), man)
    # drop the empty folders the keeptree layout left behind
    d = os.path.dirname(src)
    while d.startswith(udir) and d != udir:
        try:
            os.rmdir(d)
        except OSError:
            break
        d = os.path.dirname(d)
    return {"ok": True, "demo": False, "restored": os.path.relpath(dest, base), "renamed": final != os.path.basename(original)}


def trash_sweep(days: int = TRASH_DAYS, who=None, dry_run: bool = False) -> dict:
    """Remove what has sat in any Trash longer than `days`. The daily timer's job."""
    cfg = load()
    if cfg.demo:
        return {"ok": True, "demo": True, "removed": 1, "bytes": 38_000, "items": ["graphics: lower-thirds/draft"]}
    now = datetime.now()
    removed = []; total = 0
    for label, base in _bases_for(None):
        tdir = os.path.join(base, ".Trash")
        if not os.path.isdir(tdir):
            continue
        for u in os.listdir(tdir):
            udir = os.path.join(tdir, u)
            if not os.path.isdir(udir):
                continue
            man = read_json(_manifest_path(base, u), default={}) or {}
            changed = False
            for dp, dirs, fs in os.walk(udir, topdown=False):
                for nm in fs + dirs:
                    p = os.path.join(dp, nm)
                    if nm == ".arise-trash.json":
                        continue
                    rel = os.path.relpath(p, udir)
                    try:
                        st = os.lstat(p)
                    except OSError:
                        continue
                    when = (man.get(rel) or {}).get("when") or datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
                    if os.path.isdir(p) and not os.path.islink(p):
                        if rel in man and expired(when, now, days):
                            total += folder_size(p, 30)[0]
                            if not dry_run:
                                shutil.rmtree(p, ignore_errors=True)
                            removed.append(f"{label}: {rel}")
                        elif rel not in man and not os.listdir(p) and not dry_run:
                            os.rmdir(p)   # an empty keeptree folder
                        continue
                    if expired(when, now, days):
                        total += st.st_size
                        if not dry_run:
                            os.unlink(p)
                        removed.append(f"{label}: {rel}")
                        if rel in man:
                            del man[rel]; changed = True
            if changed and not dry_run:
                write_json(_manifest_path(base, u), man)
    return {"ok": True, "demo": False, "removed": len(removed), "bytes": total, "items": removed[:200], "dry_run": dry_run}


def trash_empty(share: str, confirm: str, who=None) -> dict:
    """Empty one share's Trash (every user's). Admin only; the share's name typed."""
    cfg = load()
    if confirm != share:
        return {"ok": False, "err": "type the share's name to confirm"}
    if who is not None and who.get("role", "admin") != "admin":
        return {"ok": False, "err": "emptying the Trash is an administrator's click"}
    if cfg.demo:
        return {"ok": True, "demo": True, "removed": 2}
    base = next((b for label, b in _bases_for(None) if label == share), None)
    if not base:
        return {"ok": False, "err": f"no share called {share}"}
    tdir = os.path.join(base, ".Trash")
    if not os.path.isdir(tdir):
        return {"ok": True, "removed": 0}
    n = 0
    for u in os.listdir(tdir):
        udir = os.path.join(tdir, u)
        if os.path.isdir(udir):
            n += sum(len(fs) for _dp, _d, fs in os.walk(udir))
            shutil.rmtree(udir, ignore_errors=True)
    return {"ok": True, "demo": False, "removed": n}

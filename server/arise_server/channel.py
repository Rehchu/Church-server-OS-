"""The Automator app's channel side: every video, its thumbnails and links, and a
search of the transcripts and the toolkit's files that opens on the video.

It reads two things, both read-only:
  * the archive's index (/var/lib/arise/archive/index.sqlite, docs/ARCHIVE.md),
  * the channel snapshots in the archive's clone of the automator repo
    (arise_archive.catalogue): titles, dates, descriptions as the PC last saw them.

It never spends quota and never touches the automator's token. The only network
call is YouTube's public oEmbed (no key, no quota) for a video's title as it is
now, cached for a week. The archive's rules (13.5) hold here too: private
folders stay hidden unless the viewer is Bradly (Claude's users, round 4, 44),
song credits are shown only as written, and transcripts carry sung lyrics, so
the page says not to copy those.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .config import load

_ARCH = Path(__file__).resolve().parents[2] / "archive"
if str(_ARCH) not in sys.path:
    sys.path.insert(0, str(_ARCH))
from arise_archive import catalogue, query, store  # noqa: E402
from arise_archive.config import Config as ArchiveConfig  # noqa: E402

ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
THUMB_WORDS = ("thumb", "podcast", "spotify")
KINDS = {"transcript", "description", "chapters", "setlist", "song", "speaker", "note", "media", "data", "history", "all"}
CHAPTER_RE = re.compile(r"^\s*((?:\d{1,2}:)?\d{1,2}:\d{2})\s*[-–—|:]?\s+(.+?)\s*$")
LYRICS_NOTE = "Transcripts include what was sung. Never copy sung words into a title, description or Short."
SNAPSHOT_NOTE = "Titles and descriptions are from the channel snapshots in the automator repo; YouTube may have newer text."
PER = 48

_lock = threading.Lock()
_facts_cache: dict = {"key": None, "facts": {}}


def acfg() -> ArchiveConfig:
    return ArchiveConfig()


def may_private(who: dict | None) -> bool:
    from .church import claude_users
    return bool(who) and str(who.get("user", "")) in claude_users()


def links(vid: str, kind: str = "") -> dict:
    return {"watch": f"https://youtube.com/shorts/{vid}" if kind == "short" else f"https://youtu.be/{vid}",
            "studio": f"https://studio.youtube.com/video/{vid}/edit",
            "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            "thumb_large": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "thumb_max": f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg"}


def hms(sec) -> str:
    s = int(sec or 0)
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def chapters_of(text: str, vid: str) -> list[dict]:
    """Chapter lines as written ('0:00 Welcome', '1:02:03 Altar'). M:SS under an hour, H:MM:SS over it."""
    out = []
    for line in (text or "").splitlines():
        m = CHAPTER_RE.match(line)
        if not m:
            continue
        n = 0
        for part in m.group(1).split(":"):
            n = n * 60 + int(part)
        out.append({"at": m.group(1), "sec": n, "title": m.group(2), "link": f"https://youtu.be/{vid}?t={n}"})
    return out if len(out) >= 2 else []


def credits_of(text: str) -> list[str]:
    """Song credit lines exactly as the description has them; nothing is looked up or added."""
    return [l.strip() for l in (text or "").splitlines() if re.search(r"\bCCLI\b", l, re.I)][:40]


# ----- the archive ------------------------------------------------------------
def _index_ok() -> bool:
    return acfg().index.exists()


def _db():
    return store.open_ro(acfg().index)


def _facts() -> dict:
    """{video_id: {kinds, title, date}} from the index, cached until the index changes."""
    p = acfg().index
    try:
        key = p.stat().st_mtime_ns
    except OSError:
        return {}
    if _facts_cache["key"] == key:
        return _facts_cache["facts"]
    facts: dict = {}
    with _db() as db:
        for r in db.execute("SELECT video_id, kind, title, date, history, path FROM docs WHERE video_id IS NOT NULL"):
            f = facts.setdefault(r["video_id"], {"kinds": set(), "title": None, "date": None})
            f["kinds"].add(r["kind"])
            if "short" in r["path"].rsplit("/", 1)[-1].lower():
                f["kinds"].add("in-shorts-kit")
            t = r["title"] or ""
            if r["kind"] == "description" and not r["history"] and t and t != r["video_id"] and not f["title"]:
                f["title"] = t
            if r["date"] and not f["date"]:
                f["date"] = r["date"]
        for (vid,) in db.execute("SELECT DISTINCT video_id FROM segments WHERE video_id IS NOT NULL"):
            facts.setdefault(vid, {"kinds": set(), "title": None, "date": None})["kinds"].add("timed")
    _facts_cache.update(key=key, facts=facts)
    return facts


def _held() -> dict:
    from . import automator
    try:
        return {v.get("id"): v.get("reason", "") for v in automator.holds().get("videos", []) if isinstance(v, dict)}
    except Exception:  # noqa: BLE001 - the hold list is a label here, never a gate
        return {}


def _row(vid: str, rec: dict, f: dict | None, held: dict) -> dict:
    kinds = (f or {}).get("kinds", set())
    # Not in a snapshot: a transcript means a service; a video named only in a Shorts kit is a Short.
    # A service title reads "Title | Speaker", so a " | " keeps a kit's parent video from being called a Short.
    t = rec.get("title") or (f or {}).get("title") or ""
    kind = rec.get("kind") or ("service" if kinds & {"timed", "transcript"} or " | " in t else "short" if "in-shorts-kit" in kinds else "video")
    return {"id": vid, "title": t,
            "date": rec.get("date") or catalogue.date_in_title((f or {}).get("title")) or (f or {}).get("date"), "kind": kind, "seconds": rec.get("seconds"),
            "privacy": rec.get("privacy"), "views": rec.get("views"), "upcoming": rec.get("upcoming"),
            "transcript": "transcript" in kinds or "timed" in kinds, "chapters": "chapters" in kinds or (rec.setdefault("_chap", bool(chapters_of(rec.get("description", ""), vid))) if rec else False),
            "in_catalogue": bool(rec), "held": vid in held, "parent": rec.get("parent"), "shorts": len(rec.get("children", [])),
            **links(vid, kind)}


def status() -> dict:
    cfg = load()
    if cfg.demo:
        return {"demo": True, "index": True, "videos": len(DEMO_VIDEOS), "built_at": None, "snapshot": [s for s, _ in catalogue.SOURCES]}
    a = acfg()
    out = {"demo": False, "index": a.index.exists(), "root": str(a.root)}
    if not out["index"]:
        out["error"] = "The archive is not built on this server yet: sudo arisectl archive setup (docs/ARCHIVE.md)"
        return out
    try:
        st = query.status(a)
        out.update(built_at=st.get("built_at"), commits=st.get("indexed_commits"), kinds=st.get("documents_by_kind"))
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
    out["videos"] = len(catalogue.load(a))
    out["snapshot"] = [s for s, _ in catalogue.SOURCES if (a.repo_dir(catalogue.AUTOMATION) / s).exists()]
    return out


def videos(q: str = "", kind: str = "", has: str = "", page: int = 1, per: int = PER) -> dict:
    cfg = load()
    if cfg.demo:
        rows = [demo_row(v) for v in DEMO_VIDEOS]
    else:
        if not _index_ok():
            return {"videos": [], "total": 0, "page": 1, "pages": 1, "error": "The archive is not built on this server yet: sudo arisectl archive setup"}
        cat, facts, held = catalogue.load(acfg()), _facts(), _held()
        ids = set(cat) | set(facts)
        rows = [_row(v, cat.get(v, {}), facts.get(v), held) for v in ids]
    ql = (q or "").strip().lower()
    if ql:
        words = ql.split()
        rows = [r for r in rows if r["id"].lower() == ql or all(w in (r["title"] or "").lower() for w in words)]
    if kind in ("service", "short", "video"):
        rows = [r for r in rows if r["kind"] == kind]
    if has == "transcript":
        rows = [r for r in rows if r["transcript"]]
    elif has == "chapters":
        rows = [r for r in rows if r["chapters"]]
    elif has == "held":
        rows = [r for r in rows if r["held"]]
    rows.sort(key=lambda r: (r["date"] or "", r["id"]), reverse=True)
    per = max(12, min(int(per or PER), 120))
    pages = max(1, -(-len(rows) // per))
    page = max(1, min(int(page or 1), pages))
    counts = {k: sum(1 for r in rows if r["kind"] == k) for k in ("service", "short", "video")}
    return {"demo": cfg.demo, "total": len(rows), "page": page, "pages": pages, "per": per, "counts": counts,
            "videos": rows[(page - 1) * per: page * per], "note": SNAPSHOT_NOTE}


def _doc_text(db, doc_id: int, limit: int = 20000) -> str:
    parts, n = [], 0
    for (t,) in db.execute("SELECT c.text FROM chunk_meta m JOIN chunks c ON c.rowid = m.id WHERE m.doc_id=? ORDER BY m.id", (doc_id,)):
        parts.append(t)
        n += len(t)
        if n > limit:
            break
    return "\n".join(parts)[:limit]


def _thumb_url(repo: str, path: str) -> str:
    return "/api/automator/archive/file?" + urllib.parse.urlencode({"repo": repo, "path": path})


def video(vid: str, who: dict | None = None) -> dict:
    if not ID_RE.fullmatch(vid or ""):
        return {"ok": False, "err": "not a YouTube video id"}
    cfg = load()
    if cfg.demo:
        return demo_video(vid)
    if not _index_ok():
        return {"ok": False, "err": "The archive is not built on this server yet: sudo arisectl archive setup"}
    a, priv = acfg(), may_private(who)
    cat, facts, held = catalogue.load(a), _facts(), _held()
    rec = cat.get(vid, {})
    row = _row(vid, rec, facts.get(vid), held)
    now = oembed(vid) if rec.get("privacy", "public") == "public" else None
    if now and catalogue.date_in_title(now.get("title")):
        row["date"] = catalogue.date_in_title(now["title"])    # YouTube's title today names the service date
    date = row["date"]
    by_date = date if row["kind"] != "short" else None   # a Short shares its service's date, not its thumbnail or set list
    with _db() as db:
        docs = [d for d in db.execute("SELECT * FROM docs WHERE video_id=? ORDER BY history, kind, path", (vid,)) if priv or not d["private"]]
        versions = []
        if rec.get("description"):
            versions.append({"source": "channel snapshot", "files": rec.get("sources", []), "text": rec["description"], "history": False})
        for d in docs:
            if d["kind"] in ("description", "history"):
                versions.append({"source": d["path"], "repo": d["repo"], "commit": d["commit_sha"], "title": d["title"],
                                 "text": _doc_text(db, d["id"]), "history": bool(d["history"]), "private": bool(d["private"])})
        chap_docs = [_doc_text(db, d["id"]) for d in docs if d["kind"] == "chapters"]
        sets = []
        if by_date:
            for d in db.execute("SELECT * FROM docs WHERE kind='setlist' AND date=?", (by_date,)):
                if priv or not d["private"]:
                    sets.append({"path": d["path"], "repo": d["repo"], "title": d["title"], "text": _doc_text(db, d["id"], 4000)})
        like = " OR ".join(["lower(path) LIKE ?"] * len(THUMB_WORDS))
        media = list(db.execute(f"SELECT * FROM docs WHERE kind='media' AND (video_id=? OR (date=? AND ({like})))",
                                (vid, by_date or "-", *[f"%{w}%" for w in THUMB_WORDS])))
        tsources = [{"repo": r[0], "path": r[1], "segments": r[2]} for r in db.execute(
            "SELECT d.repo, d.path, COUNT(*) FROM segments s JOIN docs d ON d.id = s.doc_id WHERE s.video_id=? "
            "AND (d.private = 0 OR ?) GROUP BY d.id ORDER BY COUNT(*) DESC", (vid, int(priv)))]
    thumbs, seen = [], set()
    for m in media:
        if Path(m["path"]).suffix.lower() not in IMAGE_TYPES or (m["private"] and not priv) or m["sha256"] in seen:
            continue
        seen.add(m["sha256"])
        ex = json.loads(m["extra"] or "{}")
        thumbs.append({"repo": m["repo"], "path": m["path"], "name": m["title"], "size": m["size"], "width": ex.get("width"),
                       "height": ex.get("height"), "date": m["date"], "url": _thumb_url(m["repo"], m["path"]),
                       "why": "named after this video" if m["video_id"] == vid else f"made for {m['date']}"})
    # Snapshot first, then the toolkit's description files, then what was applied, then kits and logs; history last.
    def rank(v):
        base = v["source"].rsplit("/", 1)[-1].lower()
        return (v["history"], 0 if v["source"] == "channel snapshot" else 1 if re.search(r"desc(?!_written)", base)
                else 2 if "applied" in base else 3, v["source"])
    versions.sort(key=rank)
    main = next((v for v in versions if not v["history"] and v["text"].strip()), None)
    chapters = chapters_of(main["text"], vid) if main else []
    if not chapters:
        for t in chap_docs:
            chapters = chapters_of(t, vid)
            if chapters:
                break
    kids = [_row(k, cat.get(k, {}), facts.get(k), held) for k in rec.get("children", [])]
    kids.sort(key=lambda r: r["title"] or "")
    parent = _row(rec["parent"], cat.get(rec["parent"], {}), facts.get(rec["parent"]), held) if rec.get("parent") else None
    return {"ok": True, "demo": False, **row, "held_reason": held.get(vid), "versions": versions, "chapters": chapters,
            "credits": credits_of(main["text"]) if main else [], "setlists": sets, "thumbs": thumbs, "shorts": kids, "parent_video": parent,
            "transcripts": tsources, "files": [{"repo": d["repo"], "path": d["path"], "kind": d["kind"], "history": bool(d["history"]),
                                                "private": bool(d["private"])} for d in docs],
            "now": now, "date_note": rec.get("date_note"), "note": SNAPSHOT_NOTE, "lyrics": LYRICS_NOTE}


def transcript(vid: str, source: str = "", who: dict | None = None) -> dict:
    if not ID_RE.fullmatch(vid or ""):
        return {"ok": False, "err": "not a YouTube video id"}
    if load().demo:
        return demo_transcript(vid)
    if not _index_ok():
        return {"ok": False, "err": "The archive is not built on this server yet"}
    priv = may_private(who)
    with _db() as db:
        srcs = list(db.execute("SELECT d.id, d.repo, d.path, d.private, COUNT(*) n FROM segments s JOIN docs d ON d.id = s.doc_id "
                               "WHERE s.video_id=? GROUP BY d.id ORDER BY n DESC", (vid,)))
        srcs = [s for s in srcs if priv or not s["private"]]
        if not srcs:
            return {"ok": True, "video_id": vid, "segments": [], "sources": [], "note": "No timed transcript for this video in the archive."}
        pick = next((s for s in srcs if s["path"] == source), srcs[0])
        segs = [{"t": round(r["start"], 1), "d": round(r["dur"] or 0, 1), "text": r["text"]}
                for r in db.execute("SELECT start, dur, text FROM segments WHERE doc_id=? ORDER BY start", (pick["id"],))]
    return {"ok": True, "video_id": vid, "source": pick["path"], "repo": pick["repo"],
            "sources": [{"path": s["path"], "repo": s["repo"], "segments": s["n"]} for s in srcs],
            "segments": segs, "lyrics": LYRICS_NOTE, "link": f"https://youtu.be/{vid}"}


def _mark(snip: str) -> str:
    return snip or ""


def search(q: str, kind: str = "transcript", history: bool = False, private: bool = False, who: dict | None = None) -> dict:
    q = (q or "").strip()
    kind = kind if kind in KINDS else "transcript"
    if not q:
        return {"query": q, "videos": [], "files": [], "titles": [], "songs": []}
    if load().demo:
        return demo_search(q, kind)
    if not _index_ok():
        return {"query": q, "videos": [], "files": [], "titles": [], "songs": [], "error": "The archive is not built on this server yet: sudo arisectl archive setup"}
    a = acfg()
    priv = bool(private) and may_private(who)
    try:
        res = query.search(a, q, kind=None if kind == "all" else kind, include_history=history, include_private=priv,
                           limit=200, uncapped=True)
    except Exception as e:  # noqa: BLE001 - a malformed query is an answer, not a crash
        return {"query": q, "videos": [], "files": [], "titles": [], "songs": [], "error": f"search failed: {e}"}
    cat, facts, held = catalogue.load(a), _facts(), _held()
    groups: dict = {}
    files = []
    hidden = set()
    for h in res["results"]:
        p = h["provenance"]
        hit = {"kind": h["kind"], "snippet": _mark(h.get("snippet")), "link": h.get("link"), "sec": p.get("start_sec"),
               "at": hms(p["start_sec"]) if p.get("start_sec") is not None else None, "repo": p["repo"], "path": p["path"],
               "lines": p.get("lines"), "history": bool(h.get("history")), "private": bool(h.get("private")), "title": h.get("title")}
        vid = h.get("video_id")
        if vid and vid in held:
            hidden.add(vid)          # round 7, 105: videos on the hold list stay out of search
            continue
        if vid:
            g = groups.get(vid)
            if not g:
                g = groups[vid] = {**_row(vid, cat.get(vid, {}), facts.get(vid), held), "hits": [], "total": 0}
            g["total"] += 1
            if len(g["hits"]) < 12:
                g["hits"].append(hit)
        elif len(files) < 40:
            files.append(hit)
    words = q.lower().replace('"', "").split()
    titles = [_row(v, r, facts.get(v), held) for v, r in cat.items() if v not in held and words and all(w in (r.get("title") or "").lower() for w in words)]
    titles.sort(key=lambda r: r["date"] or "", reverse=True)
    songs = []
    if re.fullmatch(r"(?i)(ccli\s*#?\s*)?\d{4,8}", q) or kind in ("song", "all"):
        try:
            songs = query.song(a, q).get("songs", [])
        except Exception:  # noqa: BLE001
            songs = []
    return {"query": q, "kind": kind, "count": len(res["results"]), "videos": list(groups.values()), "files": files,
            "titles": titles[:12], "songs": songs, "lyrics": LYRICS_NOTE, "private_allowed": may_private(who), "held_hidden": len(hidden)}


def document(repo: str, path: str, start: int | None = None, who: dict | None = None) -> dict:
    if load().demo:
        return {"ok": True, "demo": True, "repo": repo, "path": path, "text": "Sample: on the server this is the file's text from the archive."}
    if not _index_ok():
        return {"ok": False, "err": "The archive is not built on this server yet"}
    try:
        d = query.get_document(acfg(), repo, path, start_line=start)
    except (ValueError, OSError) as e:
        return {"ok": False, "err": str(e)}
    if d.get("error"):
        return {"ok": False, "err": d["error"]}
    if d.get("private") and not may_private(who):
        return {"ok": False, "err": "That file is in a private folder (emails, memory): Bradly only."}
    return {"ok": True, **d}


def image(repo: str, path: str, who: dict | None = None) -> tuple[Path | None, str, str]:
    """(file, content type, error). Only an indexed image, inside the archive, private ones for Bradly only."""
    if Path(path or "").suffix.lower() not in IMAGE_TYPES:
        return None, "", "only images are served"
    if not _index_ok():
        return None, "", "no archive here"
    a = acfg()
    with _db() as db:
        d = db.execute("SELECT * FROM docs WHERE repo=? AND path=? AND kind='media'", (repo, path)).fetchone()
    if not d:
        return None, "", "not in the archive"
    if d["private"] and not may_private(who):
        return None, "", "private"
    try:
        full = query._safe(a, repo, path)
    except ValueError as e:
        return None, "", str(e)
    if not full.is_file():
        return None, "", "missing on disk"
    return full, IMAGE_TYPES[full.suffix.lower()], ""


# ----- YouTube's public oEmbed (no key, no quota): the title as it is now -------
def _oembed_file() -> Path:
    return load().state_dir / "channel" / "oembed.json"


def oembed(vid: str, fetch=None) -> dict | None:
    """{title, author, checked} or None. A success is kept a week, a failure a day; at most one fetch at a time."""
    if load().demo or os.environ.get("ARISE_NO_NET"):
        return None
    f = _oembed_file()
    with _lock:
        try:
            cache = json.loads(f.read_text())
        except (OSError, ValueError):
            cache = {}
        hit = cache.get(vid)
        now = time.time()
        if hit and now - hit.get("at", 0) < (7 * 86400 if hit.get("ok") else 86400):
            return hit if hit.get("ok") else None
        url = "https://www.youtube.com/oembed?" + urllib.parse.urlencode({"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"})
        try:
            if fetch:
                data = fetch(url)
            else:
                req = urllib.request.Request(url, headers={"User-Agent": "ariseOS dashboard"})
                with urllib.request.urlopen(req, timeout=4) as r:
                    data = json.loads(r.read(200_000))
            hit = {"ok": True, "title": data.get("title"), "author": data.get("author_name"), "at": now,
                   "checked": time.strftime("%Y-%m-%d %H:%M", time.localtime(now))}
        except Exception:  # noqa: BLE001 - offline, private or removed: say nothing rather than guess
            hit = {"ok": False, "at": now}
        cache[vid] = hit
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(cache))
            os.replace(tmp, f)
        except OSError:
            pass
        return hit if hit.get("ok") else None


# ----- sample data (ARISE_DEMO=1 and the published preview) -------------------
# Real public video ids and titles from the channel, so the YouTube thumbnails load.
# Every transcript line, chapter and file here is a placeholder, labelled as one:
# nothing is put in a pastor's mouth.
def _svg(title: str, date: str, colour: str) -> str:
    t = title.replace("&", "&amp;").replace("<", "&lt;")[:38]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">'
           f'<rect width="1280" height="720" fill="#0b0b0d"/><rect x="0" y="560" width="1280" height="160" fill="{colour}"/>'
           f'<text x="64" y="120" fill="#fff" font-family="Oswald,Arial" font-size="40" letter-spacing="6">ARISE CHURCH</text>'
           f'<text x="64" y="360" fill="#fff" font-family="Oswald,Arial" font-size="72" font-weight="700">{t.upper()}</text>'
           f'<text x="64" y="660" fill="#fff" font-family="Oswald,Arial" font-size="44">{date} · SAMPLE THUMBNAIL</text></svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


DEMO_VIDEOS = [
    {"id": "2wVIGBvQLzE", "title": "Peace Is a Garrison | Apostle Bryant Sanders | Glory Night October 19, 2026", "date": "2026-10-19", "kind": "service", "seconds": 6420, "accent": "#601CCC", "transcript": True},
    {"id": "hu9cnsymsSo", "title": "YOUR WORDS ARE FRAMING SOMETHING | Pastor Vanessa Sanders", "date": "2026-10-18", "kind": "service", "seconds": 7380, "accent": "#D6222D", "transcript": True},
    {"id": "AnVfOCesXM4", "title": "PITCH THE SHIP | Apostle Bryant Sanders", "date": "2026-10-11", "kind": "service", "seconds": 6990, "accent": "#D6222D", "transcript": True,
     "children": ["yMewy7Nwi3c", "9s5f2cIwg8o"]},
    {"id": "4V4QeHZevgU", "title": "A Bride Willing to Follow | Apostle Bryant Sanders | Glory Night October 5, 2026", "date": "2026-10-05", "kind": "service", "seconds": 5980, "accent": "#5D1DCC", "transcript": True},
    {"id": "W8t2JYXOIBk", "title": "EXERCISING OUR SPIRITUAL SENSES | Apostle Bryant Sanders", "date": "2026-10-04", "kind": "service", "seconds": 7210, "accent": "#D6222D", "transcript": False},
    {"id": "yMewy7Nwi3c", "title": "Pitch the Ship: Intimacy with the Holy Spirit", "date": "2026-10-11", "kind": "short", "seconds": 58, "parent": "AnVfOCesXM4"},
    {"id": "9s5f2cIwg8o", "title": "Pocket Square: A Small Test of Obedience", "date": "2026-10-11", "kind": "short", "seconds": 61, "parent": "AnVfOCesXM4"},
    {"id": "MnXmccLS2p8", "title": "Sample: a held service (the GAURD spelling stays)", "date": "2026-07-12", "kind": "service", "seconds": 6600, "accent": "#D6222D", "transcript": False, "held": True},
]
_DEMO = {v["id"]: v for v in DEMO_VIDEOS}


def demo_row(v: dict) -> dict:
    return {"id": v["id"], "title": v["title"], "date": v["date"], "kind": v["kind"], "seconds": v["seconds"], "privacy": "public",
            "views": None, "upcoming": None, "transcript": bool(v.get("transcript")), "chapters": v["kind"] == "service",
            "in_catalogue": True, "held": bool(v.get("held")), "parent": v.get("parent"), "shorts": len(v.get("children", [])),
            "sample": True, **links(v["id"], v["kind"])}


def _demo_segments(v: dict) -> list[dict]:
    name = v["title"].split(" | ")[0]
    out = []
    for i in range(0, v["seconds"], 60):
        part = ("welcome and worship" if i < 1500 else "announcements and the offering" if i < 2400
                else f"the message, “{name.title()}”" if i < v["seconds"] - 900 else "the altar call and the close")
        out.append({"t": float(i), "d": 60.0, "text": f"Sample caption at {hms(i)}, during {part}. On the server this is the real StreamYard caption."})
    return out


def demo_video(vid: str) -> dict:
    v = _DEMO.get(vid)
    if not v:
        return {"ok": False, "err": "not in the sample set"}
    row = demo_row(v)
    chapters = [] if v["kind"] != "service" else [
        {"at": "0:00", "sec": 0, "title": "Welcome (sample chapter)"}, {"at": "2:30", "sec": 150, "title": "Worship (sample chapter)"},
        {"at": "25:00", "sec": 1500, "title": "Announcements (sample chapter)"}, {"at": "40:00", "sec": 2400, "title": "The message (sample chapter)"},
        {"at": hms(v["seconds"] - 900), "sec": v["seconds"] - 900, "title": "Altar call (sample chapter)"}]
    for c in chapters:
        c["link"] = f"https://youtu.be/{vid}?t={c['sec']}"
    desc = ("Sample description. On the server this is the text from the channel snapshot and from the toolkit's files, "
            "each version labelled with the file it came from.\n\n" + "\n".join(f"{c['at']} {c['title']}" for c in chapters))
    shorts = [demo_row(_DEMO[k]) for k in v.get("children", []) if k in _DEMO]
    return {"ok": True, "demo": True, **row, "held_reason": "spelling call: GAURD stays" if v.get("held") else None,
            "versions": [{"source": "channel snapshot (sample)", "text": desc, "history": False},
                         {"source": "cloud_workspace/work/_backup_sample_pre.json (sample)", "text": "Sample: an older version, kept as history.", "history": True}],
            "chapters": chapters, "credits": ["Sample credit line, shown exactly as the description writes it (CCLI numbers come only from song_bank.json)."] if v["kind"] == "service" else [],
            "setlists": [], "shorts": shorts, "parent_video": demo_row(_DEMO[v["parent"]]) if v.get("parent") in _DEMO else None,
            "thumbs": [] if v["kind"] != "service" else [{"repo": "arise-youtube-automation", "path": f"THUMB_{v['date']}_sample.jpg", "name": f"THUMB_{v['date']}_sample.jpg",
                                                           "size": 182000, "width": 1280, "height": 720, "date": v["date"], "why": f"made for {v['date']}",
                                                           "url": _svg(v["title"].split(" | ")[0], v["date"], v.get("accent", "#D6222D"))}],
            "transcripts": [{"repo": "arise-youtube-automation", "path": f"transcripts/{vid}_streamyard.vtt", "segments": len(_demo_segments(v))}] if v.get("transcript") else [],
            "files": [{"repo": "arise-youtube-automation", "path": f"transcripts/{vid}_streamyard.vtt", "kind": "transcript", "history": False, "private": False}] if v.get("transcript") else [],
            "now": None, "note": SNAPSHOT_NOTE, "lyrics": LYRICS_NOTE}


def demo_transcript(vid: str) -> dict:
    v = _DEMO.get(vid)
    if not v or not v.get("transcript"):
        return {"ok": True, "video_id": vid, "segments": [], "sources": [], "note": "No timed transcript for this video in the archive."}
    p = f"transcripts/{vid}_streamyard.vtt"
    segs = _demo_segments(v)
    return {"ok": True, "demo": True, "video_id": vid, "source": p, "repo": "arise-youtube-automation",
            "sources": [{"path": p, "repo": "arise-youtube-automation", "segments": len(segs)}], "segments": segs, "lyrics": LYRICS_NOTE,
            "link": f"https://youtu.be/{vid}"}


def demo_search(q: str, kind: str) -> dict:
    words = [w for w in re.findall(r"\w+", q.lower()) if w]
    groups, titles = [], []
    hidden = 0
    for v in DEMO_VIDEOS:
        if v.get("held"):
            hidden += 1 if words and (all(w in v["title"].lower() for w in words) or v.get("transcript")) else 0
            continue             # round 7, 105: held videos stay out of search
        if words and all(w in v["title"].lower() for w in words):
            titles.append(demo_row(v))
        if kind not in ("transcript", "all") or not v.get("transcript"):
            continue
        hits = []
        for s in _demo_segments(v):
            low = s["text"].lower()
            if words and all(w in low for w in words):
                snip = s["text"]
                for w in words:
                    snip = re.sub(f"(?i)({re.escape(w)})", r"[\1]", snip)
                hits.append({"kind": "transcript", "snippet": snip, "link": f"https://youtu.be/{v['id']}?t={int(s['t'])}", "sec": s["t"], "at": hms(s["t"]),
                             "repo": "arise-youtube-automation", "path": f"transcripts/{v['id']}_streamyard.vtt", "history": False, "private": False})
        if hits:
            groups.append({**demo_row(v), "hits": hits[:12]})
    return {"query": q, "kind": kind, "demo": True, "count": sum(len(g["hits"]) for g in groups), "videos": groups, "files": [],
            "titles": titles, "songs": [], "lyrics": LYRICS_NOTE, "private_allowed": False, "held_hidden": hidden}

"""The song list and its lyrics (the Automator app's Songs tab).

The list is song_bank.json, read-only: the copy the 02:05 job pulls into its
checkout, else the archive's clone. The server never edits it (SERVER_HANDOFF.md:
song_bank.json is the PC's). Credits come only from it: nothing here looks a
song up, guesses a number or fills in a writer.

Lyrics are Bradly's to add (Oct 28: "I'd have to add the lyrics most likely from
Proclaim"): pasted into a song, or imported from files (SongSelect's .txt and
.usr, ChordPro, plain text). One text file per song in /srv/arise/songs/lyrics,
named by CCLI number (or "t-<title>" for a song without one, "x-<title>" for
lyrics that match no song_bank entry yet). Every earlier version is kept in
.versions/, a removed one goes to .removed/; nothing is deleted. They are the
church's licensed copies (CCLI No. 245091): searchable here for Bradly, never
copied into a title, description, Short or git.
"""
from __future__ import annotations

import json
from datetime import datetime
import os
import re
import threading
import time
from pathlib import Path

from . import audit
from .config import load

_lock = threading.RLock()
CCLI_RE = re.compile(r"(?i)CCLI\s*(?:Song\s*)?(?:No\.?|#|Number)?\s*:?\s*(\d{3,8})")
KEY_RE = re.compile(r"^(?:\d{3,8}|[tx]-[a-z0-9-]{1,80})$")
HEADER_RE = re.compile(r"^(Title|CCLI|Source|Writers):\s*(.*)$")
LICENCE_NOTE = ("Lyrics are the church's licensed copies (CCLI No. 245091). They stay on this server: "
                "never in a title, description, Short or a git repository.")
IMPORT_TYPES = (".txt", ".usr", ".cho", ".chopro", ".chordpro", ".pro", ".crd")


def norm_title(t: str) -> str:
    t = (t or "").lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"[^\w\s']", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def slug(t: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", norm_title(t).replace("'", ""))).strip("-")[:80] or "untitled"


def key_of(song: dict) -> str:
    return str(song["ccli"]) if song.get("ccli") else "t-" + slug(song.get("title", ""))


# ----- the song bank (read-only) ----------------------------------------------
def _bank_paths() -> list[Path]:
    cfg = load()
    out = [Path(cfg.automator.path) / "song_bank.json"]
    root = Path(os.environ.get("ARISE_ARCHIVE_ROOT", "/srv/arise/archive"))
    out.append(root / "arise-youtube-automation" / "song_bank.json")
    return out


_bank_cache: dict = {"key": None, "songs": [], "source": None}


def bank() -> tuple[list[dict], str | None]:
    """(songs, the file they came from). Each song: title, ccli, writers, copyright, admin, credit_line,
    original, verified, note, performed_by, key."""
    if load().demo:
        return [dict(s, key=key_of(s)) for s in DEMO_BANK], "song_bank.json (sample)"
    for p in _bank_paths():
        try:
            st = p.stat()
        except OSError:
            continue
        key = (str(p), st.st_mtime_ns)
        if _bank_cache["key"] == key:
            return _bank_cache["songs"], _bank_cache["source"]
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        rows = d.items() if isinstance(d, dict) else [(x.get("title"), x) for x in d if isinstance(x, dict)]
        songs = []
        for title, v in rows:
            if not isinstance(v, dict) or str(title).startswith("_"):
                continue
            s = {"title": str(title), **{k: v.get(k) for k in ("writers", "copyright", "admin", "credit_line", "verified", "note", "performed_by")
                                         if v.get(k) not in (None, "")}}
            s["ccli"] = str(v["ccli"]).strip() if v.get("ccli") not in (None, "") else None
            s["original"] = bool(v.get("original"))
            s["key"] = key_of(s)
            songs.append(s)
        songs.sort(key=lambda s: norm_title(s["title"]))
        _bank_cache.update(key=key, songs=songs, source=str(p))
        return songs, str(p)
    return [], None


# ----- where a song was sung: set lists, and descriptions that credit its number --
def _setlists() -> list[dict]:
    if load().demo:
        return DEMO_SETLISTS
    out, seen = [], set()
    for base in [Path(load().automator.path), Path(os.environ.get("ARISE_ARCHIVE_ROOT", "/srv/arise/archive")) / "arise-youtube-automation"]:
        for p in sorted(list(base.glob("setlist_*.json")) + list(base.glob("cloud_workspace/setlist_*.json"))):
            try:
                d = json.loads(p.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            if not isinstance(d, dict) or not isinstance(d.get("songs"), list):
                continue
            date = d.get("date_ct") or d.get("date") or (re.search(r"\d{4}-\d{2}-\d{2}", p.name) or [None])[0]
            k = (date, d.get("service"))
            if k in seen:
                continue
            seen.add(k)
            out.append({"date": date, "service": d.get("service"), "video_id": d.get("video_id"), "path": p.name,
                        "songs": [s if isinstance(s, dict) else {"title": str(s)} for s in d["songs"]]})
    return out


_credit_cache: dict = {"key": None, "map": {}}


def _credited() -> dict:
    """{ccli: [video row]} from the channel snapshots' descriptions (the numbers as written)."""
    if load().demo:
        return {}
    from . import channel
    try:
        cat = channel.catalogue.load(channel.acfg())
    except Exception:  # noqa: BLE001 - no archive yet: no credits to show
        return {}
    if _credit_cache["key"] is cat:
        return _credit_cache["map"]
    m: dict = {}
    for vid, rec in cat.items():
        if rec.get("kind") == "short":
            continue
        for line in (rec.get("description") or "").splitlines():
            for n in CCLI_RE.findall(line):
                m.setdefault(n, {})[vid] = {"video_id": vid, "title": rec.get("title"), "date": rec.get("date")}
    m = {k: sorted(v.values(), key=lambda r: r["date"] or "", reverse=True) for k, v in m.items()}
    _credit_cache.update(key=cat, map=m)
    return m


def sung(song: dict) -> list[dict]:
    """Every service the set lists or the descriptions put this song in, newest first."""
    rows: dict = {}
    nt = norm_title(song["title"])
    for sl in _setlists():
        for s in sl["songs"]:
            hit = (song.get("ccli") and str(s.get("ccli") or "") == song["ccli"]) or (not s.get("ccli") and norm_title(s.get("title", "")) == nt)
            if hit:
                k = sl.get("video_id") or sl["date"]
                rows[k] = {"date": sl["date"], "service": sl.get("service"), "video_id": sl.get("video_id"), "from": "set list", "path": sl["path"]}
    if song.get("ccli"):
        for v in _credited().get(song["ccli"], []):
            r = rows.get(v["video_id"])
            if r:
                r["title"] = v["title"]
                r["from"] = "set list and description"
            else:
                rows[v["video_id"]] = {"date": v["date"], "title": v["title"], "video_id": v["video_id"], "from": "description"}
    return sorted(rows.values(), key=lambda r: r.get("date") or "", reverse=True)


# ----- the lyrics store -----------------------------------------------------------
def _dir() -> Path:
    return Path(load().system.data_root) / "songs" / "lyrics"


def _owner_ids():
    try:
        import pwd
        who = str(load().owner.user or "")
        if who and who != "root":
            pw = pwd.getpwnam(who)
            return pw.pw_uid, pw.pw_gid
    except (KeyError, ImportError, AttributeError):
        pass
    return None


def _demo_store() -> dict:
    from . import demo_state
    return demo_state.get("songs.lyrics", lambda: dict(DEMO_LYRICS))


def split_header(raw: str) -> tuple[dict, str]:
    lines = raw.splitlines()
    head = {}
    i = 0
    while i < len(lines) and HEADER_RE.match(lines[i]):
        k, v = HEADER_RE.match(lines[i]).groups()
        head[k.lower()] = v.strip()
        i += 1
    if head and i < len(lines) and not lines[i].strip():
        i += 1
    return head, "\n".join(lines[i:]).strip("\n")


def all_lyrics() -> dict:
    """{key: {title, ccli, source, text, updated}}"""
    if load().demo:
        return {k: dict(v) for k, v in _demo_store().items()}
    d = _dir()
    out = {}
    try:
        files = list(d.glob("*.txt"))
    except OSError:
        return {}
    for p in files:
        try:
            head, text = split_header(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        out[p.stem] = {"title": head.get("title"), "ccli": head.get("ccli"), "source": head.get("source"), "text": text,
                       "updated": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(p.stat().st_mtime))}
    return out


def _write(key: str, title: str, ccli: str | None, text: str, source: str, by: str) -> dict:
    body = (f"Title: {title}\n" + (f"CCLI: {ccli}\n" if ccli else "") + f"Source: {source}\n\n" + text.strip("\n") + "\n")
    if load().demo:
        _demo_store()[key] = {"title": title, "ccli": ccli, "source": source, "text": text.strip("\n"),
                              "updated": time.strftime("%Y-%m-%dT%H:%M:%S")}
        return {"ok": True, "demo": True, "key": key}
    d = _dir()
    with _lock:
        for sub in ("", ".versions", ".removed"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        p = d / f"{key}.txt"
        kept = None
        if p.exists():
            kept = d / ".versions" / f"{key}-{time.strftime('%Y%m%d-%H%M%S')}.txt"
            os.replace(p, kept)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(body, encoding="utf-8")
        os.chmod(tmp, 0o640)
        os.replace(tmp, p)
        ids = _owner_ids()
        if ids:
            for x in [d.parent, d, d / ".versions", d / ".removed", p] + ([kept] if kept else []):
                try:
                    os.chown(x, *ids)
                except OSError:
                    pass
    audit.record(by, "songs.lyrics", key, detail=f"{title} ({source})")
    return {"ok": True, "key": key, "kept_previous": bool(kept)}


# ----- reading lyrics files: SongSelect .txt and .usr, ChordPro, plain text --------
def parse_file(name: str, raw: str) -> dict:
    """{title, ccli, writers, copyright, text, format}. Never invents: a field the file lacks stays empty."""
    raw = (raw or "").replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    ext = os.path.splitext(name or "")[1].lower()
    if ext == ".usr" or re.search(r"(?m)^\[S A?\d+\]", raw):
        return _usr(raw)
    if ext in (".cho", ".chopro", ".chordpro", ".pro", ".crd") or re.search(r"(?m)^\{(title|t|soc|start_of_chorus)\b", raw):
        return _chordpro(raw)
    if re.search(r"(?m)^CCLI Song #\s*\d+", raw):
        return _songselect_txt(raw)
    head, text = split_header(raw)
    if head:
        return {"title": head.get("title"), "ccli": (re.sub(r"\D", "", head.get("ccli", "")) or None), "writers": head.get("writers"),
                "text": text, "format": "text"}
    lines = text.split("\n")
    first = next((i for i, l in enumerate(lines) if l.strip()), 0)
    title = lines[first].strip() if lines else ""
    return {"title": title or os.path.splitext(os.path.basename(name or ""))[0], "ccli": None, "text": "\n".join(lines[first + 1:]).strip("\n"),
            "format": "text"}


def _songselect_txt(raw: str) -> dict:
    lines = raw.split("\n")
    first = next((i for i, l in enumerate(lines) if l.strip()), 0)
    title = lines[first].strip()
    at = next(i for i, l in enumerate(lines) if re.match(r"^CCLI Song #\s*\d+", l))
    ccli = re.search(r"\d+", lines[at]).group(0)
    tail = [l.strip() for l in lines[at + 1:] if l.strip()]
    writers = tail[0] if tail and not tail[0].startswith("©") and not tail[0].lower().startswith("for use") else None
    copyright_ = next((l for l in tail if l.startswith("©")), None)
    return {"title": title, "ccli": ccli, "writers": writers, "copyright": copyright_,
            "text": "\n".join(lines[first + 1:at]).strip("\n"), "format": "SongSelect text"}


def _usr(raw: str) -> dict:
    vals, num = {}, None
    for line in raw.split("\n"):
        m = re.match(r"^\[S A?(\d+)\]", line)
        if m:
            num = m.group(1)
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip().lower()] = v
    fields = [f for f in vals.get("fields", "").split("/t")]
    words = [w for w in vals.get("words", "").split("/t")]
    parts = []
    for i, w in enumerate(words):
        label = fields[i].strip() if i < len(fields) else ""
        body = w.replace("/n", "\n").strip("\n")
        parts.append((label + "\n" if label else "") + body)
    return {"title": vals.get("title", "").strip() or None, "ccli": num, "writers": ", ".join(x.strip() for x in (vals.get("author") or "").split("|") if x.strip()) or None,
            "copyright": ", ".join(x.strip() for x in (vals.get("copyright") or "").split("|") if x.strip()) or None, "text": "\n\n".join(p for p in parts if p.strip()),
            "format": "SongSelect .usr"}


def _chordpro(raw: str) -> dict:
    title = ccli = writers = None
    out = []
    for line in raw.split("\n"):
        m = re.match(r"^\{\s*([a-z_]+)\s*(?::\s*(.*?))?\s*\}\s*$", line.strip(), re.I)
        if m:
            k, v = m.group(1).lower(), (m.group(2) or "").strip()
            if k in ("title", "t"):
                title = v
            elif k == "ccli":
                ccli = re.sub(r"\D", "", v) or None
            elif k in ("artist", "composer", "author", "lyricist"):
                writers = v
            elif k in ("soc", "start_of_chorus"):
                out.append("Chorus")
            elif k in ("sov", "start_of_verse") and v:
                out.append(v)
            elif k in ("sob", "start_of_bridge"):
                out.append("Bridge")
            elif k in ("comment", "c", "ci", "comment_italic") and v:
                out.append(v)
            elif k in ("eoc", "end_of_chorus", "eov", "end_of_verse", "eob", "end_of_bridge"):
                out.append("")
            continue
        if line.strip().startswith("#"):
            continue
        out.append(re.sub(r"\s{2,}", " ", re.sub(r"\[[^\]]*\]", "", line)).rstrip())
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip("\n")
    return {"title": title, "ccli": ccli, "writers": writers, "text": text, "format": "ChordPro"}


# ----- the API -------------------------------------------------------------------
def _words(q: str) -> tuple[list[str], list[str]]:
    phrases = [norm_title(p) for p in re.findall(r'"([^"]+)"', q or "")]
    rest = re.sub(r'"[^"]*"', " ", q or "")
    return [w for w in norm_title(rest).split() if w], [p for p in phrases if p]


def _snippet(text: str, words: list[str], phrases: list[str]) -> str | None:
    for line in text.split("\n"):
        n = norm_title(line)
        if (phrases and any(p in n for p in phrases)) or (words and all(w in n for w in words)):
            s = line.strip()[:160]
            for w in phrases + words:
                s = re.sub(f"(?i)({re.escape(w)})", r"[\1]", s)
            return s
    return None


def listing(q: str = "", has: str = "") -> dict:
    songs, source = bank()
    lyr = all_lyrics()
    keyed = {s["key"]: s for s in songs}
    rows = []
    for s in songs:
        rows.append({**s, "lyrics": s["key"] in lyr, "in_bank": True})
    for k, v in lyr.items():   # lyrics that match no song_bank entry yet
        if k not in keyed:
            rows.append({"key": k, "title": v.get("title") or k, "ccli": v.get("ccli"), "lyrics": True, "in_bank": False, "original": False})
    words, phrases = _words(q)
    out = []
    for r in rows:
        if words or phrases:
            meta = norm_title(" ".join(str(r.get(k) or "") for k in ("title", "ccli", "writers", "performed_by", "note")))
            on_meta = all(w in meta for w in words) and all(p in meta for p in phrases)
            snip = _snippet(lyr[r["key"]]["text"], words, phrases) if r["lyrics"] else None
            if not on_meta and not snip:
                continue
            r = {**r, "matched": "title" if on_meta and norm_title(r["title"]).find(" ".join(words)) >= 0 else "details" if on_meta else "lyrics"}
            if snip and not on_meta:
                r["snippet"] = snip
        if has == "lyrics" and not r["lyrics"]:
            continue
        if has == "missing" and r["lyrics"]:
            continue
        if has == "original" and not r.get("original"):
            continue
        out.append(r)
    for r in out:
        h = sung(r) if r.get("in_bank") else []
        r["sung"] = len(h)
        r["last_sung"] = h[0]["date"] if h else None
    order = {"title": 0, "details": 1, "lyrics": 2}
    digits = re.sub(r"(?i)^ccli\s*#?\s*", "", (q or "").strip())
    exact = lambda r: 0 if (digits.isdigit() and r.get("ccli") == digits) or norm_title(r["title"]) == norm_title(q or "") else 1  # noqa: E731
    out.sort(key=lambda r: (exact(r), order.get(r.get("matched"), 0) if (words or phrases) else 0, norm_title(r["title"])))
    return {"demo": load().demo, "source": source, "total": len(out), "songs": out, "note": LICENCE_NOTE,
            "counts": {"all": len(songs), "lyrics": sum(1 for s in songs if s["key"] in lyr),
                       "originals": sum(1 for s in songs if s.get("original")), "unlinked": sum(1 for k in lyr if k not in keyed)}}


def song(key: str) -> dict:
    if not KEY_RE.match(key or ""):
        return {"ok": False, "err": "not a song"}
    songs, source = bank()
    s = next((x for x in songs if x["key"] == key), None)
    lyr = all_lyrics().get(key)
    if not s and not lyr:
        return {"ok": False, "err": "no such song in song_bank.json"}
    base = s or {"key": key, "title": lyr.get("title") or key, "ccli": lyr.get("ccli"), "original": False}
    versions = 0
    if not load().demo:
        try:
            versions = len(list((_dir() / ".versions").glob(f"{key}-*.txt")))
        except OSError:
            pass
    return {"ok": True, **base, "in_bank": bool(s), "source": source, "lyrics": lyr, "versions": versions,
            "sung": sung(base) if s else [], "licence": LICENCE_NOTE}


def save(key: str, text: str, by: str, title: str = "", source: str = "pasted") -> dict:
    if not KEY_RE.match(key or ""):
        return {"ok": False, "err": "not a song"}
    text = (text or "").replace("\r\n", "\n").strip("\n")
    if not text.strip():
        return {"ok": False, "err": "nothing to save: paste the lyrics first"}
    if len(text) > 60_000:
        return {"ok": False, "err": "that is longer than any song (60,000 characters at most)"}
    songs, _ = bank()
    s = next((x for x in songs if x["key"] == key), None)
    have = all_lyrics().get(key)
    if not s and not have:
        return {"ok": False, "err": "no such song in song_bank.json (import a file to add lyrics for a song that is not there yet)"}
    t = s["title"] if s else (have.get("title") or title or key)
    return _write(key, t, (s or {}).get("ccli") or (have or {}).get("ccli"), text, source[:80], by)


def remove(key: str, confirm: str, by: str) -> dict:
    """Taking lyrics off a song is Bradly's click, with the title typed. The file is moved, never deleted."""
    if not KEY_RE.match(key or ""):
        return {"ok": False, "err": "not a song"}
    cur = all_lyrics().get(key)
    if not cur:
        return {"ok": False, "err": "this song has no lyrics here"}
    if (confirm or "").strip() != (cur.get("title") or key):
        return {"ok": False, "err": "type the song's title to confirm"}
    if load().demo:
        _demo_store().pop(key, None)
        return {"ok": True, "demo": True}
    d = _dir()
    (d / ".removed").mkdir(parents=True, exist_ok=True)
    to = d / ".removed" / f"{key}-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    os.replace(d / f"{key}.txt", to)
    audit.record(by, "songs.lyrics.remove", key, detail=f"moved to {to}")
    return {"ok": True, "moved_to": str(to)}


def import_files(files: list[dict], by: str) -> dict:
    """[{name, text}] -> each one parsed, matched to song_bank.json, saved.
    Matched by the CCLI number in the file, else by a title that exactly one song has. Never by a sung phrase."""
    songs, _ = bank()
    by_ccli = {s["ccli"]: s for s in songs if s.get("ccli")}
    by_title: dict = {}
    for s in songs:
        by_title.setdefault(norm_title(s["title"]), []).append(s)
    results = []
    for f in files[:200]:
        name = str(f.get("name") or "lyrics.txt")[:200]
        if not name.lower().endswith(IMPORT_TYPES):
            results.append({"name": name, "ok": False, "err": f"not a lyrics file ({', '.join(IMPORT_TYPES)})"}); continue
        try:
            p = parse_file(name, str(f.get("text") or ""))
        except Exception as e:  # noqa: BLE001 - one bad file never stops the rest
            results.append({"name": name, "ok": False, "err": f"could not read it: {e}"}); continue
        if not (p.get("text") or "").strip():
            results.append({"name": name, "ok": False, "err": "no lyrics in it"}); continue
        target, how = None, None
        if p.get("ccli") and p["ccli"] in by_ccli:
            target, how = by_ccli[p["ccli"]], "CCLI number"
        elif p.get("title") and len(by_title.get(norm_title(p["title"]), [])) == 1 and not p.get("ccli"):
            target, how = by_title[norm_title(p["title"])][0], "title (check it is the right song)"
        src = f"imported {name} ({p['format']})"
        if target:
            r = _write(target["key"], target["title"], target.get("ccli"), p["text"], src[:80], by)
            results.append({"name": name, "ok": r["ok"], "key": target["key"], "title": target["title"], "matched_by": how})
        else:
            why = ("its CCLI number is not in song_bank.json" if p.get("ccli") else
                   "several songs share that title: open the right one and paste it there" if len(by_title.get(norm_title(p.get("title") or ""), [])) > 1 else
                   "no song in song_bank.json has that title")
            key = "x-" + slug(p.get("title") or name)
            r = _write(key, p.get("title") or name, p.get("ccli"), p["text"], src[:80], by)
            results.append({"name": name, "ok": r["ok"], "key": key, "title": p.get("title") or name, "matched_by": None, "note": f"kept, not linked: {why}"})
    return {"ok": True, "demo": load().demo, "results": results,
            "linked": sum(1 for r in results if r.get("matched_by")), "unlinked": sum(1 for r in results if r.get("ok") and not r.get("matched_by")),
            "failed": sum(1 for r in results if not r.get("ok"))}


# ----- the Lyrics inbox (round 7, 99 and 100) -------------------------------------------
# Bradly exports songs from Proclaim (or SongSelect) and drops the files into "Lyrics inbox" in
# Nextcloud; he and the worship leader ([songs] inbox_users) see that folder. Every few minutes
# the server imports whatever landed there with the same rules as the Songs tab's Import, then
# moves each file to Imported/ (or Not imported/ with the reason). The lyrics stay in the
# lyrics store on this server; nothing is copied anywhere else.
INBOX_MAX = 2_000_000
INBOX_KEEP = 60


def inbox_dir() -> Path:
    return Path(load().system.data_root) / "shares" / "lyrics-inbox"


def inbox_users() -> list[str]:
    raw = load().raw
    sc = (raw.get("songs") if isinstance(raw, dict) else None) or {}
    users = [str(u) for u in (sc.get("inbox_users") or [])]
    owner = str(getattr(load().owner, "user", "") or "")
    if owner and owner not in users:
        users.insert(0, owner)
    return users


def _inbox_log_path() -> Path:
    return Path(load().state_dir) / "songs-inbox.json"


def inbox_log() -> dict:
    if load().demo:
        from . import demo_state
        return demo_state.get("songs.inbox", lambda: {"runs": [{"at": "2026-10-28T21:10", "files": 2, "linked": 1, "unlinked": 1, "failed": 0,
                                                                  "results": [{"name": "Make Room.txt", "ok": True, "title": "Make Room", "matched_by": "CCLI number"},
                                                                              {"name": "Sample song.txt", "ok": True, "title": "Sample song", "matched_by": None,
                                                                               "note": "kept, not linked: no song in song_bank.json has that title"}]}],
                                                        "folder": "Lyrics inbox", "users": inbox_users(), "demo": True})
    try:
        d = json.loads(_inbox_log_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {"runs": d.get("runs", [])[:20], "folder": "Lyrics inbox", "users": inbox_users(), "path": str(inbox_dir()), "demo": False}


def _move_aside(f: Path, sub: str) -> None:
    dest = f.parent / sub
    dest.mkdir(exist_ok=True)
    target = dest / f.name
    if target.exists():
        target = dest / f"{f.stem} {datetime.now():%Y-%m-%d %H%M%S}{f.suffix}"
    os.replace(f, target)


def inbox_scan(by: str = "the Lyrics inbox") -> dict:
    """Import everything at the top of the inbox. Files that are not lyrics stay where they are."""
    if load().demo:
        return {"ok": True, "demo": True, "files": 0, "note": "the sample has no inbox"}
    d = inbox_dir()
    if not d.is_dir():
        return {"ok": True, "files": 0, "note": f"no inbox yet ({d})"}
    picked = [f for f in sorted(d.iterdir()) if f.is_file() and not f.is_symlink() and not f.name.startswith(".")
              and f.name.lower().endswith(IMPORT_TYPES) and f.stat().st_size <= INBOX_MAX]
    if not picked:
        return {"ok": True, "files": 0}
    files = []
    for f in picked:
        try:
            files.append({"name": f.name, "text": f.read_bytes().decode("utf-8-sig", errors="replace"), "_p": f})
        except OSError:
            continue
    r = import_files([{"name": x["name"], "text": x["text"]} for x in files], by)
    for x, res in zip(files, r["results"]):
        try:
            _move_aside(x["_p"], "Imported" if res.get("ok") else "Not imported")
        except OSError:
            pass
    run = {"at": datetime.now().isoformat(timespec="minutes"), "files": len(files), "linked": r["linked"], "unlinked": r["unlinked"],
           "failed": r["failed"], "results": [{k: v for k, v in res.items() if k in ("name", "ok", "title", "matched_by", "note", "err")} for res in r["results"]]}
    lp = _inbox_log_path()
    try:
        old = json.loads(lp.read_text(encoding="utf-8")).get("runs", [])
    except (OSError, ValueError):
        old = []
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(json.dumps({"runs": [run] + old[:INBOX_KEEP - 1]}, indent=1), encoding="utf-8")
    from . import audit
    audit.record(by, "songs.inbox", f"{len(files)} file(s)", detail=f"{r['linked']} linked, {r['unlinked']} kept unlinked, {r['failed']} failed")
    return {"ok": True, **run}


# ----- the CCLI song-usage report (round 7, 106) ----------------------------------------
# What was sung and how often, for the church's CCLI reporting: titles and numbers exactly as
# song_bank.json (or the set list) has them, never a guessed number, never a lyric.
def quarter_of(d) -> tuple[str, str, str]:
    """Pure: a date -> (label, first day, last day) of its quarter, e.g. ('2026 Q4', '2026-10-01', '2026-12-31')."""
    from datetime import date as _date
    if isinstance(d, str):
        d = _date.fromisoformat(d[:10])
    q = (d.month - 1) // 3
    first = _date(d.year, q * 3 + 1, 1)
    last = _date(d.year + (q == 3), (q * 3 + 3) % 12 + 1, 1)
    from datetime import timedelta as _td
    return f"{d.year} Q{q + 1}", first.isoformat(), (last - _td(days=1)).isoformat()


def usage_report(start: str, end: str, setlists: list[dict] | None = None, songs: list[dict] | None = None) -> dict:
    """Pure given its inputs: every song in the set lists between two dates (inclusive)."""
    setlists = setlists if setlists is not None else _setlists()
    if songs is None:
        songs, _ = bank()
    by_ccli = {s["ccli"]: s for s in songs if s.get("ccli")}
    by_title = {norm_title(s["title"]): s for s in songs}
    rows: dict = {}
    services = 0
    for sl in setlists:
        dte = str(sl.get("date") or "")[:10]
        if not dte or not (start <= dte <= end):
            continue
        services += 1
        for item in sl.get("songs", []):
            num = str(item.get("ccli") or "").strip() or None
            known = by_ccli.get(num) if num else by_title.get(norm_title(item.get("title", "")))
            title = (known or {}).get("title") or item.get("title") or "?"
            ccli = num or (known or {}).get("ccli")
            k = ccli or "t:" + norm_title(title)
            r = rows.setdefault(k, {"title": title, "ccli": ccli, "times": 0, "dates": [], "original": bool((known or {}).get("original"))})
            r["times"] += 1
            r["dates"].append(dte)
    out = sorted(rows.values(), key=lambda r: (-r["times"], r["title"].lower()))
    return {"from": start, "to": end, "services": services, "songs": out,
            "no_number": [r["title"] for r in out if not r["ccli"] and not r["original"]],
            "note": "From the set lists. A song with no CCLI number here has none banked: look it up in SongSelect; nothing is guessed."}


def usage_csv(rep: dict) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Title", "CCLI song number", "Times used", "Dates"])
    for r in rep["songs"]:
        w.writerow([r["title"], r["ccli"] or ("Arise original" if r["original"] else ""), r["times"], " ".join(r["dates"])])
    return buf.getvalue()


def write_quarter_report(today=None) -> dict:
    """The quarterly report for the quarter that just ended, into <data_root>/songs/reports/."""
    from datetime import date as _date, timedelta as _td
    today = today or _date.today()
    label, first, last = quarter_of(_date(today.year, ((today.month - 1) // 3) * 3 + 1, 1) - _td(days=1))
    rep = usage_report(first, last)
    if load().demo:
        return {"ok": True, "demo": True, "label": label, **rep}
    out = Path(load().system.data_root) / "songs" / "reports"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"ccli-usage-{label.replace(' ', '-')}.csv"
    f.write_text(usage_csv(rep), encoding="utf-8")
    return {"ok": True, "label": label, "file": str(f), **rep}


# ----- sample data: songs and numbers Bradly banked (CLAUDE.md), no lyrics -----------
DEMO_BANK = [
    {"title": "Praise", "ccli": "7213077", "note": "always followed by My Worship (Bradly, Oct 6)", "original": False},
    {"title": "My Worship", "ccli": "7098688", "writers": "Philip Nathan Thompson, Zenzo Matoga", "original": False},
    {"title": "Make Room", "ccli": "7122057", "writers": "Heideriqui, Farro, Cortazio, White", "original": False},
    {"title": "Surrounded (Fight My Battles)", "ccli": "7098758", "writers": "Elyssa Figueroa", "note": "Bradly calls it “Fight My Battles”", "original": False},
    {"title": "To Worship You I Live", "ccli": "4654131", "writers": "Israel Houghton, Meleasa Houghton", "note": "Bradly calls it “I Live to Worship You”", "original": False},
    {"title": "We Want Revival", "ccli": "7247827", "writers": "Hannah Yates, Jonathan Stamper, Seth Yates", "original": False},
    {"title": "Great Expectation", "ccli": None, "writers": "Kristina Robinson", "note": "an Arise original; no CCLI", "original": True},
]
DEMO_LYRICS = {
    "7247827": {"title": "We Want Revival", "ccli": "7247827", "source": "sample", "updated": "2026-10-28T09:00:00",
                "text": "Verse 1\nSample: on the server these are the lyrics you pasted from Proclaim.\nA search for any line finds the song.\n\nChorus\nSample chorus line, kept here and never in a description."},
}
DEMO_SETLISTS = [
    {"date": "2026-10-19", "service": "Glory Night", "video_id": "2wVIGBvQLzE", "path": "setlist_2026-10-19_glory_night.json",
     "songs": [{"title": "Make Room", "ccli": "7122057"}, {"title": "Surrounded (Fight My Battles)", "ccli": "7098758"}, {"title": "To Worship You I Live", "ccli": "4654131"}]},
    {"date": "2026-10-11", "service": "Sunday Morning Service", "video_id": "AnVfOCesXM4", "path": "setlist_2026-10-11_sunday.json",
     "songs": [{"title": "Praise", "ccli": "7213077"}, {"title": "My Worship", "ccli": "7098688"}, {"title": "We Want Revival", "ccli": "7247827"}]},
]

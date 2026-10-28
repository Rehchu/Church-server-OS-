"""The read side (13.4): search, get_document, get_transcript, song, video, status.

Every answer carries provenance (repo, path, commit, lines or seconds) and is
capped at about 20 KB. The index is opened read-only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import store
from .config import Config
from .parsers import norm_title

CAP = 20_000
KIND_WEIGHT = {"code": 0.35, "media": 0.8, "data": 0.7, "history": 0.9}


def _db(cfg: Config):
    if not cfg.index.exists():
        raise FileNotFoundError(f"no index yet at {cfg.index}: arisectl archive build")
    return store.open_ro(cfg.index)


def fts_query(q: str) -> str:
    """User words -> a safe FTS5 query: quoted phrases kept, every other word quoted, all must match."""
    parts = []
    for phrase, word in re.findall(r'"([^"]+)"|(\S+)', q or ""):
        if phrase:
            parts.append('"' + phrase.replace('"', "") + '"')
        else:
            w = re.sub(r"[^\w']", "", word)
            if w:
                parts.append('"' + w.replace('"', "") + '"')
    return " ".join(parts)


def _prov(r) -> dict:
    p = {"repo": r["repo"], "path": r["path"], "commit": r["commit_sha"]}
    if r["start_sec"] is not None:
        p["start_sec"] = round(r["start_sec"], 2)
    elif r["start_line"] is not None:
        p["lines"] = [r["start_line"], r["end_line"]]
    return p


def cap(obj: dict, list_key: str | None = None) -> dict:
    """Trim the list in obj until the JSON is under CAP; say so."""
    s = json.dumps(obj, ensure_ascii=False)
    if len(s) <= CAP:
        return obj
    if list_key and isinstance(obj.get(list_key), list):
        while obj[list_key] and len(json.dumps(obj, ensure_ascii=False)) > CAP:
            obj[list_key].pop()
            obj["truncated"] = True
        obj["more"] = "trimmed to about 20 KB: narrow the query, or use get_document for one file"
    return obj


def search(cfg: Config, query: str, kind=None, repo=None, video_id=None, date_from=None, date_to=None,
           include_history: bool = False, include_private: bool = True, limit: int = 20) -> dict:
    q = fts_query(query)
    if not q:
        return {"results": [], "note": "empty query"}
    where, args = ["chunks MATCH ?"], [q]
    if kind:
        where.append("d.kind = ?"); args.append(kind)
    if repo:
        where.append("d.repo = ?"); args.append(repo)
    if video_id:
        where.append("d.video_id = ?"); args.append(video_id)
    if date_from:
        where.append("d.date >= ?"); args.append(date_from)
    if date_to:
        where.append("d.date <= ?"); args.append(date_to)
    if not include_history and kind != "history":
        where.append("d.history = 0")
    if not include_private:
        where.append("d.private = 0")
    weight = "CASE d.kind " + " ".join(f"WHEN '{k}' THEN {w}" for k, w in KIND_WEIGHT.items()) + " ELSE 1.0 END"
    sql = (f"SELECT d.*, m.start_line, m.end_line, m.start_sec, m.end_sec, m.link, "
           f"snippet(chunks, 0, '[', ']', ' … ', 28) AS snip, bm25(chunks) * {weight} AS score "
           f"FROM chunks JOIN chunk_meta m ON m.id = chunks.rowid JOIN docs d ON d.id = m.doc_id "
           f"WHERE {' AND '.join(where)} ORDER BY score LIMIT ?")
    args.append(max(1, min(int(limit or 20), 100)))
    with _db(cfg) as db:
        rows = db.execute(sql, args).fetchall()
    res = []
    for r in rows:
        item = {"kind": r["kind"], "title": r["title"], "snippet": r["snip"], "provenance": _prov(r)}
        for k in ("video_id", "date"):
            if r[k]:
                item[k] = r[k]
        if r["link"]:
            item["link"] = r["link"]
        if r["private"]:
            item["private"] = True
        if r["history"]:
            item["history"] = "a PAST state, not the live text"
        res.append(item)
    return cap({"query": query, "results": res}, "results")


def _safe(cfg: Config, repo: str, path: str) -> Path:
    if repo not in cfg.repos:
        raise ValueError(f"unknown repo {repo!r}; one of {', '.join(cfg.repos)}")
    base = cfg.assembled.resolve() if path.startswith("media-assembled/") else cfg.repo_dir(repo).resolve()
    rel = path[len("media-assembled/"):] if path.startswith("media-assembled/") else path
    full = (base / rel).resolve()
    if base not in full.parents and full != base:
        raise ValueError("that path leaves the archive")
    return full


def get_document(cfg: Config, repo: str, path: str, start_line: int | None = None, end_line: int | None = None) -> dict:
    with _db(cfg) as db:
        docs = db.execute("SELECT * FROM docs WHERE repo=? AND path=?", (repo, path)).fetchall()
        skipped = db.execute("SELECT reason FROM skipped WHERE repo=? AND path=?", (repo, path)).fetchone()
    if not docs:
        return {"error": f"not indexed: {repo}/{path}" + (f" (skipped: {skipped[0]})" if skipped else "")}
    d = docs[0]
    head = {"repo": repo, "path": path, "commit": d["commit_sha"], "kind": d["kind"], "private": bool(d["private"])}
    if d["kind"] == "media":
        return {**head, "metadata": {"size": d["size"], "sha256": d["sha256"], **json.loads(d["extra"] or "{}")},
                "note": "media: metadata only"}
    full = _safe(cfg, repo, path)
    lines = full.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    a = max(1, int(start_line or 1))
    b = min(len(lines), int(end_line or len(lines)))
    out, size = [], 0
    for i in range(a - 1, b):
        size += len(lines[i]) + 1
        if size > CAP - 600:
            head["truncated"] = True
            head["next_start_line"] = i + 1
            break
        out.append(lines[i])
    return {**head, "lines": [a, a + len(out) - 1], "total_lines": len(lines), "text": "\n".join(out)}


def get_transcript(cfg: Config, video_id: str, start_sec: float | None = None, end_sec: float | None = None) -> dict:
    with _db(cfg) as db:
        rows = db.execute("SELECT s.start, s.dur, s.text, d.repo, d.path, d.commit_sha, d.extra FROM segments s "
                          "JOIN docs d ON d.id = s.doc_id WHERE s.video_id=? AND s.start >= ? AND s.start <= ? ORDER BY s.start",
                          (video_id, float(start_sec or 0), float(end_sec if end_sec is not None else 1e9))).fetchall()
    if not rows:
        return {"video_id": video_id, "segments": [], "note": "no timed transcript for this video in the archive"}
    sources = {}
    segs = []
    for r in rows:
        src = f"{r['repo']}/{r['path']}"
        sources[src] = r["commit_sha"]
        segs.append({"start": round(r["start"], 2), "dur": round(r["dur"] or 0, 2), "text": r["text"], "source": src})
    return cap({"video_id": video_id, "sources": sources, "link": f"https://youtu.be/{video_id}",
                "warning": "Transcripts hold sung lyrics: never quote songs. Names in a transcript are sounds, not facts.",
                "segments": segs}, "segments")


def song(cfg: Config, title_or_ccli: str) -> dict:
    """Exact only: a CCLI number, or a title after case and punctuation are set aside. Never fuzzy."""
    q = (title_or_ccli or "").strip()
    digits = re.sub(r"(?i)^ccli\s*#?\s*", "", q)
    with _db(cfg) as db:
        if digits.isdigit():
            rows = db.execute("SELECT * FROM songs WHERE ccli=?", (digits,)).fetchall()
            by = "ccli"
        else:
            rows = db.execute("SELECT * FROM songs WHERE title_norm=?", (norm_title(q),)).fetchall()
            by = "title"
    hits = []
    for r in rows:
        h = {k: r[k] for k in ("title", "ccli", "writers", "copyright", "admin", "credit_line", "verified", "note") if r[k]}
        h["original"] = bool(r["original"])
        h["provenance"] = {"repo": r["repo"], "path": r["path"], "commit": r["commit_sha"]}
        hits.append(h)
    out = {"query": q, "matched_by": by, "songs": hits}
    if not hits:
        out["note"] = ("Not in song_bank.json. Never attach a CCLI number because a title or a sung phrase looks alike; "
                       "ask Bradly.")
    elif len(hits) > 1:
        out["note"] = "Several entries match: choose by writers and number, never by a sung phrase."
    return out


def video(cfg: Config, video_id: str) -> dict:
    with _db(cfg) as db:
        docs = db.execute("SELECT * FROM docs WHERE video_id=? ORDER BY kind, path", (video_id,)).fetchall()
        named = db.execute("SELECT * FROM docs WHERE kind='media' AND path LIKE ? AND (video_id IS NULL OR video_id<>?)",
                           (f"%{video_id}%", video_id)).fetchall()
        dates = sorted({d["date"] for d in docs if d["date"]})
        sets = db.execute(f"SELECT * FROM docs WHERE kind='setlist' AND date IN ({','.join('?' * len(dates))})", dates).fetchall() if dates else []
        groups: dict = {}
        for d in list(docs) + list(named) + list(sets):
            text = db.execute("SELECT c.text FROM chunk_meta m JOIN chunks c ON c.rowid = m.id WHERE m.doc_id=? ORDER BY m.id LIMIT 1",
                              (d["id"],)).fetchone()
            item = {"title": d["title"], "date": d["date"], "provenance": {"repo": d["repo"], "path": d["path"], "commit": d["commit_sha"]}}
            if d["kind"] in ("description", "history", "chapters", "setlist") and text:
                item["text"] = text[0][:1500]
            if d["history"]:
                item["history"] = "a PAST state, not the live text"
            if d["kind"] == "media":
                item["metadata"] = {"size": d["size"], "sha256": d["sha256"], **json.loads(d["extra"] or "{}")}
            groups.setdefault(d["kind"], []).append(item)
    out = {"video_id": video_id, "link": f"https://youtu.be/{video_id}", "found": groups}
    if not groups:
        out["note"] = "nothing in the archive names this video"
    # Keep it under ~20 KB: shorten texts first, then drop the longest groups' tails.
    if len(json.dumps(out, ensure_ascii=False)) > CAP:
        for items in groups.values():
            for it in items:
                if "text" in it:
                    it["text"] = it["text"][:400]
        while len(json.dumps(out, ensure_ascii=False)) > CAP:
            biggest = max(groups, key=lambda g: len(groups[g]))
            if len(groups[biggest]) <= 1:
                break
            groups[biggest].pop()
            out["truncated"] = True
    return out


def status(cfg: Config) -> dict:
    with _db(cfg) as db:
        commits = {k[len("commit:"):]: json.loads(v) for k, v in db.execute("SELECT k, v FROM meta WHERE k LIKE 'commit:%'")}
        kinds = {r[0]: r[1] for r in db.execute("SELECT kind, COUNT(*) FROM docs GROUP BY kind")}
        skipped = [{"repo": r[0], "path": r[1], "reason": r[2]} for r in db.execute("SELECT repo, path, reason FROM skipped ORDER BY repo, path")]
        built = store.get_meta(db, "built_at")
        songs = db.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
    return cap({"indexed_commits": commits, "built_at": built, "documents_by_kind": kinds, "songs": songs,
                "skipped": skipped}, "skipped")

"""The SQLite FTS5 index: one row per document, many chunk rows per document."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS docs(
  id INTEGER PRIMARY KEY, repo TEXT, path TEXT, commit_sha TEXT, kind TEXT, title TEXT,
  video_id TEXT, date TEXT, private INTEGER DEFAULT 0, history INTEGER DEFAULT 0,
  size INTEGER, sha256 TEXT, extra TEXT);
CREATE INDEX IF NOT EXISTS docs_rp ON docs(repo, path);
CREATE INDEX IF NOT EXISTS docs_vid ON docs(video_id);
CREATE INDEX IF NOT EXISTS docs_kind ON docs(kind);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(text, title, tokenize='unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS chunk_meta(id INTEGER PRIMARY KEY, doc_id INTEGER, start_line INTEGER, end_line INTEGER,
  start_sec REAL, end_sec REAL, link TEXT);
CREATE INDEX IF NOT EXISTS cm_doc ON chunk_meta(doc_id);
CREATE TABLE IF NOT EXISTS segments(doc_id INTEGER, video_id TEXT, start REAL, dur REAL, text TEXT);
CREATE INDEX IF NOT EXISTS seg_vid ON segments(video_id, start);
CREATE TABLE IF NOT EXISTS songs(id INTEGER PRIMARY KEY, doc_id INTEGER, title TEXT, title_norm TEXT, ccli TEXT,
  writers TEXT, copyright TEXT, admin TEXT, credit_line TEXT, original INTEGER, verified TEXT, note TEXT,
  repo TEXT, path TEXT, commit_sha TEXT);
CREATE INDEX IF NOT EXISTS songs_ccli ON songs(ccli);
CREATE INDEX IF NOT EXISTS songs_title ON songs(title_norm);
CREATE TABLE IF NOT EXISTS skipped(repo TEXT, path TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS inventory(repo TEXT, folder TEXT, ext TEXT, files INTEGER, bytes INTEGER, present INTEGER);
"""


def open_rw(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=30)
    db.executescript(SCHEMA)
    return db


class _Closing(sqlite3.Connection):
    """`with open_ro(...) as db:` closes the connection at the end (plain sqlite3 only commits),
    so the long-running MCP server never piles up open handles."""

    def __exit__(self, *exc):
        try:
            return super().__exit__(*exc)
        finally:
            self.close()


def open_ro(path: Path) -> sqlite3.Connection:
    """Read-only: the MCP server and the search verbs never write (13.4)."""
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30, factory=_Closing)
    db.row_factory = sqlite3.Row
    return db


def get_meta(db, k, default=None):
    r = db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return json.loads(r[0]) if r else default


def set_meta(db, k, v):
    db.execute("INSERT INTO meta(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, json.dumps(v)))


def delete_path(db, repo: str, path: str):
    ids = [r[0] for r in db.execute("SELECT id FROM docs WHERE repo=? AND path=?", (repo, path))]
    if ids:
        q = ",".join("?" * len(ids))
        db.execute(f"DELETE FROM chunks WHERE rowid IN (SELECT id FROM chunk_meta WHERE doc_id IN ({q}))", ids)
        db.execute(f"DELETE FROM chunk_meta WHERE doc_id IN ({q})", ids)
        db.execute(f"DELETE FROM segments WHERE doc_id IN ({q})", ids)
        db.execute(f"DELETE FROM songs WHERE doc_id IN ({q})", ids)
        db.execute(f"DELETE FROM docs WHERE id IN ({q})", ids)
    db.execute("DELETE FROM skipped WHERE repo=? AND path=?", (repo, path))


def delete_repo(db, repo: str):
    for (p,) in list(db.execute("SELECT DISTINCT path FROM docs WHERE repo=?", (repo,))):
        delete_path(db, repo, p)
    db.execute("DELETE FROM skipped WHERE repo=?", (repo,))
    db.execute("DELETE FROM inventory WHERE repo=?", (repo,))


def add_doc(db, d: dict) -> int:
    cur = db.execute(
        "INSERT INTO docs(repo, path, commit_sha, kind, title, video_id, date, private, history, size, sha256, extra) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (d["repo"], d["path"], d["commit_sha"], d["kind"], d.get("title"), d.get("video_id"), d.get("date"),
         int(bool(d.get("private"))), int(bool(d.get("history"))), d.get("size"), d.get("sha256"),
         json.dumps(d.get("extra") or {}, ensure_ascii=False)))
    return cur.lastrowid


def add_chunk(db, doc_id: int, text: str, title: str = "", start_line=None, end_line=None,
              start_sec=None, end_sec=None, link=None):
    if not text or not text.strip():
        return
    cur = db.execute("INSERT INTO chunk_meta(doc_id, start_line, end_line, start_sec, end_sec, link) VALUES(?,?,?,?,?,?)",
                     (doc_id, start_line, end_line, start_sec, end_sec, link))
    db.execute("INSERT INTO chunks(rowid, text, title) VALUES(?,?,?)", (cur.lastrowid, text, title or ""))

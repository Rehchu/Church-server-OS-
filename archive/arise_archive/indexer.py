"""Builds the index from the two mirrors (13.2, 13.3).

    build(cfg, full=False, pull=True)

Incremental by default: for each repo, `diff --name-status <indexed>..HEAD` decides
which files are re-read. `full=True` (the weekly rebuild) writes a fresh index next
to the old one and swaps it in atomically, so a Claude session searching meanwhile
never sees a half-built index. Only tracked files are read; untracked files,
the repository internals and the split pieces never are.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from . import parsers as P
from . import store
from .config import Config
from .secrets_filter import SCAN_LIMIT, content_has_credential, path_reason

DESC_TXT_RE = re.compile(r"(^sunday_|^glory_night_|^conf_desc_|^tonight_desc_|_for_streamyard|_description\.txt$|^desc\.txt$|^desc_)", re.I)
DESC_JSON_NAMES = {"channel_descriptions.json", "desc_written_log.json", "applied.json", "shorts_plan.json"}
README_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|[^|]*\|[^|]*\|\s*`([0-9a-f]{64})`\s*\|", re.M)


# ---------- the repository, read-only ------------------------------------------------
def git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=600)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} failed: {r.stderr.strip()[-300:]}")
    return r.stdout


def tracked(repo: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, timeout=600).stdout
    return [p for p in out.decode("utf-8", "surrogateescape").split("\0") if p]


def blob_ids(repo: Path, paths: list[str]) -> dict:
    """Blob ids from the index (no object download, so a partial clone stays partial)."""
    if not paths:
        return {}
    out = subprocess.run(["git", "-C", str(repo), "ls-files", "-s", "-z", "--", *paths], capture_output=True, timeout=120).stdout
    res = {}
    for rec in out.decode("utf-8", "surrogateescape").split("\0"):
        if "\t" in rec:
            meta, path = rec.split("\t", 1)
            res[path] = meta.split()[1]
    return res


def pull(repo: Path, log) -> None:
    try:
        git(repo, "fetch", "--quiet", "origin", "main")
        git(repo, "merge", "--ff-only", "--quiet", "origin/main")
    except RuntimeError as e:
        log(f"  ! {repo.name}: could not fast-forward to origin/main ({e}); indexing what is here")


# ---------- classification -----------------------------------------------------------
def classify(path: str):
    """(handler, reason): handler(path, data) -> [Parsed], or None with the reason to skip."""
    r = path_reason(path)
    if r:
        return None, r
    low = path.lower()
    base = low.rsplit("/", 1)[-1]
    ext = os.path.splitext(base)[1]
    if (base.endswith(".nocaptions") or base.endswith(".failed")) and "transcripts/" in low:
        return None, "transcript marker (no text)"
    if base in (".gitignore", ".gitattributes", ".gitkeep"):
        return None, "repository settings file"
    if ext == ".json":
        if base == "song_bank.json":
            return P.song_bank, None
        if base.startswith("setlist_"):
            return P.setlist, None
        if base == "speakers.json":
            return P.speakers, None
        if base.endswith("_chapters.json"):
            return P.chapters, None
        if low.startswith("transcripts/") or "/transcripts/" in low:
            return P.transcript_json, None
        if "_backup" in base or base.startswith("desc_backups") or "/_backup" in low:
            return _fallback(lambda p, d: P.description_json(p, d, history=True)), None
        if base.startswith("_shorts_kit") or base.startswith("_titles") or base in DESC_JSON_NAMES:
            return _fallback(P.description_json), None
        return _json_or_text(P.data_json), None
    if ext == ".vtt":
        return P.transcript_vtt, None
    if ext == ".txt":
        if base.endswith("_para.txt") or base.endswith("_transcript.txt"):
            return P.transcript_text, None
        if DESC_TXT_RE.search(base):
            return P.description_text, None
        return P.note, None
    if ext in P.TEXT_EXT:
        return P.note, None
    if ext == ".csv":
        return P.table_csv, None
    if ext in (".xlsx", ".xlsm"):
        return P.table_xlsx, None
    if ext in P.CODE_EXT:
        return P.code, None
    return "media", None


def _fallback(fn):
    def h(path, data):
        try:
            return fn(path, data)
        except P.Unknown:
            return P.data_json(path, data)
    return h


def _json_or_text(fn):
    def h(path, data):
        try:
            return fn(path, data)
        except ValueError:
            return P.note(path, data)
    return h


# ---------- media metadata -----------------------------------------------------------
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def media_meta(full: Path, ext: str, notes: list) -> tuple[dict, list]:
    meta, pages = {}, []
    if ext in P.IMAGE_EXT:
        try:
            from PIL import Image
            with Image.open(full) as im:
                meta.update(width=im.width, height=im.height, format=im.format)
        except Exception as e:  # noqa: BLE001 - one bad image must not stop a build
            meta["note"] = f"image not readable: {type(e).__name__}"
    elif ext in P.VIDEO_EXT or ext in P.AUDIO_EXT:
        if shutil.which("ffprobe"):
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,width,height",
                                "-of", "json", str(full)], capture_output=True, text=True, timeout=120)
            try:
                d = json.loads(r.stdout or "{}")
                dur = float(d.get("format", {}).get("duration", 0) or 0)
                meta["duration"] = round(dur, 2) if dur else None
                for s in d.get("streams", []):
                    if s.get("width"):
                        meta.update(width=s["width"], height=s["height"], codec=s.get("codec_name"))
                        break
                else:
                    if d.get("streams"):
                        meta["codec"] = d["streams"][0].get("codec_name")
            except ValueError:
                meta["note"] = "ffprobe gave no readable answer"
        else:
            meta["note"] = "duration not read: ffprobe missing"
    elif ext == ".pptx":
        try:
            pages = P.pptx_text(full.read_bytes())
        except Exception as e:  # noqa: BLE001
            meta["note"] = f"pptx text not read: {type(e).__name__}"
    elif ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(full))
            pages = [(pg.extract_text() or "") for pg in reader.pages[:200]]
        except ImportError:
            notes.append("pdf text skipped: pypdf missing")
        except Exception as e:  # noqa: BLE001
            meta["note"] = f"pdf text not read: {type(e).__name__}"
    return meta, pages


# ---------- one file -----------------------------------------------------------------
def index_file(db, cfg: Config, repo_name: str, repo: Path, path: str, commit: str, stats: dict, log) -> None:
    full = repo / path
    handler, reason = classify(path)
    if handler is None:
        db.execute("INSERT INTO skipped(repo, path, reason) VALUES(?,?,?)", (repo_name, path, reason))
        stats["skipped"] += 1
        return
    if not full.is_file():
        stats["not_present"] += 1      # a sparse or partial checkout; the box has everything
        return
    size = full.stat().st_size
    data = None
    if size <= SCAN_LIMIT:
        data = full.read_bytes()
        if content_has_credential(data):
            db.execute("INSERT INTO skipped(repo, path, reason) VALUES(?,?,?)", (repo_name, path, "credential-shaped content"))
            log(f"  ! skipped (credential-shaped content): {repo_name}/{path}")
            stats["skipped"] += 1
            return
    try:
        if handler == "media":
            notes = []
            meta, pages = media_meta(full, os.path.splitext(path.lower())[1], notes)
            for n in notes:
                log(f"  - {repo_name}/{path}: {n}")
            sha = sha256_of(full) if data is None else hashlib.sha256(data).hexdigest()
            docs = P.media(path, size, sha, meta, pages)
        else:
            docs = handler(path, data if data is not None else full.read_bytes())
            sha = hashlib.sha256(data).hexdigest() if data is not None else None
    except P.Unknown as e:
        db.execute("INSERT INTO skipped(repo, path, reason) VALUES(?,?,?)", (repo_name, path, str(e)))
        log(f"  - not indexed: {repo_name}/{path}: {e}")
        stats["skipped"] += 1
        return
    except (ValueError, UnicodeDecodeError) as e:
        db.execute("INSERT INTO skipped(repo, path, reason) VALUES(?,?,?)", (repo_name, path, f"unreadable: {type(e).__name__}"))
        log(f"  - not indexed: {repo_name}/{path}: unreadable ({type(e).__name__})")
        stats["skipped"] += 1
        return
    stats["indexed"] += 1
    for d in docs:
        _store(db, repo_name, path, commit, size, sha, d)
        stats["kinds"][d.kind] += 1


def _store(db, repo_name, path, commit, size, sha, d: P.Parsed):
    doc_id = store.add_doc(db, {"repo": repo_name, "path": path, "commit_sha": commit, "kind": d.kind, "title": d.title,
                                "video_id": d.video_id, "date": d.date, "private": d.private, "history": d.history,
                                "size": size, "sha256": sha, "extra": d.extra})
    for c in d.chunks:
        store.add_chunk(db, doc_id, c.get("text", ""), d.title, c.get("start_line"), c.get("end_line"),
                        c.get("start_sec"), c.get("end_sec"), c.get("link"))
    if d.segments:
        db.executemany("INSERT INTO segments(doc_id, video_id, start, dur, text) VALUES(?,?,?,?,?)",
                       [(doc_id, d.video_id, s["start"], s.get("dur"), s["text"]) for s in d.segments])
    for s in d.songs:
        db.execute("INSERT INTO songs(doc_id, title, title_norm, ccli, writers, copyright, admin, credit_line, original, verified, note, repo, path, commit_sha) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (doc_id, s["title"], s["title_norm"], s["ccli"], s["writers"], s["copyright"], s["admin"], s["credit_line"],
                    s["original"], s["verified"], s["note"], repo_name, path, commit))


# ---------- the large videos (13.2) ---------------------------------------------------
def readme_hashes(text: str) -> dict:
    """'Folder\\Name.mp4' rows of large-videos-split/README.md -> {'Folder/Name.mp4': sha256}."""
    return {m.group(1).replace("\\", "/"): m.group(2) for m in README_ROW_RE.finditer(text)}


def assemble(db, cfg: Config, repo_name: str, repo: Path, files: list[str], commit: str, log) -> dict:
    res = {"assembled": [], "refused": [], "incomplete": []}
    readmes = [p for p in files if p.endswith("large-videos-split/README.md")]
    cache = store.get_meta(db, "assembled", {}) or {}
    for rd in readmes:
        base_dir = rd[: -len("README.md")]
        if not (repo / rd).is_file():
            continue
        for rel, want in readme_hashes((repo / rd).read_text(encoding="utf-8", errors="replace")).items():
            parts = sorted((p for p in files if p.startswith(base_dir + rel + ".part")), key=lambda p: int(re.findall(r"(\d+)$", p)[0]))
            if not parts or not all((repo / p).is_file() for p in parts):
                res["incomplete"].append(rel)
                continue
            target = cfg.assembled / rel
            ids = blob_ids(repo, parts)
            key = str(target)
            if target.is_file() and cache.get(key, {}).get("parts") == [ids.get(p) for p in parts] and cache[key].get("sha256") == want:
                got = want
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(target.name + ".assembling")
                h = hashlib.sha256()
                with open(tmp, "wb") as out:
                    for p in parts:
                        with open(repo / p, "rb") as f:
                            for b in iter(lambda: f.read(1 << 20), b""):
                                h.update(b)
                                out.write(b)
                got = h.hexdigest()
                if got != want:
                    tmp.unlink(missing_ok=True)
                    res["refused"].append(rel)
                    log(f"  ! refused {rel}: sha256 {got[:12]}... is not the README's {want[:12]}...")
                    continue
                os.replace(tmp, target)
                cache[key] = {"parts": [ids.get(p) for p in parts], "sha256": got}
            apath = f"media-assembled/{rel}"
            store.delete_path(db, repo_name, apath)
            meta, _ = media_meta(target, os.path.splitext(rel.lower())[1], [])
            meta.update(parts=parts, readme_sha256=want, verified=True)
            for d in P.media(apath, target.stat().st_size, got, meta):
                _store(db, repo_name, apath, commit, target.stat().st_size, got, d)
            res["assembled"].append(rel)
    store.set_meta(db, "assembled", cache)
    return res


# ---------- inventory -----------------------------------------------------------------
def inventory(repo: Path, files: list[str]) -> dict:
    by = defaultdict(lambda: [0, 0, 0])
    for p in files:
        folder = p.split("/", 1)[0] + "/" if "/" in p else "(root)"
        ext = os.path.splitext(p.lower())[1] or "(none)"
        full = repo / p
        present = full.is_file()
        size = full.stat().st_size if present else 0
        for k in ((folder, "*"), ("*", ext)):
            by[k][0] += 1
            by[k][1] += size
            by[k][2] += int(present)
    return by


def du(path: Path) -> int:
    total = 0
    for root, _dirs, fls in os.walk(path):
        for f in fls:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


# ---------- the build -----------------------------------------------------------------
def build(cfg: Config | None = None, full: bool = False, pull_first: bool = True) -> dict:
    cfg = cfg or Config()
    cfg.state.mkdir(parents=True, exist_ok=True)
    lock = open(cfg.state / ".build.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return {"ok": True, "skipped": "another build holds the lock"}
    lines: list[str] = []
    log = lines.append
    t0 = time.time()
    target = cfg.index.with_name(cfg.index.name + ".new") if full else cfg.index
    if full and target.exists():
        target.unlink()
    db = store.open_rw(target)
    summary = {"ok": True, "mode": "full" if full else "incremental", "repos": {}, "started": datetime.now().isoformat(timespec="seconds")}
    log(f"ariseOS archive build, {summary['mode']}, {summary['started']}")
    try:
        for name in cfg.repos:
            repo = cfg.repo_dir(name)
            if not (repo / ".git").exists():
                log(f"\n## {name}: not cloned yet at {repo} (arisectl archive setup)")
                summary["repos"][name] = {"cloned": False}
                continue
            if pull_first:
                pull(repo, log)
            head = git(repo, "rev-parse", "HEAD").strip()
            old = None if full else store.get_meta(db, f"commit:{name}")
            files = tracked(repo)
            stats = {"indexed": 0, "skipped": 0, "not_present": 0, "reindexed": 0, "deleted": 0, "kinds": defaultdict(int)}
            ancestor = bool(old) and subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", old, head],
                                                    capture_output=True).returncode == 0
            if not old or not ancestor:
                store.delete_repo(db, name)
                todo = files
                stats["mode"] = "whole repo"
            elif old == head:
                todo = []
                stats["mode"] = "unchanged"
            else:
                todo, gone = [], []
                for ln in git(repo, "diff", "--name-status", "-M", old, head).splitlines():
                    bits = ln.split("\t")
                    st = bits[0][:1]
                    if st == "D":
                        gone.append(bits[1])
                    elif st == "R":
                        gone.append(bits[1])
                        todo.append(bits[2])
                    elif st in "AMTC":
                        todo.append(bits[-1])
                for g in gone:
                    store.delete_path(db, name, g)
                stats["deleted"] = len(gone)
                stats["mode"] = "changed files"
            for p in todo:
                store.delete_path(db, name, p)
                index_file(db, cfg, name, repo, p, head, stats, log)
            stats["reindexed"] = len(todo)
            asm = assemble(db, cfg, name, repo, files, head, log)
            # inventory, refreshed every build
            db.execute("DELETE FROM inventory WHERE repo=?", (name,))
            inv = inventory(repo, files)
            db.executemany("INSERT INTO inventory(repo, folder, ext, files, bytes, present) VALUES(?,?,?,?,?,?)",
                           [(name, f, e, c, b, pr) for (f, e), (c, b, pr) in inv.items()])
            store.set_meta(db, f"commit:{name}", head)
            indexed_set = {r[0] for r in db.execute("SELECT DISTINCT path FROM docs WHERE repo=? AND path NOT LIKE 'media-assembled/%'", (name,))}
            skipped_set = {r[0] for r in db.execute("SELECT path FROM skipped WHERE repo=?", (name,))}
            on_disk = {p for p in files if (repo / p).is_file()}
            missing = set(files) - on_disk - skipped_set
            unaccounted = set(files) - indexed_set - skipped_set - missing
            for p in sorted(unaccounted):
                log(f"  ! read but produced no document: {name}/{p}")
            rs = {"cloned": True, "old": old, "head": head, "tracked": len(files), "present": len(on_disk),
                  "indexed_paths": len(indexed_set), "skipped": len(skipped_set), "not_present": len(missing),
                  "unaccounted": len(unaccounted),
                  "reindexed": stats["reindexed"], "deleted": stats["deleted"], "mode": stats["mode"],
                  "kinds": dict(stats["kinds"]), "assembled": asm, "du_checkout": du(repo) - du(repo / ".git"), "du_git": du(repo / ".git")}
            summary["repos"][name] = rs
            _log_repo(log, name, rs, inv)
            for (p, r) in db.execute("SELECT path, reason FROM skipped WHERE repo=? ORDER BY path", (name,)):
                log(f"  skipped: {p}  ({r})")
        store.set_meta(db, "built_at", datetime.now().isoformat(timespec="seconds"))
        store.set_meta(db, "schema", 1)
        db.commit()
    except Exception as e:  # noqa: BLE001 - the log must say what failed
        db.rollback()
        summary["ok"] = False
        summary["error"] = str(e)
        log(f"\nFAILED: {e}")
    finally:
        db.close()
    if summary["ok"] and full:
        os.replace(target, cfg.index)
    summary["seconds"] = round(time.time() - t0, 1)
    log(f"\ndone in {summary['seconds']} s, ok={summary['ok']}")
    cfg.build_log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cfg.status_file.write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    for f in (cfg.index, cfg.build_log, cfg.status_file):
        try:
            os.chmod(f, 0o644)
        except OSError:
            pass
    lock.close()
    return summary


def _log_repo(log, name, rs, inv):
    log(f"\n## {name}  {(rs['old'] or 'new')[:10]} -> {rs['head'][:10]}  ({rs['mode']})")
    log(f"  tracked {rs['tracked']}; on disk {rs['present']}; indexed {rs['indexed_paths']}; skipped {rs['skipped']}; "
        f"not on disk {rs['not_present']}; re-read {rs['reindexed']}; removed {rs['deleted']}")
    log(f"  du: checkout {rs['du_checkout'] / 2**20:.1f} MB, .git {rs['du_git'] / 2**20:.1f} MB")
    log("  by folder:")
    for (f, e), (c, b, pr) in sorted(inv.items(), key=lambda x: -x[1][1]):
        if e == "*":
            log(f"    {c:5d} files {b / 2**20:9.1f} MB  {f}" + (f"  ({c - pr} not on disk)" if c - pr else ""))
    log("  by type:")
    for (f, e), (c, b, pr) in sorted(inv.items(), key=lambda x: -x[1][0]):
        if f == "*":
            log(f"    {c:5d} {e}")
    log("  documents by kind: " + ", ".join(f"{k} {v}" for k, v in sorted(rs["kinds"].items())))
    a = rs["assembled"]
    if a["assembled"] or a["refused"] or a["incomplete"]:
        log(f"  large videos: assembled {len(a['assembled'])}, refused {len(a['refused'])}, pieces not all on disk {len(a['incomplete'])}")

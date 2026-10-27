"""restic jobs from backups.yaml, a history file, and the GitHub mirror.

Every run writes a history row, success or failure - never silent.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import datetime

import yaml

from . import demo
from .config import load
from .util import now_iso, read_json, run, which, write_json

_running: dict[str, dict] = {}
_lock = threading.Lock()


def available() -> bool:
    return bool(which("restic")) and not load().demo


def _hist_path():
    return load().state_dir / "backup-history.json"


def jobs() -> dict:
    cfg = load()
    try:
        with open(cfg.backups.jobs_file, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        js = data.get("jobs", [])
        return {"demo": False, "jobs": js, "file": cfg.backups.jobs_file}
    except FileNotFoundError:
        return {"demo": True, "jobs": demo.BACKUP_JOBS, "file": cfg.backups.jobs_file}


def history(limit: int = 200) -> dict:
    if load().demo:
        rows = demo.BACKUP_HISTORY
    else:
        rows = read_json(_hist_path(), default=[])
    rows = sorted(rows, key=lambda r: r.get("started", ""), reverse=True)[:limit]
    with _lock:
        running = list(_running.values())
    return {"demo": load().demo, "rows": rows, "running": running}


def _append_history(row: dict):
    rows = read_json(_hist_path(), default=[])
    rows.append(row)
    write_json(_hist_path(), rows[-2000:])


def _env():
    cfg = load()
    env = dict(os.environ)
    env["RESTIC_REPOSITORY"] = cfg.backups.restic_repo
    env["RESTIC_PASSWORD_FILE"] = cfg.backups.password_file
    return env


def repo() -> dict:
    cfg = load()
    if not available():
        return {"demo": True, **demo.BACKUP_REPO}
    out = {"demo": False, "repo": cfg.backups.restic_repo, "ok": False, "snapshots": 0,
           "keep": {"daily": cfg.backups.keep_daily, "weekly": cfg.backups.keep_weekly, "monthly": cfg.backups.keep_monthly}}
    if not os.path.exists(cfg.backups.password_file):
        out["error"] = f"restic password file missing: {cfg.backups.password_file}"
        return out
    r = run(["restic", "snapshots", "--json"], timeout=60) if False else _restic(["snapshots", "--json"], 60)
    if not r["ok"]:
        out["error"] = (r["err"] or r["out"]).strip()[:400]
        return out
    try:
        out["snapshots"] = len(json.loads(r["out"] or "[]"))
        out["ok"] = True
    except json.JSONDecodeError:
        out["error"] = "could not read snapshot list"
    s = _restic(["stats", "--json", "--mode", "raw-data"], 120)
    if s["ok"]:
        try:
            st = json.loads(s["out"])
            out["total_size"] = st.get("total_size")
        except json.JSONDecodeError:
            pass
    state = read_json(load().state_dir / "state.json", default={})
    out["last_check"] = state.get("restic_last_check")
    return out


def _restic(args: list[str], timeout: int) -> dict:
    t0 = time.time()
    try:
        p = subprocess.run(["restic", *args], capture_output=True, text=True, timeout=timeout, env=_env())
        return {"ok": p.returncode == 0, "code": p.returncode, "out": p.stdout, "err": p.stderr, "seconds": round(time.time() - t0, 1)}
    except FileNotFoundError:
        return {"ok": False, "code": 127, "out": "", "err": "restic: not installed", "seconds": 0}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": 124, "out": "", "err": f"restic timed out after {timeout}s", "seconds": timeout}


def snapshots(limit: int = 100) -> dict:
    if not available():
        rows = [{"id": r["snapshot_id"], "time": r["started"], "tags": [r["job"]], "paths": next((j["paths"] for j in demo.BACKUP_JOBS if j["id"] == r["job"]), [])}
                for r in demo.BACKUP_HISTORY if r["ok"]][-limit:]
        return {"demo": True, "snapshots": list(reversed(rows))}
    r = _restic(["snapshots", "--json"], 60)
    if not r["ok"]:
        return {"demo": False, "snapshots": [], "error": (r["err"] or r["out"])[:400]}
    try:
        rows = json.loads(r["out"] or "[]")
    except json.JSONDecodeError:
        rows = []
    rows = [{"id": s.get("short_id") or s.get("id", "")[:8], "time": s.get("time"), "tags": s.get("tags", []), "paths": s.get("paths", []), "hostname": s.get("hostname")} for s in rows]
    rows.sort(key=lambda s: s["time"] or "", reverse=True)
    return {"demo": False, "snapshots": rows[:limit]}


def run_job(job_id: str, blocking: bool = False) -> dict:
    js = {j["id"]: j for j in jobs()["jobs"]}
    if job_id not in js:
        return {"ok": False, "err": f"no job called {job_id}"}
    with _lock:
        if job_id in _running:
            return {"ok": False, "err": f"{job_id} is already running"}
        _running[job_id] = {"job": job_id, "started": now_iso()}
    if blocking:
        return _execute(js[job_id])
    threading.Thread(target=_execute, args=(js[job_id],), daemon=True).start()
    return {"ok": True, "started": True, "job": job_id}


def _execute(job: dict) -> dict:
    started = now_iso()
    row = {"job": job["id"], "name": job.get("name", job["id"]), "started": started, "finished": None, "ok": False,
           "snapshot_id": None, "bytes_added": 0, "files_new": 0, "error": None}
    try:
        if not available():
            time.sleep(1.5)
            row.update({"ok": True, "snapshot_id": "demo0000", "bytes_added": 1234567, "files_new": 3, "demo": True})
        else:
            args = ["backup", "--json", "--host", load().system.hostname]
            for t in job.get("tags", []):
                args += ["--tag", t]
            for e in job.get("exclude", []):
                args += ["--exclude", e]
            existing = [p for p in job.get("paths", []) if os.path.exists(p)]
            missing = [p for p in job.get("paths", []) if not os.path.exists(p)]
            if not existing:
                raise RuntimeError(f"skipped - none of the paths exist (is the NAS mounted?): {missing}")
            r = _restic(args + existing, timeout=6 * 3600)
            summary = None
            for line in r["out"].splitlines():
                if line.startswith("{") and '"summary"' in line:
                    try:
                        summary = json.loads(line)
                    except json.JSONDecodeError:
                        pass
            if summary:
                row["snapshot_id"] = summary.get("snapshot_id", "")[:8]
                row["bytes_added"] = summary.get("data_added", 0)
                row["files_new"] = summary.get("files_new", 0)
            row["ok"] = r["ok"]
            if missing:
                row["warning"] = f"skipped missing paths: {missing}"
            if not r["ok"]:
                row["error"] = (r["err"] or r["out"]).strip()[-600:]
    except Exception as e:
        row["error"] = str(e)
    row["finished"] = now_iso()
    if not load().demo:
        _append_history(row)
    with _lock:
        _running.pop(job["id"], None)
    return {"ok": row["ok"], **row}


def forget_prune() -> dict:
    cfg = load()
    if not available():
        return {"ok": True, "demo": True}
    return _restic(["forget", "--prune", "--keep-daily", str(cfg.backups.keep_daily), "--keep-weekly", str(cfg.backups.keep_weekly),
                    "--keep-monthly", str(cfg.backups.keep_monthly)], timeout=3600)


def check() -> dict:
    if not available():
        return {"ok": True, "demo": True}
    r = _restic(["check"], timeout=3600)
    state_p = load().state_dir / "state.json"
    st = read_json(state_p, default={})
    st["restic_last_check"] = now_iso()
    st["restic_last_check_ok"] = r["ok"]
    write_json(state_p, st)
    return r


def mirror_github() -> dict:
    """git clone --mirror / remote update for every repo in arise.toml."""
    cfg = load()
    base = cfg.github.mirror_path
    token = ""
    try:
        token = open(cfg.github.token_file).read().strip()
    except OSError:
        pass
    results = []
    os.makedirs(base, exist_ok=True)
    for full in cfg.github.repos:
        name = full.split("/")[-1]
        dest = os.path.join(base, name + ".git")
        url = f"https://{token + '@' if token else ''}github.com/{full}.git"
        if os.path.isdir(dest):
            r = run(["git", "-C", dest, "remote", "update", "--prune"], timeout=600)
        else:
            r = run(["git", "clone", "--mirror", url, dest], timeout=1200)
        results.append({"repo": full, "ok": r["ok"], "error": None if r["ok"] else (r["err"] or r["out"]).replace(token, "***")[-300:]})
    row = {"job": "github-mirror", "name": "GitHub mirror", "started": now_iso(), "finished": now_iso(),
           "ok": all(x["ok"] for x in results), "snapshot_id": None, "bytes_added": 0, "files_new": 0,
           "error": "; ".join(f"{x['repo']}: {x['error']}" for x in results if not x["ok"]) or None}
    if not cfg.demo:
        _append_history(row)
    return {"ok": row["ok"], "repos": results}

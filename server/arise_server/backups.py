"""restic jobs from backups.yaml, a history file, and the GitHub mirror.

Every run writes a history row, success or failure - never silent.
"""
from __future__ import annotations

import json
from pathlib import Path
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta

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
            if job.get("samba_offline"):
                pre = samba_offline_backup()
                if not pre.get("ok"):
                    row["warning"] = "samba offline backup skipped: " + str(pre.get("err", ""))[:200]
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


SAMBA_BACKUP_DIR = "/var/lib/arise/samba-backup"


def samba_offline_backup(keep: int = 2) -> dict:
    """`samba-tool domain backup offline`: a consistent copy of the domain's database
    (sam.ldb and friends) that `samba-tool domain backup restore` can rebuild a DC
    from. Copying /var/lib/samba/private while Samba is writing can give a torn
    ldb; the offline backup locks each database first. Runs before the system
    job's restic backup (backups.yaml: samba_offline: true); the last two kept."""
    if not which("samba-tool"):
        return {"ok": False, "err": "samba-tool not installed"}
    d = Path(SAMBA_BACKUP_DIR)
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    r = run(["samba-tool", "domain", "backup", "offline", f"--targetdir={d}"], timeout=1800)
    if not r["ok"]:
        return {"ok": False, "err": (r["err"] or r["out"]).strip()[-300:]}
    tars = sorted(d.glob("samba-backup-*.tar.bz2"), key=lambda x: x.stat().st_mtime)
    for old in tars[:-keep] if len(tars) > keep else []:
        try:
            old.unlink()
        except OSError:
            pass
    return {"ok": True, "file": str(tars[-1]) if tars else ""}


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


# ---- the restore drill -----------------------------------------------------------
def drill(quiet: bool = False) -> dict:
    """Restore one random file from the latest snapshot into a scratch folder and
    compare it with the live file. A backup nobody has restored from is a hope,
    not a backup. Result shape: {when, snapshot, file, bytes, matched, ok, note};
    kept in <state_dir>/drill-history.json (last 24). The scratch folder is wiped."""
    import hashlib
    import random
    import shutil
    cfg = load()
    hist_p = cfg.state_dir / "drill-history.json"
    if not available():
        row = {"when": now_iso(), "snapshot": "a1b2c3d4", "file": "/srv/arise/homes/bradly.dyer/Documents/Sunday setlist 2026-10-26.pdf", "bytes": 182_000, "matched": True, "ok": True, "note": "sample drill", "demo": True}
        return {**row, "history": [row]}
    row = {"when": now_iso(), "snapshot": "", "file": "", "bytes": 0, "matched": None, "ok": False, "note": ""}
    scratch = cfg.state_dir / "drill"
    try:
        snaps = _restic(["snapshots", "--json", "--latest", "1"], 60)
        if not snaps["ok"]:
            row["note"] = "could not list snapshots: " + (snaps["err"] or snaps["out"])[:200]
            return _drill_done(hist_p, row)
        try:
            latest = json.loads(snaps["out"] or "[]")
        except json.JSONDecodeError:
            latest = []
        if not latest:
            row["note"] = "no snapshots yet"
            return _drill_done(hist_p, row)
        snap = latest[-1]["short_id"] if "short_id" in latest[-1] else latest[-1]["id"][:8]
        row["snapshot"] = snap
        ls = _restic(["ls", "--json", snap], 600)
        if not ls["ok"]:
            row["note"] = "could not list the snapshot: " + (ls["err"] or ls["out"])[:200]
            return _drill_done(hist_p, row)
        files = []
        for line in ls["out"].splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("struct_type") == "node" and e.get("type") == "file" and 0 < int(e.get("size") or 0) < 50 * 1024 * 1024:
                files.append(e)
        if not files:
            row["note"] = "no regular file under 50 MB in the snapshot"
            return _drill_done(hist_p, row)
        pick = random.choice(files)
        row["file"] = pick["path"]; row["bytes"] = int(pick["size"])
        shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir(parents=True, exist_ok=True)
        r = _restic(["restore", snap, "--target", str(scratch), "--include", pick["path"]], 1800)
        if not r["ok"]:
            row["note"] = "restore failed: " + (r["err"] or r["out"])[:200]
            return _drill_done(hist_p, row)
        restored = scratch / pick["path"].lstrip("/")
        if not restored.exists():
            row["note"] = "restic said ok but the file is not in the scratch folder"
            return _drill_done(hist_p, row)
        got = hashlib.sha256(restored.read_bytes()).hexdigest()
        row["ok"] = True
        row["system_job"] = _drill_system_check()
        live = pick["path"]
        if os.path.isfile(live):
            same = hashlib.sha256(open(live, "rb").read()).hexdigest() == got
            row["matched"] = same
            row["note"] = "restored and identical to the live file" if same else "restored; the live file has changed since the snapshot (normal for a working file)"
        else:
            row["matched"] = None
            row["note"] = f"restored {row['bytes']} bytes; the live file no longer exists, nothing to compare"
    except Exception as e:  # the drill must never take the box down
        row["note"] = f"drill error: {e}"[:200]
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return _drill_done(hist_p, row)


def _drill_system_check() -> dict:
    """Round 3, 24: the reinstall path depends on the system job. Does its newest
    snapshot hold /etc/arise/arise.toml and a samba offline backup?"""
    try:
        r = _restic(["snapshots", "--json", "--latest", "1", "--tag", "system"], 60)
        latest = json.loads(r["out"] or "[]") if r["ok"] else []
        if not latest:
            return {"ok": False, "note": "no snapshot tagged 'system' yet (backups.yaml: the system job)"}
        snap = latest[-1].get("short_id") or latest[-1]["id"][:8]
        ls = _restic(["ls", snap, "/etc/arise/arise.toml", SAMBA_BACKUP_DIR], 300)
        has_toml = "/etc/arise/arise.toml" in ls["out"]
        has_samba = "samba-backup-" in ls["out"]
        return {"ok": has_toml, "snapshot": snap, "arise_toml": has_toml, "samba_backup": has_samba,
                "note": "arise.toml " + ("present" if has_toml else "MISSING") + "; samba offline backup " + ("present" if has_samba else "missing")}
    except Exception as e:
        return {"ok": False, "note": f"could not check: {e}"[:160]}


def _drill_done(hist_p, row: dict) -> dict:
    hist = read_json(hist_p, default=[]) or []
    hist = ([row] + hist)[:24]
    write_json(hist_p, hist)
    return {**row, "history": hist}


def drill_history() -> list[dict]:
    if not available():
        return [drill()] if False else [{"when": now_iso(), "snapshot": "a1b2c3d4", "file": "/srv/arise/homes/bradly.dyer/Documents/Sunday setlist 2026-10-26.pdf", "bytes": 182_000, "matched": True, "ok": True, "note": "sample drill", "demo": True}]
    return read_json(load().state_dir / "drill-history.json", default=[]) or []


# ---- Previous Versions (v0.8, docs/ANSWERS.md round 3, 2) --------------------------
def job_for(path: str) -> dict | None:
    """The backup job whose paths cover this file, or None (then it is not backed up)."""
    path = os.path.normpath(path)
    for j in jobs()["jobs"]:
        for p in j.get("paths", []):
            p = p.rstrip("/")
            if path == p or path.startswith(p + "/"):
                return j
    return None


def parse_find(out: str, snap_times: dict) -> list[dict]:
    """`restic find --json <path>` output -> [{snapshot, time, size, mtime, dir}], newest first.
    One row per snapshot that holds the file."""
    try:
        groups = json.loads(out or "[]")
    except json.JSONDecodeError:
        return []
    rows = []
    for g in groups:
        sid = (g.get("snapshot") or "")[:8]
        for m in g.get("matches", []):
            is_dir = m.get("type") == "dir"
            rows.append({"snapshot": sid, "time": snap_times.get(sid), "size": None if is_dir else m.get("size"), "mtime": m.get("mtime"), "dir": is_dir})
    rows.sort(key=lambda r: r.get("time") or "", reverse=True)
    return rows


def versions_of(path: str) -> dict:
    """Every nightly copy of a file the backup holds."""
    job = job_for(path)
    if not available():
        rows = [{"snapshot": f"{(abs(hash(path)) + i * 7919) % 16 ** 8:08x}", "time": (datetime.now().replace(hour=3, minute=0, second=0, microsecond=0) - timedelta(days=d)).isoformat(timespec="seconds"),
                 "size": 182_000 - d * 1_200, "mtime": (datetime.now() - timedelta(days=d + 1)).isoformat(timespec="seconds"), "dir": False} for i, d in enumerate((0, 1, 2, 6, 13))]
        return {"demo": True, "path": path, "job": job["id"] if job else None, "job_name": job.get("name") if job else None, "versions": rows if job else [], "backed_up": bool(job)}
    if not job:
        return {"demo": False, "path": path, "job": None, "job_name": None, "versions": [], "backed_up": False}
    snaps = _restic(["snapshots", "--json"], 60)
    times = {}
    if snaps["ok"]:
        try:
            for sn in json.loads(snaps["out"] or "[]"):
                times[(sn.get("short_id") or sn.get("id", ""))[:8]] = sn.get("time")
        except json.JSONDecodeError:
            pass
    r = _restic(["find", "--json", path], 300)
    if not r["ok"]:
        return {"demo": False, "path": path, "job": job["id"], "job_name": job.get("name"), "versions": [], "backed_up": True, "error": (r["err"] or r["out"])[:300]}
    return {"demo": False, "path": path, "job": job["id"], "job_name": job.get("name"), "versions": parse_find(r["out"], times)[:60], "backed_up": True}


def restored_name(name: str, date: str, taken) -> str:
    """'setlist.pdf' + '2026-10-27' -> 'setlist (restored 2026-10-27).pdf', numbered if that is taken."""
    stem, ext = os.path.splitext(name)
    cand = f"{stem} (restored {date}){ext}"
    n = 2
    while taken(cand):
        cand = f"{stem} (restored {date} {n}){ext}"; n += 1
    return cand


def restore_version(path: str, snapshot: str, who: dict | None = None) -> dict:
    """Bring one snapshot's copy of a file back BESIDE the live one; never over it."""
    import shutil
    cfg = load()
    name = os.path.basename(path)
    if not available():
        return {"ok": True, "demo": True, "restored": restored_name(name, datetime.now().strftime("%Y-%m-%d"), lambda n: False)}
    if not re.fullmatch(r"[0-9a-f]{8,64}|latest", snapshot or ""):
        return {"ok": False, "err": "bad snapshot id"}
    scratch = cfg.state_dir / "restore-scratch" / f"{int(time.time())}-{os.getpid()}"
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        r = _restic(["restore", snapshot, "--target", str(scratch), "--include", path], 1800)
        if not r["ok"]:
            return {"ok": False, "err": "restore failed: " + (r["err"] or r["out"])[:300]}
        got = scratch / path.lstrip("/")
        if not got.exists():
            return {"ok": False, "err": "restic said ok but the file was not in that snapshot"}
        folder = os.path.dirname(path)
        os.makedirs(folder, exist_ok=True)
        snap_date = snapshot[:8]
        try:
            for sn in json.loads(_restic(["snapshots", "--json", snapshot], 60)["out"] or "[]"):
                snap_date = (sn.get("time") or "")[:10] or snap_date
        except (json.JSONDecodeError, KeyError):
            pass
        final = restored_name(name, snap_date, lambda n: os.path.lexists(os.path.join(folder, n)))
        dest = os.path.join(folder, final)
        shutil.move(str(got), dest)
        if who and who.get("user"):
            try:
                import pwd
                pw = pwd.getpwnam(who["user"]); os.chown(dest, pw.pw_uid, pw.pw_gid)
            except (KeyError, OSError):
                pass
        return {"ok": True, "demo": False, "restored": final, "path": dest}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

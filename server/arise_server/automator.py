"""The nightly YouTube job, as seen from the server.

This module only runs arise_daily.py and reads what it writes. The rules
(holds, quota, chapters) are the automator's own; nothing here edits them.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta

from . import demo
from .config import load
from .util import now_iso, read_json, read_text

_run_lock = threading.Lock()
_last_manual: dict = {}


def _paths():
    cfg = load()
    root = cfg.automator.path
    auto = os.path.join(root, "automator")
    return {
        "root": root, "automator": auto,
        "script": os.path.join(auto, "arise_daily.py"),
        "latest": os.path.join(auto, "LATEST_REPORT.md"),
        "reports": os.path.join(auto, "reports"),
        "holds": os.path.join(auto, "holds.json"),
        "worklist": os.path.join(auto, "worklist.json"),
        "ledger": os.path.join(auto, "quota_ledger.json"),
        "token": os.path.join(root, "token.json"),
        "secret": os.path.join(root, "client_secret.json"),
        "last_run_log": os.path.join(auto, "last-run.log"),
    }


def available() -> bool:
    return os.path.exists(_paths()["script"]) and not load().demo


def _next_run(schedule: str) -> str:
    try:
        hh, mm = (int(x) for x in schedule.split(":"))
    except ValueError:
        hh, mm = 2, 5
    now = datetime.now()
    nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return nxt.isoformat(timespec="seconds")


def overview() -> dict:
    cfg = load()
    if not available():
        d = dict(demo.AUTOMATOR)
        d["next_run"] = _next_run(cfg.automator.schedule)
        d["demo"] = True
        d["schedule"] = cfg.automator.schedule
        return d
    p = _paths()
    latest = read_text(p["latest"], "")
    head = latest.splitlines()[:4]
    summary = next((l for l in head if "jobs done" in l), "")
    m = re.search(r"(\d[\d,]*) of (\d[\d,]*) units", summary)
    spent = int(m.group(1).replace(",", "")) if m else None
    daily = int(m.group(2).replace(",", "")) if m else 10000
    last_run = None
    try:
        last_run = datetime.fromtimestamp(os.path.getmtime(p["latest"])).isoformat(timespec="seconds")
    except OSError:
        pass
    holds = read_json(p["holds"], default={"videos": [], "rules": []}) or {}
    work = read_json(p["worklist"], default={"jobs": []}) or {}
    jobs = work.get("jobs", work) if isinstance(work, dict) else work
    if isinstance(jobs, dict):
        jobs = list(jobs.values())
    ledger = read_json(p["ledger"], default={}) or {}
    today = datetime.now().strftime("%Y-%m-%d")
    spent_today = None
    if isinstance(ledger, dict):
        day = ledger.get(today) or ledger.get("days", {}).get(today) if isinstance(ledger.get("days"), dict) else ledger.get(today)
        if isinstance(day, dict):
            spent_today = day.get("spent") or day.get("total")
        elif isinstance(day, (int, float)):
            spent_today = day
    reports = []
    try:
        reports = sorted(os.listdir(p["reports"]), reverse=True)[:60]
    except OSError:
        pass
    token_ok = os.path.exists(p["token"])
    token_days_left = None
    if token_ok:
        try:
            age = time.time() - os.path.getmtime(p["token"])
            token_days_left = max(0, int(7 - age / 86400))
        except OSError:
            pass
    signed = ""
    m2 = re.search(r"signed in as \*\*(.+?)\*\*", latest)
    if m2:
        signed = m2.group(1)
    return {
        "demo": False, "path": p["root"], "schedule": cfg.automator.schedule,
        "last_run": last_run, "last_ok": ("failed · 0" in summary) or ("0 failed" in summary) if summary else None,
        "last_summary": summary, "next_run": _next_run(cfg.automator.schedule),
        "quota_today": spent_today if spent_today is not None else spent, "quota_daily": daily, "quota_reset": "2:00 AM Central",
        "holds": len(holds.get("videos", [])), "rules": len(holds.get("rules", [])),
        "worklist_enabled": sum(1 for j in jobs if isinstance(j, dict) and j.get("enabled", True)), "worklist_total": len(jobs),
        "token_ok": token_ok, "token_days_left": token_days_left,
        "token_note": None if token_ok else f"token.json is missing from {p['root']} - run authorize.py on a machine signed in as the channel owner and copy it here.",
        "client_secret_ok": os.path.exists(p["secret"]),
        "signed_in_as": signed, "latest_report": latest or "(no report yet - the automator has not run on this server)",
        "reports": reports, "manual": _last_manual,
    }


def report(name: str) -> dict:
    if not re.match(r"^[\w.-]+\.md$", name or ""):
        return {"error": "bad report name"}
    if not available():
        return {"demo": True, "name": name, "text": demo.AUTOMATOR["latest_report"]}
    return {"demo": False, "name": name, "text": read_text(os.path.join(_paths()["reports"], name), "(not found)")}


def worklist() -> dict:
    if not available():
        return {"demo": True, "jobs": demo.WORKLIST}
    w = read_json(_paths()["worklist"], default={}) or {}
    jobs = w.get("jobs", w) if isinstance(w, dict) else w
    if isinstance(jobs, dict):
        jobs = [{"id": k, **(v if isinstance(v, dict) else {"note": str(v)})} for k, v in jobs.items()]
    return {"demo": False, "jobs": jobs, "raw": w}


def holds() -> dict:
    if not available():
        return {"demo": True, **demo.HOLDS}
    h = read_json(_paths()["holds"], default={"videos": [], "rules": []}) or {}
    vids = h.get("videos", [])
    if isinstance(vids, dict):
        vids = [{"id": k, "reason": v} for k, v in vids.items()]
    return {"demo": False, "videos": vids, "rules": h.get("rules", [])}


def quota() -> dict:
    if not available():
        return {"demo": True, **demo.QUOTA}
    return {"demo": False, "ledger": read_json(_paths()["ledger"], default={})}


def start(mode: str) -> dict:
    """mode: 'run' or 'preview' (dry run). Non-blocking; result lands in last-run.log and LATEST_REPORT.md."""
    if mode not in ("run", "preview"):
        return {"ok": False, "err": "mode must be run or preview"}
    if not available():
        _last_manual.update({"mode": mode, "started": now_iso(), "finished": now_iso(), "ok": True, "demo": True, "out": f"(demo) {mode} would start arise_daily.py"})
        return {"ok": True, "demo": True, "mode": mode}
    if not _run_lock.acquire(blocking=False):
        return {"ok": False, "err": "the automator is already running"}
    p = _paths()
    cfg = load()
    args = [cfg.automator.python, p["script"]] + (["--dry-run"] if mode == "preview" else [])
    _last_manual.clear()
    _last_manual.update({"mode": mode, "started": now_iso(), "finished": None, "ok": None})

    def go():
        try:
            env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            with open(p["last_run_log"], "a", encoding="utf-8") as log:
                log.write(f"\n=== {mode} started from the dashboard {now_iso()} ===\n")
                log.flush()
                r = subprocess.run(args, cwd=p["automator"], stdout=log, stderr=subprocess.STDOUT, env=env, timeout=3 * 3600)
            _last_manual.update({"finished": now_iso(), "ok": r.returncode == 0, "code": r.returncode})
        except Exception as e:
            _last_manual.update({"finished": now_iso(), "ok": False, "error": str(e)})
        finally:
            _run_lock.release()

    threading.Thread(target=go, daemon=True).start()
    return {"ok": True, "mode": mode, "started": True}

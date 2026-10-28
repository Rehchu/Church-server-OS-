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
from .util import now_iso, read_json, read_text, run, which

_run_lock = threading.Lock()
_last_manual: dict = {}


ENV_FILE = "/etc/arise/arise.env"
UNIT, PREVIEW_UNIT, TIMER = "arise-automator.service", "arise-automator-preview.service", "arise-automator.timer"
STATE_FILES = ("_starfix_state.json", "_tx_run.json", "_retitle_report.txt", "_ss_fix_report.txt")  # handoff section 3


def read_env(path: str = ENV_FILE) -> dict:
    """Pure-ish: KEY=VALUE lines of /etc/arise/arise.env (the automator units' environment)."""
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln and not ln.startswith("#") and "=" in ln:
                    k, v = ln.split("=", 1)
                    out[k.strip()] = v.strip().strip('"')
    except OSError:
        pass
    return out


def _paths():
    """Where the automator lives on this box. The checkout from [automator] path; the token,
    the client and the state dir from /etc/arise/arise.env, as the units see them
    (the handoff's ARISE_TOKEN / ARISE_CLIENT_SECRET / ARISE_STATE_DIR)."""
    cfg = load()
    env = read_env()
    root = env.get("ARISE_REPO") or cfg.automator.path
    auto = os.path.join(root, "automator")
    state = env.get("ARISE_STATE_DIR") or "/var/lib/arise/automator"
    return {
        "root": root, "automator": auto, "state": state,
        "script": os.path.join(auto, "arise_daily.py"),
        "latest": os.path.join(state, "LATEST_REPORT.md"),
        "reports": os.path.join(state, "reports"),
        "ledger": os.path.join(state, "quota_ledger.json"),
        "last_run_log": os.path.join(state, "last-run.log"),
        "holds": os.path.join(auto, "holds.json"),
        "worklist": os.path.join(auto, "worklist.json"),
        "runner": os.path.join(auto, "runner.json"),
        "token": env.get("ARISE_TOKEN") or "/etc/arise/secrets/youtube/token.json",
        "secret": env.get("ARISE_CLIENT_SECRET") or "/etc/arise/secrets/youtube/client_secret.json",
        "machine": env.get("ARISE_RUNNER_NAME") or "ariseOS",
    }


def pacific_day(now: datetime | None = None) -> str:
    """The Google quota day's weekday key (mon..sun): midnight Pacific is 02:00 Central."""
    from zoneinfo import ZoneInfo
    now = now or datetime.now(ZoneInfo("America/Chicago"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("America/Chicago"))
    return ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[now.astimezone(ZoneInfo("America/Los_Angeles")).weekday()]


def runner_info(runner_doc: dict | None, machine: str, now: datetime | None = None) -> dict:
    """Pure: who runs tonight and this machine's cap today, from automator/runner.json (the repo's, Bradly's)."""
    if not isinstance(runner_doc, dict) or not runner_doc.get("runner"):
        return {"runner": None, "machine": machine, "is_runner": False, "budget": None, "day": pacific_day(now),
                "note": "runner.json is missing or unreadable: every machine stops (it fails closed)"}
    runner = str(runner_doc["runner"])
    b = (runner_doc.get("budgets") or {}).get(machine) or {}
    day = pacific_day(now)
    budget = b.get(day, b.get("default"))
    is_runner = runner.lower() == machine.lower()
    return {"runner": runner, "machine": machine, "is_runner": is_runner, "budget": budget, "day": day,
            "note": "this server runs the 02:05 job" if is_runner else f"{runner} runs the 02:05 job; this server writes a 'not the runner' report and changes nothing"}


def file_mode_ok(path: str, owner: str = "arise-yt") -> dict:
    """Is a secret file there, 0600, owned by the automator's user? Never reads its content."""
    try:
        st = os.stat(path)
    except OSError:
        return {"present": False, "ok": False}
    mode = st.st_mode & 0o777
    try:
        import pwd
        who = pwd.getpwuid(st.st_uid).pw_name
    except (KeyError, ImportError):
        who = str(st.st_uid)
    return {"present": True, "mode": oct(mode), "owner": who, "ok": mode == 0o600 and who == owner,
            "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}


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
        d["demo"] = cfg.demo
        d["schedule"] = cfg.automator.schedule
        d["manual"] = dict(_last_manual)
        d["timer_enabled"] = timer_enabled()
        d["runner"] = runner_info({"runner": "pc", "budgets": {"pc": {"default": 10000}, "ariseOS": {"default": 6000}}}, "ariseOS")
        if not cfg.demo:
            d["error"] = f"the automator is not on this server yet ({_paths()['script']} is missing)"
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
    tok = file_mode_ok(p["token"])
    sec = file_mode_ok(p["secret"])
    token_ok = tok["present"]
    token_days_left = None   # a Published OAuth app's refresh token does not expire after 7 days (handoff 4.1)
    runner = runner_info(read_json(p["runner"], default=None), p["machine"])
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
        "token_ok": token_ok, "token_days_left": token_days_left, "token": tok, "client_secret": sec,
        "token_note": None if tok["ok"] else (f"{p['token']} is {tok.get('mode')} owned by {tok.get('owner')}; it must be 0600 and owned by arise-yt" if tok["present"]
                       else "the server is not signed in to YouTube yet: sudo arisectl automator signin (docs/AUTOMATOR.md)"),
        "client_secret_ok": sec["present"], "runner": runner, "state_dir": p["state"],
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


def timer_enabled() -> bool:
    """Is arise-automator.timer on? (CLAUDE.md rule 3: never run the real job by hand while it is.)"""
    if load().demo:
        from . import automations
        return any(t["timer"] == "arise-automator.timer" and t.get("enabled") for t in automations.list_automations()["timers"])
    if not which("systemctl"):
        return False
    return run(["systemctl", "is-enabled", "arise-automator.timer"], timeout=5)["out"].strip() == "enabled"


def ran_tonight(now: float | None = None, hours: float = 12.0) -> bool:
    """Did the real job already run in the last twelve hours (the timer's report, or a run from here)?"""
    import time as _t
    now = now or _t.time()
    if load().demo:
        return False
    try:
        if now - os.path.getmtime(_paths()["latest"]) < hours * 3600:
            return True
    except OSError:
        pass
    return False


def run_refusal() -> str | None:
    """Why a real run from the dashboard is refused, or None. Preview (the dry run) is never refused."""
    if timer_enabled():
        return "The nightly timer is on (02:05). A real run by hand would make two runs in one night. Use Preview, or pause the timer in Automations first."
    if ran_tonight():
        return "The automator already ran in the last twelve hours. It never runs twice in a night; use Preview."
    return None


def start(mode: str) -> dict:
    """mode: 'run' or 'preview' (dry run). Non-blocking; result lands in last-run.log and LATEST_REPORT.md."""
    if mode not in ("run", "preview"):
        return {"ok": False, "err": "mode must be run or preview"}
    if mode == "run":
        why = run_refusal()
        if why:
            return {"ok": False, "err": why}
    if load().demo:
        _last_manual.update({"mode": mode, "started": now_iso(), "finished": now_iso(), "ok": True, "demo": True, "out": f"(sample) {mode} of arise_daily.py"})
        return {"ok": True, "demo": True, "mode": mode, "started": True}
    if not available():
        return {"ok": False, "err": f"the automator is not here ({_paths()['script']} is missing): sudo arisectl automator setup"}
    unit = UNIT if mode == "run" else PREVIEW_UNIT
    if not which("systemctl"):
        return {"ok": False, "err": "systemd is not here; the automator runs only through its units (as arise-yt, with /etc/arise/arise.env)"}
    r = run(["systemctl", "start", "--no-block", unit], timeout=20)
    if not r["ok"]:
        return {"ok": False, "err": f"{unit} did not start: " + (r.get("err") or r.get("out") or "").strip()[-300:]}
    _last_manual.clear()
    _last_manual.update({"mode": mode, "started": now_iso(), "unit": unit})
    note = "Plan only: nothing changes on YouTube, but its reads spend real quota on the shared 10,000-unit project." if mode == "preview" else ""
    return {"ok": True, "mode": mode, "started": True, "unit": unit, "note": note,
            "watch": f"{_paths()['state']}/LATEST_REPORT.md and last-run.log"}


def cutover(now: datetime | None = None) -> dict:
    """The handoff's section 9 checklist, as far as the server can see it. Each row: ok / warn / bad / you.
    'you' means only Bradly can confirm it (on the PC or in the Cloud Console)."""
    p = _paths()
    rows = []
    add = lambda n, level, text, fix="": rows.append({"n": n, "level": level, "text": text, "fix": fix})  # noqa: E731
    if load().demo:
        return {"demo": True, "rows": [
            {"n": 1, "level": "you", "text": "The OAuth app is Published (Cloud Console, Audience)", "fix": ""},
            {"n": 2, "level": "warn", "text": "Sample: no server token yet", "fix": "sudo arisectl automator signin"},
            {"n": 3, "level": "warn", "text": "Sample: no 'not the runner' report yet", "fix": "wait for 02:05, or: sudo systemctl start arise-automator.service"},
            {"n": 4, "level": "warn", "text": "Sample: no plan-only report yet", "fix": "sudo arisectl automator preview"},
            {"n": 5, "level": "ok", "text": "The job's state files are untracked and live in the state folder (decided Oct 28)", "fix": ""},
            {"n": 6, "level": "ok", "text": "sunday-playlist-reassign is parked; the cap here is 6,000 (decided Oct 28)", "fix": ""},
            {"n": 7, "level": "warn", "text": "The PC's _starfix_state.json is not in /var/lib/arise/automator yet", "fix": "copy it there at cutover, owned by arise-yt"},
            {"n": 8, "level": "you", "text": "The PC is clean and pushed", "fix": ""}],
            "runner": "pc", "machine": "ariseOS"}
    ri = runner_info(read_json(p["runner"], default=None), p["machine"], now)
    add(1, "you", "The OAuth app is Published (Cloud Console → OAuth consent screen → Audience). In Testing, tokens die after 7 days.")
    sec, tok = file_mode_ok(p["secret"]), file_mode_ok(p["token"])
    if tok["ok"] and sec["present"]:
        add(2, "ok", f"The server's own client and token are here (token {tok['mode']}, {tok['owner']}, refreshed {tok['modified']})")
    else:
        add(2, "bad", "The server's own OAuth client and/or token are missing or not 0600 arise-yt",
            "copy the 'ariseOS server' client JSON to " + p["secret"] + ", then: sudo arisectl automator signin")
    reports = []
    try:
        reports = sorted(os.listdir(p["reports"]))
    except OSError:
        pass
    nr = [r for r in reports if "not the runner" in read_text(os.path.join(p["reports"], r), "")[:4000].lower()]
    add(3, "ok" if nr else "warn", f"The timer has written a 'not the runner' report ({nr[-1]})" if nr else "No 'not the runner' report yet",
        "" if nr else "it appears after the first 02:05 run, or: sudo systemctl start arise-automator.service")
    latest = read_text(p["latest"], "")
    signed = "signed in as arise church" in latest.lower()
    m = re.search(r"(\d+) videos? on hold, (\d+) standing rules?", latest)
    add(4, "ok" if signed and m else "warn",
        (f"A plan-only run signed in as Arise Church; {m.group(1)} on hold, {m.group(2)} rules (compare with the PC's LATEST_REPORT.md)" if signed and m
         else "No plan-only report that shows 'signed in as Arise Church' yet"),
        "" if signed and m else "sudo arisectl automator preview   (its reads spend real quota)")
    tracked = []
    if os.path.isdir(os.path.join(p["root"], ".git")):
        r = run(["git", "-C", p["root"], "ls-files", "--", *STATE_FILES], timeout=20)
        tracked = [x for x in (r.get("out") or "").split() if x]
        tr = run(["git", "-C", p["root"], "ls-files", "--", "transcripts"], timeout=20)
        ntx = len([x for x in (tr.get("out") or "").splitlines() if x])
        add(5, "warn" if tracked or ntx else "ok",
            (f"Tracked in git, so the server's writes to them will block the next pull: {', '.join(tracked)}" + (f"; and {ntx} files in transcripts/" if ntx else "")) if tracked or ntx
            else "None of the job's state files are tracked in git", "Bradly decides on the PC (the handoff says: don't untrack them from the server)" if tracked or ntx else "")
        st = run(["git", "-C", p["root"], "status", "--porcelain", "--untracked-files=no"], timeout=20)
        dirty = (st.get("out") or "").strip()
        add(8, "warn" if dirty else "you", ("The server's checkout has modified tracked files: " + dirty.replace("\n", ", ")[:200]) if dirty
            else "The server's checkout is clean; the PC must also be clean and pushed (git status on the PC)")
    else:
        add(5, "bad", "No checkout here yet", "sudo arisectl automator setup")
    w = read_json(p["worklist"], default={}) or {}
    jobs = w.get("jobs", w) if isinstance(w, dict) else w
    reassign = next((j for j in (jobs or []) if isinstance(j, dict) and j.get("id") == "sunday-playlist-reassign"), None)
    if reassign and reassign.get("enabled", True):
        est = reassign.get("estimate_units") or reassign.get("estimate") or reassign.get("units")
        add(6, "warn", f"sunday-playlist-reassign is enabled and books {est} units a night against a {ri.get('budget')} cap here", "Bradly decides on the PC")
    else:
        add(6, "ok", "sunday-playlist-reassign is off (or gone)")
    sf = os.path.join(p["state"], "_starfix_state.json")   # the revised handoff: job state lives in ARISE_STATE_DIR
    if os.path.exists(sf):
        add(7, "ok", f"_starfix_state.json is in the state folder (from {datetime.fromtimestamp(os.path.getmtime(sf)).date()}); check it is the PC's latest at cutover")
    else:
        add(7, "warn", "The PC's _starfix_state.json is not in " + p["state"] + " yet", "copy it there at cutover (scp), then: sudo chown arise-yt: " + sf)
    blocked = pull_blocked()
    if blocked:
        add(9, "bad", "Last night's pull was blocked by untracked files the PC has since committed: " + ", ".join(blocked[:5]),
            "sudo arisectl automator unblock   (moves them aside; the next pull goes through)")
    rows.sort(key=lambda r: r["n"])
    return {"demo": False, "rows": rows, "runner": ri["runner"], "machine": ri["machine"], "is_runner": ri["is_runner"], "budget": ri["budget"]}


_BLOCK_RE = re.compile(r"untracked working tree files would be overwritten by merge:\s*\n((?:\s+\S.*\n)+)", re.M)


def pull_blocked_files(log_text: str) -> list[str]:
    """Pure: the files git named in the LAST 'untracked working tree files would be overwritten' error.
    The revised handoff, section 3: a Whisper transcript the server wrote, which the PC later committed,
    stops the fast-forward and the night runs plan-only."""
    runs = log_text.split("Arise automator - started")
    last = runs[-1] if runs else ""
    m = None
    for m in _BLOCK_RE.finditer(last):
        pass
    if not m:
        return []
    return [ln.strip() for ln in m.group(1).splitlines() if ln.strip() and not ln.strip().startswith(("Please", "Aborting"))]


def pull_blocked() -> list[str]:
    if load().demo:
        return []
    return pull_blocked_files(read_text(_paths()["last_run_log"], ""))


def unblock(files: list[str], now: datetime | None = None) -> dict:
    """Move (never delete) the named untracked files out of the checkout into the state folder."""
    p = _paths()
    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    dest_root = os.path.join(p["state"], "displaced", stamp)
    moved, refused = [], []
    for f in files:
        rel = os.path.normpath(f)
        if rel.startswith("..") or os.path.isabs(rel):
            refused.append(f); continue
        src = os.path.join(p["root"], rel)
        tracked = run(["git", "-C", p["root"], "ls-files", "--error-unmatch", "--", rel], timeout=10)
        if tracked.get("ok") or not os.path.isfile(src):
            refused.append(f); continue      # tracked files and missing files are never touched
        dst = os.path.join(dest_root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.replace(src, dst)
        moved.append({"file": rel, "to": dst})
    return {"ok": not refused, "moved": moved, "refused": refused, "folder": dest_root}

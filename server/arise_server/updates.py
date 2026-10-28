"""Software Update: what is pending, what Bradly queued, and the Saturday 03:30 apply.

The rule (docs/ANSWERS.md round 3, 4 and 25): security patches install on their
own (unattended-upgrades, step 6f); everything else is listed here and waits for
a click. "Install at the window" writes the queue; arise-update.timer runs
`arisectl update apply` Saturday 03:30 America/Chicago, which refuses during a
service, takes a system snapshot first, then installs the queue and reboots only
if the kernel asks and nothing is in service. "Install now" is the same apply,
right away.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timedelta

from . import apps as _apps
from .config import load
from .util import now_iso, read_json, run, which

WINDOW = "Saturday 03:30"
REBOOT_FLAG = "/run/reboot-required"
APT_LINE = re.compile(r"^(?P<pkg>[^/\s]+)/(?P<suite>\S+)\s+(?P<ver>\S+)\s+(?P<arch>\S+)(?:\s+\[upgradable from:\s*(?P<from>[^\]]*)\])?")
_lock = threading.Lock()


# ----- pure helpers (pinned by the tests) ------------------------------------
def parse_apt_upgradable(text: str) -> dict:
    """`apt list --upgradable` → {"security": [...], "other": [...]}.

    A package is security when its suite carries "-security" (noble-security,
    or the ESM apps/infra security pockets). Those are what unattended-upgrades
    installs on its own; the rest wait for Bradly."""
    sec, other = [], []
    for line in (text or "").splitlines():
        m = APT_LINE.match(line.strip())
        if not m or m.group("pkg") == "Listing...":
            continue
        row = {"name": m.group("pkg"), "suite": m.group("suite"), "version": m.group("ver"), "from": (m.group("from") or "").strip()}
        (sec if "-security" in m.group("suite") else other).append(row)
    return {"security": sec, "other": other}


def in_service_window(now: datetime | None = None, services: list | None = None, before_min: int = 60, after_min: int = 180) -> dict | None:
    """The service that is on (or about to be) right now, else None.
    A service "window" is an hour before its start to three hours after: no update,
    reboot or app restart happens inside it. Pure, for the tests."""
    now = now or datetime.now()
    cfg = load()
    services = services if services is not None else (cfg.church.get("services") or [
        {"name": "Sunday Service", "day": "Sunday", "time": "10:30", "site": "Pineville"},
        {"name": "Sunday Service", "day": "Sunday", "time": "10:00", "site": "Alexandria"},
        {"name": "Glory Night", "day": "Monday", "time": "19:00", "site": "Pineville"},
    ])
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for s in services:
        try:
            wd = days.index(str(s.get("day", "")).capitalize())
            h, m = [int(x) for x in str(s.get("time", "0:00")).split(":")[:2]]
        except (ValueError, IndexError):
            continue
        for delta in (-7, 0, 7):
            start = (now - timedelta(days=(now.weekday() - wd) % 7)).replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(days=delta)
            if start - timedelta(minutes=before_min) <= now <= start + timedelta(minutes=after_min):
                return {"name": s.get("name"), "site": s.get("site"), "day": s.get("day"), "time": s.get("time"), "starts": start.isoformat(timespec="minutes")}
    return None


def _in_service():
    """Prefer the church module's own guard if a later block added one."""
    try:
        from . import church
        fn = getattr(church, "in_service_now", None)
        if fn:
            r = fn()
            return r if isinstance(r, dict) or r is None else ({"name": "a service"} if r else None)
    except Exception:  # noqa: BLE001 - the guard must never crash an apply
        pass
    return in_service_window()


# ----- the queue --------------------------------------------------------------
def _queue_path():
    return load().state_dir / "updates-queue.json"


def _sample_queue() -> dict:
    from . import demo_state
    return demo_state.get("updates.queue", lambda: {"packages": ["samba", "tzdata"], "apps": ["uptime-kuma"], "reboot": True, "queued_at": now_iso(), "by": "bradly"})


def queue() -> dict:
    if load().demo:
        return _sample_queue()
    q = read_json(_queue_path(), default=None) or {}
    q.setdefault("packages", [])
    q.setdefault("apps", [])
    q.setdefault("reboot", False)
    return q


def set_queue(packages: list[str] | None = None, app_names: list[str] | None = None, reboot: bool | None = None, who: str = "") -> dict:
    q = queue()
    if packages is not None:
        q["packages"] = sorted({p for p in packages if re.match(r"^[a-z0-9][a-z0-9+.:~-]*$", p)})
    if app_names is not None:
        q["apps"] = sorted({a for a in app_names if _apps.NAME_RE.match(a)})
    if reboot is not None:
        q["reboot"] = bool(reboot)
    q["queued_at"] = now_iso()
    q["by"] = who
    if load().demo:
        return {"ok": True, "demo": True, "queue": q}   # q is the sample's own queue (queue() returned it)
    from .util import write_json
    write_json(_queue_path(), q)
    return {"ok": True, "queue": q}


# ----- what is pending -------------------------------------------------------
def _apt_pending() -> dict:
    if not which("apt"):
        return {"security": [], "other": [], "note": "apt not on this machine"}
    r = run(["apt", "list", "--upgradable"], timeout=60)
    return parse_apt_upgradable(r["out"])


def _app_updates_cached() -> dict:
    return read_json(load().state_dir / "updates-apps.json", default=None) or {"checked_at": None, "apps": []}


def check_apps() -> dict:
    """Pull every installed app's images and say which ones changed. Never recreates
    a container: the new image waits in the local store until the app is updated."""
    cfg = load()
    if not _apps.available():
        return {"ok": True, "demo": True, "checked_at": now_iso(), "apps": [{"name": "uptime-kuma", "current": "sha256:1a2b…", "latest": "sha256:9f8e…", "update": True}, {"name": "netdata", "current": "sha256:77aa…", "latest": "sha256:77aa…", "update": False}]}
    out = []
    for a in _apps.list_apps()["apps"]:
        name = a["name"]
        dest = os.path.join(cfg.apps.root, name)
        base = ["docker", "compose", "-p", name, "-f", os.path.join(dest, "compose.yaml"), "--env-file", os.path.join(dest, ".env")]
        before = _running_images(base)
        pull = run(base + ["pull", "-q"], timeout=1800)
        after = {}
        for svc, img in _service_images(base).items():
            insp = run(["docker", "image", "inspect", "--format", "{{.Id}}", img], timeout=20)
            after[svc] = insp["out"].strip()
        changed = [svc for svc, cur in before.items() if after.get(svc) and cur and after[svc] != cur]
        out.append({"name": name, "update": bool(changed), "services": changed, "pull_ok": pull["ok"], "error": "" if pull["ok"] else (pull["err"] or pull["out"])[-200:]})
    res = {"checked_at": now_iso(), "apps": out}
    from .util import write_json
    write_json(cfg.state_dir / "updates-apps.json", res)
    res["ok"] = True
    return res


def _running_images(base: list[str]) -> dict:
    """service → image ID of the container that is running now."""
    r = run(base + ["images", "--format", "json"], timeout=30)
    out = {}
    try:
        rows = json.loads(r["out"] or "[]")
        if isinstance(rows, dict):
            rows = [rows]
    except json.JSONDecodeError:
        rows = []
    for row in rows:
        svc = row.get("Service") or row.get("ContainerName", "")
        out[svc] = row.get("ID", "")
    return out


def _service_images(base: list[str]) -> dict:
    """service → image reference from the resolved compose file."""
    r = run(base + ["config", "--format", "json"], timeout=30)
    try:
        cfg = json.loads(r["out"] or "{}")
    except json.JSONDecodeError:
        return {}
    return {svc: (d or {}).get("image", "") for svc, d in (cfg.get("services") or {}).items() if (d or {}).get("image")}


_status_cache: dict = {"t": 0.0, "data": None}


def status(fresh: bool = False) -> dict:
    """What is pending. Cached ten minutes on a real box: `apt list` is cheap but the
    git fetch behind arise_behind is not, and the menu-bar badge asks every minute."""
    import time
    cfg = load()
    if not cfg.demo and not fresh and _status_cache["data"] and time.time() - _status_cache["t"] < 600:
        d = dict(_status_cache["data"])
        d["queue"] = queue()           # the queue changes without the lists changing
        d["in_service"] = _in_service()
        return d
    d = _status_uncached()
    if not cfg.demo:
        _status_cache.update(t=time.time(), data=d)
    return d


def _status_uncached() -> dict:
    cfg = load()
    if cfg.demo:
        pend = parse_apt_upgradable(
            "Listing...\nlinux-image-generic/noble-updates 6.8.0-48.48 amd64 [upgradable from: 6.8.0-47.47]\n"
            "openssl/noble-security 3.0.13-0ubuntu3.4 amd64 [upgradable from: 3.0.13-0ubuntu3.3]\n"
            "samba/noble-updates 2:4.19.5+dfsg-4ubuntu9 amd64 [upgradable from: 2:4.19.5+dfsg-4ubuntu8]\n"
            "tzdata/noble-updates 2024b-0ubuntu0.24.04 all [upgradable from: 2024a-3ubuntu1.1]\n")
        return {"demo": True, "window": WINDOW, "security": pend["security"], "other": pend["other"], "reboot_required": True,
                "reboot_pkgs": ["linux-image-6.8.0-47-generic"], "apps": {"checked_at": now_iso(), "apps": [{"name": "uptime-kuma", "update": True, "services": ["uptime-kuma"]}, {"name": "netdata", "update": False, "services": []}]},
                "queue": _sample_queue(),
                "arise": {"behind": 0, "version": _version()}, "last_apply": _sample_last(),
                "in_service": in_service_window(), "last_check": now_iso()}
    pend = _apt_pending()
    reboot_pkgs = []
    try:
        with open(REBOOT_FLAG + ".pkgs", encoding="utf-8") as f:
            reboot_pkgs = [l.strip() for l in f if l.strip()]
    except OSError:
        pass
    from . import system
    arise = system.updates()
    return {"demo": False, "window": WINDOW, "security": pend["security"], "other": pend["other"], "note": pend.get("note", ""),
            "reboot_required": os.path.exists(REBOOT_FLAG), "reboot_pkgs": reboot_pkgs, "apps": _app_updates_cached(), "queue": queue(),
            "arise": {"behind": arise.get("arise_behind"), "version": _version()}, "last_apply": (read_json(cfg.state_dir / "updates-last.json", default=None)),
            "in_service": _in_service(), "last_check": now_iso()}


def _sample_last() -> dict:
    from . import demo_state
    return demo_state.get("updates.last", lambda: {"when": (datetime.now() - timedelta(days=5)).isoformat(timespec="minutes"), "ok": True, "summary": "2 packages, 1 app, no reboot needed"})


def _version():
    from . import VERSION
    return VERSION


def refresh() -> dict:
    """`apt-get update`: the package lists, nothing installed."""
    if load().demo:
        return {"ok": True, "demo": True, "out": "(sample) apt-get update"}
    if not which("apt-get"):
        return {"ok": False, "err": "apt-get is not here; this is not an Ubuntu box"}
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    import subprocess
    p = subprocess.run(["apt-get", "update", "-q"], capture_output=True, text=True, timeout=600, env=env)
    _status_cache.update(t=0.0, data=None)
    return {"ok": p.returncode == 0, "out": p.stdout[-800:], "err": p.stderr[-800:]}


# ----- apply ------------------------------------------------------------------
def apply(no_snapshot: bool = False, force_service: bool = False, log=print) -> dict:
    """Install what is queued. Called by `arisectl update apply` (the Saturday timer)
    and by the dashboard's Install now. Every step is logged; nothing is silent."""
    cfg = load()
    q = status()["queue"] if cfg.demo else queue()
    result = {"when": now_iso(), "ok": True, "steps": [], "summary": ""}

    def step(name, r):
        okk = r.get("ok", True) if isinstance(r, dict) else bool(r)
        result["steps"].append({"step": name, "ok": okk, "out": ((r.get("out") or r.get("err") or "") if isinstance(r, dict) else str(r))[-400:]})
        log(f"{'ok ' if okk else 'BAD'} {name}")
        return okk

    svc = _in_service()
    if svc and not force_service:
        result.update({"ok": False, "summary": f"refused: {svc.get('name')} is on ({svc.get('day')} {svc.get('time')}); nothing was changed"})
        log(result["summary"])
        return _finish(cfg, result)
    if not q["packages"] and not q["apps"] and not q["reboot"]:
        result["summary"] = "nothing queued; nothing to do"
        log(result["summary"])
        return _finish(cfg, result)
    if cfg.demo:
        from . import demo_state
        result["summary"] = f"(sample) installed {len(q['packages'])} packages and updated {len(q['apps'])} apps" + (", then rebooted" if q["reboot"] else "")
        result["demo"] = True
        demo_state.put("updates.last", {"when": result["when"][:16], "ok": True, "summary": result["summary"]})
        q.update({"packages": [], "apps": [], "reboot": False})
        log(result["summary"])
        return result
    if not _lock.acquire(blocking=False):
        return {"ok": False, "summary": "an apply is already running"}
    try:
        if not no_snapshot:
            snap = run(["arisectl", "snapshot", "create", "before update"], timeout=1800) if which("arisectl") else {"ok": False, "err": "arisectl not on PATH"}
            if not snap["ok"] and ("invalid choice" in (snap["err"] or "") or "not on PATH" in (snap["err"] or "")):
                result.update({"ok": False, "summary": "no system snapshot verb on this box yet (arisectl snapshot): stopped before touching anything. Re-run with --no-snapshot to go without one."})
                step("snapshot", snap)
                return _finish(cfg, result)
            if not step("snapshot before update", snap):
                result.update({"ok": False, "summary": "the snapshot failed; nothing was installed"})
                return _finish(cfg, result)
        done_pkgs = done_apps = 0
        if q["packages"]:
            env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
            import subprocess
            p = subprocess.run(["apt-get", "install", "-y", "-q", "--only-upgrade", *q["packages"]], capture_output=True, text=True, timeout=3600, env=env)
            r = {"ok": p.returncode == 0, "out": p.stdout, "err": p.stderr}
            if step(f"apt-get install --only-upgrade {' '.join(q['packages'])}", r):
                done_pkgs = len(q["packages"])
                q["packages"] = []
            else:
                result["ok"] = False
        for name in list(q["apps"]):
            r = _apps.act(name, "update")
            if step(f"update app {name}", r):
                done_apps += 1
                q["apps"].remove(name)
            else:
                result["ok"] = False
        from .util import write_json
        write_json(_queue_path(), dict(q, queued_at=q.get("queued_at"), by=q.get("by")))
        reboot_needed = os.path.exists(REBOOT_FLAG)
        result["summary"] = f"{done_pkgs} packages, {done_apps} apps" + (", reboot needed" if reboot_needed else ", no reboot needed")
        _finish(cfg, result)
        if reboot_needed and q["reboot"] and result["ok"]:
            if _in_service() and not force_service:
                log("reboot skipped: a service is on")
            else:
                log("rebooting")
                q["reboot"] = False
                write_json(_queue_path(), q)
                run(["systemctl", "reboot"], timeout=10)
        return result
    finally:
        _lock.release()


def _finish(cfg, result):
    if not cfg.demo:
        try:
            from .util import write_json
            write_json(cfg.state_dir / "updates-last.json", result)
            with open(os.path.join(cfg.paths.log_dir, "updates.log"), "a", encoding="utf-8") as f:
                f.write(f"{result['when']} {'ok' if result['ok'] else 'FAILED'} {result['summary']}\n")
        except OSError:
            pass
    return result

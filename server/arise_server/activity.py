"""Activity Monitor: processes and containers, who is using the box, End Process.

psutil for processes, `docker stats` for the containers. The whole answer is
cached for three seconds so a dashboard polling every two does not become the
load it is measuring. Ending a process refuses the ones the box cannot live
without (round 3, 6)."""
from __future__ import annotations

import json
import os
import re
import signal
import threading
import time

import psutil

from .config import load
from .util import run, which

PROTECTED_NAMES = {"systemd", "samba", "smbd", "nmbd", "winbindd", "samba-dcerpcd", "rpcd_lsad", "dockerd", "containerd", "containerd-shim-runc-v2", "sshd", "arise-web", "uvicorn", "cage", "firefox", "firefox-bin", "firefox-esr", "epiphany", "journald", "systemd-journald", "systemd-logind", "dbus-daemon", "nut-monitor", "upsmon", "upsd"}
PROTECTED_CMD = ("arise_server", "samba", "dockerd", "containerd", "sshd", "/usr/sbin/cage")
_cache: dict = {"t": 0.0, "data": None}
_lock = threading.Lock()


def may_kill(pid: int, name: str = "", cmdline: str = "", me: int | None = None) -> tuple[bool, str]:
    """Pure: may this process be ended from the dashboard? (ok, reason)."""
    me = os.getpid() if me is None else me
    if pid <= 1:
        return False, "PID 1 is the system itself"
    if pid == me or pid == os.getppid():
        return False, "that is the dashboard"
    n = (name or "").lower()
    if n in PROTECTED_NAMES or any(n.startswith(p) for p in ("systemd-", "rpcd_")):
        return False, f"{name} keeps the box alive (domain, Docker, SSH, the dashboard, the closet monitor, systemd)"
    if any(p in (cmdline or "") for p in PROTECTED_CMD):
        return False, "that process belongs to the domain, Docker, SSH or the dashboard"
    return True, ""


def _processes(limit: int = 60) -> list[dict]:
    procs = []
    for p in psutil.process_iter(["pid", "name", "username", "cmdline", "memory_info", "status", "create_time", "num_threads"]):
        try:
            p.cpu_percent(None)  # prime
            procs.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    time.sleep(0.35)
    rows = []
    for p in procs:
        try:
            info = p.info
            mem = info["memory_info"].rss if info.get("memory_info") else 0
            io = None
            try:
                c = p.io_counters()
                io = {"read": c.read_bytes, "write": c.write_bytes}
            except (psutil.AccessDenied, AttributeError, psutil.NoSuchProcess):
                pass
            cmd = " ".join(info.get("cmdline") or [])[:160]
            rows.append({"pid": info["pid"], "name": info.get("name") or "?", "user": info.get("username") or "", "cpu": round(p.cpu_percent(None), 1), "mem": mem,
                         "status": info.get("status", ""), "threads": info.get("num_threads"), "since": info.get("create_time"), "io": io, "cmd": cmd,
                         "container": _container_of(info["pid"]), "protected": not may_kill(info["pid"], info.get("name") or "", cmd)[0]})
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    rows.sort(key=lambda r: (r["cpu"], r["mem"]), reverse=True)
    return rows[:limit]


_cg_cache: dict = {}


def _container_of(pid: int) -> str:
    """The container (short id) a process runs in, from its cgroup, else ''."""
    try:
        with open(f"/proc/{pid}/cgroup", encoding="utf-8") as f:
            txt = f.read()
    except OSError:
        return ""
    m = re.search(r"docker[-/]([0-9a-f]{12})", txt)
    return m.group(1) if m else ""


def _containers() -> list[dict]:
    if not which("docker"):
        return []
    r = run(["docker", "stats", "--no-stream", "--format", "{{json .}}"], timeout=20)
    out = []
    for line in r["out"].splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        from .apps import _parse_mem
        mem = d.get("MemUsage", "0B / 0B").split("/")
        out.append({"id": d.get("ID", "")[:12], "name": d.get("Name", ""), "cpu": float((d.get("CPUPerc") or "0%").rstrip("%") or 0), "mem": _parse_mem(mem[0].strip()),
                    "mem_limit": _parse_mem(mem[1].strip()) if len(mem) > 1 else 0, "net": d.get("NetIO", ""), "block": d.get("BlockIO", ""), "pids": d.get("PIDs", "")})
    out.sort(key=lambda c: c["cpu"], reverse=True)
    return out


def snapshot(limit: int = 60) -> dict:
    cfg = load()
    if cfg.demo:
        from . import demo_state
        gone = demo_state.get("activity.ended", set)
        d = _demo()
        d["processes"] = [p for p in d["processes"] if p["pid"] not in gone]
        return d
    with _lock:
        if _cache["data"] and time.time() - _cache["t"] < 3:
            return _cache["data"]
        vm = psutil.virtual_memory()
        la = os.getloadavg() if hasattr(os, "getloadavg") else (0, 0, 0)
        data = {"demo": False, "t": time.time(), "processes": _processes(limit), "containers": _containers(),
                "totals": {"cpu": psutil.cpu_percent(None), "cores": psutil.cpu_count() or 1, "mem_total": vm.total, "mem_used": vm.used, "mem_pct": vm.percent, "load": [round(x, 2) for x in la], "procs": len(psutil.pids())}}
        _cache.update(t=time.time(), data=data)
        return data


def kill(pid: int, confirm: str) -> dict:
    """End a process. confirm must be the PID as text (the dashboard asks for it)."""
    if str(pid) != str(confirm):
        return {"ok": False, "err": "type the PID to confirm"}
    if load().demo:
        row = next((p for p in _demo()["processes"] if p["pid"] == pid), None)
        from . import demo_state
        gone = demo_state.get("activity.ended", set)
        if not row or pid in gone:
            return {"ok": False, "err": f"no process {pid} (it already ended)"}
        okk, why = may_kill(pid, row["name"], row["cmd"])
        if not okk:
            return {"ok": False, "err": why}
        gone.add(pid)
        return {"ok": True, "demo": True, "out": f"(sample) {row['name']} ({pid}) ended"}
    try:
        p = psutil.Process(pid)
        name, cmd = p.name(), " ".join(p.cmdline())
    except psutil.NoSuchProcess:
        return {"ok": False, "err": f"no process {pid} (it already ended)"}
    except psutil.AccessDenied:
        name, cmd = "?", ""
    okk, why = may_kill(pid, name, cmd)
    if not okk:
        return {"ok": False, "err": why}
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.6)
        if psutil.pid_exists(pid):
            os.kill(pid, signal.SIGKILL)
            return {"ok": True, "out": f"{name} ({pid}) did not stop politely; it was killed"}
        return {"ok": True, "out": f"{name} ({pid}) ended"}
    except PermissionError:
        return {"ok": False, "err": "not permitted (the dashboard runs without that right)"}
    except ProcessLookupError:
        return {"ok": True, "out": "it ended on its own"}


def _demo() -> dict:
    sample = [
        ("samba", "root", 3.2, 412_000_000, "/usr/sbin/samba -D", True), ("python3", "arise", 1.8, 96_000_000, "/opt/arise/venv/bin/python -m arise_server", True),
        ("dockerd", "root", 1.1, 148_000_000, "/usr/bin/dockerd -H fd://", True), ("netdata", "netdata", 2.6, 210_000_000, "/usr/sbin/netdata -D", False),
        ("node", "1000", 0.9, 142_000_000, "node server/server.js (uptime-kuma)", False), ("postgres", "999", 0.4, 88_000_000, "postgres -D /var/lib/postgresql/data", False),
        ("java", "1001", 2.2, 690_000_000, "java -jar guacamole (tomcat)", False), ("restic", "root", 0.0, 0, "", False), ("sshd", "root", 0.0, 9_000_000, "sshd: /usr/sbin/sshd -D", True),
        ("cage", "arise-kiosk", 4.1, 120_000_000, "/usr/bin/cage -s -- /usr/local/bin/arise-browser http://127.0.0.1:4147/?kiosk=1", True), ("firefox", "arise-kiosk", 6.3, 540_000_000, "firefox --kiosk --profile /var/lib/arise/browser/profiles/neutral", True),
        ("smbd", "root", 0.7, 64_000_000, "/usr/sbin/smbd", True), ("cron", "root", 0.0, 3_000_000, "/usr/sbin/cron -f", False), ("rsyslogd", "syslog", 0.1, 5_000_000, "/usr/sbin/rsyslogd -n", False),
    ]
    procs = [{"pid": 400 + i * 7, "name": n, "user": u, "cpu": c, "mem": m, "status": "sleeping", "threads": 4 + i, "since": time.time() - 86400 * 14, "io": {"read": 10_000_000 * (i + 1), "write": 2_000_000 * i}, "cmd": cmd, "container": "" if p else f"c{i:011x}", "protected": p}
             for i, (n, u, c, m, cmd, p) in enumerate(sample)]
    procs.sort(key=lambda r: (r["cpu"], r["mem"]), reverse=True)
    conts = [{"id": "3f9c0a1b2c3d", "name": "arise-app-netdata", "cpu": 2.6, "mem": 210_000_000, "mem_limit": 512 * 1024 ** 2, "net": "1.2MB / 300kB", "block": "0B / 12MB", "pids": "38"},
             {"id": "9a8b7c6d5e4f", "name": "arise-app-uptime-kuma", "cpu": 0.9, "mem": 142_000_000, "mem_limit": 384 * 1024 ** 2, "net": "4.1MB / 1.1MB", "block": "0B / 2MB", "pids": "11"},
             {"id": "1122334455aa", "name": "arise-app-guacamole", "cpu": 2.2, "mem": 690_000_000, "mem_limit": 1024 * 1024 ** 2, "net": "800kB / 2.3MB", "block": "0B / 0B", "pids": "61"},
             {"id": "1122334455bb", "name": "arise-app-guacamole-db", "cpu": 0.4, "mem": 88_000_000, "mem_limit": 1024 * 1024 ** 2, "net": "120kB / 90kB", "block": "0B / 4MB", "pids": "8"}]
    return {"demo": True, "t": time.time(), "processes": procs, "containers": conts,
            "totals": {"cpu": 23.4, "cores": 4, "mem_total": 16 * 1024 ** 3, "mem_used": int(5.8 * 1024 ** 3), "mem_pct": 36.2, "load": [0.42, 0.58, 0.61], "procs": 212}}

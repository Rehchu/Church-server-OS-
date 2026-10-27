"""Live system stats: a collector thread, a 60-sample ring, and an SSE feed.

Same idea as HomeDock's StatsCollector: one thread samples psutil once a
second into a cache; every SSE client just reads the cache, so ten open
dashboards cost the same as one.
"""
from __future__ import annotations

import asyncio
import collections
import json
import os
import platform
import threading
import time

import psutil

from .util import human_bytes

RING = 60
_lock = threading.Lock()
_history = collections.deque(maxlen=RING)
_latest: dict = {}
_started = False
_prev = {"net": None, "disk": None, "t": None}


def _temps():
    try:
        info = psutil.sensors_temperatures()
    except Exception:
        return None
    for key in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
        if key in info and info[key]:
            return round(info[key][0].current, 1)
    for entries in info.values():
        for e in entries:
            if e.current:
                return round(e.current, 1)
    return None


def _disks():
    out = []
    seen = set()
    for part in psutil.disk_partitions(all=False):
        if part.fstype in ("squashfs", "tmpfs", "devtmpfs", "overlay") or part.mountpoint in seen:
            continue
        if part.mountpoint.startswith(("/snap", "/boot/efi", "/var/lib/docker")):
            continue
        seen.add(part.mountpoint)
        try:
            u = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        out.append({"mount": part.mountpoint, "fs": part.fstype, "total": u.total, "used": u.used, "free": u.free, "pct": round(u.percent, 1)})
    return out


def sample() -> dict:
    now = time.time()
    cpu = psutil.cpu_percent(interval=None)
    per_core = psutil.cpu_percent(interval=None, percpu=True)
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    net = psutil.net_io_counters()
    dio = psutil.disk_io_counters()
    rx = tx = rd = wr = 0.0
    if _prev["t"] and _prev["net"] and net:
        dt = max(now - _prev["t"], 1e-3)
        rx = (net.bytes_recv - _prev["net"].bytes_recv) / dt
        tx = (net.bytes_sent - _prev["net"].bytes_sent) / dt
        if dio and _prev["disk"]:
            rd = (dio.read_bytes - _prev["disk"].read_bytes) / dt
            wr = (dio.write_bytes - _prev["disk"].write_bytes) / dt
    _prev.update({"net": net, "disk": dio, "t": now})
    try:
        load = os.getloadavg()
    except (AttributeError, OSError):
        load = (0.0, 0.0, 0.0)
    return {
        "t": int(now),
        "cpu": round(cpu, 1), "cores": [round(c, 0) for c in per_core],
        "cpu_count": psutil.cpu_count(logical=True) or 1,
        "temp": _temps(),
        "ram": {"total": vm.total, "used": vm.total - vm.available, "pct": round(vm.percent, 1)},
        "swap": {"total": sw.total, "used": sw.used, "pct": round(sw.percent, 1)},
        "net": {"rx": round(rx), "tx": round(tx)},
        "disk_io": {"read": round(rd), "write": round(wr)},
        "load": [round(x, 2) for x in load],
        "uptime": int(now - psutil.boot_time()),
    }


def _loop():
    psutil.cpu_percent(interval=None)
    while True:
        try:
            s = sample()
            s["disks"] = _disks() if int(s["t"]) % 10 == 0 or not _latest.get("disks") else _latest["disks"]
            with _lock:
                _latest.clear()
                _latest.update(s)
                _history.append({k: s[k] for k in ("t", "cpu", "ram", "net", "disk_io")} | {"ram": s["ram"]["pct"]})
        except Exception as e:  # keep the thread alive whatever psutil throws
            with _lock:
                _latest["error"] = str(e)
        time.sleep(1)


def start():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, name="arise-metrics", daemon=True).start()


def latest() -> dict:
    with _lock:
        return dict(_latest)


def history() -> list:
    with _lock:
        return list(_history)


def static_info() -> dict:
    vm = psutil.virtual_memory()
    return {
        "hostname": platform.node(), "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(), "python": platform.python_version(),
        "cpu_model": _cpu_model(), "cpu_count": psutil.cpu_count(logical=True),
        "ram_total": vm.total, "ram_total_h": human_bytes(vm.total),
        "boot_time": int(psutil.boot_time()),
    }


def _cpu_model() -> str:
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


async def sse():
    """One event per second with the latest sample. Browser reconnects on its own."""
    last_t = None
    while True:
        s = latest()
        if s and s.get("t") != last_t:
            last_t = s.get("t")
            yield f"data: {json.dumps(s)}\n\n"
        await asyncio.sleep(1)

"""Storage: what is eating the disk (round 3, 9).

df for every real mount; a walk of the shares and the app data folders that
sums each one, keeps the 50 biggest files and the files not changed in a year.
The walk runs in a background thread with a time cap and the result is cached
in /var/lib/arise/storage.json with an "as of"; the dashboard shows the cache
and offers a rescan. Nothing here deletes anything: Finder does that, by hand.

Honest note: Linux does not track "last opened" on these filesystems (relatime
makes atime unreliable), so "old" means not CHANGED in a year."""
from __future__ import annotations

import heapq
import os
import threading
import time
from datetime import datetime, timedelta

import psutil

from .config import load
from .util import now_iso, read_json, write_json

SKIP_FS = {"tmpfs", "devtmpfs", "squashfs", "overlay", "proc", "sysfs", "cgroup2", "efivarfs", "nsfs", "fuse.portal", "autofs"}
DISK_ALERT_PCT = 75     # Bradly, Oct 28: say so at 75 % full
DISK_BAD_PCT = 90
_state: dict = {"running": False, "started": None}


def disk_alerts(mounts_: list[dict] | None = None, warn_pct: int = DISK_ALERT_PCT, bad_pct: int = DISK_BAD_PCT) -> list[dict]:
    """Needs-you items for full disks. Pure when given mounts."""
    items = []
    for m in (mounts_ if mounts_ is not None else mounts()):
        pct = float(m.get("pct") or 0)
        if pct >= bad_pct:
            items.append({"level": "bad", "text": f"{m['mount']} is {pct:.0f}% full: {_h(m.get('free'))} left. Storage shows what is eating it; free space before backups and uploads start failing."})
        elif pct >= warn_pct:
            items.append({"level": "warn", "text": f"{m['mount']} is {pct:.0f}% full ({_h(m.get('free'))} left). Storage shows what is eating it."})
    return items


def _h(n):
    from .util import human_bytes
    return human_bytes(n)


def mounts() -> list[dict]:
    out = []
    seen = set()
    for p in psutil.disk_partitions(all=True):
        if p.fstype in SKIP_FS or p.mountpoint.startswith(("/snap", "/boot/efi", "/run", "/sys", "/proc", "/dev")) or p.mountpoint in seen:
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
        except (PermissionError, OSError):
            continue
        seen.add(p.mountpoint)
        out.append({"mount": p.mountpoint, "device": p.device, "fs": p.fstype, "total": u.total, "used": u.used, "free": u.free, "pct": u.percent})
    return out


def walk(roots: list[dict], time_cap: float = 120.0, top_n: int = 50, old_days: int = 365) -> dict:
    """One pass over the given roots ({"id","name","path","kind"}): size per root,
    the biggest files, the big-and-old files. Gives up politely at time_cap."""
    t0 = time.time()
    cutoff = time.time() - old_days * 86400
    from . import sharing
    private = os.path.normpath(sharing.pastors_path())
    sizes, biggest, old = [], [], []
    truncated = False
    for r in roots:
        total, files = 0, 0
        if not os.path.isdir(r["path"]):
            sizes.append({**r, "bytes": None, "files": 0, "missing": True})
            continue
        for dirpath, dirnames, filenames in os.walk(r["path"]):
            dirnames[:] = [d for d in dirnames if not d.startswith(".Trash") and d not in ("node_modules", "__pycache__")]
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                try:
                    st = os.lstat(fp)
                except OSError:
                    continue
                total += st.st_size
                files += 1
                if private and (fp == private or fp.startswith(private + os.sep)):
                    continue   # round 5, row 18: the Pastors folder counts in the totals, its names never show
                item = (st.st_size, fp, st.st_mtime)
                if len(biggest) < top_n:
                    heapq.heappush(biggest, item)
                elif st.st_size > biggest[0][0]:
                    heapq.heapreplace(biggest, item)
                if st.st_mtime < cutoff and st.st_size > 1_000_000:
                    if len(old) < top_n:
                        heapq.heappush(old, item)
                    elif st.st_size > old[0][0]:
                        heapq.heapreplace(old, item)
            if time.time() - t0 > time_cap:
                truncated = True
                break
        sizes.append({**r, "bytes": total, "files": files, "partial": truncated})
        if truncated:
            break
    fmt = lambda lst: [{"path": p, "bytes": s, "mtime": datetime.fromtimestamp(m).isoformat(timespec="minutes")} for s, p, m in sorted(lst, reverse=True)]
    return {"as_of": now_iso(), "seconds": round(time.time() - t0, 1), "truncated": truncated, "roots": sizes, "biggest": fmt(biggest), "old": fmt(old), "old_days": old_days}


def _roots() -> list[dict]:
    cfg = load()
    out = []
    try:
        from . import shares
        for s in shares.list_shares()["shares"]:
            if s.get("path") and s["name"] != "sysvol" and "%" not in s["path"]:
                out.append({"id": "share:" + s["name"], "name": s["name"], "path": s["path"], "kind": "share"})
    except Exception:  # noqa: BLE001
        pass
    root = cfg.apps.root
    if os.path.isdir(root):
        for d in sorted(os.listdir(root)):
            if os.path.isdir(os.path.join(root, d)):
                out.append({"id": "app:" + d, "name": d, "path": os.path.join(root, d), "kind": "app"})
    return out


def _cache_path():
    return load().state_dir / "storage.json"


def status() -> dict:
    cfg = load()
    if cfg.demo:
        return _demo()
    cache = read_json(_cache_path(), default=None)
    return {"demo": False, "mounts": mounts(), "scan": cache, "scanning": _state["running"], "scan_started": _state["started"], "note": "Linux does not record when a file was last opened on these disks; 'old' means not changed in a year."}


def scan(background: bool = True) -> dict:
    cfg = load()
    if cfg.demo:
        return {"ok": True, "demo": True}
    if _state["running"]:
        return {"ok": True, "out": "a scan is already running"}
    def go():
        _state.update(running=True, started=now_iso())
        try:
            res = walk(_roots())
            write_json(_cache_path(), res)
        finally:
            _state["running"] = False
    if background:
        threading.Thread(target=go, daemon=True, name="arise-storage-scan").start()
        return {"ok": True, "out": "scan started; the page refreshes when it is done"}
    go()
    return {"ok": True, "out": "scanned"}


def _demo() -> dict:
    now = datetime.now()
    old = (now - timedelta(days=500)).isoformat(timespec="minutes")
    roots = [
        {"id": "share:shares", "name": "shares", "path": "/srv/arise/shares", "kind": "share", "bytes": 212_000_000_000, "files": 48_210},
        {"id": "share:homes", "name": "homes", "path": "/srv/arise/homes", "kind": "share", "bytes": 48_700_000_000, "files": 61_004},
        {"id": "share:graphics", "name": "graphics", "path": "/srv/arise/shares/graphics", "kind": "share", "bytes": 58_000_000_000, "files": 3_912},
        {"id": "share:media", "name": "media", "path": "/mnt/synology/media", "kind": "share", "bytes": 1_240_000_000_000, "files": 1_820},
        {"id": "app:jellyfin", "name": "jellyfin", "path": "/srv/arise/apps/jellyfin", "kind": "app", "bytes": 3_100_000_000, "files": 12_400},
        {"id": "app:immich", "name": "immich", "path": "/srv/arise/apps/immich", "kind": "app", "bytes": 9_800_000_000, "files": 22_300},
        {"id": "app:guacamole", "name": "guacamole", "path": "/srv/arise/apps/guacamole", "kind": "app", "bytes": 410_000_000, "files": 1_200},
        {"id": "app:netdata", "name": "netdata", "path": "/srv/arise/apps/netdata", "kind": "app", "bytes": 1_900_000_000, "files": 330},
    ]
    biggest = [{"path": f"/mnt/synology/media/sermons/2026-10-{26 - i:02d} Sunday Service.mp4", "bytes": 6_420_000_000 - i * 310_000_000, "mtime": (now - timedelta(days=i * 7)).isoformat(timespec="minutes")} for i in range(12)]
    biggest += [{"path": "/srv/arise/shares/graphics/loops/stage-flame-4k.mov", "bytes": 2_900_000_000, "mtime": "2026-09-30T11:20"}, {"path": "/srv/arise/homes/bradly/Downloads/proclaim-backup-2026-08.zip", "bytes": 1_750_000_000, "mtime": "2026-08-14T09:03"}]
    oldf = [{"path": "/srv/arise/shares/graphics/backgrounds/easter-2025-set.psd", "bytes": 640_000_000, "mtime": old}, {"path": "/srv/arise/homes/office/Old bulletins 2024.zip", "bytes": 210_000_000, "mtime": old}, {"path": "/srv/arise/shares/worship/tracks/christmas-2024-stems.zip", "bytes": 1_100_000_000, "mtime": old}]
    return {"demo": True, "mounts": [{"mount": "/", "device": "/dev/sda2", "fs": "ext4", "total": 2.4e11, "used": 7.1e10, "free": 1.69e11, "pct": 30}, {"mount": "/srv/arise", "device": "/dev/sdb1", "fs": "ext4", "total": 9.6e11, "used": 2.6e11, "free": 7e11, "pct": 27}, {"mount": "/mnt/synology", "device": "//synology/arise", "fs": "cifs", "total": 1.6e13, "used": 4.9e12, "free": 1.11e13, "pct": 31}],
            "scan": {"as_of": (now - timedelta(hours=6)).isoformat(timespec="minutes"), "seconds": 41.2, "truncated": False, "roots": roots, "biggest": biggest, "old": oldf, "old_days": 365},
            "scanning": False, "scan_started": None, "note": "Linux does not record when a file was last opened on these disks; 'old' means not changed in a year."}

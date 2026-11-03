"""The internet speed, every hour (round 7, 121), charted in Activity Monitor → Network, so a
slow evening can be shown to Optimum with numbers. Cloudflare's public speed endpoints
(speed.cloudflare.com, no account, no key); about 25 MB down and 5 MB up a test. Skipped
during a service (church.hold("heavy")): the stream gets the line to itself.

Results: <state_dir>/speedtest.json, the last 45 days. Nothing else is recorded.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from .config import load

DOWN_URL = "https://speed.cloudflare.com/__down?bytes={n}"
UP_URL = "https://speed.cloudflare.com/__up"
DOWN_BYTES = 25_000_000
UP_BYTES = 5_000_000
KEEP_DAYS = 45


def _path() -> Path:
    return Path(load().state_dir) / "speedtest.json"


def mbps(nbytes: int, seconds: float) -> float:
    """Pure: bytes over seconds as megabits a second, one decimal."""
    return round(nbytes * 8 / max(seconds, 1e-6) / 1e6, 1)


def _down(n: int) -> tuple[int, float]:
    t0 = time.monotonic()
    got = 0
    with urllib.request.urlopen(urllib.request.Request(DOWN_URL.format(n=n), headers={"User-Agent": "ariseOS/speedtest"}), timeout=60) as r:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            got += len(chunk)
    return got, time.monotonic() - t0


def _up(n: int) -> tuple[int, float]:
    body = os.urandom(n)
    t0 = time.monotonic()
    req = urllib.request.Request(UP_URL, data=body, method="POST", headers={"User-Agent": "ariseOS/speedtest", "Content-Type": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read()
    return n, time.monotonic() - t0


def _ping() -> float:
    best = None
    for _ in range(3):
        t0 = time.monotonic()
        with urllib.request.urlopen(urllib.request.Request(DOWN_URL.format(n=0), headers={"User-Agent": "ariseOS/speedtest"}), timeout=10) as r:
            r.read()
        ms = (time.monotonic() - t0) * 1000
        best = ms if best is None else min(best, ms)
    return round(best or 0, 1)


def history() -> list[dict]:
    if load().demo:
        return _sample()
    try:
        return json.loads(_path().read_text(encoding="utf-8")).get("runs", [])
    except (OSError, ValueError):
        return []


def run(now: datetime | None = None, tester=None) -> dict:
    """One test. tester() -> {down, up, ping} for the tests."""
    from . import church
    now = now or datetime.now()
    if load().demo:
        return {"ok": True, "demo": True, **_sample()[-1]}
    h = church.hold("heavy", now)
    if h:
        return {"ok": False, "held": True, "err": h["why"]}
    try:
        if tester:
            r = tester()
        else:
            ping = _ping()
            d = _down(DOWN_BYTES)
            u = _up(UP_BYTES)
            r = {"down": mbps(*d), "up": mbps(*u), "ping": ping}
        row = {"at": now.isoformat(timespec="minutes"), "down": r["down"], "up": r["up"], "ping": r["ping"]}
    except Exception as e:  # noqa: BLE001 - offline is a result: it is charted as a gap with the reason
        row = {"at": now.isoformat(timespec="minutes"), "down": None, "up": None, "ping": None, "err": str(e)[:160]}
    cut = (now - timedelta(days=KEEP_DAYS)).isoformat(timespec="minutes")
    runs = [x for x in history() if x.get("at", "") >= cut] + [row]
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"runs": runs}), encoding="utf-8")
    return {"ok": "err" not in row, **row}


def summary(runs: list[dict] | None = None, days: int = 7) -> dict:
    """Pure-ish: the last result and the week's medians."""
    runs = runs if runs is not None else history()
    if not runs:
        return {"runs": [], "last": None, "week": None, "plan": "Optimum Business (round 7, 127)", "demo": load().demo}
    last = runs[-1]
    cut = (datetime.fromisoformat(last["at"]) - timedelta(days=days)).isoformat(timespec="minutes")
    week = [r for r in runs if r.get("at", "") >= cut and r.get("down") is not None]

    def med(k):
        v = sorted(r[k] for r in week if r.get(k) is not None)
        return v[len(v) // 2] if v else None
    return {"runs": runs[-24 * 7:], "last": last, "week": {"down": med("down"), "up": med("up"), "ping": med("ping"), "tests": len(week),
            "failed": sum(1 for r in runs if r.get("at", "") >= cut and r.get("down") is None)},
            "plan": "Optimum Business (round 7, 127)", "demo": load().demo}


def _sample() -> list[dict]:
    """A week of hourly sample results (the preview has no internet line)."""
    import math
    base = datetime.now().replace(minute=5, second=0, microsecond=0)
    out = []
    for i in range(24 * 7, 0, -1):
        t = base - timedelta(hours=i)
        dip = 0.55 if t.hour in (19, 20, 21) else 1.0
        out.append({"at": t.isoformat(timespec="minutes"), "down": round((880 + 60 * math.sin(i / 5)) * dip, 1), "up": round(38 + 4 * math.cos(i / 7), 1),
                    "ping": round(11 + 3 * abs(math.sin(i / 3)), 1), "sample": True})
    return out

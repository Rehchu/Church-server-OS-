"""Service mode on the closet monitor (round 7, 87): while a service runs, the desktop shows
the stream's health, every department checklist's progress, and the run sheet.

- The stream: is the channel live right now? Read from the channel's public /live page (no
  API, no quota), checked at most once a minute, plus the last internet speed test.
- The checklists: done of total per department, for this service's round.
- The run sheet: the newest Markdown or text file named "run sheet" in the Church folder's
  "Run sheets" folder or on the owner's Desktop, preferring one whose name has the service's
  name or today's date. Shown read-only; nothing is changed.
"""
from __future__ import annotations

import re
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from .config import load

LIVE_TTL = 60
RUN_SHEET_MAX = 40_000
_live = {"at": 0.0, "data": None}
_lock = threading.Lock()


def live_status(fetch=None) -> dict:
    """{live: True/False/None, checked, why}. None = could not tell (offline, page changed)."""
    from .sermons import CHANNEL
    if load().demo:
        return {"live": True, "checked": datetime.now().isoformat(timespec="minutes"), "demo": True, "url": f"https://www.youtube.com/channel/{CHANNEL}/live"}
    with _lock:
        if _live["data"] and time.time() - _live["at"] < LIVE_TTL:
            return _live["data"]
        url = f"https://www.youtube.com/channel/{CHANNEL}/live"
        try:
            html = (fetch or _get)(url)
            live = is_live_page(html)
            d = {"live": live, "checked": datetime.now().isoformat(timespec="minutes"), "url": url}
        except Exception as e:  # noqa: BLE001
            d = {"live": None, "checked": datetime.now().isoformat(timespec="minutes"), "url": url, "why": str(e)[:120]}
        _live.update(at=time.time(), data=d)
        return d


def is_live_page(html: str) -> bool | None:
    """Pure: does the channel's /live page say a broadcast is on now?"""
    if not html:
        return None
    if re.search(r'"isLiveNow"\s*:\s*true', html) or re.search(r'"isLive"\s*:\s*true', html):
        return True
    if '"isLiveNow":false' in html or 'ytInitialData' in html:
        return False
    return None


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ariseOS/service-mode", "Accept-Language": "en-US"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read(2_000_000).decode("utf-8", errors="ignore")


def run_sheet(service: str, today: str | None = None, dirs: list[Path] | None = None) -> dict:
    """The run sheet for this service, read-only."""
    today = today or datetime.now().date().isoformat()
    if load().demo:
        return {"ok": True, "name": "Glory Night run sheet.md", "demo": True, "text": DEMO_SHEET}
    cfg = load()
    if dirs is None:
        owner = str(getattr(cfg.owner, "user", "") or cfg.web.admin_user)
        dirs = [Path(cfg.system.data_root) / "shares" / str(cfg.storage.church_folder) / "Run sheets", Path(cfg.directory.homes_path) / owner / "Desktop"]
    best = pick_sheet([f for d in dirs if d.is_dir() for f in d.iterdir()], service, today)
    if not best:
        return {"ok": False, "why": "no run sheet yet: put a file named “… run sheet.md” in Church → Run sheets"}
    try:
        text = best.read_text(encoding="utf-8", errors="replace")[:RUN_SHEET_MAX]
    except OSError as e:
        return {"ok": False, "why": str(e)[:120]}
    return {"ok": True, "name": best.name, "text": text}


def pick_sheet(files: list[Path], service: str, today: str) -> Path | None:
    """Pure-ish: a run sheet by name; today's date or the service's name first, then the newest."""
    cand = [f for f in files if f.is_file() and not f.is_symlink() and f.suffix.lower() in (".md", ".txt") and "run sheet" in f.name.lower()]
    if not cand:
        return None
    svc = (service or "").lower()

    def score(f: Path):
        n = f.name.lower()
        return (today in n, bool(svc) and svc in n, f.stat().st_mtime)
    return max(cand, key=score)


def now_view(now: datetime | None = None) -> dict:
    """What the monitor shows: in a service or not, and if so the three panels."""
    from . import church, checklists, speedtest
    now = now or datetime.now()
    svc = church.in_service_now(now)
    if load().demo and not svc and _demo_force["on"]:
        svc = {"name": "Glory Night", "site": "Pineville", "started": now.replace(hour=19, minute=0).isoformat(timespec="minutes"), "ends_at": "9:00 PM", "sample": True}
    if not svc:
        nxt = church.next_service(now)
        return {"in_service": False, "next": nxt, "demo": load().demo}
    lists = checklists.all_lists({"user": "the monitor", "role": "admin"}, now)["lists"]
    mine = [{"dept": l["dept"], "done": l["done"], "total": len(l["items"]), "left": [i["text"] for i in l["items"] if not i["done"]][:6]}
            for l in lists if svc["name"] in (l.get("services") or []) or svc.get("special")]
    sp = speedtest.summary()
    return {"in_service": True, "service": svc, "stream": live_status(), "internet": sp.get("last"),
            "checklists": mine, "run_sheet": run_sheet(svc["name"], now.date().isoformat()), "demo": load().demo}


# The preview has no service on most days; its Service mode button shows one anyway.
_demo_force = {"on": False}


def demo_force(on: bool) -> dict:
    _demo_force["on"] = bool(on) and load().demo
    return {"ok": True, "on": _demo_force["on"]}


DEMO_SHEET = """# Glory Night run sheet (sample)

- 6:00 PM  Call time: media, worship, sound
- 6:45 PM  Doors; pre-service loop on the screens
- 7:00 PM  Welcome and worship
- 7:35 PM  Offering
- 7:45 PM  The message
- 8:45 PM  Altar and close
- After    Stop the recording; end the stream; the automator runs at 2:05
"""

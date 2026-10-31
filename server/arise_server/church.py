"""The church itself: name, service times, the verse of the day, the Sunday
checklist, and the public signage feed. Config: [church] in arise.toml.

Nothing here invents a sermon, a speaker or a verse text: the verse list is
fixed references, and the text comes from bible.lookup (public-domain KJV
sample offline, bible-api.com online).
"""
from __future__ import annotations

import json
import re
import os
from datetime import datetime, timedelta

from . import bible
from .config import load

DEFAULT_SERVICES = [
    {"name": "Sunday Service", "day": "Sunday", "time": "10:30", "site": "Pineville"},
    {"name": "Sunday Service", "day": "Sunday", "time": "10:00", "site": "Alexandria"},
    {"name": "Glory Night", "day": "Monday", "time": "19:00", "site": "Pineville"},
]
DEFAULT_CHECKLIST = [
    "Streaming Mac on, StreamYard signed in, OBS virtual camera running",
    "NDI cameras answering in StreamYard; lower thirds from Proclaim showing",
    "Proclaim slides updated; graphics share synced to the media Mac",
    "YouTube live page scheduled with tonight's title (the automator writes the description)",
    "Owncast backup stream key in StreamYard's second destination (if used)",
    "Sound check done; Icecast feed up if the nursery or translation needs it",
    "Recording to the recordings share started",
    "After service: stop the recording, end the YouTube stream, leave the automator to run at 02:05",
]
VERSES = ["John 3:16", "Psalm 23:1", "Romans 8:28", "Isaiah 40:31", "Philippians 4:6", "Exodus 19:5", "Psalm 46:1",
          "Proverbs 3:5", "Matthew 11:28", "Joshua 1:9", "Jeremiah 29:11", "Psalm 119:105", "2 Timothy 1:7", "Romans 12:2",
          "Isaiah 41:10", "Hebrews 11:1", "1 Peter 5:7", "Psalm 27:1", "Galatians 5:22", "John 14:6", "Matthew 6:33",
          "Psalm 34:8", "Ephesians 2:8", "James 1:5", "Romans 5:8", "Psalm 100:4", "Isaiah 26:3", "1 Corinthians 13:4",
          "Philippians 4:13", "Lamentations 3:22", "Micah 6:8"]
# Round 7, 90: the team's call time for each service; the checklists open then.
DEFAULT_CALL_TIMES = {"Sunday Service": "09:00", "Glory Night": "18:00"}
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def info() -> dict:
    cfg = load()
    raw = cfg.raw.get("church") if isinstance(cfg.raw, dict) else None
    raw = raw or {}
    services = raw.get("services") or DEFAULT_SERVICES
    calls = dict(DEFAULT_CALL_TIMES)
    calls.update({str(k): str(v) for k, v in (raw.get("call_times") or {}).items()})
    return {"name": raw.get("name", "Arise Church"), "city": raw.get("city", "Pineville, LA"),
            "tagline": raw.get("tagline", ""), "services": services, "call_times": calls,
            "checklist": raw.get("sunday_checklist") or DEFAULT_CHECKLIST}


def call_time(name: str) -> str | None:
    """When the team is called for a service (round 7, 90): its checklists open then. HH:MM or None."""
    t = info()["call_times"].get(name)
    return t if t and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t) else None


def next_service(now: datetime | None = None, services: list | None = None) -> dict | None:
    """The next service from now, with how long until it (pure, for the tests)."""
    now = now or datetime.now()
    best = None
    for s in services if services is not None else info()["services"]:
        try:
            day = DAYS.index(s["day"])
            hh, mm = [int(x) for x in str(s["time"]).split(":")[:2]]
        except (ValueError, KeyError):
            continue
        delta_days = (day - now.weekday()) % 7
        when = (now + timedelta(days=delta_days)).replace(hour=hh, minute=mm, second=0, microsecond=0)
        if when < now:
            when += timedelta(days=7)
        if best is None or when < best["when"]:
            best = {"when": when, **s}
    if not best:
        return None
    mins = int((best["when"] - now).total_seconds() // 60)
    return {"name": best["name"], "site": best["site"], "day": best["day"], "time": best["time"],
            "at": best["when"].isoformat(timespec="minutes"), "in_minutes": mins,
            "in_words": (f"{mins // 1440} days" if mins >= 2880 else f"{mins // 60} h {mins % 60} min" if mins >= 60 else f"{mins} min")}


def in_service_now(now: datetime | None = None, services: list | None = None, hours: float = 2.0, events: list | None = None) -> dict | None:
    """The service happening right now, if any: from its start until two hours after.
    Pure, for the tests. Power actions and the domain restart are refused while this is set.
    Round 7, 93 and 94: every configured service counts (Alexandria's 10:00 too), and so does
    a Calendar event marked "counts as a service" (Easter, The Outpour), for its own length."""
    now = now or datetime.now()
    for s in services if services is not None else info()["services"]:
        try:
            day = DAYS.index(s["day"])
            hh, mm = [int(x) for x in str(s["time"]).split(":")[:2]]
        except (ValueError, KeyError):
            continue
        if day != now.weekday():
            continue
        start = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        end = start + timedelta(hours=hours)
        if start <= now < end:
            return {"name": s["name"], "site": s.get("site", ""), "started": start.isoformat(timespec="minutes"), "ends": end.isoformat(timespec="minutes"),
                    "ends_at": end.strftime("%-I:%M %p")}
    if events is None and services is None:
        try:
            from . import calendar as _cal
            events = [e for e in _cal.events() if e.get("is_service")]
        except Exception:  # noqa: BLE001 - the calendar must never break the guard
            events = []
    for e in events or []:
        try:
            start = datetime.fromisoformat(e["start"])
            end = datetime.fromisoformat(e["end"]) if e.get("end") else start + timedelta(hours=hours)
        except (KeyError, TypeError, ValueError):
            continue
        end = max(end, start + timedelta(minutes=30))
        if start <= now < end:
            return {"name": e.get("title", "a special service"), "site": e.get("where", ""), "started": start.isoformat(timespec="minutes"),
                    "ends": end.isoformat(timespec="minutes"), "ends_at": end.strftime("%-I:%M %p"), "special": True}
    return None


# Round 7, 91: what a service holds back. One answer for every caller (Software Update, the
# Mac helper, restarts, the Nextcloud sweep, the speed test, the lyrics inbox): hold(kind).
HOLD_KINDS = {"update": "updates", "restart": "restarts", "mac": "changes to the church Macs", "sync": "heavy syncing",
              "heavy": "heavy work (speed tests, big copies)"}


def hold(kind: str, now: datetime | None = None, **kw) -> dict | None:
    """None when the work may go ahead; otherwise {service, kind, why}. Unknown kinds are held too."""
    svc = in_service_now(now, **kw)
    if not svc:
        return None
    what = HOLD_KINDS.get(kind, "that")
    return {"service": svc, "kind": kind, "why": f"{svc['name']} is on until {svc.get('ends_at', 'it ends')}: {what} wait until after"}


def verse_of_day(now: datetime | None = None) -> dict:
    now = now or datetime.now()
    pool = VERSES
    if load().demo:  # offline: only the references the sample Bible carries
        pool = [v for v in VERSES if v.lower() in bible.SAMPLE] or VERSES
    ref = pool[now.timetuple().tm_yday % len(pool)]
    try:
        r = bible.lookup(ref, "kjv")
        text = " ".join((v.get("text", "") if isinstance(v, dict) else v[1]) for v in (r.get("verses") or []))
        return {"ref": r.get("reference", ref), "text": " ".join(text.split()), "translation": r.get("translation_name") or "King James Version", "demo": bool(r.get("demo"))}
    except Exception:
        return {"ref": ref, "text": "", "translation": "King James Version"}


# ---- the Sunday checklist --------------------------------------------------
def _sunday_key(now: datetime | None = None) -> str:
    now = now or datetime.now()
    ahead = (6 - now.weekday()) % 7
    return (now + timedelta(days=ahead)).date().isoformat()


def _path() -> str:
    return str(load().state_dir / "sunday.json")


_DEMO_STATE: dict = {}


def checklist(now: datetime | None = None) -> dict:
    cfg = load()
    key = _sunday_key(now)
    items = info()["checklist"]
    state = _DEMO_STATE if cfg.demo else _read()
    done = state.get(key, {}) if state.get("_key") == key or cfg.demo else {}
    if cfg.demo and not _DEMO_STATE:
        done = {"0": {"by": "bradly.dyer", "at": "2026-10-25T09:40"}, "2": {"by": "media", "at": "2026-10-25T09:52"}}
    return {"sunday": key, "items": [{"i": i, "text": t, "done": str(i) in done, "by": done.get(str(i), {}).get("by", ""), "at": done.get(str(i), {}).get("at", "")} for i, t in enumerate(items)],
            "demo": cfg.demo}


def _read() -> dict:
    try:
        with open(_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def toggle(i: int, who: str, now: datetime | None = None) -> dict:
    cfg = load()
    key = _sunday_key(now)
    items = info()["checklist"]
    if not 0 <= i < len(items):
        return {"ok": False, "err": "no such item"}
    if cfg.demo:
        d = _DEMO_STATE.setdefault(key, {"0": {"by": "bradly.dyer", "at": "2026-10-25T09:40"}})
        _DEMO_STATE["_key"] = key
    else:
        state = _read()
        if state.get("_key") != key:  # a new Sunday: a clean sheet
            state = {"_key": key, key: {}}
        d = state.setdefault(key, {})
    if str(i) in d:
        del d[str(i)]
    else:
        d[str(i)] = {"by": who, "at": (now or datetime.now()).isoformat(timespec="minutes")}
    if not cfg.demo:
        os.makedirs(os.path.dirname(_path()), exist_ok=True)
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1)
    return {"ok": True, **checklist(now)}


# ---- the kiosk can open a real site on the monitor ---------------------------
ASSISTANTS = [
    {"id": "claude", "name": "Claude", "url": "https://claude.ai/new", "what": "Bradly's account. Also on this box as the `claude` command (Terminal)."},
    {"id": "chatgpt", "name": "ChatGPT", "url": "https://chatgpt.com/", "what": "Your normal account; nothing is stored here."},
    {"id": "grok", "name": "Grok", "url": "https://grok.com/", "what": "Your normal account; nothing is stored here."},
    {"id": "studio", "name": "YouTube Studio", "url": "https://studio.youtube.com/", "what": "The channel, signed in as the church."},
    {"id": "streamyard", "name": "StreamYard", "url": "https://streamyard.com/", "what": "The stream's control room."},
]
OPEN_HOSTS = {"claude.ai", "chatgpt.com", "chat.openai.com", "grok.com", "x.com", "studio.youtube.com", "www.youtube.com", "youtube.com",
              "streamyard.com", "www.streamyard.com", "arisecenla.church", "www.arisecenla.church", "github.com", "login.tailscale.com"}


def allowed_url(url: str) -> bool:
    from urllib.parse import urlparse
    try:
        u = urlparse(url)
    except ValueError:
        return False
    return u.scheme == "https" and u.hostname in OPEN_HOSTS


def open_on_kiosk(url: str) -> dict:
    """The fallback for the Epiphany browser: open a site in its own window on the
    closet monitor, on top of the desktop. The desktop now opens sites itself, as
    Firefox tabs (docs/BROWSER.md); this route is only for a monitor still running
    Epiphany. It starts a second Epiphany in application mode with its own profile,
    run as the kiosk user on cage's Wayland display. Closing that window returns to
    the desktop."""
    import subprocess
    if not allowed_url(url):
        return {"ok": False, "err": "that site is not on the list the monitor may open"}
    cfg = load()
    if cfg.demo:
        return {"ok": True, "demo": True, "out": f"(sample) would open {url} on the monitor"}
    runtime = "/run/user/1501"
    if not os.path.isdir(runtime):
        return {"ok": False, "err": "the kiosk is not running on this box (no /run/user/1501)"}
    display = next((f for f in os.listdir(runtime) if f.startswith("wayland-") and not f.endswith(".lock")), "wayland-0")
    from urllib.parse import urlparse
    profile = f"/var/lib/arise/kiosk-{urlparse(url).hostname.replace('.', '-')}"
    cmd = ["sudo", "-u", "arise-kiosk", "env", f"XDG_RUNTIME_DIR={runtime}", f"WAYLAND_DISPLAY={display}", "GDK_BACKEND=wayland",
           "epiphany", "--application-mode", f"--profile={profile}", url]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        return {"ok": False, "err": str(e)}
    return {"ok": True, "opened": url}


def signage() -> dict:
    """What a lobby screen shows, with no login: service times, the next one, the verse, the latest sermon titles."""
    from . import sermons
    i = info()
    try:
        vids = [{"title": v["title"], "date": v.get("published", v.get("date", "")), "thumb": v.get("thumbnail", ""), "kind": v.get("kind", "")} for v in sermons.videos(6).get("videos", [])]
    except Exception:
        vids = []
    return {"name": i["name"], "city": i["city"], "tagline": i["tagline"], "services": i["services"], "next": next_service(), "verse": verse_of_day(), "latest": vids,
            "now": datetime.now().isoformat(timespec="minutes")}


def claude_users(cfg=None) -> set[str]:
    """Who may open Claude on the box: Bradly (round 4, 44), as the dashboard's admin user, his
    domain account and his Linux account ([owner] user), plus anyone in [claude] users (empty by default)."""
    cfg = cfg or load()
    raw = cfg.raw.get("claude", {}) if isinstance(cfg.raw, dict) else {}
    owner = str((cfg.raw.get("owner") or {}).get("user", "") if isinstance(cfg.raw, dict) else "")
    return {cfg.web.admin_user, "bradly.dyer", *([owner] if owner else []), *[str(u) for u in (raw.get("users") or [])]}


def claude_desktop(action: str, who: str) -> dict:
    """Open, close or ask about Claude Desktop on the closet monitor (scripts/arise-claude-desktop).
    Opening is Bradly's only; closing is anyone's (the screen lock does it)."""
    import subprocess
    if action not in ("open", "close", "status"):
        return {"ok": False, "err": "action is open, close or status"}
    if action == "open" and who not in claude_users():
        return {"ok": False, "err": "Claude on this box is Bradly's (round 4, 44)"}
    cfg = load()
    if cfg.demo:
        return {"ok": True, "demo": True, "action": action, "state": "open" if action == "open" else "closed"}
    tool = "/usr/local/bin/arise-claude-desktop"
    if not os.path.exists(tool):
        return {"ok": False, "err": "Claude Desktop is not set up on this box: sudo bash /opt/arise/scripts/arise-claude-desktop-setup"}
    try:
        r = subprocess.run([tool, action], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "err": str(e)}
    out = (r.stdout or r.stderr).strip()
    return {"ok": r.returncode == 0, "action": action, "state": out if action == "status" else ("open" if action == "open" else "closed"),
            **({} if r.returncode == 0 else {"err": out or f"exit {r.returncode}"})}


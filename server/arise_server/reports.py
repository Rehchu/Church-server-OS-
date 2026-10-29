"""What the server tells people, on a clock (round 7): Discord's four channels, the all-green
an hour before each service, the Monday report, the pastors' monthly note (drafted here, sent
only when Bradly approves it), the plain-words line for a failed 02:05 run, and the nightly
copy of the channel's text and thumbnails.

Discord webhooks live in /etc/arise/secrets/discord.toml (alerts, sunday, weekly, daily;
docs/DISCORD.md). They are never sent to a page: status() says only which are set.
Nothing here reads YouTube's API: the channel's numbers come from files the automator already
keeps, and thumbnails from i.ytimg.com (public, no quota). Nothing here invents a number.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import load

DISCORD_FILE = "/etc/arise/secrets/discord.toml"
CHANNELS = ("alerts", "sunday", "weekly", "daily")
GREEN_LEAD_MIN = 60          # round 7, 78: an hour before each service
PARTNER_SUBS, PARTNER_HOURS = 1000, 4000


# ----- Discord ------------------------------------------------------------------------
def _discord() -> dict:
    try:
        import tomllib
        with open(DISCORD_FILE, "rb") as f:
            d = tomllib.load(f)
    except (OSError, ValueError, ImportError):
        return {}
    return {k: str(v) for k, v in d.items() if k in CHANNELS and isinstance(v, str) and v.startswith("https://")}


def status() -> dict:
    """Which channels are set: names only, never an address."""
    d = _discord()
    return {"channels": {c: c in d for c in CHANNELS}, "file": DISCORD_FILE, "demo": load().demo}


def _sent_path() -> Path:
    return Path(load().state_dir) / "discord-sent.json"


def _sent() -> dict:
    try:
        return json.loads(_sent_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def post(channel: str, text: str, key: str = "", sender=None) -> dict:
    """Post one plain line (or a few) to a channel, once per key. sender(url, text) for the tests."""
    if channel not in CHANNELS:
        return {"ok": False, "err": f"no such channel: {channel}"}
    sent = _sent()
    if key and key in sent:
        return {"ok": True, "duplicate": True}
    if load().demo:
        return {"ok": True, "demo": True, "channel": channel, "text": text}
    url = _discord().get(channel)
    if not url:
        return {"ok": False, "err": f"Discord #{channel} is not set ({DISCORD_FILE})"}
    if sender:
        r = sender(url, text)
    else:
        from .system import send_webhook
        r = send_webhook(text, url)
    if r.get("ok") and key:
        sent[key] = datetime.now().isoformat(timespec="minutes")
        # keep the last 500 keys; older ones can never repeat (they name a date)
        keep = dict(sorted(sent.items(), key=lambda kv: kv[1])[-500:])
        p = _sent_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(keep), encoding="utf-8")
    return r


# ----- the all-green, an hour before each service (round 7, 78 and 79) ------------------
def services_starting(now: datetime, lead_min: int = GREEN_LEAD_MIN, services: list | None = None, events: list | None = None) -> list[dict]:
    """Pure given its inputs: the services (and Calendar events that count as services) that
    start exactly lead_min minutes from now (to the minute)."""
    from . import church
    target = (now + timedelta(minutes=lead_min)).replace(second=0, microsecond=0)
    out = []
    for s in services if services is not None else church.info()["services"]:
        try:
            if church.DAYS.index(s["day"]) != target.weekday():
                continue
            hh, mm = [int(x) for x in str(s["time"]).split(":")[:2]]
        except (ValueError, KeyError):
            continue
        if (hh, mm) == (target.hour, target.minute):
            out.append({"name": s["name"], "site": s.get("site", ""), "start": target.isoformat(timespec="minutes")})
    if events is None:
        try:
            from . import calendar as _cal
            events = [e for e in _cal.events() if e.get("is_service")]
        except Exception:  # noqa: BLE001
            events = []
    for e in events:
        try:
            st = datetime.fromisoformat(e["start"]).replace(second=0, microsecond=0)
        except (KeyError, TypeError, ValueError):
            continue
        if st == target:
            out.append({"name": e.get("title", "A special service"), "site": e.get("where", ""), "start": st.isoformat(timespec="minutes"), "special": True})
    return out


def green_text(svc: dict, attention: list[dict], lists: list[dict] | None = None) -> str:
    """Pure: the post for one service. All green, or what still needs someone."""
    at = datetime.fromisoformat(svc["start"]).strftime("%-I:%M %p")
    where = f" ({svc['site']})" if svc.get("site") else ""
    head = f"{svc['name']}{where} at {at}"
    bad = [a for a in attention if a.get("level") == "bad"]
    warn = [a for a in attention if a.get("level") != "bad"]
    lines = []
    if not attention:
        lines.append(f"✅ All green for {head}: services up, backups ok, Synology mounted, nothing needs you.")
    else:
        lines.append(f"{'🔴' if bad else '🟡'} {head}: {len(attention)} thing(s) need you before it starts.")
        lines += [f"- {a['text']}" for a in (bad + warn)[:6]]
    for lst in lists or []:
        total = len(lst.get("items", []))
        if total:
            lines.append(f"{lst['dept']} checklist: {lst.get('done', 0)} of {total} done")
    return "\n".join(lines)


def tick_green(now: datetime | None = None, attention=None, sender=None) -> list[dict]:
    """Called each minute by the reminders loop. Posts once per service to #sunday."""
    now = now or datetime.now()
    due = services_starting(now)
    if not due:
        return []
    if attention is None:
        try:
            from .main import _attention_now
            attention = _attention_now()
        except Exception:  # noqa: BLE001
            attention = []
    try:
        from . import checklists
        lists = checklists.all_lists({"user": "the server", "role": "admin"}, now)["lists"]
    except Exception:  # noqa: BLE001
        lists = []
    out = []
    for svc in due:
        mine = [l for l in lists if svc["name"] in (l.get("services") or [])]
        out.append(post("sunday", green_text(svc, attention, mine), key=f"green:{svc['start']}:{svc['name']}:{svc.get('site', '')}", sender=sender))
    return out


# ----- the channel's numbers (round 7, 80 and 85) --------------------------------------------
STAT_FILES = ("cloud_workspace/_channel_stats.json", "cloud_workspace/_analytics.json", "channel_stats.json")


def channel_numbers(base: Path | None = None) -> dict:
    """Subscribers and public watch hours, only from a file the automator already keeps.
    No file, no number: "not available yet"."""
    if load().demo:
        return {"ok": True, "demo": True, "subscribers": 742, "watch_hours": 2913.0, "as_of": "2026-10-28", "source": "sample",
                **partner(742, 2913.0)}
    if base is None:
        base = Path(os.environ.get("ARISE_ARCHIVE_ROOT", "/srv/arise/archive")) / "arise-youtube-automation"
    for rel in STAT_FILES:
        p = base / rel
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        subs = _num(d, ("subscriberCount", "subscribers", "subs"))
        hours = _num(d, ("watch_hours", "watchHours", "public_watch_hours"))
        if hours is None:
            mins = _num(d, ("estimatedMinutesWatched", "watch_minutes"))
            hours = round(mins / 60, 1) if mins is not None else None
        if subs is None and hours is None:
            continue
        return {"ok": True, "subscribers": subs, "watch_hours": hours, "as_of": str(d.get("as_of") or d.get("date") or "")[:10],
                "source": rel, **partner(subs, hours)}
    return {"ok": False, "why": "not available yet: no channel numbers in the automator's files"}


def _num(d: dict, keys) -> float | None:
    for k in keys:
        v = d.get(k) if isinstance(d, dict) else None
        if v is None and isinstance(d, dict) and isinstance(d.get("statistics"), dict):
            v = d["statistics"].get(k)
        try:
            if v is not None:
                return float(v)
        except (TypeError, ValueError):
            continue
    return None


def partner(subs: float | None, hours: float | None) -> dict:
    """Pure: how far along the Partner Program bar (1,000 subscribers, 4,000 public watch hours)."""
    out = {}
    if subs is not None:
        out["subs_left"] = max(0, PARTNER_SUBS - int(subs))
        out["subs_pct"] = min(100, round(100 * subs / PARTNER_SUBS))
    if hours is not None:
        out["hours_left"] = max(0.0, round(PARTNER_HOURS - hours, 1))
        out["hours_pct"] = min(100, round(100 * hours / PARTNER_HOURS))
    return out


# ----- the Monday report (round 7, 80) -------------------------------------------------------
def weekly_facts(now: datetime | None = None) -> dict:
    """Everything the report says, gathered once. Each part says when it isn't available."""
    from . import audit, backups, storage
    now = now or datetime.now()
    since = (now - timedelta(days=7)).isoformat(timespec="seconds")
    f: dict = {"week_ending": now.date().isoformat()}
    try:
        rows = [r for r in backups.history(limit=200)["rows"] if str(r.get("started", "")) >= since]
        f["backups"] = {"runs": len(rows), "failed": [r.get("name") or r.get("job") for r in rows if not r.get("ok")]}
    except Exception as e:  # noqa: BLE001
        f["backups"] = {"error": str(e)[:120]}
    try:
        f["storage"] = [{"mount": d.get("mount"), "pct": round(d["pct"]) if d.get("pct") is not None else None} for d in (storage.status().get("mounts") or [])][:6]
    except Exception:  # noqa: BLE001
        f["storage"] = []
    try:
        from . import macs
        ms = macs.listing().get("macs", [])
        f["macs"] = {"count": len(ms), "offline": [m["name"] for m in ms if not m.get("online")], "failed_tasks": sum(int(m.get("failed") or 0) for m in ms)}
    except Exception:  # noqa: BLE001
        f["macs"] = {}
    try:
        ev = audit.recent(q="auth.login", limit=2000).get("events", [])
        ev = [e for e in ev if str(e.get("at", e.get("when", ""))) >= since]
        f["signins"] = {"ok": sum(1 for e in ev if e.get("ok", True)), "failed": sum(1 for e in ev if e.get("ok") is False),
                        "people": len({e.get("who") for e in ev if e.get("ok", True)})}
    except Exception:  # noqa: BLE001
        f["signins"] = {}
    try:
        from . import updates
        q = updates.status()
        f["updates"] = {"waiting": len(q.get("security") or []) + len(q.get("other") or [])}
    except Exception:  # noqa: BLE001
        f["updates"] = {}
    f["channel"] = channel_numbers()
    return f


def weekly_text(f: dict) -> str:
    """Pure: the Monday report from its facts."""
    lines = [f"📋 Arise Server, the week to {f['week_ending']}"]
    b = f.get("backups") or {}
    if "error" in b:
        lines.append(f"Backups: could not read the history ({b['error']})")
    else:
        lines.append(f"Backups: {b.get('runs', 0)} runs" + (f", failed: {', '.join(map(str, b['failed'][:5]))}" if b.get("failed") else ", all ok"))
    st = [d for d in f.get("storage") or [] if d.get("pct") is not None]
    if st:
        lines.append("Storage: " + ", ".join(f"{d['mount']} {d['pct']}%" for d in st))
    m = f.get("macs") or {}
    if m:
        lines.append(f"Macs: {m.get('count', 0)} church Macs" + (f"; not seen lately: {', '.join(m['offline'][:6])}" if m.get("offline") else "; all checking in")
                     + (f"; {m['failed_tasks']} task(s) failed" if m.get("failed_tasks") else ""))
    s = f.get("signins") or {}
    if s:
        lines.append(f"Sign-ins: {s.get('ok', 0)} by {s.get('people', 0)} people" + (f", {s['failed']} wrong passwords" if s.get("failed") else ""))
    u = f.get("updates") or {}
    if u:
        lines.append(f"Updates waiting for a click: {u.get('waiting', 0)}")
    c = f.get("channel") or {}
    if c.get("ok"):
        parts = []
        if c.get("subscribers") is not None:
            parts.append(f"{int(c['subscribers']):,} subscribers ({c.get('subs_left', 0):,} to go)")
        if c.get("watch_hours") is not None:
            parts.append(f"{c['watch_hours']:,.0f} public watch hours ({c.get('hours_left', 0):,.0f} to go)")
        lines.append("Channel: " + "; ".join(parts) + (f", as of {c['as_of']}" if c.get("as_of") else "") + ". Partner Program: 1,000 and 4,000.")
    else:
        lines.append("Channel: numbers not available yet.")
    return "\n".join(lines)


def send_weekly(now: datetime | None = None, sender=None) -> dict:
    now = now or datetime.now()
    text = weekly_text(weekly_facts(now))
    if now.day <= 7:
        text += f"\nThe pastors' note for {(now.replace(day=1) - timedelta(days=1)):%B} is ready to look over (Settings → Notifications)."
    r = post("weekly", text, key=f"weekly:{now.date().isoformat()}", sender=sender)
    return {**r, "text": text}


# ----- the pastors' monthly note (round 7, 81 and 144) ----------------------------------------
# Five plain lines from the month's own facts. The server drafts; Bradly reads, edits and
# presses Send. Nothing goes to the pastors unapproved.
def _notes_path() -> Path:
    return Path(load().state_dir) / "pastor-notes.json"


def _notes() -> dict:
    if load().demo:
        from . import demo_state
        return demo_state.get("reports.pastors", lambda: {})
    try:
        return json.loads(_notes_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_notes(d: dict) -> None:
    if load().demo:
        from . import demo_state
        demo_state.put("reports.pastors", d)
        return
    p = _notes_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1), encoding="utf-8")
    os.chmod(p, 0o600)


def month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def last_month(today: date | None = None) -> str:
    today = today or date.today()
    return month_key(today.replace(day=1) - timedelta(days=1))


def month_facts(key: str) -> dict:
    """What happened in one month, from the server's own records."""
    from . import audit, backups
    y, m = [int(x) for x in key.split("-")]
    start = date(y, m, 1)
    end = date(y + (m == 12), m % 12 + 1, 1)
    s, e = start.isoformat(), end.isoformat()
    if load().demo:
        return {"month": key, "services": 9, "backups": 31, "backups_failed": 0, "accounts_made": 2, "macs": 3, "videos": 14, "demo": True}
    f = {"month": key}
    try:
        rows = backups.history(limit=1000)["rows"]
        rows = [r for r in rows if s <= str(r.get("started", ""))[:10] < e]
        f["backups"], f["backups_failed"] = len(rows), sum(1 for r in rows if not r.get("ok"))
    except Exception:  # noqa: BLE001
        pass
    try:
        ev = audit.recent(q="directory.user", limit=2000).get("events", [])
        f["accounts_made"] = sum(1 for x in ev if s <= str(x.get("at", ""))[:10] < e and "create" in str(x.get("action", "")))
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import macs
        f["macs"] = len(macs.listing().get("macs", []))
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import church, calendar as _cal
        f["services"] = sum(1 for _ in _cal.service_occurrences(start, end - timedelta(days=1)))
    except Exception:  # noqa: BLE001
        pass
    return f


def draft_text(f: dict) -> str:
    """Pure: five plain lines for the pastors. Facts only; no names, no files."""
    when = datetime.strptime(f["month"], "%Y-%m").strftime("%B %Y")
    lines = [f"The church server in {when}, in five lines:"]
    if f.get("services") is not None:
        lines.append(f"1. It stayed out of the way of {f['services']} services: no updates or restarts while they ran.")
    if f.get("backups") is not None:
        lines.append(f"2. It backed up the church's files {f['backups']} times" + (f"; {f['backups_failed']} needed a second try." if f.get("backups_failed") else ", every one complete."))
    if f.get("accounts_made") is not None:
        lines.append(f"3. {f['accounts_made']} new account(s) were made for staff.")
    if f.get("macs") is not None:
        lines.append(f"4. {f['macs']} church Mac(s) are looked after by it, with everyone's Desktop and Documents kept on the server.")
    lines.append("5. Nothing is reachable from the internet; it all stays inside the church and Tailscale.")
    return "\n".join(lines[:6])


def pastors(key: str | None = None) -> dict:
    key = key or last_month()
    if not re.fullmatch(r"\d{4}-\d{2}", key):
        return {"ok": False, "err": "month is YYYY-MM"}
    d = _notes()
    rec = d.get(key) or {}
    to = [str(u) for u in (load().storage.pastors or [])]
    return {"ok": True, "month": key, "draft": rec.get("text") or draft_text(month_facts(key)), "edited": bool(rec.get("text")),
            "sent": rec.get("sent"), "sent_by": rec.get("by"), "to": to, "demo": load().demo}


def pastors_save(key: str, text: str, who: str) -> dict:
    if not re.fullmatch(r"\d{4}-\d{2}", key or ""):
        return {"ok": False, "err": "month is YYYY-MM"}
    text = (text or "").strip()[:2000]
    if not text:
        return {"ok": False, "err": "the note is empty"}
    d = _notes()
    d.setdefault(key, {}).update({"text": text, "edited_by": who, "edited": datetime.now().isoformat(timespec="minutes")})
    _save_notes(d)
    return {"ok": True, **pastors(key)}


def pastors_send(key: str, text: str, who: str) -> dict:
    """Bradly's Send: the note as he left it, to the two pastors' personal email."""
    from . import audit, mail
    r = pastors_save(key, text, who)
    if not r.get("ok"):
        return r
    d = _notes()
    if d.get(key, {}).get("sent"):
        return {"ok": False, "err": f"the note for {key} was already sent {d[key]['sent']}"}
    to = r["to"]
    sent, missing = [], []
    for u in to:
        from . import notify
        addr = notify.personal_email(u)
        if not addr:
            missing.append(u)
            continue
        if load().demo:
            sent.append(u)
            continue
        res = mail.send_one(addr, f"The church server in {datetime.strptime(key, '%Y-%m'):%B}", d[key]["text"] + "\n")
        (sent if res.get("ok") else missing).append(u)
    if sent:
        d[key].update({"sent": datetime.now().isoformat(timespec="minutes"), "by": who, "to": sent})
        _save_notes(d)
    audit.record(who, "reports.pastors.send", key, ok=bool(sent), detail=f"to {', '.join(sent) or 'nobody'}" + (f"; no email for {', '.join(missing)}" if missing else ""))
    return {"ok": bool(sent), "sent_to": sent, "no_email": missing, "demo": load().demo,
            **({} if sent else {"err": "no pastor has a personal email on file (Directory → the profile)"})}


# ----- the morning note: a failed 02:05 run in plain words (round 7, 145) ---------------------
FAIL_RE = re.compile(r"(?i)\b(fail(?:ed|ure)?|error|quotaExceeded|refused|could not|traceback)\b")


def explain_failure(report: str, limit: int = 4) -> list[str]:
    """Pure: the report's own failed lines, under the job each belongs to, said plainly.
    Only what the report says; no guesses about why."""
    out, job = [], None
    for raw in (report or "").splitlines():
        line = raw.strip()
        m = re.match(r"^#+\s*Job:\s*(.+?)\s*(\(.*\))?$", line)
        if m:
            job = m.group(1)
            continue
        if not line or line.startswith("#") or "jobs done" in line or not FAIL_RE.search(line):
            continue   # the summary line is already in the note; the job lines say which
        if re.search(r"(?i)\b0 failed\b", line) and not re.search(r"(?i)\b[1-9]\d* failed\b", line):
            continue
        text = re.sub(r"^[-*]\s*", "", line)
        if "quotaexceeded" in text.lower():
            text += " (YouTube's daily quota ran out; it resets at 2:00 AM Central)"
        out.append(f"{job}: {text}" if job else text)
        if len(out) >= limit:
            break
    return out


# ----- the nightly copy of the channel's text and thumbnails (round 7, 62) --------------------
THUMB_URL = "https://i.ytimg.com/vi/{id}/hqdefault.jpg"
THUMBS_PER_NIGHT = 300


def copy_dir() -> Path:
    return Path(load().system.data_root) / "channel-copy"


def channel_copy(today: date | None = None, fetch=None, base: Path | None = None) -> dict:
    """Copy the automator's channel snapshots (titles, descriptions) into a dated folder, and
    fetch the thumbnail of every video that has none yet. Never deletes; never the API."""
    from . import church
    from arise_archive import catalogue
    today = today or date.today()
    if load().demo:
        return {"ok": True, "demo": True, "files": 4, "thumbs": 0}
    h = church.hold("heavy")
    if h:
        return {"ok": False, "held": True, "err": h["why"]}
    if base is None:
        base = Path(os.environ.get("ARISE_ARCHIVE_ROOT", "/srv/arise/archive")) / catalogue.AUTOMATION
    dest = copy_dir() / today.isoformat()
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for rel, _shape in catalogue.SOURCES:
        src = base / rel
        if src.is_file():
            shutil.copy2(src, dest / rel.replace("/", "__"))
            copied += 1
    if not copied:
        return {"ok": False, "err": f"no channel snapshots under {base} (is the archive set up? docs/ARCHIVE.md)"}
    try:
        from . import channel
        ids = set(catalogue.load(channel.acfg()).keys())
    except Exception:  # noqa: BLE001 - no catalogue: the text is copied, the thumbnails wait
        ids = set()
    thumbs = copy_dir() / "thumbnails"
    thumbs.mkdir(exist_ok=True)
    fetch = fetch or _get
    got, failed = 0, 0
    for vid in sorted(ids):
        if got + failed >= THUMBS_PER_NIGHT:
            break
        f = thumbs / f"{vid}.jpg"
        if f.exists():
            continue
        try:
            data = fetch(THUMB_URL.format(id=vid))
        except Exception:  # noqa: BLE001 - not a real video id, or offline: try again tomorrow
            failed += 1
            continue
        if data and data[:3] == b"\xff\xd8\xff":
            f.write_bytes(data)
            got += 1
        else:
            failed += 1
    return {"ok": True, "folder": str(dest), "files": copied, "thumbs": got, "thumbs_failed": failed}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ariseOS/channel-copy"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read(3_000_000)

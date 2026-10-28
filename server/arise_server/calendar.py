"""The church calendar: services from [church] in arise.toml (generated, never
stored) plus the events staff add, kept in /var/lib/arise/calendar.json. One
ICS feed with no login so every Mac and phone can subscribe (round 3, 10).

Nothing here invents an event: the sample events in demo mode say "sample"
in their titles.
"""
from __future__ import annotations

import os
import secrets
from datetime import date, datetime, timedelta

from . import church
from .config import load
from .util import read_json, write_json

DAYS = church.DAYS
TZ = "America/Chicago"


def _path():
    return load().state_dir / "calendar.json"


def _demo_events(now: datetime | None = None) -> list[dict]:
    """Sample events pinned to the week the preview is looked at, so the month view is never empty."""
    now = now or datetime.now()
    wed = now + timedelta(days=(2 - now.weekday()) % 7 or 7)
    sat = now + timedelta(days=(5 - now.weekday()) % 7 or 7)
    nxt = now + timedelta(days=10)
    mk = lambda d, h, m: d.replace(hour=h, minute=m, second=0, microsecond=0).isoformat(timespec="minutes")
    return [
        {"id": "demo1", "title": "Media team meeting (sample)", "start": mk(wed, 18, 30), "end": mk(wed, 19, 30), "where": "Pineville, the booth", "note": "A sample event. Real ones come from the Calendar app.", "who": "bradly", "added": "2026-10-20T09:00"},
        {"id": "demo2", "title": "Building walk-through (sample)", "start": mk(sat, 9, 0), "end": mk(sat, 10, 0), "where": "Pineville", "note": "", "who": "office", "added": "2026-10-21T14:10"},
        {"id": "demo3", "title": "Volunteer lunch (sample)", "start": mk(nxt, 12, 0), "end": mk(nxt, 13, 30), "where": "The fellowship hall", "note": "", "who": "bradly", "added": "2026-10-22T08:45"},
    ]


_DEMO: dict = {}


def _read() -> list[dict]:
    cfg = load()
    if cfg.demo:
        if "events" not in _DEMO:
            _DEMO["events"] = _demo_events()
        return _DEMO["events"]
    d = read_json(_path(), default={}) or {}
    return list(d.get("events") or [])


def _write(events: list[dict]) -> None:
    if load().demo:
        _DEMO["events"] = events
        return
    write_json(_path(), {"events": events})


def _clean(body: dict) -> dict | None:
    title = str(body.get("title", "")).strip()[:120]
    start = str(body.get("start", "")).strip()[:16]
    if not title or not _parse(start):
        return None
    end = str(body.get("end", "") or "").strip()[:16]
    if end and (not _parse(end) or _parse(end) < _parse(start)):
        end = ""
    return {"title": title, "start": start, "end": end, "where": str(body.get("where", "") or "").strip()[:120],
            "note": str(body.get("note", "") or "").strip()[:1000]}


def _parse(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def events() -> list[dict]:
    return sorted(_read(), key=lambda e: e.get("start", ""))


def add(body: dict, who: str, now: datetime | None = None) -> dict:
    c = _clean(body)
    if not c:
        return {"ok": False, "err": "a title and a start time are needed"}
    ev = {"id": secrets.token_hex(4), **c, "who": who, "added": (now or datetime.now()).isoformat(timespec="minutes")}
    evs = _read() + [ev]
    _write(evs)
    return {"ok": True, "event": ev, "demo": load().demo}


def update(ev_id: str, body: dict, who: str) -> dict:
    c = _clean(body)
    if not c:
        return {"ok": False, "err": "a title and a start time are needed"}
    evs = _read()
    for e in evs:
        if e.get("id") == ev_id:
            e.update(c)
            e["edited_by"] = who
            _write(evs)
            return {"ok": True, "event": e, "demo": load().demo}
    return {"ok": False, "err": "no such event"}


def remove(ev_id: str) -> dict:
    evs = _read()
    keep = [e for e in evs if e.get("id") != ev_id]
    if len(keep) == len(evs):
        return {"ok": False, "err": "no such event"}
    _write(keep)
    return {"ok": True, "demo": load().demo}


# ---- occurrences: the services, generated ------------------------------------
def service_occurrences(start: date, end: date, services: list | None = None) -> list[dict]:
    """Every service between two dates (inclusive), from the configured list. Pure."""
    out = []
    services = services if services is not None else church.info()["services"]
    d = start
    while d <= end:
        for s in services:
            try:
                if DAYS.index(s["day"]) != d.weekday():
                    continue
                hh, mm = [int(x) for x in str(s["time"]).split(":")[:2]]
            except (ValueError, KeyError):
                continue
            when = datetime(d.year, d.month, d.day, hh, mm)
            out.append({"id": f"svc-{s['day']}-{s['time']}-{d.isoformat()}", "title": s["name"], "start": when.isoformat(timespec="minutes"),
                        "end": (when + timedelta(hours=2)).isoformat(timespec="minutes"), "where": s.get("site", ""), "service": True})
        d += timedelta(days=1)
    return out


def month(year: int, mon: int) -> dict:
    """Everything shown in one month: the services and the events, by day."""
    first = date(year, mon, 1)
    last = (date(year + (mon == 12), (mon % 12) + 1, 1) - timedelta(days=1))
    items = service_occurrences(first, last)
    for e in events():
        d = _parse(e["start"])
        if d and first <= d.date() <= last:
            items.append({**e, "service": False})
    items.sort(key=lambda x: x["start"])
    return {"year": year, "month": mon, "items": items, "demo": load().demo}


def upcoming(days: int = 7, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now()
    end = now + timedelta(days=days)
    items = [s for s in service_occurrences(now.date(), end.date()) if _parse(s["start"]) >= now]
    for e in events():
        d = _parse(e["start"])
        if d and now <= d <= end:
            items.append({**e, "service": False})
    items.sort(key=lambda x: x["start"])
    return items


# ---- the ICS feed -------------------------------------------------------------
_VTIMEZONE = """BEGIN:VTIMEZONE
TZID:America/Chicago
X-LIC-LOCATION:America/Chicago
BEGIN:DAYLIGHT
TZOFFSETFROM:-0600
TZOFFSETTO:-0500
TZNAME:CDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0500
TZOFFSETTO:-0600
TZNAME:CST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE"""

_BYDAY = {"Monday": "MO", "Tuesday": "TU", "Wednesday": "WE", "Thursday": "TH", "Friday": "FR", "Saturday": "SA", "Sunday": "SU"}


def _ics_text(s: str) -> str:
    return str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_dt(iso: str) -> str:
    d = _parse(iso)
    return d.strftime("%Y%m%dT%H%M%S") if d else ""


def _fold(line: str) -> str:
    """RFC 5545: lines longer than 75 octets are folded with CRLF + a space."""
    out, b = [], line.encode("utf-8")
    while len(b) > 75:
        cut = 75
        while cut > 0 and (b[cut] & 0xC0) == 0x80:  # never split a UTF-8 sequence
            cut -= 1
        out.append(b[:cut].decode("utf-8"))
        b = b" " + b[cut:]
    out.append(b.decode("utf-8"))
    return "\r\n".join(out)


def ics(host: str = "arise-server", services: list | None = None, evs: list | None = None, anchor: date | None = None) -> str:
    """The whole calendar as text/calendar: each service a weekly RRULE, each event a VEVENT. Pure given its inputs."""
    info = church.info()
    services = services if services is not None else info["services"]
    evs = evs if evs is not None else events()
    anchor = anchor or date(2026, 1, 4)  # a Sunday; the RRULE's first instance is the first matching day on or after it
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//ariseOS//{_ics_text(info['name'])}//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{_ics_text(info['name'])}", f"X-WR-TIMEZONE:{TZ}", "X-PUBLISHED-TTL:PT1H", "REFRESH-INTERVAL;VALUE=DURATION:PT1H"]
    lines += _VTIMEZONE.split("\n")
    from datetime import timezone as _tz
    stamp = datetime.now(_tz.utc).strftime("%Y%m%dT%H%M%SZ")
    for s in services:
        try:
            wd = DAYS.index(s["day"])
            hh, mm = [int(x) for x in str(s["time"]).split(":")[:2]]
        except (ValueError, KeyError):
            continue
        first = anchor + timedelta(days=(wd - anchor.weekday()) % 7)
        start = datetime(first.year, first.month, first.day, hh, mm)
        uid = f"service-{s['day'].lower()}-{str(s['time']).replace(':', '')}-{_ics_text(s.get('site', '')).lower().replace(' ', '-')}@{host}"
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}", f"DTSTART;TZID={TZ}:{start.strftime('%Y%m%dT%H%M%S')}",
                  f"DTEND;TZID={TZ}:{(start + timedelta(hours=2)).strftime('%Y%m%dT%H%M%S')}", f"RRULE:FREQ=WEEKLY;BYDAY={_BYDAY[s['day']]}",
                  f"SUMMARY:{_ics_text(s['name'])}", f"LOCATION:{_ics_text(s.get('site', ''))}", f"DESCRIPTION:{_ics_text(info['name'])} · every {s['day']} at {s['time']}", "END:VEVENT"]
    for e in evs:
        if not _ics_dt(e.get("start", "")):
            continue
        end = _ics_dt(e.get("end", "")) or (_parse(e["start"]) + timedelta(hours=1)).strftime("%Y%m%dT%H%M%S")
        lines += ["BEGIN:VEVENT", f"UID:{e.get('id', secrets.token_hex(4))}@{host}", f"DTSTAMP:{stamp}", f"DTSTART;TZID={TZ}:{_ics_dt(e['start'])}", f"DTEND;TZID={TZ}:{end}",
                  f"SUMMARY:{_ics_text(e.get('title', ''))}"]
        if e.get("where"):
            lines.append(f"LOCATION:{_ics_text(e['where'])}")
        if e.get("note"):
            lines.append(f"DESCRIPTION:{_ics_text(e['note'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


def subscribe_info(host: str) -> dict:
    """What the Subscribe button shows: the two addresses and how to use them."""
    return {"webcal": f"webcal://{host}/calendar.ics", "https": f"http://{host}/calendar.ics",
            "mac": "Calendar → File → New Calendar Subscription… → paste the address → Subscribe. Set Auto-refresh to every hour.",
            "iphone": "Settings → Calendar → Accounts → Add Account → Other → Add Subscribed Calendar → paste the address.",
            "note": "On the church network the address works as it is. Away from it, the phone needs Tailscale on first."}

"""Notifications for one person (round 5, 28): calendar reminders, a file shared
with them, internal mail, the Sunday checklist and their department checklists.

    notify.add(user, kind, text, link="")    the one call other modules make

Every notification lands in that person's feed (the notification centre, for
whoever uses the desktop). It is also delivered where staff actually are, since
they use their Macs and not the OS (Bradly, after round 5): push to a device the
person turned push on for, and, when [notify] email_staff is on and Resend is
set up, an email to their personal address. Nothing is sent during a service.

The reminders loop (start_reminders, run by the dashboard) is the only clock
here: calendar events 30 minutes ahead for the people in them, the Sunday
checklist at 9:30 for staff when items are left, and each department list's
own nudge time.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from datetime import datetime, timedelta

from .config import load

KINDS = {"calendar", "shared", "mail", "sunday", "checklist", "system"}
KEEP = 200
_lock = threading.RLock()


def _path() -> str:
    return str(load().state_dir / "notifications.json")


def _read() -> dict:
    if load().demo:
        from . import demo_state
        return demo_state.get("notify.feed", lambda: {u: [dict(x) for x in v] for u, v in DEMO_FEED.items()})
    try:
        with open(_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write(d: dict):
    if load().demo:
        return
    p = _path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(p + ".tmp", p)


def _cfg() -> dict:
    raw = load().raw
    return (raw.get("notify") if isinstance(raw, dict) else None) or {}


def add(user: str, kind: str, text: str, link: str = "", key: str = "", deliver: bool = True, now: datetime | None = None) -> dict:
    """Add one notification for `user`. `key` makes it idempotent: the same key is never added twice
    (a reminder loop that runs every minute must not repeat itself)."""
    if not user or kind not in KINDS or not (text or "").strip():
        return {"ok": False, "err": "user, a known kind and some text are needed"}
    now = now or datetime.now()
    with _lock:
        d = _read()
        rows = d.setdefault(user, [])
        if key and any(r.get("key") == key for r in rows):
            return {"ok": True, "duplicate": True}
        item = {"id": secrets.token_hex(5), "kind": kind, "text": text.strip()[:300], "link": (link or "")[:300],
                "at": now.isoformat(timespec="seconds"), "read": False, **({"key": key} if key else {})}
        rows.insert(0, item)
        del rows[KEEP:]
        _write(d)
    sent = _deliver(user, item) if deliver else {}
    return {"ok": True, "item": item, "delivered": sent}


def feed(user: str, limit: int = 50) -> dict:
    d = _read()
    if load().demo and user not in d:   # sample mode: everyone sees the sample feed
        d[user] = [dict(x) for x in DEMO_FEED["bradly"]]
    rows = d.get(user, [])
    return {"items": rows[:max(1, min(int(limit or 50), KEEP))], "unread": sum(1 for r in rows if not r.get("read"))}


def mark_read(user: str, ids: list[str] | None = None) -> dict:
    with _lock:
        d = _read()
        n = 0
        for r in d.get(user, []):
            if not r.get("read") and (ids is None or r["id"] in ids):
                r["read"] = True
                n += 1
        _write(d)
    return {"ok": True, "marked": n, **feed(user, 1)}


def _deliver(user: str, item: dict) -> dict:
    """Push to the person's own devices, and email when [notify] email_staff is on. Quiet during a service."""
    if load().demo:
        return {"demo": True}
    from . import church
    if church.in_service_now():
        return {"held": "during a service"}
    out = {}
    try:
        from . import push
        out["push"] = push.send_to([user], "ariseOS", item["text"], item.get("link") or "/", tag=f"n:{item['id']}", throttle_s=0)
    except Exception as e:  # noqa: BLE001 - a delivery never breaks the caller
        out["push"] = {"ok": False, "err": str(e)}
    if _cfg().get("email_staff"):
        addr = personal_email(user)
        if addr:
            try:
                from . import mail
                out["email"] = mail.send_note(addr, "ariseOS: " + item["text"][:70], item["text"] + (f"\n\n{item['link']}" if item.get("link") else ""))
            except Exception as e:  # noqa: BLE001
                out["email"] = {"ok": False, "err": str(e)}
    return out


def personal_email(user: str) -> str | None:
    """The profile's personal email (round 5, 9), when the directory has one."""
    # The profile holds it (profiles.py); directory never had a personal_email(), so this
    # used to return None for everyone and staff notices were never emailed.
    try:
        from . import profiles
        return (profiles._read().get((user or "").lower(), {}) or {}).get("personal_email") or None
    except Exception:  # noqa: BLE001
        return None


# ----- who is "in" what --------------------------------------------------------------
def members_of(entries: list[str]) -> set[str]:
    """['bradly', '@Media'] -> the users, groups expanded."""
    from . import directory
    out: set[str] = set()
    groups = None
    for e in entries or []:
        e = str(e).strip()
        if not e:
            continue
        if e.startswith("@"):
            if groups is None:
                try:
                    groups = {g["name"].lower(): g for g in directory.list_groups().get("groups", [])}
                except Exception:  # noqa: BLE001
                    groups = {}
            g = groups.get(e[1:].lower())
            out.update(g.get("members", []) if g else [])
        else:
            out.add(e)
    return out


def staff_users() -> set[str]:
    """Staff and admins: the people the Sunday checklist nudge goes to."""
    return members_of(["@Staff", "@Media", "@Domain Admins"])


# ----- the reminders (pure planner + a thread) ---------------------------------------
def due_reminders(now: datetime, events: list[dict], lead_min: int = 30) -> list[dict]:
    """Pure: the calendar events whose start is within the next `lead_min` minutes (and not past)."""
    out = []
    for e in events:
        try:
            st = datetime.fromisoformat(str(e.get("start", ""))[:16])
        except ValueError:
            continue
        if now <= st <= now + timedelta(minutes=lead_min) and e.get("people"):
            out.append(e)
    return out


def tick(now: datetime | None = None) -> dict:
    """One pass of the reminders. Safe to run every minute: every add() has a key."""
    now = now or datetime.now()
    from . import calendar as churchcal, church, checklists
    sent = 0
    try:   # round 7, 78 and 79: the all-green an hour before each service, to Discord #sunday
        from . import reports
        reports.tick_green(now)
    except Exception:  # noqa: BLE001 - a Discord hiccup never stops the reminders
        pass
    if church.in_service_now(now):
        return {"held": "during a service"}
    try:
        for e in due_reminders(now, churchcal.events()):
            for u in members_of(e["people"]):
                r = add(u, "calendar", f"{e['title']} at {datetime.fromisoformat(e['start'][:16]).strftime('%-I:%M %p')}" + (f" · {e['where']}" if e.get("where") else ""),
                        "/#calendar", key=f"cal:{e['id']}:{e['start']}", now=now)
                sent += 0 if r.get("duplicate") else 1
    except Exception:  # noqa: BLE001
        pass
    # The Sunday checklist at 9:30 on Sunday, to staff and admins, while items are left (round 4, 78; round 5, 28).
    if now.weekday() == 6 and (now.hour, now.minute) >= (9, 30) and now.hour < 10:
        cl = church.checklist(now)
        left = sum(1 for i in cl["items"] if not i["done"])
        if left:
            for u in staff_users():
                r = add(u, "sunday", f"Sunday checklist: {left} of {len(cl['items'])} left", "/#sunday", key=f"sunday:{cl['sunday']}", now=now)
                sent += 0 if r.get("duplicate") else 1
    for n in checklists.due_nudges(now):
        for u in n["to"]:
            r = add(u, "checklist", n["text"], "/checklist", key=n["key"], now=now)
            sent += 0 if r.get("duplicate") else 1
    return {"ok": True, "sent": sent}


def start_reminders(every_s: int = 60):
    def loop():
        time.sleep(30)
        while True:
            try:
                tick()
            except Exception:  # noqa: BLE001 - the loop never dies
                pass
            time.sleep(every_s)
    t = threading.Thread(target=loop, daemon=True, name="arise-notify")
    t.start()
    return t


DEMO_FEED = {
    "bradly": [
        {"id": "dn1", "kind": "checklist", "text": "Media checklist: 2 of 5 left before Sunday Service", "link": "/#sunday", "at": "2026-10-25T09:15:00", "read": False},
        {"id": "dn2", "kind": "shared", "text": "Kristina shared “Outpour graphics” with you (sample)", "link": "/#files", "at": "2026-10-24T16:02:00", "read": False},
        {"id": "dn3", "kind": "calendar", "text": "Media team meeting (sample) at 6:30 PM · the booth", "link": "/#calendar", "at": "2026-10-22T18:00:00", "read": True},
    ],
}

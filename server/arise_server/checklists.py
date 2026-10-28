"""Department checklists (round 5, 28 to 30): every department has its own list,
like the Sunday one.

- The departments are [church] departments in arise.toml (default: Media,
  Childrens-Department, Inedge, Worship), each a directory group.
- A leader per department (set by an admin) edits its items; admins edit any;
  the department's members tick. Until Bradly decides how staff reach it from
  their Macs, ticking from the dashboard is for admins (staff_access, round 5).
- Each list resets the night before each service it is for (Sunday Service and
  Glory Night by default): from 20:00 the evening before, or when the previous
  service ends if that is later. The finished round goes to its history.
- Each list has its own nudge time per service, on that service's day and
  always before it starts (nothing is scheduled during a service). Default:
  75 minutes before the earliest start (Sunday Service 08:45, Glory Night 17:45).

State: <state_dir>/checklists.json. Nothing here touches the Sunday checklist,
which stays in church.py.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timedelta

from .config import load

DEFAULT_DEPARTMENTS = ["Media", "Childrens-Department", "Inedge", "Worship"]
DEFAULT_SERVICES = ["Sunday Service", "Glory Night"]
SERVICE_HOURS = 2.0
RESET_HOUR = 20
HISTORY_KEEP = 60
_lock = threading.RLock()


def departments() -> list[str]:
    raw = load().raw
    c = (raw.get("church") if isinstance(raw, dict) else None) or {}
    return list(c.get("departments") or DEFAULT_DEPARTMENTS)


# ----- the cycle: which service a list is getting ready for (pure) -----------------
def occurrences(services: list[dict], names: list[str], start: datetime, days: int = 15, site: str | None = None) -> list[datetime]:
    """Every start of the named services from start-8 days to start+days, earliest per (date, name)."""
    from .church import DAYS
    out: dict = {}
    base = (start - timedelta(days=8)).replace(hour=0, minute=0, second=0, microsecond=0)
    for s in services:
        if s.get("name") not in names or (site and s.get("site") and s.get("site") != site):
            continue
        try:
            dow = DAYS.index(s["day"])
            hh, mm = [int(x) for x in str(s["time"]).split(":")[:2]]
        except (ValueError, KeyError):
            continue
        for k in range(days + 9):
            d = base + timedelta(days=k)
            if d.weekday() == dow:
                when = d.replace(hour=hh, minute=mm)
                key = (when.date(), s["name"])
                if key not in out or when < out[key][0]:
                    out[key] = (when, s["name"])
    return sorted(out.values())


def cycle(now: datetime, services: list[dict], names: list[str] | None = None, site: str | None = None) -> dict | None:
    """Pure: the round a list is on now. {key, service, at, resets_at, previous}.
    The next service S whose end is after now is the target, but only from the night
    before it (20:00 the day before, or when the previous service ended, whichever is
    later); until then the list stays on the previous round."""
    occ = occurrences(services, names or DEFAULT_SERVICES, now, site=site)
    if not occ:
        return None
    ends = [(w, n, w + timedelta(hours=SERVICE_HOURS)) for w, n in occ]
    nxt = next(((w, n, e) for w, n, e in ends if e > now), None)
    if not nxt:
        return None
    i = ends.index(nxt)
    prev = ends[i - 1] if i > 0 else None
    night_before = (nxt[0] - timedelta(days=1)).replace(hour=RESET_HOUR, minute=0)
    resets = max(night_before, prev[2]) if prev else night_before
    if now >= resets or prev is None:
        cur, before = nxt, prev
    else:
        cur, before = prev, (ends[i - 2] if i > 1 else None)
    key = lambda o: f"{o[0].date().isoformat()} {o[1]}"  # noqa: E731
    return {"key": key(cur), "service": cur[1], "at": cur[0].isoformat(timespec="minutes"),
            "moves_on": resets.isoformat(timespec="minutes"), "next": key(nxt), "previous": key(before) if before else None}


def valid_nudge(t: str) -> bool:
    return bool(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t or ""))


# ----- the store -----------------------------------------------------------------------
def _path() -> str:
    return str(load().state_dir / "checklists.json")


def _read() -> dict:
    if load().demo:
        from . import demo_state
        return demo_state.get("checklists", lambda: json.loads(json.dumps(DEMO_STATE)))
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


def _list(d: dict, dept: str) -> dict:
    lists = d.setdefault("lists", {})
    lst = lists.setdefault(dept, {"items": [], "leader": None, "nudge": {}, "services": list(DEFAULT_SERVICES), "ticks": {}, "history": []})
    if not isinstance(lst.get("nudge"), dict):
        lst["nudge"] = {}
    for name in lst["services"]:
        lst["nudge"].setdefault(name, default_nudge(name))
    return lst


def service_start(name: str) -> str | None:
    """The earliest start of a service by name (Sunday Service: Alexandria's 10:00 comes first)."""
    times = sorted(str(s.get("time", ""))[:5] for s in _services() if s.get("name") == name)
    return times[0] if times else None


def default_nudge(name: str) -> str:
    h, m = [int(x) for x in (service_start(name) or "10:30").split(":")]
    total = max(0, h * 60 + m - 75)
    return f"{total // 60:02d}:{total % 60:02d}"


def _roll(lst: dict, cur_key: str):
    """Move every round that is not the current one into history (newest first)."""
    for k in sorted([k for k in lst.get("ticks", {}) if k != cur_key], reverse=True):
        t = lst["ticks"].pop(k)
        lst.setdefault("history", []).insert(0, {"round": k, "done": len(t), "total": len(lst["items"]),
                                                 "by": sorted({v.get("by", "") for v in t.values()} - {""})})
    del lst.setdefault("history", [])[HISTORY_KEEP:]


def _services() -> list[dict]:
    from . import church
    return church.info()["services"]


def can_edit(who: dict, dept: str, lst: dict) -> bool:
    return who.get("role") == "admin" or (lst.get("leader") and lst["leader"] == who.get("user"))


def can_tick(who: dict, dept: str) -> bool:
    if who.get("role") == "admin":
        return True
    from . import directory
    try:
        return dept in directory.user_groups(who.get("user", ""))
    except Exception:  # noqa: BLE001
        return False


def view(dept: str, lst: dict, now: datetime, who: dict | None = None) -> dict:
    c = cycle(now, _services(), lst.get("services") or DEFAULT_SERVICES)
    ck = c["key"] if c else "-"
    ticks = lst.get("ticks", {}).get(ck, {})
    items = [{"i": i, "text": t, "done": str(i) in ticks, "by": ticks.get(str(i), {}).get("by", ""), "at": ticks.get(str(i), {}).get("at", "")}
             for i, t in enumerate(lst.get("items", []))]
    return {"dept": dept, "leader": lst.get("leader"), "nudge": lst.get("nudge"), "services": lst.get("services") or DEFAULT_SERVICES,
            "round": c, "items": items, "done": sum(1 for x in items if x["done"]), "history": lst.get("history", [])[:12],
            **({"can_edit": can_edit(who, dept, lst), "can_tick": can_tick(who, dept)} if who else {})}


def all_lists(who: dict, now: datetime | None = None) -> dict:
    """Admins see every department; anyone else sees the departments they are in."""
    now = now or datetime.now()
    with _lock:
        d = _read()
        out = []
        mine = None
        if who.get("role") != "admin":
            from . import directory
            try:
                mine = set(directory.user_groups(who.get("user", "")))
            except Exception:  # noqa: BLE001
                mine = set()
        for dept in departments():
            if mine is not None and dept not in mine:
                continue
            lst = _list(d, dept)
            c = cycle(now, _services(), lst.get("services") or DEFAULT_SERVICES)
            if c:
                _roll(lst, c["key"])
            out.append(view(dept, lst, now, who))
        _write(d)
    return {"lists": out, "demo": load().demo}


def _check_dept(dept: str) -> str | None:
    return None if dept in departments() else f"{dept} is not one of the departments ([church] departments in arise.toml)"


def tick(dept: str, i: int, who: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    if (e := _check_dept(dept)):
        return {"ok": False, "err": e}
    if not can_tick(who, dept):
        return {"ok": False, "err": f"only {dept} and the admins tick this list"}
    with _lock:
        d = _read()
        lst = _list(d, dept)
        if not 0 <= int(i) < len(lst["items"]):
            return {"ok": False, "err": "no such item"}
        c = cycle(now, _services(), lst.get("services") or DEFAULT_SERVICES)
        if not c:
            return {"ok": False, "err": "no service ahead for this list"}
        _roll(lst, c["key"])
        t = lst.setdefault("ticks", {}).setdefault(c["key"], {})
        if str(i) in t:
            del t[str(i)]
        else:
            t[str(i)] = {"by": who.get("user", ""), "at": now.isoformat(timespec="minutes")}
        _write(d)
        return {"ok": True, **view(dept, lst, now, who)}


def edit(dept: str, who: dict, items: list[str] | None = None, leader: str | None = None, nudge: str | None = None,
         services: list[str] | None = None, now: datetime | None = None) -> dict:
    """Items: the leader or an admin. Leader, nudge time and services: an admin."""
    now = now or datetime.now()
    if (e := _check_dept(dept)):
        return {"ok": False, "err": e}
    with _lock:
        d = _read()
        lst = _list(d, dept)
        if not can_edit(who, dept, lst):
            return {"ok": False, "err": f"only the {dept} leader and the admins edit this list"}
        if items is not None:
            clean = [str(x).strip()[:200] for x in items if str(x).strip()][:40]
            if clean != lst["items"]:
                # Changing the items clears this round's ticks: an old tick could point at a different line.
                c = cycle(now, _services(), lst.get("services") or DEFAULT_SERVICES)
                if c:
                    lst.get("ticks", {}).pop(c["key"], None)
                lst["items"] = clean
        admin_only = {"leader": leader, "nudge": nudge, "services": services}
        if any(v is not None for v in admin_only.values()) and who.get("role") != "admin":
            return {"ok": False, "err": "the leader, the nudge time and the services are set by an admin"}
        if leader is not None:
            lst["leader"] = leader.strip() or None
        if services is not None:
            known = {s["name"] for s in _services()}
            sv = [s for s in services if s in known]
            if not sv:
                return {"ok": False, "err": "pick at least one service"}
            lst["services"] = sv
        new = dict(lst["nudge"])
        if nudge is not None:
            if not isinstance(nudge, dict):
                return {"ok": False, "err": 'nudge is a time per service, e.g. {"Sunday Service": "09:15"}'}
            for name, t in nudge.items():
                if not valid_nudge(str(t)):
                    return {"ok": False, "err": f"the nudge time for {name} is HH:MM, 24-hour"}
                new[name] = str(t)
        for name in lst["services"]:
            new.setdefault(name, default_nudge(name))
            st = service_start(name)
            # A nudge must come before the service it is for: never during a service.
            if st and new[name] >= st:
                return {"ok": False, "err": f"the nudge at {new[name]} would land at or after {name} ({st}): pick an earlier time"}
        lst["nudge"] = new
        _write(d)
        return {"ok": True, **view(dept, lst, now, who)}


def due_nudges(now: datetime) -> list[dict]:
    """For the reminders loop: each list whose nudge time is now (same minute) on its service's day, with items left.
    {to: users, text, key}. The members of the department, plus its leader."""
    out = []
    from .notify import members_of
    with _lock:
        d = _read()
        for dept in departments():
            lst = _list(d, dept)
            if not lst["items"]:
                continue
            c = cycle(now, _services(), lst.get("services") or DEFAULT_SERVICES)
            if not c or c["at"][:10] != now.date().isoformat() or now.strftime("%H:%M") != lst["nudge"].get(c["service"]):
                continue
            left = len(lst["items"]) - len(lst.get("ticks", {}).get(c["key"], {}))
            if left <= 0:
                continue
            to = members_of(["@" + dept]) | ({lst["leader"]} if lst.get("leader") else set())
            out.append({"to": sorted(to), "text": f"{dept} checklist: {left} of {len(lst['items'])} left before {c['service']}", "key": f"dept:{dept}:{c['key']}"})
    return out


DEMO_STATE = {"lists": {
    "Media": {"items": ["Cameras on and answering in StreamYard", "Lower thirds loaded in Proclaim", "Recording started to the recordings share",
                        "Audio check with the sound desk", "Shorts plan for tonight agreed"],
              "leader": "bradly", "nudge": {"Sunday Service": "08:45", "Glory Night": "17:45"}, "services": ["Sunday Service", "Glory Night"], "ticks": {}, "history": [
                  {"round": "2026-10-19 Glory Night", "done": 5, "total": 5, "by": ["bradly", "media-mac"]},
                  {"round": "2026-10-18 Sunday Service", "done": 4, "total": 5, "by": ["bradly"]}]},
    "Childrens-Department": {"items": ["Classrooms open and lights on", "Check-in station signed in", "Snacks and supplies stocked"],
                             "leader": "childrens.department", "nudge": {"Sunday Service": "08:30"}, "services": ["Sunday Service"], "ticks": {}, "history": []},
}}

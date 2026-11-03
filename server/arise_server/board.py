"""The house board (round 8, Q28, Q29, Q30 and Q126): what the closet monitor shows at rest and any
lobby TV shows at /board, with no login.

Facts only, and never about a person: the next service (or the one running), whether the last
backup worked and when, how many things need Bradly (a count, never the items), whether the stream
is live, the verse of the day, and during a service each department's checklist as done of total.
No name, no path, no address, no hostname, no file name, no secret: tests/test_board.py pins the
exact keys and feeds it sample data full of all of those to prove none comes out.

Clock-independent: the page counts down from `next.at` itself, so the answer can be cached and
a lobby TV polling every minute costs the box one look every half minute at most.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable

from .config import load

KEYS = ("church", "next", "backup", "needs_you", "stream", "verse", "checklists", "demo")
TTL = 30            # seconds one answer is reused for (every TV and the monitor share it)
STREAM_TTL = 600    # outside a service the channel's live page is read every ten minutes at most

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "data": None}
_stream: dict = {"at": 0.0, "live": None}


def reset() -> None:
    """Forget the cached answers (the tests, and a config reload)."""
    with _lock:
        _cache.update(at=0.0, data=None)
        _stream.update(at=0.0, live=None)


def _bool_or_none(v):
    return v if isinstance(v, bool) else None


def _next(view: dict) -> dict | None:
    """The service on now (in_service true, `at` = when it started) or the next one."""
    if view.get("in_service"):
        s = view.get("service") or {}
        return {"name": str(s.get("name") or "Service"), "site": str(s.get("site") or ""),
                "at": str(s.get("started") or "")[:16], "in_service": True}
    n = view.get("next")
    if not n:
        return None
    return {"name": str(n.get("name") or ""), "site": str(n.get("site") or ""), "at": str(n.get("at") or "")[:16], "in_service": False}


def _backup() -> dict:
    """The newest backup run: did it work, and when it finished. Never the job's paths or errors."""
    from . import backups
    try:
        rows = backups.history(limit=1).get("rows") or []
    except Exception:  # noqa: BLE001 - the board never breaks for one panel
        rows = []
    if not rows:
        return {"ok": None, "when": None}
    r = rows[0]
    when = str(r.get("finished") or r.get("started") or "")[:16] or None
    return {"ok": _bool_or_none(r.get("ok")), "when": when}


def _stream_live(view: dict, demo: bool) -> bool | None:
    from . import servicemode
    if view.get("in_service"):
        return _bool_or_none((view.get("stream") or {}).get("live"))
    if demo:
        return False   # the sample church is not live on a weekday; service mode's preview says LIVE
    with _lock:
        if time.time() - _stream["at"] < STREAM_TTL:
            return _stream["live"]
    try:
        live = _bool_or_none(servicemode.live_status().get("live"))
    except Exception:  # noqa: BLE001
        live = None
    with _lock:
        _stream.update(at=time.time(), live=live)
    return live


def _checklists(view: dict) -> list[dict]:
    """During a service: each department's list as done of total. Item texts and who ticked stay out."""
    if not view.get("in_service"):
        return []
    out = []
    for c in view.get("checklists") or []:
        try:
            out.append({"dept": str(c.get("dept") or ""), "done": int(c.get("done") or 0), "total": int(c.get("total") or 0)})
        except (TypeError, ValueError):
            continue
    return out


def build(attention: Callable[[], list] | None = None, now: datetime | None = None) -> dict:
    """The board, fresh. `attention` returns the Needs-you list (main._attention_now); only its length leaves."""
    from . import church, servicemode
    c = load()
    try:
        view = servicemode.now_view(now)
    except Exception:  # noqa: BLE001
        view = {"in_service": False, "next": church.next_service(now)}
    try:
        info = church.info()
    except Exception:  # noqa: BLE001
        info = {}
    try:
        v = church.verse_of_day(now)
        verse = {"text": str(v.get("text") or ""), "ref": str(v.get("ref") or "")}
    except Exception:  # noqa: BLE001
        verse = {"text": "", "ref": ""}
    needs = None
    if attention is not None:
        try:
            needs = len(attention() or [])
        except Exception:  # noqa: BLE001
            needs = None
    return {
        "church": {"name": str(info.get("name") or "Arise Church"), "city": str(info.get("city") or "")},
        "next": _next(view),
        "backup": _backup(),
        "needs_you": needs,
        "stream": {"live": _stream_live(view, bool(c.demo))},
        "verse": verse,
        "checklists": _checklists(view),
        "demo": bool(c.demo),
    }


def view(attention: Callable[[], list] | None = None) -> dict:
    """The board as the route serves it: one answer shared for TTL seconds."""
    with _lock:
        if _cache["data"] is not None and time.time() - _cache["at"] < TTL:
            return _cache["data"]
    data = build(attention)
    with _lock:
        _cache.update(at=time.time(), data=data)
    return data

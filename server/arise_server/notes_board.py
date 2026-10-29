"""The admins' notes board (round 7, 116): sticky notes on the closet desktop that all four
admins see. Add, edit, pin, and put away. Putting a note away keeps it under "Put away" (it is
never deleted: deleting is Bradly's click, and this board has no delete).

State: <state_dir>/notes-board.json.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime
from pathlib import Path

from .config import load

MAX_NOTES, MAX_TEXT = 60, 600
COLOURS = ("ink", "red", "amber", "green")
_lock = threading.RLock()


def _path() -> Path:
    return Path(load().state_dir) / "notes-board.json"


def _read() -> dict:
    if load().demo:
        from . import demo_state
        return demo_state.get("notes.board", lambda: json.loads(json.dumps(DEMO)))
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"notes": [], "away": []}


def _write(d: dict) -> None:
    if load().demo:
        from . import demo_state
        demo_state.put("notes.board", d)
        return
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.chmod(tmp, 0o640)
    os.replace(tmp, p)


def _now() -> str:
    return datetime.now().isoformat(timespec="minutes")


def board() -> dict:
    d = _read()
    notes = sorted(d.get("notes", []), key=lambda n: (not n.get("pinned"), n.get("at", "")), reverse=False)
    pinned = [n for n in notes if n.get("pinned")]
    rest = sorted([n for n in notes if not n.get("pinned")], key=lambda n: n.get("at", ""), reverse=True)
    return {"notes": pinned + rest, "away": d.get("away", [])[:30], "demo": load().demo}


def add(text: str, who: str, colour: str = "ink") -> dict:
    text = (text or "").strip()[:MAX_TEXT]
    if not text:
        return {"ok": False, "err": "the note is empty"}
    with _lock:
        d = _read()
        if len(d.setdefault("notes", [])) >= MAX_NOTES:
            return {"ok": False, "err": f"the board holds {MAX_NOTES} notes: put some away first"}
        d["notes"].append({"id": secrets.token_hex(4), "text": text, "by": who, "at": _now(), "colour": colour if colour in COLOURS else "ink", "pinned": False})
        _write(d)
    return {"ok": True, **board()}


def edit(note_id: str, who: str, text: str | None = None, pinned: bool | None = None, colour: str | None = None) -> dict:
    with _lock:
        d = _read()
        n = next((x for x in d.get("notes", []) if x["id"] == note_id), None)
        if not n:
            return {"ok": False, "err": "no such note"}
        if text is not None:
            t = text.strip()[:MAX_TEXT]
            if not t:
                return {"ok": False, "err": "the note is empty: put it away instead"}
            n["text"] = t
            n["edited_by"], n["edited"] = who, _now()
        if pinned is not None:
            n["pinned"] = bool(pinned)
        if colour is not None and colour in COLOURS:
            n["colour"] = colour
        _write(d)
    return {"ok": True, **board()}


def put_away(note_id: str, who: str) -> dict:
    with _lock:
        d = _read()
        n = next((x for x in d.get("notes", []) if x["id"] == note_id), None)
        if not n:
            return {"ok": False, "err": "no such note"}
        d["notes"].remove(n)
        d.setdefault("away", []).insert(0, {**n, "away_by": who, "away_at": _now()})
        _write(d)
    return {"ok": True, **board()}


def bring_back(note_id: str, who: str) -> dict:
    with _lock:
        d = _read()
        n = next((x for x in d.get("away", []) if x["id"] == note_id), None)
        if not n:
            return {"ok": False, "err": "no such note"}
        d["away"].remove(n)
        n = {k: v for k, v in n.items() if k not in ("away_by", "away_at")}
        d.setdefault("notes", []).append(n)
        _write(d)
    return {"ok": True, **board()}


DEMO = {"notes": [
    {"id": "n1", "text": "Sample: the new mic stands arrive Thursday. Media closet, second shelf.", "by": "bradly", "at": "2026-10-28T10:15", "colour": "amber", "pinned": True},
    {"id": "n2", "text": "Sample: ask the pastors about their closet desktop on install week (round 7, 22).", "by": "kristina.robinson", "at": "2026-10-28T16:40", "colour": "ink", "pinned": False},
], "away": []}

"""The audit log: who did what, kept forever (round 2, 23; round 4, 79).

One JSON line per event in <state_dir>/audit.jsonl, append-only. Nothing in
the dashboard or arisectl deletes or edits it. Bodies are never recorded, so
no password, code or secret can land here: only who, what (method and path,
or a named action), the target, the result and where from.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path

from .config import load

_lock = threading.Lock()
_DEMO: list[dict] = []          # demo mode keeps its events in memory, seeded below
_SEEDED = {"done": False}
# The word before a value names the collection: /api/directory/users/<name>/disable
COLLECTIONS = {"users", "groups", "members", "shares", "apps", "links", "calendar", "devices", "services", "automations",
               "broadcasts", "run", "leaving", "reports"}

# Paths whose calls are noise, not actions (heartbeats, previews that change nothing).
QUIET = ("/api/auth/reauth", "/api/auth/forgot", "/api/auth/reset",   # the reset logs itself, with the person
         "/api/mail/preview", "/api/files/text/preview", "/api/push/test",
         "/api/files/upload/chunk", "/api/stats/")


def path() -> Path:
    return load().state_dir / "audit.jsonl"


def action_of(method: str, url_path: str) -> str:
    """Pure: a short verb for a route, e.g. 'POST /api/directory/users/x/disable' -> 'directory.users.disable'."""
    p = url_path.split("?")[0].strip("/").split("/")
    if p and p[0] == "api":
        p = p[1:]
    words = [w for i, w in enumerate(p) if w and not _is_target(p, i)]
    verb = {"POST": "", "PUT": "edit", "DELETE": "delete", "PATCH": "edit"}.get(method.upper(), method.lower())
    name = ".".join(words[:4]) or "root"
    return f"{name}.{verb}" if verb and not name.endswith(verb) else name


def _looks_like_value(w: str) -> bool:
    # user names (first.last), ids, tokens, unit names, numbers: the target, not the action
    return "." in w or w.isdigit() or len(w) > 24 or any(c.isdigit() for c in w) and len(w) > 6


def _is_target(p: list[str], i: int) -> bool:
    return _looks_like_value(p[i]) or (i > 0 and p[i - 1] in COLLECTIONS and p[i] not in COLLECTIONS and i < len(p))


def target_of(url_path: str) -> str:
    """Pure: the thing acted on: the path parts that are values, not route words."""
    p = [w for w in url_path.split("?")[0].strip("/").split("/") if w]
    if p and p[0] == "api":
        p = p[1:]
    return "/".join(w for i, w in enumerate(p) if _is_target(p, i))[:120]


def record(who: str, action: str, target: str = "", ok: bool = True, status: int | None = None,
           ip: str = "", detail: str = "", now: datetime | None = None) -> dict:
    ev = {"t": (now or datetime.now()).isoformat(timespec="seconds"), "who": who or "?", "action": action,
          "target": target, "ok": bool(ok)}
    if status is not None:
        ev["status"] = int(status)
    if ip:
        ev["ip"] = ip
    if detail:
        ev["detail"] = detail[:300]
    cfg = load()
    with _lock:
        if cfg.demo:
            _DEMO.append(ev)
            return ev
        try:
            p = path()
            p.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except OSError:
            pass  # the action itself must not fail because the log could not be written; doctor reports it
    return ev


def matches(ev: dict, q: str = "", who: str = "", failed_only: bool = False) -> bool:
    """Pure filter used by the list and by the tests."""
    if who and ev.get("who") != who:
        return False
    if failed_only and ev.get("ok", True):
        return False
    if q:
        hay = " ".join(str(ev.get(k, "")) for k in ("who", "action", "target", "detail", "ip")).lower()
        return all(part in hay for part in q.lower().split())
    return True


def _demo_seed():
    if _SEEDED["done"]:
        return
    _SEEDED["done"] = True
    from .demo import _ago
    seeds = []
    for t, who, act, tgt, ok in [
        (_ago(days=6, hours=3), "bradly", "auth.login", "", True),
        (_ago(days=6, hours=3), "bradly", "directory.users", "office.staff", True),
        (_ago(days=5, hours=1), "office", "auth.login", "", True),
        (_ago(days=5), "office", "links", "Documents/Bulletin 2026-11-01.docx", True),
        (_ago(days=3, hours=2), "unknown", "auth.login", "", False),
        (_ago(days=2), "bradly", "directory.users.disable", "guest-speaker", True),
        (_ago(days=1, hours=5), "media-mac", "sunday", "3", True),
        (_ago(hours=4), "bradly", "backups.run", "homes", True),
    ]:
        seeds.append({"t": t, "who": who, "action": act, "target": tgt, "ok": ok, "sample": True})
    _DEMO[0:0] = seeds   # older than anything recorded since start; the list stays oldest-first


def recent(limit: int = 200, q: str = "", who: str = "", failed_only: bool = False) -> dict:
    """Newest first. Reads the tail of the file; never rewrites it."""
    cfg = load()
    limit = max(1, min(int(limit or 200), 2000))
    if cfg.demo:
        _demo_seed()
        rows = [e for e in reversed(_DEMO) if matches(e, q, who, failed_only)][:limit]
        return {"demo": True, "events": rows, "kept": "forever", "path": "(sample: in memory)"}
    p = path()
    rows: list[dict] = []
    try:
        size = p.stat().st_size
        with open(p, "rb") as f:
            f.seek(max(0, size - 4_000_000))   # the last ~4 MB is months of a church's activity
            lines = f.read().decode("utf-8", "replace").splitlines()
        for ln in reversed(lines):
            try:
                e = json.loads(ln)
            except ValueError:
                continue
            if matches(e, q, who, failed_only):
                rows.append(e)
                if len(rows) >= limit:
                    break
    except FileNotFoundError:
        pass
    except OSError as e:
        return {"events": [], "error": str(e), "kept": "forever", "path": str(p)}
    return {"events": rows, "kept": "forever", "path": str(p)}

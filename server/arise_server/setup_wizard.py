"""The guided setup (round 5, 33): the first time an admin signs in after the
install, a step-by-step window: People (the list, round 5, 8), Shares, the
Synology, Discord, Resend, Tailscale. Each step is skippable; progress is kept on
the server (<state_dir>/setup.json), so it carries on where it stopped, on any
device, and it opens again from Settings.

Each step also says whether the box already looks done, from a cheap check, so
a step that is in place shows as such even when nobody clicked it.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from .config import load

STEPS = [
    {"id": "people", "title": "People", "what": "Paste or upload the list of everyone: name, title, departments, personal email, mobile, birthday. Each gets an account with a temporary password."},
    {"id": "shares", "title": "Shares", "what": "The Church folder, a folder per department, Pastors, Alexandria: check they are there and who can use them."},
    {"id": "synology", "title": "The Synology", "what": "Join it to the domain and mount it, so recordings and the backups have their home (docs/SYNOLOGY.md)."},
    {"id": "discord", "title": "Discord", "what": "The four webhook addresses (failures, Sunday all-green, the live link, #daily) into /etc/arise/secrets/discord.toml."},
    {"id": "resend", "title": "Resend", "what": "The API key and the sending address at mail.arisecenla.com, with its SPF and DKIM records added at Wix."},
    {"id": "tailscale", "title": "Tailscale", "what": "Sign the box in to the church's Tailscale account, so admins reach it from home."},
]
IDS = [s["id"] for s in STEPS]


def _path() -> str:
    return str(load().state_dir / "setup.json")


def _read() -> dict:
    if load().demo:
        from . import demo_state
        return demo_state.get("setup.wizard", lambda: {"steps": {}, "dismissed": False})
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {"steps": {}}
    except (FileNotFoundError, json.JSONDecodeError):
        return {"steps": {}, "dismissed": False}


def _write(d: dict):
    if load().demo:
        return
    p = _path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(p + ".tmp", p)


def looks_done() -> dict:
    """{step: bool | None}: what the box can see by itself. None = cannot tell."""
    out: dict = {k: None for k in IDS}
    cfg = load()
    if cfg.demo:
        return {"people": False, "shares": True, "synology": False, "discord": False, "resend": False, "tailscale": True}
    try:
        from . import directory
        out["people"] = len(directory.list_users().get("users", [])) > 4
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import shares
        names = {s["name"] for s in shares.list_shares().get("shares", [])}
        out["shares"] = "church" in names or len(names) > 5
    except Exception:  # noqa: BLE001
        pass
    try:
        out["synology"] = bool(os.path.ismount(cfg.nas.mount))
    except Exception:  # noqa: BLE001
        pass
    out["discord"] = os.path.exists("/etc/arise/secrets/discord.toml")
    try:
        from . import mail
        m = mail.cfg_mail()
        out["resend"] = bool(m.get("from_email")) and os.path.exists("/etc/arise/secrets/resend-api-key")
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import remote
        st = remote.status() if hasattr(remote, "status") else {}
        out["tailscale"] = bool((st.get("tailscale") or {}).get("up"))
    except Exception:  # noqa: BLE001
        pass
    return out


def state(who: dict) -> dict:
    d = _read()
    seen = looks_done()
    steps = []
    for s in STEPS:
        mark = (d.get("steps") or {}).get(s["id"]) or {}
        status = mark.get("status") or ("done" if seen.get(s["id"]) else "todo")
        steps.append({**s, "status": status, "by": mark.get("by"), "at": mark.get("at"), "looks_done": seen.get(s["id"])})
    left = [s for s in steps if s["status"] == "todo"]
    return {"steps": steps, "left": len(left), "dismissed": bool(d.get("dismissed")),
            "show": who.get("role") == "admin" and not d.get("dismissed") and bool(left), "demo": load().demo}


def mark(step: str, status: str, who: dict) -> dict:
    if step not in IDS:
        return {"ok": False, "err": "no such step"}
    if status not in ("done", "skipped", "todo"):
        return {"ok": False, "err": "status is done, skipped or todo"}
    d = _read()
    d.setdefault("steps", {})[step] = {"status": status, "by": who.get("user"), "at": datetime.now().isoformat(timespec="minutes")}
    _write(d)
    return {"ok": True, **state(who)}


def dismiss(who: dict, dismissed: bool = True) -> dict:
    """Close the setup for now (dismissed) or bring it back (from Settings)."""
    d = _read()
    d["dismissed"] = bool(dismissed)
    _write(d)
    return {"ok": True, **state(who)}

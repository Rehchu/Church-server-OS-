"""Telling one person something, where they are (round 7, 84): staff use their Macs, not the
dashboard, so a notice is an email to their personal address and a Mac notification on every
church Mac where they have an account.

    notices.notify_person(user, title, body, kind="info")   the one call other modules make
    notices.alert_admins(text, key="")                       Bradly: push and Discord #alerts (round 7, 77)

The Mac side is the helper's `notice` task (mac/helper/arise-mac-helper): shown at once if they
are signed in, otherwise at their next sign-in. A notice changes nothing on a Mac, so it goes out
in watch mode too; nothing goes out during a service.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime

from .config import load

KINDS = ("info", "warn", "bad")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_lock = threading.RLock()


def personal_email(user: str) -> str | None:
    """The profile's personal email (round 5, 9)."""
    try:
        from . import profiles
        v = (profiles._read().get((user or "").lower()) or {}).get("personal_email") or ""
        return v if EMAIL_RE.match(v) else None
    except Exception:  # noqa: BLE001
        return None


def notify_person(user: str, title: str, body: str, kind: str = "info") -> dict:
    """Email the person's personal address (when one is on file) and queue a Mac notification on
    every church Mac where they have an account. Never raises: a notice never breaks its caller."""
    user = (user or "").strip().lower()
    kind = kind if kind in KINDS else "info"
    title, body = (title or "").strip()[:120], (body or "").strip()[:600]
    if not user or not title:
        return {"ok": False, "err": "a person and a title are needed"}
    out: dict = {"ok": True, "user": user, "email": None, "macs": []}
    addr = personal_email(user)
    if addr:
        try:
            from . import mail
            out["email"] = mail.send_one(addr, title, body + "\n\n— Arise Church IT")
        except Exception as e:  # noqa: BLE001
            out["email"] = {"ok": False, "err": str(e)[:200]}
    else:
        out["email"] = {"ok": False, "err": "no personal email on file"}
    try:
        from . import macs
        out["macs"] = macs.queue_notice(user, title, body, kind)
    except Exception as e:  # noqa: BLE001
        out["macs_err"] = str(e)[:200]
    try:
        from . import audit
        audit.record("ariseOS", "notice", user, detail=f"{title[:80]} · email {'sent' if (out['email'] or {}).get('ok') else 'not sent'} · {len(out['macs'])} Mac(s)")
    except Exception:  # noqa: BLE001
        pass
    return out


# ----- Bradly: push and Discord #alerts ----------------------------------------------------
def _state_path() -> str:
    return str(load().state_dir / "notices.json")


def _seen(key: str) -> bool:
    try:
        with open(_state_path(), encoding="utf-8") as f:
            return key in (json.load(f).get("sent") or {})
    except (OSError, ValueError):
        return False


def _mark(key: str):
    p = _state_path()
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    sent = d.setdefault("sent", {})
    sent[key] = datetime.now().isoformat(timespec="seconds")
    if len(sent) > 500:   # oldest first out
        for k in sorted(sent, key=sent.get)[:len(sent) - 500]:
            sent.pop(k, None)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(p + ".tmp", p)


def discord_url(channel: str = "alerts") -> str:
    """The webhook for one channel from /etc/arise/secrets/discord.toml (round 4, 101): a key per
    channel, at the top or under [webhooks]. The address is read here and never shown or logged."""
    path = os.environ.get("ARISE_DISCORD_TOML", "/etc/arise/secrets/discord.toml")
    try:
        import tomllib
        with open(path, "rb") as f:
            d = tomllib.load(f)
    except (OSError, ValueError, ImportError):
        return ""
    v = d.get(channel) or (d.get("webhooks") or {}).get(channel) or ""
    return v if isinstance(v, str) and v.startswith("https://") else ""


def alert_admins(text: str, key: str = "") -> dict:
    """One line for Bradly (round 7, 77: #alerts is his only): a push to his devices and Discord
    #alerts when its webhook is set. `key` sends it once; nothing is sent in sample mode."""
    text = (text or "").strip()[:500]
    if not text:
        return {"ok": False, "err": "nothing to say"}
    if load().demo:
        return {"ok": True, "demo": True}
    with _lock:
        if key and _seen(key):
            return {"ok": True, "duplicate": True}
        out: dict = {"ok": True}
        owner = str((load().raw.get("owner") or {}).get("user", "")) if isinstance(load().raw, dict) else ""
        try:
            from . import push
            out["push"] = push.send("ariseOS", text, "/", tag=key or text[:40], throttle_s=0, users=[owner] if owner else None)
        except Exception as e:  # noqa: BLE001
            out["push"] = {"ok": False, "err": str(e)[:200]}
        url = discord_url("alerts")
        if url:
            try:
                from . import system
                out["discord"] = system.send_webhook("🟡 " + text, url)
            except Exception as e:  # noqa: BLE001
                out["discord"] = {"ok": False, "err": str(e)[:200]}
        if key:
            _mark(key)
    return out

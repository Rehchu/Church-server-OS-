"""The four Discord channels (docs/DISCORD.md; round 4, 101): #alerts, #sunday, #weekly, #daily.

    discord.post("alerts", "Backups missed last night ...", key="backup-missed:2026-10-29")

The webhook addresses are credentials: they live in /etc/arise/secrets/discord.toml
(root only), are never logged and never returned by the API. `key` makes a post
happen once: the same key is never posted twice (a check that runs every hour must
not repeat itself). Round 7, 77: #alerts is Bradly's alone; who reads which channel
is Discord's own setting, not this file's.
"""
from __future__ import annotations

import json
import threading
import tomllib
import urllib.request
from datetime import datetime

from .config import load
from .util import read_json, write_json

CHANNELS = ("alerts", "sunday", "weekly", "daily")
SECRETS = "/etc/arise/secrets/discord.toml"
_lock = threading.Lock()


def _hooks(path: str = SECRETS) -> dict:
    try:
        with open(path, "rb") as f:
            d = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return {k: str(v) for k, v in d.items() if k in CHANNELS and str(v).startswith("https://")}


def status() -> dict:
    """Which channels are set: names only, never the addresses."""
    h = _hooks()
    return {"set": sorted(h), "missing": [c for c in CHANNELS if c not in h], "file": SECRETS, "demo": load().demo}


def _sent_path():
    return load().state_dir / "discord-sent.json"


def already(key: str) -> bool:
    if not key:
        return False
    return key in (read_json(_sent_path(), default={}) or {})


def _mark(key: str) -> None:
    p = _sent_path()
    d = read_json(p, default={}) or {}
    d[key] = datetime.now().isoformat(timespec="seconds")
    if len(d) > 2000:   # the oldest keys go; a key that old will not come back
        d = dict(sorted(d.items(), key=lambda kv: kv[1])[-1500:])
    write_json(p, d)


def line(text: str, fix: str = "", now: datetime | None = None) -> str:
    """Pure: the house style (docs/DISCORD.md): the time, one line of what happened, the command that fixes it."""
    now = now or datetime.now()
    out = f"{now:%a %b %-d, %-I:%M %p} · {text.strip()}"
    if fix:
        out += f"\n→ `{fix.strip()}`"
    return out[:1900]


def post(channel: str, text: str, key: str = "", fix: str = "", hooks: dict | None = None, send=None) -> dict:
    """One post. Never raises: a Discord outage must never break the caller."""
    if channel not in CHANNELS:
        return {"ok": False, "err": f"no channel called {channel}"}
    if load().demo and hooks is None:
        return {"ok": True, "demo": True, "channel": channel, "text": line(text, fix)}
    with _lock:
        if key and already(key):
            return {"ok": True, "duplicate": True, "channel": channel}
        url = (hooks if hooks is not None else _hooks()).get(channel)
        if not url:
            return {"ok": False, "err": f"Discord #{channel} is not set ({SECRETS})", "channel": channel}
        body = line(text, fix)
        try:
            if send:
                send(url, body)
            else:
                req = urllib.request.Request(url, data=json.dumps({"content": body}).encode(),
                                             headers={"Content-Type": "application/json", "User-Agent": "ariseOS"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    if not 200 <= r.status < 300:
                        return {"ok": False, "err": f"Discord answered {r.status}", "channel": channel}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "err": str(e)[:160], "channel": channel}
        if key:
            _mark(key)
    return {"ok": True, "channel": channel}


def test(channel: str) -> dict:
    return post(channel, f"ariseOS test post to #{channel} from {load().system.hostname}. If you can read this, the server can post here.")


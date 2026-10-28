"""Web push to Bradly's phone (answer 10: to him only), through the browser's
own push service with VAPID keys. No account with anyone; the keys are made
on the box and kept root-only. pywebpush and py-vapid do the sending; without
them (or in sample mode) nothing is sent and the API says so.

Sends: a new red item in Needs You, a backup failure, a stream drop on a
Sunday (later), the morning report ready (later). Always short, always with
a link into the dashboard.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime

from .config import load

KEYS = "/etc/arise/secrets/vapid.json"
_last_sent: dict = {}


def _state_path() -> str:
    return str(load().state_dir / "push.json")


def _subs() -> dict:
    try:
        with open(_state_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(d: dict):
    p = _state_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(p + ".tmp", p)


def keys() -> dict | None:
    """The VAPID key pair, made on first use. None when py_vapid is missing."""
    try:
        with open(KEYS, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    try:
        from py_vapid import Vapid, b64urlencode
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        return None
    v = Vapid()
    v.generate_keys()
    pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    priv = v.private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    d = {"public": b64urlencode(pub), "private_pem": priv, "made": datetime.now().isoformat(timespec="minutes")}
    try:
        os.makedirs(os.path.dirname(KEYS), exist_ok=True)
        with open(KEYS, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.chmod(KEYS, 0o600)
    except OSError:
        pass
    return d


def public_key() -> dict:
    if load().demo:
        return {"demo": True, "key": "", "available": False, "note": "sample mode: no push"}
    k = keys()
    if not k:
        return {"key": "", "available": False, "note": "pip install pywebpush py-vapid (server/requirements.txt), then restart arise-web"}
    return {"key": k["public"], "available": True}


def valid_subscription(sub: dict) -> bool:
    """Pure: the shape a browser's PushSubscription.toJSON() has."""
    return bool(isinstance(sub, dict) and isinstance(sub.get("endpoint"), str) and sub["endpoint"].startswith("https://")
                and isinstance(sub.get("keys"), dict) and sub["keys"].get("p256dh") and sub["keys"].get("auth"))


def subscribe(user: str, sub: dict, label: str = "") -> dict:
    if not valid_subscription(sub):
        return {"ok": False, "err": "that is not a push subscription"}
    if load().demo:
        return {"ok": True, "demo": True}
    d = _subs()
    rows = d.setdefault(user, [])
    rows[:] = [r for r in rows if r["sub"]["endpoint"] != sub["endpoint"]]
    rows.append({"sub": sub, "label": label[:60], "added": datetime.now().isoformat(timespec="minutes")})
    _save(d)
    return {"ok": True, "count": len(rows)}


def unsubscribe(user: str, endpoint: str) -> dict:
    d = _subs()
    rows = d.get(user, [])
    before = len(rows)
    rows[:] = [r for r in rows if r["sub"]["endpoint"] != endpoint]
    if len(rows) != before:
        _save(d)
    return {"ok": True, "count": len(rows)}


def who_gets() -> list[str]:
    """Answer 10: Bradly only. The admin_user, plus anyone listed in [push] users."""
    cfg = load()
    raw = (cfg.raw.get("push") if isinstance(cfg.raw, dict) else None) or {}
    return list(dict.fromkeys([cfg.web.admin_user] + list(raw.get("users") or [])))


def send(title: str, body: str, url: str = "/", tag: str = "", throttle_s: int = 3600) -> dict:
    """To every device of every person in who_gets(). The same tag is not sent
    again within throttle_s, so a red item does not buzz every five minutes."""
    now = time.time()
    if tag and now - _last_sent.get(tag, 0) < throttle_s:
        return {"ok": True, "skipped": "throttled"}
    if tag:
        _last_sent[tag] = now
    if load().demo:
        return {"ok": True, "demo": True, "sent": 0}
    k = keys()
    if not k:
        return {"ok": False, "err": "push not available (pywebpush/py-vapid missing)"}
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return {"ok": False, "err": "pywebpush missing"}
    d = _subs()
    sent, dead = 0, []
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag or "arise"})
    for user in who_gets():
        for r in list(d.get(user, [])):
            try:
                webpush(subscription_info=r["sub"], data=payload, vapid_private_key=k["private_pem"], vapid_claims={"sub": "mailto:admin@arisecenla.church"}, ttl=3600)
                sent += 1
            except WebPushException as e:
                if getattr(e, "response", None) is not None and e.response.status_code in (404, 410):
                    dead.append((user, r["sub"]["endpoint"]))
            except Exception:
                pass
    for user, ep in dead:
        unsubscribe(user, ep)
    return {"ok": True, "sent": sent, "removed": len(dead)}


# ---- the watcher: new red items in Needs You -> a push ------------------------
_seen: set = set()


def watch(get_attention, every_s: int = 300):
    """A thread: calls get_attention() every few minutes and pushes a new 'bad' item once."""
    def loop():
        time.sleep(60)
        while True:
            try:
                items = get_attention() or []
                for it in items:
                    key = (it.get("level"), (it.get("text") or "")[:80])
                    if it.get("level") == "bad" and key not in _seen:
                        _seen.add(key)
                        send("Arise Server needs you", it.get("text", "")[:160], "/#overview", tag="att:" + key[1][:40], throttle_s=6 * 3600)
                # a cleared item may come back later and deserves a new push
                live = {(i.get("level"), (i.get("text") or "")[:80]) for i in items}
                _seen.intersection_update(live)
            except Exception:
                pass
            time.sleep(every_s)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t

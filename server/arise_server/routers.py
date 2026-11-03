"""What sits behind the other routers, read from the routers themselves.

The ARP scan (devices.py) sees only the wire the server is on. The office
Netgear and the Google Mesh each run their own network behind a NAT. A
consumer Netgear router will *tell* you its attached devices over its SOAP
API if you log in as admin (the same list its "Attached Devices" page shows,
and sometimes more). This module asks, read-only, and never writes anything
to a router. Google Mesh has no equivalent that works without Google's
cloud, so its clients stay in the Google Home app; that is said in the
dashboard rather than faked.

Config: [[routers]] in arise.toml (kind = "netgear", host, user,
password_file). Missing config = nothing asked.
"""
from __future__ import annotations

from pathlib import Path

from .config import load


def routers() -> list[dict]:
    cfg = load()
    raw = cfg.raw.get("routers") if isinstance(cfg.raw, dict) else None
    out = []
    for r in raw or []:
        out.append({k: r.get(k, "") for k in ("id", "name", "kind", "host", "user", "password_file")})
    return out


def normalize(dev) -> dict:
    """A pynetgear Device (or any object/dict with name, ip, mac, type, signal, link_rate) -> our shape."""
    g = (lambda k: getattr(dev, k, None)) if not isinstance(dev, dict) else dev.get
    mac = (g("mac") or "").lower()
    return {"mac": mac, "ip": g("ip") or "", "hostname": g("name") or "", "name": "", "vendor": "",
            "kind_final": (g("type") or "unknown").lower() if g("type") else "unknown", "signal": g("signal"), "link_rate": g("link_rate"),
            "online": True, "behind": True}


def attached(router: dict) -> dict:
    """The devices a Netgear router reports as attached. Read-only."""
    if router.get("kind") != "netgear":
        return {"ok": False, "err": f"kind {router.get('kind')!r} is not supported; only netgear routers answer this"}
    try:
        pw = Path(router["password_file"]).read_text().strip()
    except (OSError, KeyError):
        return {"ok": False, "err": f"password file {router.get('password_file')} not readable"}
    try:
        from pynetgear import Netgear
    except ImportError:
        return {"ok": False, "err": "pynetgear is not installed: pip install pynetgear (server/requirements.txt)"}
    try:
        ng = Netgear(password=pw, host=router["host"], user=router.get("user") or "admin")
        if not ng.login():
            return {"ok": False, "err": f"{router['host']}: login refused (admin password?)"}
        devs = ng.get_attached_devices() or []
    except Exception as e:  # the router is off, the address is wrong, the firmware is odd
        return {"ok": False, "err": f"{router['host']}: {e}"}
    return {"ok": True, "devices": [normalize(d) for d in devs]}


def behind() -> dict:
    """Every configured router's attached devices, plus which ones answered."""
    cfg = load()
    if cfg.demo:
        from . import demo
        return {"demo": True, "routers": demo.ROUTERS_BEHIND}
    out = []
    for r in routers():
        res = attached(r)
        out.append({"id": r["id"], "name": r["name"] or r["host"], "host": r["host"], "kind": r["kind"], "ok": res.get("ok", False), "err": res.get("err", ""), "devices": res.get("devices", [])})
    return {"demo": False, "routers": out}

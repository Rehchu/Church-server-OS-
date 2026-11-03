"""The campuses: Pineville (main), Alexandria, the Apostolic Hub.

Each site is a [[sites]] block in arise.toml. The server lives at the main
site; the others reach it over the VPN. Status is a ping of each site's
probe host (its router or its Mac), nothing more.
"""
from __future__ import annotations

import ipaddress
import time

from . import demo
from .config import load
from .util import run, which

DEFAULT_SITES = [
    {"id": "pineville", "name": "Arise Church Pineville", "kind": "main", "address": "501 Ates Road, Pineville, LA", "subnet": "192.168.1.0/24", "probe": "", "services": "Sunday 10:30 AM · Glory Night Monday 7 PM", "note": "The server, the Synology and the domain live here."},
    {"id": "alexandria", "name": "Arise Church Alexandria", "kind": "campus", "address": "", "subnet": "192.168.2.0/24", "probe": "", "services": "Sunday 10:00 AM", "note": "Reaches the server over the VPN. Macs here bind to the domain through it."},
    {"id": "hub", "name": "The Apostolic Hub", "kind": "office", "address": "", "subnet": "192.168.3.0/24", "probe": "", "services": "", "note": "Office and leadership computers. VPN clients, no site router needed."},
]


def sites() -> list[dict]:
    cfg = load()
    raw = cfg.raw.get("sites") if isinstance(cfg.raw, dict) else None
    out = []
    for s in (raw or DEFAULT_SITES):
        d = {k: s.get(k, "") for k in ("id", "name", "kind", "address", "subnet", "probe", "services", "note")}
        out.append(d)
    return out


def _ping(host: str) -> dict:
    if not host:
        return {"ok": None, "ms": None}
    if not which("ping"):
        return {"ok": None, "ms": None}
    t0 = time.time()
    r = run(["ping", "-c", "1", "-W", "2", host], timeout=5)
    return {"ok": r["ok"], "ms": round((time.time() - t0) * 1000) if r["ok"] else None}


def status(computers: list[dict] | None = None) -> dict:
    cfg = load()
    out = []
    for s in sites():
        d = dict(s)
        if cfg.demo:
            d["probe_status"] = {"pineville": {"ok": True, "ms": 1}, "alexandria": {"ok": True, "ms": 34}, "hub": {"ok": None, "ms": None}}.get(s["id"], {"ok": None, "ms": None})
            d["vpn"] = {"pineville": "local", "alexandria": "site-to-site", "hub": "clients"}.get(s["id"], "")
        else:
            d["probe_status"] = _ping(s.get("probe", ""))
            d["vpn"] = "local" if s.get("kind") == "main" else "vpn"
        d["computers"] = []
        if computers:
            try:
                net = ipaddress.ip_network(s.get("subnet") or "0.0.0.0/32", strict=False)
                for c in computers:
                    ip = c.get("ip")
                    if ip and ipaddress.ip_address(ip) in net:
                        d["computers"].append(c["name"])
            except ValueError:
                pass
        out.append(d)
    return {"demo": cfg.demo, "sites": out}

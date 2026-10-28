"""Everything on the switch: an ARP scan of the server's own network.

The server sits on Netgear A's network, so this lists every device on that
wire: Macs, the Synology, printers, and the WAN side of the office Netgear
and the Google Mesh (each of those is one entry here; what sits behind them
is their own network and cannot be seen from this side, by design of NAT).

Tools, in order: `arp-scan --localnet` (apt install arp-scan; needs root,
which the service is), else a ping sweep of the subnet followed by the
kernel's neighbour table. Results merge into <state_dir>/devices.json keyed
by MAC: first seen, last seen, the addresses it has had, and any name or
note a person gives it in the dashboard. Nothing here changes a device.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import subprocess
import time
from datetime import datetime

from .config import load
from .util import run, which

# A small OUI table: the first three bytes of a MAC say who made it. Enough
# for the church's gear; anything else shows the vendor arp-scan reports.
OUI = {
    "apple": ("Apple", "mac"), "dell": ("Dell", "pc"), "synology": ("Synology", "nas"), "netgear": ("Netgear", "router"),
    "google": ("Google", "router"), "cisco": ("Cisco", "switch"), "ubiquiti": ("Ubiquiti", "network"), "tp-link": ("TP-Link", "network"),
    "hewlett": ("HP", "printer"), "hp inc": ("HP", "printer"), "brother": ("Brother", "printer"), "canon": ("Canon", "printer"), "epson": ("Epson", "printer"),
    "blackmagic": ("Blackmagic", "camera"), "ptzoptics": ("PTZOptics", "camera"), "birddog": ("BirdDog", "camera"), "newtek": ("NewTek", "camera"),
    "sony": ("Sony", "camera"), "panasonic": ("Panasonic", "camera"), "axis": ("Axis", "camera"), "hikvision": ("Hikvision", "camera"), "ring": ("Ring", "camera"),
    "intel": ("Intel", "pc"), "raspberry": ("Raspberry Pi", "pc"), "amazon": ("Amazon", "iot"), "sonos": ("Sonos", "iot"), "roku": ("Roku", "iot"),
    "nest": ("Google Nest", "iot"), "ecobee": ("ecobee", "iot"), "honeywell": ("Honeywell", "iot"), "samsung": ("Samsung", "phone"), "lg ": ("LG", "iot"),
}
KINDS = ("server", "nas", "mac", "pc", "router", "switch", "network", "printer", "camera", "iot", "phone", "unknown")


def _store() -> str:
    return str(load().state_dir / "devices.json")


def _load() -> dict:
    try:
        with open(_store(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(d: dict):
    p = _store()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, p)


def own_network() -> dict:
    """The interface and subnet the server sits on."""
    r = run(["sh", "-c", "ip -o route get 1.1.1.1"], timeout=5)
    iface = ip = ""
    for i, tok in enumerate(r["out"].split()):
        if tok == "dev":
            iface = r["out"].split()[i + 1]
        if tok == "src":
            ip = r["out"].split()[i + 1]
    cidr = ""
    if iface:
        a = run(["sh", "-c", f"ip -o -4 addr show dev {iface}"], timeout=5)
        m = re.search(r"inet (\S+)", a["out"])
        if m:
            cidr = str(ipaddress.ip_interface(m.group(1)).network)
    return {"iface": iface, "ip": ip, "subnet": cidr}


def classify(vendor: str, hostname: str = "") -> tuple[str, str]:
    """(vendor name, kind) from what arp-scan or the OUI table says."""
    v = (vendor or "").lower()
    h = (hostname or "").lower()
    for key, (name, kind) in OUI.items():
        if key in v:
            return name, kind
    if "synology" in h or h.startswith("ds"):
        return vendor or "", "nas"
    if h.endswith(".local") or "macbook" in h or "imac" in h:
        return vendor or "Apple", "mac"
    return vendor or "", "unknown"


def parse_arp_scan(text: str) -> list[dict]:
    """Rows of `arp-scan --localnet --plain`: '192.168.1.5\\t00:11:22:33:44:55\\tApple, Inc.'"""
    out = []
    for line in text.splitlines():
        parts = line.strip().split("\t")
        if len(parts) >= 2 and re.match(r"^\d+\.\d+\.\d+\.\d+$", parts[0]) and re.match(r"^[0-9a-f:]{17}$", parts[1].lower()):
            out.append({"ip": parts[0], "mac": parts[1].lower(), "vendor": parts[2] if len(parts) > 2 else ""})
    return out


def parse_neigh(text: str) -> list[dict]:
    """Rows of `ip -4 neigh show`: '192.168.1.5 dev eth0 lladdr 00:11:... REACHABLE'"""
    out = []
    for line in text.splitlines():
        m = re.match(r"^(\d+\.\d+\.\d+\.\d+) dev \S+ lladdr ([0-9a-f:]{17}) (\S+)", line.strip())
        if m and m.group(3) not in ("FAILED", "INCOMPLETE"):
            out.append({"ip": m.group(1), "mac": m.group(2), "vendor": ""})
    return out


def _sweep(subnet: str, iface: str):
    """Ping every address once, in parallel, so the neighbour table fills."""
    net = ipaddress.ip_network(subnet, strict=False)
    if net.num_addresses > 1024:
        return
    hosts = [str(h) for h in net.hosts()]
    procs = []
    for h in hosts:
        procs.append(subprocess.Popen(["ping", "-c", "1", "-W", "1", h], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        if len(procs) >= 64:
            for p in procs:
                p.wait()
            procs = []
    for p in procs:
        p.wait()


def _rdns(ip: str) -> str:
    try:
        socket.setdefaulttimeout(0.4)
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


def scan(quiet: bool = False) -> dict:
    cfg = load()
    if cfg.demo:
        return {"demo": True, "scanned": True, **list_devices()}
    net = own_network()
    if not net["subnet"]:
        return {"ok": False, "err": "could not tell which network this box is on"}
    found = []
    tool = ""
    if which("arp-scan"):
        r = run(["arp-scan", "--localnet", "--plain", "--interface", net["iface"], "--retry", "2"], timeout=90)
        found = parse_arp_scan(r["out"])
        tool = "arp-scan"
    if not found and which("nmap"):
        # nmap -sn is a ping/ARP sweep that prints MACs when run as root.
        r = run(["nmap", "-sn", "-n", "--send-ip", net["subnet"]], timeout=120)
        for block in r["out"].split("Nmap scan report for "):
            m_ip = re.match(r"(\d+\.\d+\.\d+\.\d+)", block)
            m_mac = re.search(r"MAC Address: ([0-9A-F:]{17}) \(([^)]*)\)", block)
            if m_ip and m_mac:
                found.append({"ip": m_ip.group(1), "mac": m_mac.group(1).lower(), "vendor": m_mac.group(2)})
        tool = "nmap" if found else tool
    if not found:
        _sweep(net["subnet"], net["iface"])
        r = run(["ip", "-4", "neigh", "show", "dev", net["iface"]], timeout=10)
        found = parse_neigh(r["out"])
        tool = tool or "ping sweep + neighbour table"
    now = datetime.now().isoformat(timespec="minutes")
    store = _load()
    seen = set()
    known_computers = set()
    try:
        from . import directory
        known_computers = {c["name"].lower().rstrip("$") for c in directory.list_computers().get("computers", [])}
    except Exception:
        pass
    new = 0
    for f in found:
        mac = f["mac"]
        seen.add(mac)
        host = _rdns(f["ip"])
        vendor, kind = classify(f["vendor"], host)
        d = store.get(mac)
        if not d:
            d = {"mac": mac, "first_seen": now, "ips": [], "name": "", "note": "", "kind": ""}
            new += 1
            store[mac] = d
        d["last_seen"] = now
        d["ip"] = f["ip"]
        if f["ip"] not in d["ips"]:
            d["ips"] = (d["ips"] + [f["ip"]])[-5:]
        d["vendor"] = vendor or d.get("vendor", "")
        d["guess"] = kind
        d["hostname"] = host or d.get("hostname", "")
        short = (host.split(".")[0] if host else "").lower()
        d["joined"] = bool(short and short in known_computers)
        if f["ip"] == net["ip"]:
            d["guess"] = "server"; d["hostname"] = d["hostname"] or cfg.system.hostname
    store["_meta"] = {"last_scan": now, "tool": tool, "subnet": net["subnet"], "iface": net["iface"], "found": len(found), "new": new}
    _save(store)
    return {"ok": True, "scanned": True, "tool": tool, "found": len(found), "new": new, **list_devices()}


def list_devices() -> dict:
    cfg = load()
    if cfg.demo:
        from . import demo
        return {"demo": True, "meta": demo.DEVICES_META, "devices": demo.DEVICES, "network": {"subnet": "192.168.1.0/24", "iface": "eno1", "ip": "192.168.1.57"}}
    store = _load()
    meta = store.get("_meta", {})
    devs = [v for k, v in store.items() if not k.startswith("_")]
    last = meta.get("last_scan", "")
    for d in devs:
        d["online"] = bool(last) and d.get("last_seen") == last
        d["kind_final"] = d.get("kind") or d.get("guess") or "unknown"
    devs.sort(key=lambda d: (not d["online"], tuple(int(x) for x in (d.get("ip") or "0.0.0.0").split("."))))
    return {"demo": False, "meta": meta, "devices": devs, "network": own_network()}


def label(mac: str, name: str | None = None, note: str | None = None, kind: str | None = None) -> dict:
    mac = (mac or "").lower()
    if load().demo:
        return {"ok": True, "demo": True}
    store = _load()
    d = store.get(mac)
    if not d:
        return {"ok": False, "err": "no such device"}
    if name is not None:
        d["name"] = name.strip()[:60]
    if note is not None:
        d["note"] = note.strip()[:200]
    if kind is not None:
        if kind and kind not in KINDS:
            return {"ok": False, "err": f"kind must be one of {', '.join(KINDS)}"}
        d["kind"] = kind
    _save(store)
    return {"ok": True}


def forget(mac: str) -> dict:
    """Drop a device that is gone for good from the list (it comes back if it is seen again)."""
    mac = (mac or "").lower()
    if load().demo:
        return {"ok": True, "demo": True}
    store = _load()
    if mac in store:
        del store[mac]
        _save(store)
    return {"ok": True}

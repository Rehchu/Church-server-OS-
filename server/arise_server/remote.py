"""Remote access: SSH, the VPN (Tailscale or WireGuard), browser remote desktop (Guacamole).

Everything reads state; the one write is adding a WireGuard peer, which hands
back a client config to paste into the WireGuard app on the off-site computer.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime

from . import demo
from .config import load
from .util import read_text, run, which

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{1,40}$")


def _remote_cfg():
    cfg = load()
    r = dict(cfg.raw.get("remote", {}) if isinstance(cfg.raw, dict) else {})
    r.setdefault("ssh_port", 22)
    r.setdefault("vpn", "tailscale")           # tailscale | wireguard | none
    r.setdefault("wg_interface", "wg0")
    r.setdefault("wg_endpoint", "")             # public-host:51820, set when the router forwards it
    r.setdefault("wg_subnet", "10.47.0.0/24")
    r.setdefault("guacamole_url", f"http://{cfg.system.hostname}:8084")
    r.setdefault("lan_subnet", "192.168.1.0/24")
    return r


def ssh_status() -> dict:
    rc = _remote_cfg()
    if load().demo or not which("systemctl"):
        return {"active": True, "port": rc["ssh_port"], "password_auth": False, "keys": 2, "last_logins": [
            {"user": "bradly", "from": "100.101.102.5 (tailscale)", "when": datetime.now().isoformat(timespec="minutes")},
            {"user": "bradly", "from": "192.168.1.41", "when": "2026-10-26T21:14"}]}
    act = run(["systemctl", "is-active", "ssh"], timeout=5)
    conf = read_text("/etc/ssh/sshd_config", "") + "\n" + "\n".join(read_text(os.path.join("/etc/ssh/sshd_config.d", f), "") for f in (os.listdir("/etc/ssh/sshd_config.d") if os.path.isdir("/etc/ssh/sshd_config.d") else []))
    pw = re.search(r"^\s*PasswordAuthentication\s+(\S+)", conf, re.M | re.I)
    keys = 0
    for home in ("/root", *[os.path.join("/home", u) for u in (os.listdir("/home") if os.path.isdir("/home") else [])]):
        keys += len([l for l in read_text(os.path.join(home, ".ssh", "authorized_keys"), "").splitlines() if l.strip() and not l.startswith("#")])
    last = run(["last", "-n", "8", "-w", "--time-format", "iso"], timeout=10)
    logins = []
    for line in last["out"].splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1].startswith("pts"):
            logins.append({"user": parts[0], "from": parts[2], "when": parts[3][:16]})
    return {"active": act["out"].strip() == "active", "port": rc["ssh_port"], "password_auth": (pw.group(1).lower() == "yes") if pw else True, "keys": keys, "last_logins": logins[:8]}


def tailscale_status() -> dict | None:
    if load().demo:
        return {"installed": True, "up": True, "self": {"name": "arise-server", "ip": "100.101.102.1", "dns": "arise-server.tailnet-xyz.ts.net"},
                "subnet_routes": ["192.168.1.0/24"], "peers": [
                    {"name": "bradly-macbook", "ip": "100.101.102.5", "os": "macOS", "online": True, "last_seen": "now", "site": "roaming"},
                    {"name": "alexandria-imac", "ip": "100.101.102.7", "os": "macOS", "online": True, "last_seen": "now", "site": "alexandria"},
                    {"name": "hub-office-pc", "ip": "100.101.102.9", "os": "Windows", "online": False, "last_seen": "2026-10-26T18:40", "site": "hub"},
                    {"name": "bradly-iphone", "ip": "100.101.102.12", "os": "iOS", "online": True, "last_seen": "now", "site": "roaming"}]}
    if not which("tailscale"):
        return {"installed": False}
    r = run(["tailscale", "status", "--json"], timeout=10)
    if not r["ok"]:
        return {"installed": True, "up": False, "error": (r["err"] or r["out"]).strip()[:200]}
    try:
        st = json.loads(r["out"])
    except json.JSONDecodeError:
        return {"installed": True, "up": False, "error": "could not read tailscale status"}
    me = st.get("Self", {})
    peers = []
    for p in (st.get("Peer") or {}).values():
        peers.append({"name": p.get("HostName"), "ip": (p.get("TailscaleIPs") or [""])[0], "os": p.get("OS"), "online": p.get("Online", False),
                      "last_seen": (p.get("LastSeen") or "")[:16], "site": ""})
    return {"installed": True, "up": st.get("BackendState") == "Running", "self": {"name": me.get("HostName"), "ip": (me.get("TailscaleIPs") or [""])[0], "dns": (me.get("DNSName") or "").rstrip(".")},
            "subnet_routes": me.get("PrimaryRoutes") or [], "peers": sorted(peers, key=lambda x: (not x["online"], x["name"] or ""))}


def wireguard_status() -> dict | None:
    rc = _remote_cfg()
    if load().demo:
        return {"installed": True, "up": True, "interface": rc["wg_interface"], "endpoint": "arise.dyndns.example:51820", "subnet": rc["wg_subnet"], "peers": _sample_peers()}
    if not which("wg"):
        return {"installed": False}
    r = run(["wg", "show", rc["wg_interface"], "dump"], timeout=10)
    if not r["ok"]:
        return {"installed": True, "up": False, "interface": rc["wg_interface"], "error": (r["err"] or "").strip()[:200]}
    names = _peer_names()
    peers = []
    lines = r["out"].splitlines()
    for line in lines[1:]:
        f = line.split("\t")
        if len(f) < 8:
            continue
        hs = int(f[4] or 0)
        peers.append({"name": names.get(f[0], f[0][:10] + "…"), "ip": f[3], "handshake": _ago(hs), "rx": int(f[5] or 0), "tx": int(f[6] or 0), "online": bool(hs) and (datetime.now().timestamp() - hs) < 180})
    return {"installed": True, "up": True, "interface": rc["wg_interface"], "endpoint": rc["wg_endpoint"], "subnet": rc["wg_subnet"], "peers": peers}


def _sample_peers() -> list[dict]:
    from . import demo_state
    return demo_state.get("wg.peers", [
        {"name": "alexandria-router", "ip": "10.47.0.2", "handshake": "28 s ago", "rx": 183_000_000, "tx": 912_000_000, "online": True},
        {"name": "hub-laptop", "ip": "10.47.0.5", "handshake": "2 days ago", "rx": 2_100_000, "tx": 4_400_000, "online": False}])


def next_peer_ip(conf: str, subnet: str) -> str | None:
    """Pure: the first free host address in the WireGuard subnet (.2 to .249), from the config's AllowedIPs."""
    prefix = subnet.split("/")[0].rsplit(".", 1)[0]
    used = set(re.findall(rf"AllowedIPs\s*=\s*{re.escape(prefix)}\.(\d+)/32", conf))
    n = next((i for i in range(2, 250) if str(i) not in used), None)
    return f"{prefix}.{n}" if n else None


def _ago(ts: int) -> str:
    if not ts:
        return "never"
    s = int(datetime.now().timestamp() - ts)
    return f"{s} s ago" if s < 60 else f"{s // 60} min ago" if s < 3600 else f"{s // 3600} h ago" if s < 86400 else f"{s // 86400} days ago"


def _peer_names() -> dict:
    out = {}
    d = "/etc/wireguard/peers"
    if os.path.isdir(d):
        for f in os.listdir(d):
            if f.endswith(".json"):
                try:
                    j = json.load(open(os.path.join(d, f)))
                    out[j["public_key"]] = j["name"]
                except Exception:
                    pass
    return out


def add_wireguard_peer(name: str) -> dict:
    """Create keys, add the peer to the live interface and its config, return the client config."""
    rc = _remote_cfg()
    if not NAME_RE.match(name or ""):
        return {"ok": False, "err": "name: letters, digits, dot, dash, underscore"}
    if not load().demo and not which("wg"):
        return {"ok": False, "err": "WireGuard is not installed (install.sh --wireguard); no peer was made"}
    if load().demo:
        peers = _sample_peers()
        if any(x["name"] == name for x in peers):
            return {"ok": False, "err": f"a device called {name} already has a key"}
        ip = next_peer_ip("".join(f"AllowedIPs = {x['ip']}/32\n" for x in peers), rc["wg_subnet"]) or "10.47.0.249"
        peers.append({"name": name, "ip": ip, "handshake": "never", "rx": 0, "tx": 0, "online": False})
        return {"ok": True, "demo": True, "name": name, "ip": ip, "config": f"[Interface]\nPrivateKey = (sample)\nAddress = {ip}/32\nDNS = 10.47.0.1\n\n[Peer]\nPublicKey = (server key)\nEndpoint = {rc['wg_endpoint'] or 'arise.example:51820'}\nAllowedIPs = {rc['wg_subnet']}, {rc['lan_subnet']}\nPersistentKeepalive = 25\n"}
    iface = rc["wg_interface"]
    conf_path = f"/etc/wireguard/{iface}.conf"
    conf = read_text(conf_path, "")
    if not conf:
        return {"ok": False, "err": f"{conf_path} not found; set up WireGuard first (installer/install.sh --with-wireguard)"}
    m = re.search(r"^\s*PrivateKey\s*=\s*(\S+)", conf, re.M)
    if not m:
        return {"ok": False, "err": "server PrivateKey missing from the config"}
    if name in _peer_names().values():
        return {"ok": False, "err": f"a device called {name} already has a key"}
    keys = [run(["wg", "pubkey"], timeout=5, input_text=m.group(1)), run(["wg", "genkey"], timeout=5)]
    if not all(k["ok"] for k in keys):
        return {"ok": False, "err": "wg could not make keys: " + next((k["err"] or k["out"]).strip() for k in keys if not k["ok"])[:200]}
    server_pub, priv = keys[0]["out"].strip(), keys[1]["out"].strip()
    pk, ps = run(["wg", "pubkey"], timeout=5, input_text=priv), run(["wg", "genpsk"], timeout=5)
    if not (pk["ok"] and ps["ok"]):
        return {"ok": False, "err": "wg could not make keys: " + ((pk["err"] or ps["err"]) or "").strip()[:200]}
    pub, psk = pk["out"].strip(), ps["out"].strip()
    ip = next_peer_ip(conf, rc["wg_subnet"])
    if not ip:
        return {"ok": False, "err": f"the WireGuard subnet {rc['wg_subnet']} is full"}
    with open(conf_path, "a", encoding="utf-8") as f:
        f.write(f"\n# {name} (added {datetime.now():%Y-%m-%d})\n[Peer]\nPublicKey = {pub}\nPresharedKey = {psk}\nAllowedIPs = {ip}/32\n")
    os.makedirs("/etc/wireguard/peers", exist_ok=True)
    with open(f"/etc/wireguard/peers/{name}.json", "w") as f:
        json.dump({"name": name, "public_key": pub, "ip": ip, "created": datetime.now().isoformat(timespec="seconds")}, f)
    r = run(["wg", "set", iface, "peer", pub, "preshared-key", "/dev/stdin", "allowed-ips", f"{ip}/32"], timeout=10, input_text=psk + "\n")
    client = (f"[Interface]\nPrivateKey = {priv}\nAddress = {ip}/32\nDNS = {rc['wg_subnet'].rsplit('.', 1)[0]}.1\n\n[Peer]\nPublicKey = {server_pub}\nPresharedKey = {psk}\n"
              f"Endpoint = {rc['wg_endpoint'] or '<public-address>:51820'}\nAllowedIPs = {rc['wg_subnet']}, {rc['lan_subnet']}\nPersistentKeepalive = 25\n")
    return {"ok": r["ok"], "err": None if r["ok"] else r["err"], "name": name, "ip": ip, "config": client}


def guacamole_status() -> dict:
    rc = _remote_cfg()
    if load().demo:
        return {"installed": True, "running": True, "url": rc["guacamole_url"], "connections": [
            {"name": "arise-server (SSH)", "protocol": "ssh"}, {"name": "Media Mac (VNC)", "protocol": "vnc"}, {"name": "Lobby PC (RDP)", "protocol": "rdp"}, {"name": "Alexandria iMac (VNC)", "protocol": "vnc"}]}
    if not which("docker"):
        return {"installed": False, "url": rc["guacamole_url"]}
    r = run(["docker", "ps", "--filter", "name=guacamole", "--format", "{{.Names}}|{{.Status}}"], timeout=10)
    rows = [l for l in r["out"].splitlines() if l.strip()]
    return {"installed": bool(rows), "running": any("Up" in l for l in rows), "url": rc["guacamole_url"], "connections": []}


def overview() -> dict:
    rc = _remote_cfg()
    cfg = load()
    out = {"demo": cfg.demo, "vpn_mode": rc["vpn"], "ssh": ssh_status(), "guacamole": guacamole_status(),
           "dashboard_url": f"http://{cfg.system.hostname}:{cfg.web.port}", "hostname": cfg.system.hostname}
    out["tailscale"] = tailscale_status()
    out["wireguard"] = wireguard_status()
    return out

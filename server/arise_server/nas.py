"""The Synology: mount state, free space, and DSM health when dsm_url is set."""
from __future__ import annotations

import json
import os
import shutil
import ssl
import urllib.parse
import urllib.request

from . import demo
from .config import load
from .util import read_json, run, which


def available() -> bool:
    return load().nas.enabled and not load().demo


def _mounted(path: str) -> bool:
    return os.path.ismount(path)


def status() -> dict:
    cfg = load()
    if cfg.demo:
        from . import demo_state
        return {"demo": True, **demo_state.get("nas", demo.NAS)}
    if not available():
        return {"demo": False, "enabled": False, "mounted": False, "host": cfg.nas.host, "mount": cfg.nas.mount,
                "note": "the Synology is not set up here yet ([nas] enabled = false in arise.toml)"}
    out = {"demo": False, "enabled": True, "host": cfg.nas.host, "mount": cfg.nas.mount, "protocol": cfg.nas.protocol, "share": cfg.nas.share,
           "mounted": _mounted(cfg.nas.mount), "total": None, "used": None, "free": None, "dsm": None, "domain_joined": None, "hyper_backup": None}
    if out["mounted"]:
        try:
            u = shutil.disk_usage(cfg.nas.mount)
            out.update({"total": u.total, "used": u.used, "free": u.free})
        except OSError:
            pass
    ping = run(["ping", "-c", "1", "-W", "2", cfg.nas.host], timeout=5)
    out["reachable"] = ping["ok"]
    if cfg.nas.dsm_url:
        out["dsm"] = dsm_health()
    return out


def mount() -> dict:
    cfg = load()
    if cfg.demo:
        from . import demo_state
        demo_state.get("nas", demo.NAS)["mounted"] = True
        return {"ok": True, "demo": True, "out": "(sample) mounted"}
    if not available():
        return {"ok": False, "err": "the Synology is not set up here ([nas] enabled = false in arise.toml)"}
    if _mounted(cfg.nas.mount):
        return {"ok": True, "out": "already mounted"}
    os.makedirs(cfg.nas.mount, exist_ok=True)
    r = run(mount_cmd(cfg.nas.protocol, cfg.nas.host, cfg.nas.share, cfg.nas.mount, os.path.join(os.path.dirname(cfg.nas.dsm_credentials_file), "synology.cred")), timeout=30)
    if not r["ok"]:
        return {"ok": False, "err": "mount: " + ((r["err"] or r["out"]).strip()[:300] or f"exit {r['code']}")}
    return {"ok": True, "out": f"mounted at {cfg.nas.mount}"}


def mount_cmd(protocol: str, host: str, share: str, mount: str, cred: str) -> list[str]:
    """Pure: the mount command for the Synology share (SMB 3 with a credentials file, or NFS)."""
    if protocol == "nfs":
        return ["mount", "-t", "nfs", f"{host}:/volume1/{share}", mount]
    opts = f"credentials={cred},vers=3.0,iocharset=utf8,uid=0,gid=0,file_mode=0660,dir_mode=0770,_netdev"
    return ["mount", "-t", "cifs", f"//{host}/{share}", mount, "-o", opts]


def unmount() -> dict:
    cfg = load()
    if cfg.demo:
        from . import demo_state
        demo_state.get("nas", demo.NAS)["mounted"] = False
        return {"ok": True, "demo": True, "out": "(sample) unmounted"}
    if not available():
        return {"ok": False, "err": "the Synology is not set up here ([nas] enabled = false in arise.toml)"}
    if not _mounted(cfg.nas.mount):
        return {"ok": True, "out": "not mounted"}
    r = run(["umount", cfg.nas.mount], timeout=30)
    return {"ok": True, "out": "unmounted"} if r["ok"] else {"ok": False, "err": "umount: " + ((r["err"] or r["out"]).strip()[:300] or f"exit {r['code']}")}


def dsm_health() -> dict:
    """Synology Web API: login, read system info and storage. Read-only."""
    cfg = load()
    creds = read_json(cfg.nas.dsm_credentials_file, default=None)
    if not creds:
        return {"ok": False, "error": f"no DSM credentials at {cfg.nas.dsm_credentials_file} (json with user/password)"}
    base = cfg.nas.dsm_url.rstrip("/")
    ctx = ssl.create_default_context()
    if creds.get("insecure"):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    def get(path, params):
        q = urllib.parse.urlencode(params)
        with urllib.request.urlopen(f"{base}/webapi/{path}?{q}", context=ctx, timeout=10) as r:
            return json.loads(r.read().decode())

    try:
        auth = get("auth.cgi", {"api": "SYNO.API.Auth", "version": "6", "method": "login", "account": creds["user"], "passwd": creds["password"], "session": "Core", "format": "sid"})
        if not auth.get("success"):
            return {"ok": False, "error": f"DSM login failed: {auth.get('error')}"}
        sid = auth["data"]["sid"]
        info = get("entry.cgi", {"api": "SYNO.Core.System", "version": "3", "method": "info", "_sid": sid}).get("data", {})
        stor = get("entry.cgi", {"api": "SYNO.Storage.CGI.Storage", "version": "1", "method": "load_info", "_sid": sid}).get("data", {})
        get("auth.cgi", {"api": "SYNO.API.Auth", "version": "6", "method": "logout", "session": "Core", "_sid": sid})
        vols = stor.get("volumes", []) or []
        disks = stor.get("disks", []) or []
        return {"ok": True, "model": info.get("model"), "version": info.get("firmware_ver"), "temperature": info.get("sys_temp"),
                "volume_status": ", ".join(sorted({v.get("status", "?") for v in vols})) or "?", "drives": len(disks),
                "raid": ", ".join(sorted({v.get("fs_type", "") + " " + (v.get("raid_type") or "") for v in vols})).strip() or "?",
                "uptime": info.get("up_time")}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}

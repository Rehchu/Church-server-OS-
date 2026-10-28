"""Active Directory via samba-tool. Everything shells out; nothing is cached.

Deleting a user is Bradly's click: DELETE needs confirm == name in the body,
and the home folder is never removed by this module.
"""
from __future__ import annotations

import os
import subprocess

import re

from . import demo
from .config import load
from .util import run, which

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{1,63}$")


def available() -> bool:
    cfg = load()
    return bool(which("samba-tool")) and cfg.directory.enabled and not cfg.demo


def _ok_name(name: str) -> bool:
    return bool(NAME_RE.match(name or ""))


def status() -> dict:
    cfg = load()
    if not available():
        return {"demo": True, **demo.DIRECTORY_STATUS}
    info = run(["samba-tool", "domain", "info", "127.0.0.1"], timeout=15)
    d = {"realm": cfg.directory.realm, "netbios": cfg.directory.netbios, "role": "Domain Controller", "dc": "", "forest_level": ""}
    for line in info["out"].splitlines():
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "dc name":
            d["dc"] = v
        elif k == "forest":
            d["realm"] = v.upper()
        elif k == "netbios domain":
            d["netbios"] = v
    lvl = run(["samba-tool", "domain", "level", "show"], timeout=15)
    m = re.search(r"Forest function level:\s*\(?([^)\n]+)", lvl["out"])
    if m:
        d["forest_level"] = m.group(1).strip()
    dns = run(["samba-tool", "dns", "query", "127.0.0.1", cfg.directory.realm.lower(), "@", "SRV", "-k", "yes"], timeout=15)
    d["dns_ok"] = dns["ok"]
    d["ldap_ok"] = info["ok"]
    d["kerberos_ok"] = run(["samba-tool", "domain", "info", "127.0.0.1"], timeout=15)["ok"]
    d["users"] = len(list_users()["users"])
    d["groups"] = len(list_groups()["groups"])
    d["computers"] = len(list_computers()["computers"])
    d["demo"] = False
    if not info["ok"]:
        d["error"] = info["err"] or info["out"]
    return d


def list_users() -> dict:
    if not available():
        return {"demo": True, "users": demo.USERS}
    r = run(["samba-tool", "user", "list"], timeout=20)
    names = sorted(n.strip() for n in r["out"].splitlines() if n.strip() and not n.startswith("krbtgt"))
    users = []
    for n in names:
        users.append(_user_detail(n))
    return {"demo": False, "users": users, "error": None if r["ok"] else r["err"]}


def _user_detail(name: str) -> dict:
    cfg = load()
    d = {"name": name, "display": name, "groups": [], "enabled": True, "last_logon": None, "home": f"\\\\{cfg.system.hostname}\\homes\\{name}"}
    r = run(["samba-tool", "user", "show", name], timeout=15)
    for line in r["out"].splitlines():
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if k == "displayName":
            d["display"] = v
        elif k == "userAccountControl":
            try:
                d["enabled"] = not (int(v) & 2)
            except ValueError:
                pass
        elif k == "lastLogon" and v not in ("0", ""):
            d["last_logon"] = v
        elif k == "memberOf":
            m = re.match(r"CN=([^,]+)", v)
            if m:
                d["groups"].append(m.group(1))
    return d


def add_user(name: str, password: str, display: str = "", groups: list[str] | None = None) -> dict:
    if not _ok_name(name):
        return {"ok": False, "err": "name: letters, digits, dot, dash, underscore; 2-64 chars; starts with a letter"}
    if len(password or "") < 8:
        return {"ok": False, "err": "password: at least 8 characters"}
    if not available():
        return {"ok": True, "demo": True, "out": f"(demo) created {name}"}
    cmd = ["samba-tool", "user", "create", name, password, "--home-directory", f"\\\\{load().system.hostname}\\homes\\{name}", "--home-drive", "H:"]
    if display:
        cmd += ["--given-name", display.split(" ")[0], "--surname", " ".join(display.split(" ")[1:]) or display]
    r = run(cmd, timeout=30)
    if not r["ok"]:
        return r
    _mkhome(name)
    for g in groups or []:
        run(["samba-tool", "group", "addmembers", g, name], timeout=20)
    return r


def _mkhome(name: str):
    import os
    cfg = load()
    p = os.path.join(cfg.directory.homes_path, name)
    try:
        os.makedirs(p, exist_ok=True)
        os.chmod(p, 0o700)
        run(["chown", f"{name}:", p], timeout=10)  # idmap maps the AD user via winbind
    except OSError:
        pass


def set_password(name: str, password: str) -> dict:
    if not _ok_name(name) or len(password or "") < 8:
        return {"ok": False, "err": "bad name or password shorter than 8"}
    if not available():
        return {"ok": True, "demo": True}
    return run(["samba-tool", "user", "setpassword", name, "--newpassword", password], timeout=30)


def enable_user(name: str, enabled: bool) -> dict:
    if not _ok_name(name):
        return {"ok": False, "err": "bad name"}
    if not available():
        return {"ok": True, "demo": True}
    return run(["samba-tool", "user", "enable" if enabled else "disable", name], timeout=20)


def delete_user(name: str, confirm: str) -> dict:
    if confirm != name:
        return {"ok": False, "err": "type the user name to confirm; the home folder is kept either way"}
    if not _ok_name(name):
        return {"ok": False, "err": "bad name"}
    if not available():
        return {"ok": True, "demo": True}
    return run(["samba-tool", "user", "delete", name], timeout=20)


def list_groups() -> dict:
    if not available():
        return {"demo": True, "groups": demo.GROUPS}
    r = run(["samba-tool", "group", "list"], timeout=20)
    hide = {"Allowed RODC Password Replication Group", "Denied RODC Password Replication Group", "Read-only Domain Controllers",
            "Enterprise Read-only Domain Controllers", "Cert Publishers", "RAS and IAS Servers", "DnsUpdateProxy", "DnsAdmins",
            "Pre-Windows 2000 Compatible Access", "Incoming Forest Trust Builders", "Windows Authorization Access Group",
            "Terminal Server License Servers", "Distributed COM Users", "Performance Monitor Users", "Performance Log Users",
            "Cryptographic Operators", "Event Log Readers", "Certificate Service DCOM Access", "Group Policy Creator Owners",
            "Enterprise Admins", "Schema Admins", "Domain Controllers", "Domain Computers", "Domain Guests", "Guests",
            "Users", "Account Operators", "Backup Operators", "Print Operators", "Server Operators", "Replicator",
            "Network Configuration Operators", "Remote Desktop Users", "IIS_IUSRS", "Protected Users", "Key Admins",
            "Enterprise Key Admins", "Storage Replica Administrators"}
    groups = []
    for n in sorted(x.strip() for x in r["out"].splitlines() if x.strip()):
        if n in hide:
            continue
        m = run(["samba-tool", "group", "listmembers", n], timeout=15)
        groups.append({"name": n, "members": [x.strip() for x in m["out"].splitlines() if x.strip()], "description": ""})
    return {"demo": False, "groups": groups}


def add_group(name: str, description: str = "") -> dict:
    if not _ok_name(name.replace(" ", "_")):
        return {"ok": False, "err": "bad group name"}
    if not available():
        return {"ok": True, "demo": True}
    cmd = ["samba-tool", "group", "add", name]
    if description:
        cmd += ["--description", description]
    return run(cmd, timeout=20)


def add_member(group: str, user: str) -> dict:
    if not available():
        return {"ok": True, "demo": True}
    return run(["samba-tool", "group", "addmembers", group, user], timeout=20)


def remove_member(group: str, user: str) -> dict:
    if not available():
        return {"ok": True, "demo": True}
    return run(["samba-tool", "group", "removemembers", group, user], timeout=20)


def list_computers() -> dict:
    if not available():
        return {"demo": True, "computers": demo.COMPUTERS}
    r = run(["samba-tool", "computer", "list"], timeout=20)
    out = []
    for n in sorted(x.strip().rstrip("$") for x in r["out"].splitlines() if x.strip()):
        d = {"name": n, "os": "", "kind": "pc", "last_seen": None, "ip": ""}
        s = run(["samba-tool", "computer", "show", n], timeout=15)
        for line in s["out"].splitlines():
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip()
            if k == "operatingSystem":
                d["os"] = v
                low = v.lower()
                d["kind"] = "mac" if "mac" in low else "nas" if "synology" in low or "dsm" in low else "windows" if "windows" in low else "pc"
            elif k == "lastLogon" and v not in ("0", ""):
                d["last_seen"] = v
        out.append(d)
    return {"demo": False, "computers": out}


def user_groups(name: str) -> list[str]:
    """Group names the user belongs to (direct and nested)."""
    if not _ok_name(name):
        return []
    if not available():
        u = next((x for x in demo.USERS if x["name"] == name), None)
        return list(u["groups"]) if u else []
    r = run(["samba-tool", "user", "getgroups", name], timeout=20)
    if not r["ok"]:
        return []
    return [g.strip() for g in r["out"].splitlines() if g.strip()]


def authenticate(name: str, password: str) -> bool:
    """Is this the directory password for this user? A Kerberos login against the
    local KDC, which is the same check a Mac or PC makes at its login window.
    No LDAP library, no bind account: kinit is on every domain controller."""
    if not _ok_name(name) or not password:
        return False
    if not available():
        # sample mode: any listed, enabled user with any password
        u = next((x for x in demo.USERS if x["name"] == name), None)
        return bool(u and u["enabled"])
    realm = load().directory.realm.upper()
    if which("kinit"):
        env = dict(os.environ, KRB5CCNAME="MEMORY:arise-login")
        try:
            p = subprocess.run(["kinit", f"{name}@{realm}"], input=password + "\n", capture_output=True, text=True, timeout=15, env=env)
            return p.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False
    if which("smbclient"):  # fallback: an SMB session against ourselves
        r = run(["smbclient", "-L", "127.0.0.1", "-U", f"{name}%{password}"], timeout=15)
        return r["ok"]
    return False


def is_admin(name: str) -> bool:
    cfg = load()
    if name == cfg.web.admin_user:
        return True
    admins = cfg.web.get("admins_group", "Domain Admins")
    return admins in user_groups(name)

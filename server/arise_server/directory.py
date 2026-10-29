"""Active Directory via samba-tool. Everything shells out; nothing is cached.

Deleting a user is Bradly's click: DELETE needs confirm == name in the body,
and the home folder is never removed by this module.
"""
from __future__ import annotations

import os
import subprocess

import re

from datetime import datetime, timedelta, timezone

from . import demo, demo_state
from .config import load
from .util import run, which

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{1,63}$")
GROUP_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 ._'-]{1,63}$")


def available() -> bool:
    cfg = load()
    return bool(which("samba-tool")) and cfg.directory.enabled and not cfg.demo


def _ok_name(name: str) -> bool:
    return bool(NAME_RE.match(name or ""))


def _ok_group(name: str) -> bool:
    return bool(GROUP_RE.match(name or "")) and not name.endswith(" ")


def _no_domain() -> dict:
    """A real server with no domain to talk to: a result to report, not a sample to show."""
    cfg = load()
    why = ("the directory is turned off in arise.toml ([directory] enabled = false)" if not cfg.directory.enabled
           else "samba-tool is not installed (install.sh step 5 provisions the domain)")
    return {"ok": False, "err": f"No domain on this server: {why}"}


def _failed(r: dict, what: str, secret: str | None = None) -> dict:
    """A command that did not work is a result to report, with the tool's own words."""
    msg = (r.get("err") or r.get("out") or "").strip()
    # samba-tool prints "ERROR(...): <what happened>"; keep the last line, it is the reason
    last = msg.splitlines()[-1] if msg else ""
    return {"ok": False, "err": _redact(f"{what}: {last or 'samba-tool exited ' + str(r.get('code'))}", secret), "code": r.get("code"),
            "cmd": _redact(r.get("cmd", ""), secret)}


def _redact(text: str, secret: str | None = None) -> str:
    """Never echo a password back to the browser or a log (samba-tool takes it on the command line)."""
    text = re.sub(r"(--newpassword[= ])\S+", r"\1********", text or "")
    return text.replace(secret, "********") if secret else text


# ---- the sample directory (demo mode): a real list that clicks change ----------
def _users() -> list[dict]:
    return demo_state.get("dir.users", demo.USERS)


def _groups() -> list[dict]:
    return demo_state.get("dir.groups", demo.GROUPS)


def _u(name: str) -> dict | None:
    return next((x for x in _users() if x["name"].lower() == (name or "").lower()), None)


def _g(name: str) -> dict | None:
    return next((x for x in _groups() if x["name"].lower() == (name or "").lower()), None)


def filetime_iso(v: str) -> str | None:
    """samba-tool shows lastLogon as a Windows FILETIME (100 ns since 1601). 0 = never."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return v or None
    if n <= 0:
        return None
    dt = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=n // 10)
    return dt.astimezone().isoformat(timespec="seconds")


def status() -> dict:
    cfg = load()
    if not available():
        if not load().demo:
            return {"demo": False, "error": _no_domain()["err"], "users": 0, "groups": 0, "computers": 0, "realm": cfg.directory.realm, "netbios": cfg.directory.netbios}
        return {"demo": True, **demo.DIRECTORY_STATUS, "users": len(_users()), "groups": len(_groups()), "computers": len(demo.COMPUTERS)}
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
        if not load().demo:
            return {"demo": False, "users": [], "error": _no_domain()["err"]}
        mc = demo_state.get("dir.mustchange", set())
        return {"demo": True, "users": [dict(u, must_change=u["name"].lower() in mc) for u in _users()]}
    r = run(["samba-tool", "user", "list"], timeout=20)
    if not r["ok"]:
        return {"demo": False, "users": [], "error": _failed(r, "could not list the users")["err"]}
    names = sorted(n.strip() for n in r["out"].splitlines() if n.strip() and not n.startswith("krbtgt"))
    users = [_user_detail(n) for n in names]
    return {"demo": False, "users": users, "error": None}


def parse_user_show(name: str, text: str, hostname: str = "arise-server") -> dict:
    """Pure: one `samba-tool user show <name>` into the dashboard's row."""
    d = {"name": name, "display": name, "groups": [], "enabled": True, "last_logon": None, "home": f"\\\\{hostname}\\homes\\{name}"}
    for line in text.splitlines():
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if k == "displayName":
            d["display"] = v
        elif k == "userAccountControl":
            try:
                d["enabled"] = not (int(v) & 2)   # ACCOUNTDISABLE
            except ValueError:
                pass
        elif k in ("lastLogon", "lastLogonTimestamp") and v not in ("0", ""):
            d["last_logon"] = filetime_iso(v) if k == "lastLogon" or not d["last_logon"] else d["last_logon"]
        elif k == "memberOf":
            m = re.match(r"CN=([^,]+)", v)
            if m:
                d["groups"].append(m.group(1))
        elif k == "homeDirectory" and v:
            d["home"] = v
        elif k == "pwdLastSet":
            d["must_change"] = v == "0"   # 0 = "must change at next logon"
    return d


def _user_detail(name: str) -> dict:
    r = run(["samba-tool", "user", "show", name], timeout=15)
    d = parse_user_show(name, r["out"], load().system.hostname)
    if not r["ok"]:
        d["error"] = _failed(r, f"could not read {name}")["err"]
    return d


def add_user(name: str, password: str, display: str = "", groups: list[str] | None = None, temporary: bool = False) -> dict:
    """temporary: the password is a first one; AD makes them choose their own at the next login,
    on a Mac's login window or here (round 5, 5: pwdLastSet = 0)."""
    name = (name or "").strip()
    if not _ok_name(name):
        return {"ok": False, "err": "name: letters, digits, dot, dash, underscore; 2-64 chars; starts with a letter (first.last)"}
    if len(password or "") < 8:
        return {"ok": False, "err": "password: at least 8 characters"}
    groups = [g for g in (groups or []) if g]
    bad = [g for g in groups if not _ok_group(g)]
    if bad:
        return {"ok": False, "err": f"not a group name: {', '.join(bad)}"}
    if not available():
        if not load().demo:
            return _no_domain()
        with demo_state._lock:
            if _u(name):
                return {"ok": False, "err": f"{name} already exists"}
            missing = [g for g in groups if not _g(g)]
            if missing:
                return {"ok": False, "err": f"no such group: {', '.join(missing)}"}
            host = load().system.hostname
            row = {"name": name, "display": (display or "").strip() or name, "groups": [], "enabled": True, "last_logon": None, "home": f"\\\\{host}\\homes\\{name}"}
            _users().append(row)
            demo_state.get("dir.passwords", {})[name.lower()] = password
            if temporary:
                demo_state.get("dir.mustchange", set()).add(name.lower())
            for g in groups:
                _add_member_demo(_g(g), row)
        return {"ok": True, "demo": True, "out": f"(sample) created {name}", "user": row}
    cmd = ["samba-tool", "user", "create", name, password, "--home-directory", f"\\\\{load().system.hostname}\\homes\\{name}", "--home-drive", "H:"]
    if temporary:
        cmd.append("--must-change-at-next-login")
    if display:
        parts = display.strip().split(" ")
        cmd += ["--given-name", parts[0]]
        if len(parts) > 1:
            cmd += ["--surname", " ".join(parts[1:])]
    r = run(cmd, timeout=30)
    if not r["ok"]:
        return _failed(r, f"could not create {name}", password)
    _mkhome(name)
    failed = []
    for g in groups:
        m = run(["samba-tool", "group", "addmembers", g, name], timeout=20)
        if not m["ok"]:
            failed.append(f"{g} ({_failed(m, 'addmembers')['err'].split(': ', 1)[-1]})")
    out = {"ok": not failed, "out": f"created {name}", "user": name}
    if failed:
        out["err"] = f"{name} was created, but not added to: {'; '.join(failed)}"
        out["created"] = True
    return out


def _mkhome(name: str):
    cfg = load()
    p = os.path.join(cfg.directory.homes_path, name)
    try:
        os.makedirs(p, exist_ok=True)
        os.chmod(p, 0o700)
        run(["chown", f"{name}:", p], timeout=10)  # idmap maps the AD user via winbind
    except OSError:
        pass


def set_password(name: str, password: str, temporary: bool = False) -> dict:
    """temporary: an admin's reset; they choose their own at the next login (Mac or here)."""
    if not _ok_name(name):
        return {"ok": False, "err": "bad name"}
    if len(password or "") < 8:
        return {"ok": False, "err": "password: at least 8 characters"}
    if not available():
        if not load().demo:
            return _no_domain()
        if not _u(name):
            return {"ok": False, "err": f"no such user: {name}"}
        demo_state.get("dir.passwords", {})[name.lower()] = password
        mc = demo_state.get("dir.mustchange", set())
        (mc.add if temporary else mc.discard)(name.lower())
        return {"ok": True, "demo": True, "out": f"(sample) new password for {name}", "must_change": bool(temporary)}
    r = run(["samba-tool", "user", "setpassword", name, f"--newpassword={password}"] + (["--must-change-at-next-login"] if temporary else []), timeout=30)
    if not r["ok"]:
        return _failed(r, f"could not set {name}'s password", password)
    from .auth import revoke_sessions
    revoke_sessions(name)   # a new password signs out every device that used the old one
    return {"ok": True, "out": f"new password set for {name}", "must_change": bool(temporary)}


def enable_user(name: str, enabled: bool) -> dict:
    if not _ok_name(name):
        return {"ok": False, "err": "bad name"}
    if not available():
        if not load().demo:
            return _no_domain()
        u = _u(name)
        if not u:
            return {"ok": False, "err": f"no such user: {name}"}
        u["enabled"] = bool(enabled)
        return {"ok": True, "demo": True, "out": f"(sample) {name} {'enabled' if enabled else 'disabled'}", "enabled": u["enabled"]}
    r = run(["samba-tool", "user", "enable" if enabled else "disable", name], timeout=20)
    if not r["ok"]:
        return _failed(r, f"could not {'enable' if enabled else 'disable'} {name}")
    if not enabled:
        from .auth import revoke_sessions
        revoke_sessions(name)   # a disabled account's open sessions end now, not in a year
    return {"ok": True, "out": f"{name} {'enabled' if enabled else 'disabled'}", "enabled": bool(enabled)}


def delete_user(name: str, confirm: str) -> dict:
    if confirm != name:
        return {"ok": False, "err": "type the user name to confirm; the home folder is kept either way"}
    if not _ok_name(name):
        return {"ok": False, "err": "bad name"}
    if not available():
        if not load().demo:
            return _no_domain()
        with demo_state._lock:
            u = _u(name)
            if not u:
                return {"ok": False, "err": f"no such user: {name}"}
            _users().remove(u)
            for g in _groups():
                g["members"] = [m for m in g.get("members", []) if m.lower() != name.lower()]
            demo_state.get("dir.passwords", {}).pop(name.lower(), None)
        return {"ok": True, "demo": True, "out": f"(sample) deleted {name}; the home folder is kept"}
    r = run(["samba-tool", "user", "delete", name], timeout=20)
    if not r["ok"]:
        return _failed(r, f"could not delete {name}")
    from .auth import revoke_sessions
    revoke_sessions(name)
    return {"ok": True, "out": f"deleted {name}; the home folder is kept"}


def list_groups() -> dict:
    if not available():
        if not load().demo:
            return {"demo": False, "groups": [], "error": _no_domain()["err"]}
        return {"demo": True, "groups": _groups()}
    r = run(["samba-tool", "group", "list"], timeout=20)
    if not r["ok"]:
        return {"demo": False, "groups": [], "error": _failed(r, "could not list the groups")["err"]}
    groups = []
    for n in sorted(x.strip() for x in r["out"].splitlines() if x.strip()):
        if n in HIDDEN_GROUPS:
            continue
        m = run(["samba-tool", "group", "listmembers", n], timeout=15)
        groups.append({"name": n, "members": [x.strip() for x in m["out"].splitlines() if x.strip()], "description": ""})
    return {"demo": False, "groups": groups}


HIDDEN_GROUPS = {"Allowed RODC Password Replication Group", "Denied RODC Password Replication Group", "Read-only Domain Controllers",
                 "Enterprise Read-only Domain Controllers", "Cert Publishers", "RAS and IAS Servers", "DnsUpdateProxy", "DnsAdmins",
                 "Pre-Windows 2000 Compatible Access", "Incoming Forest Trust Builders", "Windows Authorization Access Group",
                 "Terminal Server License Servers", "Distributed COM Users", "Performance Monitor Users", "Performance Log Users",
                 "Cryptographic Operators", "Event Log Readers", "Certificate Service DCOM Access", "Group Policy Creator Owners",
                 "Enterprise Admins", "Schema Admins", "Domain Controllers", "Domain Computers", "Domain Guests", "Guests",
                 "Users", "Account Operators", "Backup Operators", "Print Operators", "Server Operators", "Replicator",
                 "Network Configuration Operators", "Remote Desktop Users", "IIS_IUSRS", "Protected Users", "Key Admins",
                 "Enterprise Key Admins", "Storage Replica Administrators"}


def add_group(name: str, description: str = "") -> dict:
    name = (name or "").strip()
    if not _ok_group(name):
        return {"ok": False, "err": "group name: letters, digits, space, dot, dash; 2-64 chars; starts with a letter"}
    if not available():
        if not load().demo:
            return _no_domain()
        if _g(name):
            return {"ok": False, "err": f"group {name} already exists"}
        row = {"name": name, "members": [], "description": (description or "").strip()}
        _groups().append(row)
        return {"ok": True, "demo": True, "out": f"(sample) group {name} added", "group": row}
    cmd = ["samba-tool", "group", "add", name]
    if description:
        cmd += ["--description", description]
    r = run(cmd, timeout=20)
    return {"ok": True, "out": f"group {name} added"} if r["ok"] else _failed(r, f"could not add group {name}")


def _add_member_demo(g: dict, u: dict):
    if u["name"] not in g.setdefault("members", []):
        g["members"].append(u["name"])
    if g["name"] not in u.setdefault("groups", []):
        u["groups"].append(g["name"])


def add_member(group: str, user: str) -> dict:
    if not _ok_group(group) or not _ok_name(user):
        return {"ok": False, "err": "bad group or user name"}
    if not available():
        if not load().demo:
            return _no_domain()
        g, u = _g(group), _u(user)
        if not g:
            return {"ok": False, "err": f"no such group: {group}"}
        if not u:
            return {"ok": False, "err": f"no such user: {user}"}
        _add_member_demo(g, u)
        return {"ok": True, "demo": True, "out": f"(sample) {user} added to {group}"}
    r = run(["samba-tool", "group", "addmembers", group, user], timeout=20)
    return {"ok": True, "out": f"{user} added to {group}"} if r["ok"] else _failed(r, f"could not add {user} to {group}")


def remove_member(group: str, user: str) -> dict:
    if not _ok_group(group) or not _ok_name(user):
        return {"ok": False, "err": "bad group or user name"}
    if not available():
        if not load().demo:
            return _no_domain()
        g, u = _g(group), _u(user)
        if not g:
            return {"ok": False, "err": f"no such group: {group}"}
        if not u or u["name"] not in g.get("members", []):
            return {"ok": False, "err": f"{user} is not in {group}"}
        g["members"].remove(u["name"])
        u["groups"] = [x for x in u.get("groups", []) if x != g["name"]]
        return {"ok": True, "demo": True, "out": f"(sample) {user} removed from {group}"}
    r = run(["samba-tool", "group", "removemembers", group, user], timeout=20)
    return {"ok": True, "out": f"{user} removed from {group}"} if r["ok"] else _failed(r, f"could not remove {user} from {group}")


def list_computers() -> dict:
    if not available():
        if not load().demo:
            return {"demo": False, "computers": [], "error": _no_domain()["err"]}
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
        if not load().demo:
            return []
        u = _u(name)
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
        if not load().demo:
            return False
        # sample mode: an enabled user; one created (or re-passworded) in the sample needs that password,
        # the seeded sample people take any password
        u = _u(name)
        if not u or not u.get("enabled", True):
            return False
        pw = demo_state.get("dir.passwords", {}).get(name.lower())
        return pw is None or pw == password
    realm = load().directory.realm.upper()
    if which("kinit"):
        env = dict(os.environ, KRB5CCNAME="MEMORY:arise-login")
        try:
            p = subprocess.run(["kinit", f"{name}@{realm}"], input=password + "\n", capture_output=True, text=True, timeout=15, env=env)
            return p.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False
    if which("smbclient"):  # fallback: an SMB session against ourselves; the password goes in the
        # environment (PASSWD), never on the command line where `ps` would show it
        try:
            p = subprocess.run(["smbclient", "-L", "127.0.0.1", "-U", name, "-m", "SMB3"], capture_output=True, text=True, timeout=15,
                               env=dict(os.environ, PASSWD=password))
            return p.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False
    return False


# ---- "must change at next logon": the sign-in tells a wrong password from an expired one ----
EXPIRED_RE = re.compile(r"(?i)password (has )?expired|key has expired|must change (it|your password)|password change required")


def classify_kinit(code: int, text: str) -> str:
    """Pure: kinit's answer -> 'ok' | 'expired' | 'bad'. An expired password was the right one:
    the KDC only says so after the password checked out."""
    if code == 0:
        return "ok"
    return "expired" if EXPIRED_RE.search(text or "") else "bad"


def check_login(name: str, password: str) -> str:
    """'ok', 'expired' (right password, but AD says choose a new one first) or 'bad'."""
    if not _ok_name(name) or not password:
        return "bad"
    if not available():
        if not load().demo:
            return "bad"
        if not authenticate(name, password):
            return "bad"
        return "expired" if name.lower() in demo_state.get("dir.mustchange", set()) else "ok"
    if not which("kinit"):
        return "ok" if authenticate(name, password) else "bad"
    realm = load().directory.realm.upper()
    try:
        p = subprocess.run(["kinit", f"{name}@{realm}"], input=password + "\n", capture_output=True, text=True, timeout=15,
                           env=dict(os.environ, KRB5CCNAME="MEMORY:arise-check"))
    except (subprocess.TimeoutExpired, OSError):
        return "bad"
    return classify_kinit(p.returncode, (p.stdout or "") + (p.stderr or ""))


def change_expired(name: str, old: str, new: str) -> dict:
    """The person chooses their own password in place of a temporary one. Through kinit's own
    change (the kpasswd protocol), as that person, so the domain's rules apply exactly as at a Mac."""
    if not _ok_name(name):
        return {"ok": False, "err": "bad name"}
    if len(new or "") < 8:
        return {"ok": False, "err": "at least 8 characters"}
    if new == old:
        return {"ok": False, "err": "choose a password different from the temporary one"}
    state = check_login(name, old)
    if state == "bad":
        return {"ok": False, "err": "Wrong user or password"}
    if not available():
        if not load().demo:
            return _no_domain()
        demo_state.get("dir.passwords", {})[name.lower()] = new
        demo_state.get("dir.mustchange", set()).discard(name.lower())
        return {"ok": True, "demo": True}
    if state == "ok":   # nothing to change on the domain's side; an ordinary change
        r = run(["samba-tool", "user", "setpassword", name, f"--newpassword={new}"], timeout=30)
        return {"ok": True} if r["ok"] else _failed(r, "the domain refused the new password", new)
    realm = load().directory.realm.upper()
    try:
        p = subprocess.run(["kinit", f"{name}@{realm}"], input=f"{old}\n{new}\n{new}\n", capture_output=True, text=True, timeout=20,
                           env=dict(os.environ, KRB5CCNAME="MEMORY:arise-change"))
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"ok": False, "err": f"could not reach the domain: {e}"}
    if p.returncode == 0:
        return {"ok": True}
    msg = [ln for ln in ((p.stderr or "") + (p.stdout or "")).splitlines() if ln.strip() and "password" in ln.lower()]
    return {"ok": False, "err": _redact((msg[-1] if msg else "the domain refused the new password").strip(), new).replace(old, "********")}


def is_admin(name: str) -> bool:
    cfg = load()
    if name == cfg.web.admin_user:
        return True
    admins = cfg.web.get("admins_group", "Domain Admins")
    return admins in user_groups(name)


# ---- the password rules, in words ------------------------------------------------
def rules_from_show(text: str) -> dict:
    """`samba-tool domain passwordsettings show` as words. Only what the domain
    reports is said; nothing is assumed. Pure."""
    import re as _re
    get = lambda label: (_re.search(label + r":\s*(\S+)", text or "") or [None, None])[1]
    min_len = get(r"Minimum password length")
    complexity = get(r"Password complexity")
    history = get(r"Password history length")
    max_age = get(r"Maximum password age \(days\)")
    words = []
    if min_len and min_len.isdigit():
        words.append(f"At least {min_len} characters")
    if complexity and complexity.lower() == "on":
        words.append("Three of the four kinds: capitals, small letters, numbers, symbols")
        words.append("Not your name or any part of it")
    if history and history.isdigit() and int(history) > 0:
        words.append(f"Not one of your last {history} passwords")
    if max_age is not None:
        words.append("Never expires" if max_age == "0" else f"Expires after {max_age} days")
    return {"min_length": int(min_len) if min_len and min_len.isdigit() else None, "complexity": (complexity or "").lower() == "on",
            "history": int(history) if history and history.isdigit() else None, "max_age_days": int(max_age) if max_age and max_age.isdigit() else None, "words": words}


# What installer/install.sh step 5b sets (no history line: the installer leaves that to the domain's default).
_DEMO_SHOW = "Minimum password length: 12\nPassword complexity: on\nMaximum password age (days): 0\n"


def password_rules() -> dict:
    if not available():
        if not load().demo:
            return {"min_length": 8, "complexity": None, "history": None, "max_age_days": None,
                    "words": ["At least 8 characters (there is no domain here to ask; this is the dashboard's own floor)"], "err": _no_domain()["err"]}
        return {**rules_from_show(_DEMO_SHOW), "demo": True}
    r = run(["samba-tool", "domain", "passwordsettings", "show"], timeout=20)
    if not r["ok"]:
        return {"min_length": 8, "complexity": None, "history": None, "max_age_days": None, "words": ["At least 8 characters (the domain did not answer; this is the dashboard's own floor)"], "err": r["err"]}
    return rules_from_show(r["out"])

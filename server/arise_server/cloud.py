"""Mac and phone syncing (docs/ANSWERS.md round 6, rows 13-19, 39, 40): Nextcloud
over the server's own folders. docs/SYNC.md is the plain-words version.

How the pieces fit:

* A person's Nextcloud files ARE their server home folder. Nextcloud keeps each
  user's files in <data>/<user>/files; ariseOS makes that a link to
  /homes/<user> inside the container (the host's /srv/arise/homes/<user>), so
  the Mac over SMB, the dashboard's Finder and every Nextcloud client see one
  set of files. Desktop and Documents sync in full on the Macs (row 13).
* The shares are Nextcloud "Local" storages over the same folders: Church
  (everyone), each department (two mounts at one place: read-write for staff,
  admins and the department's own login, read-only for the department's people,
  the higher priority winning, so the rule is sharing.folder_access's), Pastors
  (the two pastors), and Shared with me (/shared/<user>, the links
  sharing.py places). Nextcloud's own sharing is off: sharing stays the
  server's Share with…, so SMB, the dashboard and the clients agree.
  Why Local and not SMB storages: SMB storages need each person's domain
  password at the moment they sync, and a linked local account (R6-MAC) or a
  phone signs in with a device app password only. Local storages work with app
  passwords; the price is that Nextcloud reads the folders as its own user
  (www-data, uid 33, given rwX by ACL), so who-sees-what is enforced by the
  mounts' applicable users and groups, which this module derives from the same
  rules as the Samba lines.
* Changes made over SMB reach the clients through `arise-cloud-watch`, which
  turns inotify events into `occ files:scan --shallow` of just that folder.
* Conflicts, row 15 "newest wins": the hourly sweep finds the clients'
  "(conflicted copy …)" files; the newer copy keeps the name and the older one
  goes to that place's Trash (the dashboard's 30-day Trash). Nothing is deleted.
* Every client signs in with a device app password the server issues
  (app_password), never a domain password; revoke() cuts a device or a person off.

Reachable only on the church network and over Tailscale, through Caddy on the
church certificate (cloud.<realm>); the container publishes on 127.0.0.1 only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import threading
import time
from datetime import datetime

from . import audit, demo_state
from .config import load
from .util import read_json, run, which, write_json

LOCAL = "\\OC\\Files\\Storage\\Local"
SCANNER = "arise-sync"   # Nextcloud's own admin (made at install): scans the mounts, never a person
SERVICE_ACCOUNT = "arise-nextcloud"   # the domain account Nextcloud reads the directory with; signs no one in
SECRETS_ENV = "/etc/arise/secrets/apps/nextcloud.env"
IN = {"homes": "/homes", "shares": "/shares", "shared": "/shared", "pastors": "/pastors"}
DEVICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,59}$")
USER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
CONFLICT_RES = [
    # Nextcloud desktop 3.x: "Budget (conflicted copy 2026-10-29 101500).xlsx", optionally with a name before the date
    re.compile(r"^(?P<stem>.+?) \(conflicted copy(?: [^()]*?)? (?P<date>\d{4}-\d{2}-\d{2} \d{6})\)(?P<ext>\.[^.]+)?$"),
    # older clients: "Budget_conflict-20261029-101500.xlsx"
    re.compile(r"^(?P<stem>.+?)_conflict-(?P<date>\d{8}-\d{6})(?P<ext>\.[^.]+)?$"),
]
SKIP_DIRS = {".Trash", ".sync", ".nextcloudsync.log", "__MACOSX"}
_lock = threading.Lock()


# ----- where things are ---------------------------------------------------------
def host() -> str:
    cfg = load()
    return str(cfg.cloud.host or "") or "cloud." + str(cfg.directory.realm).lower()


def url() -> str:
    return "https://" + host()


def paths() -> dict:
    """The host paths the container mounts (and where Nextcloud keeps its records)."""
    from . import sharing
    cfg = load()
    data_root = cfg.system.data_root.rstrip("/")
    return {
        "homes": cfg.directory.homes_path.rstrip("/"),
        "shares": os.path.join(data_root, "shares"),
        "shared": str(cfg.storage.shared_path or os.path.join(data_root, "shared")).rstrip("/"),
        "pastors": sharing.pastors_path().rstrip("/"),
        "data": str(cfg.cloud.data_dir or os.path.join(cfg.apps.root, "nextcloud", "data")).rstrip("/"),
    }


def label(dept: str) -> str:
    """childrens-department -> 'Childrens Department' (the folder's name in Finder's sidebar)."""
    return " ".join(p[:1].upper() + p[1:] for p in dept.replace("_", "-").split("-"))


# ----- the mounts, from the same rules as the Samba lines --------------------------
def mounts() -> list[dict]:
    """Pure given the config: every Nextcloud Local storage ariseOS manages.
    users/groups empty = everyone. The scanner is added to every restricted mount."""
    from . import sharing
    cfg = load()
    church = str(cfg.storage.church_folder)
    out = [{"mount_point": "/" + label(church), "datadir": f"{IN['shares']}/{church}", "users": [], "groups": [],
            "readonly": False, "priority": 100, "why": "row 16: every account writes"}]
    for d in sharing.departments():
        writers_u = sorted(sharing.department_accounts(d))
        out.append({"mount_point": "/" + label(d), "datadir": f"{IN['shares']}/{d}", "users": writers_u + [SCANNER],
                    "groups": [str(cfg.storage.staff_group), "Domain Admins"], "readonly": False, "priority": 200,
                    "why": "row 17: staff, admins and the department's own login write"})
        out.append({"mount_point": "/" + label(d), "datadir": f"{IN['shares']}/{d}", "users": [],
                    "groups": [sharing.group_of(d)], "readonly": True, "priority": 100,
                    "why": "row 17: the department's people read"})
    pastors = [str(u) for u in (cfg.storage.pastors or [])]
    out.append({"mount_point": "/Pastors", "datadir": IN["pastors"], "users": pastors + [SCANNER], "groups": [],
                "readonly": False, "priority": 100, "why": "round 5, 18: the two pastors only"})
    out.append({"mount_point": "/Shared with me", "datadir": IN["shared"] + "/$user", "users": [], "groups": [],
                "readonly": False, "priority": 100, "why": "round 5, 19: what others shared with this person"})
    return out


def import_json(ms: list[dict] | None = None) -> list[dict]:
    """The file `occ files_external:import` reads."""
    rows = []
    for m in ms if ms is not None else mounts():
        rows.append({"mount_point": m["mount_point"], "storage": LOCAL, "authentication_type": "null::null",
                     "configuration": {"datadir": m["datadir"]},
                     "options": {"readonly": bool(m["readonly"]), "enable_sharing": False, "previews": True,
                                 "filesystem_check_changes": 1, "encoding_compatibility": False},
                     "applicable_users": list(m["users"]), "applicable_groups": list(m["groups"]),
                     "priority": int(m["priority"])})
    return rows


def ldap_settings(bind_password: str = "{LDAP_BIND_PASSWORD}") -> dict:
    """user_ldap against the Samba AD DC over LDAPS: first.last logs in; enabled accounts only."""
    cfg = load()
    realm = str(cfg.directory.realm)
    base = ",".join("DC=" + p for p in realm.lower().split("."))
    fqdn = f"{cfg.system.hostname}.{realm.lower()}"
    return {
        "ldapHost": f"ldaps://{fqdn}", "ldapPort": "636", "ldapTLS": "0",
        "ldapAgentName": f"CN={SERVICE_ACCOUNT},CN=Users,{base}", "ldapAgentPassword": bind_password,
        "ldapBase": base, "ldapBaseUsers": base, "ldapBaseGroups": base,
        # A disabled account (the leaving rule) stops syncing at once.
        "ldapUserFilter": f"(&(objectClass=user)(!(objectClass=computer))(!(sAMAccountName={SERVICE_ACCOUNT}))(!(userAccountControl:1.2.840.113556.1.4.803:=2)))",
        "ldapLoginFilter": "(&(objectClass=user)(!(objectClass=computer))(sAMAccountName=%uid))",
        "ldapGroupFilter": "(objectClass=group)", "ldapGroupMemberAssocAttr": "member", "ldapNestedGroups": "1",
        "ldapExpertUsernameAttr": "sAMAccountName", "ldapExpertUUIDUserAttr": "objectGUID",
        "ldapUserDisplayName": "displayName", "ldapEmailAttribute": "mail", "ldapGroupDisplayName": "cn",
        "ldapPagingSize": "500", "turnOnPasswordChange": "0", "ldapCacheTTL": "600", "ldapConfigurationActive": "1",
    }


def occ_plan(bind_password: str = "{LDAP_BIND_PASSWORD}") -> list[list[str]]:
    """Pure given the config: the occ commands setup() runs, in order (each idempotent)."""
    h = host()
    plan = [
        ["app:enable", "user_ldap"], ["app:enable", "files_external"],
        ["app:disable", "firstrunwizard"], ["app:disable", "recommendations"],
        ["config:system:set", "skeletondirectory", "--value", ""],          # nothing written into a home at first sign-in
        ["config:system:set", "templatedirectory", "--value", ""],
        ["config:system:set", "localstorage.allowsymlinks", "--value", "true", "--type", "boolean"],   # <data>/<user>/files -> /homes/<user>
        ["config:system:set", "filesystem_check_changes", "--value", "1", "--type", "integer"],
        ["config:system:set", "memcache.local", "--value", "\\OC\\Memcache\\APCu"],
        ["config:system:set", "memcache.locking", "--value", "\\OC\\Memcache\\Redis"],                # file locking
        ["config:system:set", "redis", "host", "--value", "redis"],
        ["config:system:set", "redis", "port", "--value", "6379", "--type", "integer"],
        ["config:system:set", "trusted_domains", "1", "--value", h],
        ["config:system:set", "overwrite.cli.url", "--value", "https://" + h],
        ["config:system:set", "overwriteprotocol", "--value", "https"],
        ["config:system:set", "trusted_proxies", "0", "--value", "172.16.0.0/12"],
        ["config:system:set", "default_phone_region", "--value", "US"],
        ["config:system:set", "maintenance_window_start", "--value", "9", "--type", "integer"],      # 03:00-07:00 Central, after the 02:05 job
        # Nextcloud keeps no copy of anyone's domain password, not even encrypted inside a web sign-in.
        ["config:system:set", "auth.storeCryptedPassword", "--value", "false", "--type", "boolean"],
        ["config:app:set", "core", "shareapi_enabled", "--value", "no"],    # sharing is the server's Share with…
        # Storage is the home's own quota (row 5 of the panel: against 50 GB); Nextcloud adds none of its own.
        ["config:app:set", "files", "default_quota", "--value", "none"],
        # Round 7, 46: earlier versions of a file kept a year, then let go (Nextcloud's own setting).
        ["config:system:set", "versions_retention_obligation", "--value", "auto, 365"],
        ["config:app:set", "files", "max_chunk_size", "--value", "104857600"],   # 100 MB chunks: big files (row 18) upload in pieces
        ["background:cron"],
        ["theming:config", "name", "Arise"], ["theming:config", "slogan", "Arise Church · Pineville"],
        ["theming:config", "color", "#D6222D"], ["theming:config", "url", "https://arisecenla.church"],
        ["theming:config", "background", "backgroundColor"], ["theming:config", "logo", "/arise-web/favicon.svg"],
        ["theming:config", "disable-user-theming", "yes"],
    ]
    for k, v in ldap_settings(bind_password).items():
        plan.append(["ldap:set-config", "s01", k, v])
    return plan


# ----- paths: host <-> Nextcloud --------------------------------------------------
def nc_path(host_path: str) -> dict | None:
    """Pure: where a changed host path is, in Nextcloud's terms. None when Nextcloud doesn't carry it."""
    p = paths()
    hp = os.path.normpath(host_path)
    parts = hp.split("/")
    if any(x in SKIP_DIRS for x in parts) or os.path.basename(hp).startswith((".~lock", "._", ".sync_")):
        return None
    if hp.startswith(p["homes"] + "/"):
        rel = hp[len(p["homes"]) + 1:]
        user, _, rest = rel.partition("/")
        if not USER_RE.match(user):
            return None
        return {"kind": "home", "user": user, "path": f"/{user}/files" + ("/" + rest if rest else "")}
    if hp.startswith(p["pastors"] + "/") or hp == p["pastors"]:
        rest = hp[len(p["pastors"]):].lstrip("/")
        return {"kind": "mount", "user": SCANNER, "path": f"/{SCANNER}/files/Pastors" + ("/" + rest if rest else "")}
    if hp.startswith(p["shares"] + "/"):
        rel = hp[len(p["shares"]) + 1:]
        folder, _, rest = rel.partition("/")
        # The scanner sees every share's read-write mount (it is in each restricted mount's users).
        for m in mounts():
            if m["datadir"] == f"{IN['shares']}/{folder}" and not m["readonly"]:
                return {"kind": "mount", "user": SCANNER, "path": f"/{SCANNER}/files{m['mount_point']}" + ("/" + rest if rest else "")}
        return None
    if hp.startswith(p["shared"] + "/"):
        rel = hp[len(p["shared"]) + 1:]
        user, _, rest = rel.partition("/")
        if not USER_RE.match(user):
            return None
        return {"kind": "shared", "user": user, "path": f"/{user}/files/Shared with me" + ("/" + rest if rest else "")}
    return None


def scan_cmd(m: dict) -> list[str]:
    return ["files:scan", "--path", m["path"], "--shallow"]


# ----- running occ in the container --------------------------------------------
def occ(argv: list[str], env: dict | None = None, timeout: int = 300) -> dict:
    """`php occ <argv>` as www-data in the Nextcloud container. env reaches occ only (never argv, never a log)."""
    cfg = load()
    cmd = ["docker", "exec", "-u", "www-data"]
    for k in (env or {}):
        cmd += ["-e", k]
    cmd += [str(cfg.cloud.container), "php", "occ", "--no-interaction", *argv]
    old = {k: os.environ.get(k) for k in (env or {})}
    try:
        os.environ.update(env or {})
        return run(cmd, timeout=timeout)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ----- homes: Nextcloud's files folder is the home -----------------------------------
def link_home(user: str, data_dir: str | None = None, uid: int | None = None) -> dict:
    """<data>/<user>/files -> /homes/<user> (the container's view of the home). A real,
    non-empty files folder is never replaced: that would hide what is in it."""
    if not USER_RE.match(user or ""):
        return {"ok": False, "err": "not a username"}
    cfg = load()
    d = os.path.join(data_dir or paths()["data"], user)
    link = os.path.join(d, "files")
    target = f"{IN['homes']}/{user}"
    if os.path.islink(link):
        if os.readlink(link) == target:
            return {"ok": True, "already": True}
        os.unlink(link)
    elif os.path.isdir(link):
        if os.listdir(link):
            return {"ok": False, "err": f"{link} already holds files; move them into the home, then run this again"}
        os.rmdir(link)
    os.makedirs(d, exist_ok=True)
    os.symlink(target, link)
    w = uid if uid is not None else int(cfg.cloud.www_uid)
    for x in (d,):
        try:
            os.chown(x, w, w)
        except OSError:
            pass
    try:
        os.lchown(link, w, w)
    except OSError:
        pass
    return {"ok": True, "link": link, "to": target}


def acl_plan(users: list[str] | None = None) -> list[list[str]]:
    """Pure: the setfacl lines that let Nextcloud (uid 33) read and write the synced folders, and keep
    each owner able to change what Nextcloud writes (default ACLs on every home)."""
    cfg = load()
    w = int(cfg.cloud.www_uid)
    p = paths()
    cmds = []
    for key in ("shares", "shared", "pastors"):
        cmds.append(["setfacl", "-R", "-m", f"u:{w}:rwX,d:u:{w}:rwX", p[key]])
    for u in users or []:
        if USER_RE.match(u):
            h = os.path.join(p["homes"], u)
            cmds.append(["setfacl", "-R", "-m", f"u:{w}:rwX,d:u:{w}:rwX,u:{u}:rwX,d:u:{u}:rwX", h])
    return cmds


# ----- devices: app passwords ------------------------------------------------------
def _devices_file():
    return load().state_dir / "cloud-devices.json"


def _devices() -> dict:
    if load().demo:
        return demo_state.get("cloud.devices", lambda: json.loads(json.dumps(DEMO_DEVICES)))
    return read_json(_devices_file(), default={}) or {}


def _save_devices(d: dict):
    if not load().demo:
        write_json(_devices_file(), d)


def device_name(mac_name: str, local: str) -> str:
    """Pure: 'Office iMac' + 'kristina' -> 'Office iMac kristina' (what the Sync panel and revoke() show)."""
    s = re.sub(r"[^A-Za-z0-9 ._-]+", " ", f"{mac_name or 'Mac'} {local or ''}").strip()
    s = re.sub(r"\s+", " ", s)[:60].strip()
    return s if DEVICE_RE.match(s) else "Mac"


def _home_owner(user: str) -> tuple[int, int] | None:
    import pwd
    try:
        p = pwd.getpwnam(user)
        return p.pw_uid, p.pw_gid
    except KeyError:
        return None


def ensure_sync_folders(user: str, homes: str | None = None) -> list[str]:
    """Desktop and Documents in the person's server home, theirs, so the first sync has somewhere to land."""
    cfg = load()
    base = os.path.join(homes or paths()["homes"], user)
    made = []
    if not os.path.isdir(base):
        return made
    owner = _home_owner(user)
    for f in cfg.cloud.sync_folders or []:
        d = os.path.join(base, str(f))
        if not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
            made.append(d)
            if owner:
                try:
                    os.chown(d, *owner)
                except OSError:
                    pass
    return made


def parse_token(out: str) -> str | None:
    """The app password occ prints after 'app password:' (72 letters and digits)."""
    for line in reversed((out or "").splitlines()):
        m = re.fullmatch(r"\s*([A-Za-z0-9]{40,128})\s*", line)
        if m:
            return m.group(1)
    return None


def _tokens(run_occ, user: str) -> list[dict]:
    """Nextcloud's sign-ins for this person: [{id, name, lastActivity, type}]. Raises when it can't say."""
    r = run_occ(["user:auth-tokens:list", user, "--output=json"])
    if not r.get("ok"):
        raise RuntimeError("could not list the person's devices in Nextcloud; revoke them there: Personal settings → Security")
    try:
        t = json.loads(r.get("out") or "[]")
    except ValueError:
        raise RuntimeError("Nextcloud's device list did not read as JSON")
    return [x for x in t if isinstance(x, dict)] if isinstance(t, list) else []


def _drop_tokens(run_occ, user: str, ids: set[int] | None) -> list[int]:
    """Delete these sign-ins (every one the person has when ids is None: web, phone, Mac)."""
    gone = []
    for t in _tokens(run_occ, user):
        try:
            tid = int(t.get("id"))
        except (TypeError, ValueError):
            continue
        if ids is None or tid in ids:
            if run_occ(["user:auth-tokens:delete", user, str(tid)]).get("ok"):
                gone.append(tid)
    return gone


def app_password(user: str, device: str, by: str = "", runner=None, mac_id: str = "", local: str = "") -> dict:
    """A device app password for this server user (a Mac profile, a linked local account, a phone).
    Returned once, never stored here (only a sha256 and Nextcloud's id for it). It is made with no
    login password behind it, so Nextcloud holds no domain password for it either (and never
    re-checks one). Issuing again for the same device replaces the old one."""
    user = (user or "").strip().lower()
    if not USER_RE.match(user) or user in (SERVICE_ACCOUNT, SCANNER):
        return {"ok": False, "err": "not a username"}
    if not DEVICE_RE.match(device or ""):
        return {"ok": False, "err": "name the device: letters, digits, spaces, . _ - (60 at most)"}
    cfg = load()
    row = {"created": datetime.now().isoformat(timespec="seconds"), "revoked": None, **({"mac_id": mac_id} if mac_id else {}),
           **({"local": local} if local else {})}
    if cfg.demo:
        with _lock:
            _devices().setdefault(user, {})[device] = {**row, "sha256": "sample"}
        return {"ok": True, "demo": True, "user": user, "device": device, "server": url(), "login": user,
                "app_password": "sample-app-password-shown-once"}
    run_occ = runner or occ
    home = link_home(user)
    if not home["ok"]:
        return home
    ensure_sync_folders(user)
    old = ((_devices().get(user) or {}).get(device) or {}).get("token_id")
    try:
        before = {int(t["id"]) for t in _tokens(run_occ, user) if "id" in t}
    except (RuntimeError, TypeError, ValueError):
        before = set()
    last = run_occ(["user:auth-tokens:add", user])
    tok = parse_token(last.get("out", "")) if last.get("ok") else None
    if not tok:
        return {"ok": False, "err": "Nextcloud did not issue an app password: " + (last.get("err") or last.get("out") or "no answer")[-300:].strip()}
    try:
        new = sorted({int(t["id"]) for t in _tokens(run_occ, user) if "id" in t} - before)
    except (RuntimeError, TypeError, ValueError):
        new = []
    if old:
        try:
            _drop_tokens(run_occ, user, {int(old)})
        except (RuntimeError, TypeError, ValueError):
            pass
    run_occ(["files:scan", "--path", f"/{user}/files", "--shallow"])
    with _lock:
        d = _devices()
        d.setdefault(user, {})[device] = {**row, "sha256": hashlib.sha256(tok.encode()).hexdigest(), "token_id": new[-1] if new else None}
        _save_devices(d)
    audit.record(by or "arise", "cloud.app_password", user, detail=f"device {device}")
    return {"ok": True, "user": user, "device": device, "server": url(), "login": user, "app_password": tok}


def revoke(user: str, device: str | None = None, by: str = "", runner=None) -> dict:
    """Cut off one device of a person, or every sign-in they have (a lost Mac, row 11; someone leaving)."""
    user = (user or "").strip().lower()
    if not USER_RE.match(user):
        return {"ok": False, "err": "not a username"}
    if device is not None and not DEVICE_RE.match(device):
        return {"ok": False, "err": "not a device name"}
    cfg = load()
    now = datetime.now().isoformat(timespec="seconds")
    rows = _devices().get(user) or {}
    if device is not None and device not in rows:
        return {"ok": False, "err": f"{user} has no device called {device}"}
    if cfg.demo:
        with _lock:
            for name, row in rows.items():
                if device is None or name == device:
                    row["revoked"] = now
        return {"ok": True, "demo": True, "user": user, "device": device, "revoked": [device] if device else sorted(rows)}
    ids = None
    if device is not None:
        tid = rows[device].get("token_id")
        if tid is None:
            return {"ok": False, "err": f"ariseOS has no Nextcloud id for {device}; revoke it in Nextcloud: Personal settings → Security"}
        ids = {int(tid)}
    try:
        gone = _drop_tokens(runner or occ, user, ids)
    except RuntimeError as e:
        return {"ok": False, "err": str(e)}
    with _lock:
        d = _devices()
        for name, row in (d.get(user) or {}).items():
            if device is None or name == device:
                row["revoked"] = now
        _save_devices(d)
    audit.record(by or "arise", "cloud.revoke", user, detail=f"device {device}" if device else "every sign-in")
    return {"ok": True, "user": user, "device": device, "revoked": gone}


def revoke_mac(mac_id: str, by: str = "", runner=None) -> dict:
    """Every Nextcloud sign-in a Mac holds, for every account on it (row 11: a lost or stolen Mac;
    row 6: retiring one). R6-MAC's Cut off and Retire call this."""
    out = []
    for user, rows in sorted(_devices().items()):
        for name, row in sorted(rows.items()):
            if row.get("mac_id") == mac_id and not row.get("revoked"):
                out.append(revoke(user, name, by=by, runner=runner))
    return {"ok": all(r.get("ok") for r in out), "revoked": out}


# ----- the Mac helper's door ---------------------------------------------------------
def mac_task_open(mac: dict, user: str, local: str) -> bool:
    """Has an admin queued a `nextcloud` task for this server user and local account on this Mac?
    The helper may only ask for an app password the Macs app asked it to set up."""
    try:
        from . import macs
        tasks = (macs._read().get("tasks") or {}).get(mac.get("id"), [])
    except Exception:   # the Macs app (R6-MAC) is not on this box
        return False
    for t in tasks:
        a = t.get("args") or {}
        if t.get("kind") == "nextcloud" and t.get("state") in ("queued", "sent") and a.get("user") == user and a.get("local", user) == local:
            return True
    return False


def agent_app_password(mac: dict, user: str, local: str, runner=None) -> dict:
    """POST /api/cloud/agent/app-password: an enrolled Mac's helper, mid-task, asking for the device
    password of one server user signed in on one local account. Nothing else gets through."""
    user = (user or "").strip().lower()
    local = (local or user).strip()
    if not USER_RE.match(user) or not re.match(r"^[A-Za-z0-9._-]{1,64}$", local):
        return {"ok": False, "err": "not a username"}
    if not mac_task_open(mac, user, local):
        return {"ok": False, "err": f"no Nextcloud task open on this Mac for {local} as {user}: queue it from the Macs app"}
    return app_password(user, device_name(mac.get("name", "Mac"), local), by=f"mac:{mac.get('name', '?')}", runner=runner,
                        mac_id=str(mac.get("id", "")), local=local)


# ----- conflicts: newest wins (row 15) -----------------------------------------------
def conflict_of(name: str) -> tuple[str, str] | None:
    """Pure: 'Budget (conflicted copy 2026-10-29 101500).xlsx' -> ('Budget.xlsx', '2026-10-29 101500')."""
    for rx in CONFLICT_RES:
        m = rx.match(name)
        if m:
            return m.group("stem") + (m.group("ext") or ""), m.group("date")
    return None


def decide(original_mtime: float | None, conflict_mtime: float) -> str:
    """Pure: 'conflict' (the conflict copy is newer, or the original is gone: it takes the name)
    or 'original' (the original is newer: the conflict copy goes to the Trash)."""
    if original_mtime is None or conflict_mtime > original_mtime:
        return "conflict"
    return "original"


def _conflicts_log():
    return load().state_dir / "cloud-conflicts.jsonl"


def _to_trash(path: str, user: str) -> str:
    """Into the place's .Trash/<user>/ the way finder.trash_put does, so Put Back works."""
    from . import finder
    base = finder.trash_base(path)
    if not base or not path.startswith(base + "/"):
        raise OSError(f"no Trash covers {path}")
    udir = os.path.join(base, ".Trash", user)
    relp = finder.trash_rel(base, path)
    dest_dir = os.path.join(udir, os.path.dirname(relp))
    os.makedirs(dest_dir, exist_ok=True)
    name = os.path.basename(path)
    final = finder.versioned_name(name, lambda n: os.path.lexists(os.path.join(dest_dir, n)))
    dest = os.path.join(dest_dir, final)
    shutil.move(path, dest)
    try:
        os.utime(dest, None)
    except OSError:
        pass
    man_p = finder._manifest_path(base, user)
    man = read_json(man_p, default={}) or {}
    man[os.path.relpath(dest, udir)] = {"original": relp, "who": "sync", "when": datetime.now().isoformat(timespec="seconds"),
                                        "dir": False, "root": "sync", "why": "an older copy from a sync conflict (newest wins)"}
    write_json(man_p, man)
    return dest


def _owner_label(path: str) -> str:
    homes = paths()["homes"]
    if path.startswith(homes + "/"):
        u = path[len(homes) + 1:].split("/")[0]
        if USER_RE.match(u):
            return u
    return "sync"


def sweep(dry_run: bool = False, roots: list[str] | None = None) -> dict:
    """Find the clients' conflict copies and settle each one: the newer copy keeps the name,
    the older goes to the Trash. Logged; nothing deleted."""
    cfg = load()
    if cfg.demo and roots is None:
        return {"ok": True, "demo": True, "moved": [], "checked": 0}
    p = paths()
    roots = roots or [p["homes"], p["shares"], p["pastors"]]
    moved, checked = [], 0
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirs, fnames in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".Trash")]
            for fn in fnames:
                c = conflict_of(fn)
                if not c:
                    continue
                checked += 1
                cpath = os.path.join(dirpath, fn)
                opath = os.path.join(dirpath, c[0])
                try:
                    cm = os.stat(cpath).st_mtime
                    om = os.stat(opath).st_mtime if os.path.exists(opath) else None
                except OSError:
                    continue
                winner = decide(om, cm)
                who = _owner_label(cpath)
                row = {"t": datetime.now().isoformat(timespec="seconds"), "file": opath, "conflict": cpath,
                       "kept": "conflict copy (newer)" if winner == "conflict" else "original (newer)", "user": who}
                if not dry_run:
                    try:
                        if winner == "conflict":
                            if om is not None:
                                row["trash"] = _to_trash(opath, who)
                            os.replace(cpath, opath)
                        else:
                            row["trash"] = _to_trash(cpath, who)
                    except OSError as e:
                        row["error"] = str(e)
                    _conflicts_log().parent.mkdir(parents=True, exist_ok=True)
                    with open(_conflicts_log(), "a") as f:
                        f.write(json.dumps(row) + "\n")
                moved.append(row)
    if moved and not dry_run:
        audit.record("arise-cloud", "cloud.conflicts", "", detail=f"{len(moved)} settled, newest kept")
    return {"ok": True, "demo": False, "dry_run": dry_run, "checked": checked, "moved": moved}


def conflicts(limit: int = 100) -> dict:
    if load().demo:
        return {"demo": True, "conflicts": DEMO_CONFLICTS}
    rows = []
    try:
        with open(_conflicts_log()) as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return {"demo": False, "conflicts": rows[-limit:][::-1]}


# ----- the watcher: SMB changes reach the clients ----------------------------------------
def debounce(events: list[str]) -> list[dict]:
    """Pure: changed host paths -> the folders to rescan, each once (its parent folder, shallow)."""
    seen, out = set(), []
    for e in events:
        m = nc_path(os.path.dirname(e.rstrip("/")) or "/")
        if not m:
            continue
        k = (m["user"], m["path"])
        if k not in seen:
            seen.add(k)
            out.append(m)
    return out


def owner_fix(path: str, homes: str | None = None, www_uid: int | None = None) -> tuple[int, int] | None:
    """A file Nextcloud wrote into a home belongs to www-data; give it back to the home's owner, so
    their quota counts it and SMB shows it as theirs. (uid, gid) to chown to, or None to leave it."""
    homes = (homes or paths()["homes"]).rstrip("/")
    w = int(load().cloud.www_uid) if www_uid is None else www_uid
    if not path.startswith(homes + "/"):
        return None
    user = path[len(homes) + 1:].split("/")[0]
    try:
        st = os.lstat(path)
        home = os.stat(os.path.join(homes, user))
    except OSError:
        return None
    if st.st_uid != w or home.st_uid == w:
        return None
    return home.st_uid, home.st_gid


def watch(stop=None):
    """arise-cloud-watch: inotifywait over the synced folders; a few seconds after a change, rescan
    just the folders that changed, and give files Nextcloud wrote into a home back to its owner."""
    import selectors
    import subprocess
    p = paths()
    roots = [r for r in (p["homes"], p["shares"], p["shared"], p["pastors"]) if os.path.isdir(r)]
    if not which("inotifywait") or not roots:
        raise SystemExit("inotifywait (inotify-tools) and the synced folders are needed")
    proc = subprocess.Popen(["inotifywait", "-m", "-r", "-q", "--format", "%w%f", "-e", "close_write,create,delete,moved_to,moved_from", *roots],
                            stdout=subprocess.PIPE)
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)
    fd = proc.stdout.fileno()
    buf, part, first = [], b"", None
    try:
        while not (stop and stop()):
            if sel.select(timeout=1):
                chunk = os.read(fd, 65536)
                if not chunk:
                    break   # inotifywait ended; systemd starts the watcher again
                lines = (part + chunk).split(b"\n")
                part = lines.pop()
                for ln in lines:
                    path = ln.decode("utf-8", "surrogateescape").strip()
                    if path:
                        buf.append(path)
                        first = first or time.time()
                        fix = owner_fix(path, p["homes"])
                        if fix:
                            try:
                                os.lchown(path, *fix)
                            except OSError:
                                pass
            if buf and (time.time() - first >= 3 or len(buf) > 500):
                for m in debounce(buf):
                    occ(scan_cmd(m), timeout=120)
                buf, first = [], None
    finally:
        proc.terminate()


# ----- status, people, setup ---------------------------------------------------------
def _running() -> bool | None:
    if not which("docker"):
        return None
    r = run(["docker", "inspect", "-f", "{{.State.Running}}", str(load().cloud.container)], timeout=10)
    return r["ok"] and r["out"].strip() == "true"


def status() -> dict:
    cfg = load()
    if cfg.demo:
        return {"demo": True, "url": url(), "running": True, "mounts": len({m["mount_point"] for m in mounts()}), "sync_folders": list(cfg.cloud.sync_folders),
                "conflicts": cfg.cloud.conflicts, "people": len(DEMO_DEVICES), "client": cfg.cloud.client_version}
    return {"demo": False, "url": url(), "running": _running(), "mounts": len({m["mount_point"] for m in mounts()}), "sync_folders": list(cfg.cloud.sync_folders),
            "conflicts": cfg.cloud.conflicts, "client": cfg.cloud.client_version, "paths": paths(),
            "devices": sum(1 for u in _devices().values() for r in u.values() if not r.get("revoked"))}


def people(runner=None) -> dict:
    """Per person: devices (with each one's last sync, Nextcloud's last activity of its sign-in),
    conflicts settled, storage against the home quota."""
    from . import directory, sharing
    cfg = load()
    devs = _devices()
    clog = conflicts(1000)["conflicts"]
    users = [u["name"] for u in (directory.list_users().get("users") or []) if u["name"] not in (SERVICE_ACCOUNT, SCANNER)]
    out = []
    for u in sorted(set(users) | set(devs)):
        rows = [{"device": k, **{x: y for x, y in v.items() if x != "sha256"}} for k, v in sorted((devs.get(u) or {}).items())]
        if cfg.demo:
            for r in rows:
                r["last_sync"] = None if r.get("revoked") else DEMO_LAST.get(u)
        elif any(not r.get("revoked") for r in rows):
            try:
                acts = {int(t["id"]): int(t.get("lastActivity") or 0) for t in _tokens(runner or occ, u) if "id" in t}
            except (RuntimeError, TypeError, ValueError):
                acts = {}
            for r in rows:
                a = acts.get(int(r["token_id"])) if r.get("token_id") is not None else None
                r["last_sync"] = datetime.fromtimestamp(a).isoformat(timespec="seconds") if a else None
        live = [r["last_sync"] for r in rows if r.get("last_sync") and not r.get("revoked")]
        q = sharing.quota_of(u)
        out.append({"user": u, "devices": rows, "last_sync": max(live) if live else None,
                    "conflicts": sum(1 for c in clog if c.get("user") == u), "storage": q})
    return {"demo": cfg.demo, "quota_gb": int(cfg.storage.home_quota_gb or 0), "people": out}


def env_keys() -> dict:
    """This box's real paths and names, for compose.yaml (apps.deploy and setup() write them into .env)."""
    cfg = load()
    p = paths()
    return {"ARISE_HOMES": p["homes"], "ARISE_SHARES": p["shares"], "ARISE_SHARED": p["shared"], "ARISE_PASTORS": p["pastors"],
            "CLOUD_HOST": host(), "DC_FQDN": f"{cfg.system.hostname}.{str(cfg.directory.realm).lower()}"}


def read_env(path: str) -> dict:
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.rstrip("\n").split("=", 1)
                    out[k.strip()] = v
    except OSError:
        pass
    return out


def merge_env(path: str, keys: dict) -> bool:
    """Set these keys in an .env file, keeping every other line as it is. True when it changed. 0600."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    left, out, changed = dict(keys), [], False
    for line in lines:
        k = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if k in left:
            new = f"{k}={left.pop(k)}"
            changed |= new != line
            out.append(new)
        else:
            out.append(line)
    for k, v in left.items():
        out.append(f"{k}={v}")
        changed = True
    if changed:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        os.chmod(path, 0o600)
    return changed


def service_account_plan(password: str) -> list[list[str]]:
    """Pure: the samba-tool lines that make (or refresh) the directory account Nextcloud binds as.
    The first fails harmlessly when the account exists; the password is then set again so .env and the
    domain agree. It never expires, and it is not a person: the user filter leaves it out of Nextcloud."""
    return [
        ["samba-tool", "user", "create", SERVICE_ACCOUNT, password, "--description", "ariseOS: Nextcloud reads the directory (docs/SYNC.md)"],
        ["samba-tool", "user", "setpassword", SERVICE_ACCOUNT, f"--newpassword={password}"],
        ["samba-tool", "user", "setexpiry", SERVICE_ACCOUNT, "--noexpiry"],
    ]


def _step(name: str, r: dict) -> dict:
    """A setup step for the report: never the command line (it can hold a password), only what it said."""
    return {"step": name, "ok": bool(r.get("ok")), **({} if r.get("ok") else {"err": (r.get("err") or r.get("out") or "")[-200:].strip()})}


def setup(dry_run: bool = False) -> dict:
    """Make Nextcloud ariseOS's: the directory account, this box's paths in .env, the occ plan, the mounts
    (replacing the ones ariseOS made before), every home linked and given its ACLs. Run by
    `arisectl cloud setup` (the installer calls it after the apps are up). Safe to run again."""
    from . import directory
    cfg = load()
    if dry_run or cfg.demo:
        plan = occ_plan("***")
        return {"ok": True, "dry_run": True, "demo": cfg.demo, "url": url(), "env": env_keys(),
                "account": [" ".join(a) for a in service_account_plan("***")],
                "plan": [" ".join(a) for a in plan],
                "mounts": import_json(), "acl": [" ".join(a) for a in acl_plan(["<each user>"])]}
    app_dir = os.path.join(cfg.apps.root, "nextcloud")
    app_env = os.path.join(app_dir, ".env")
    env = read_env(SECRETS_ENV)
    for k, v in read_env(app_env).items():
        env.setdefault(k, v)
    pw = env.get("LDAP_BIND_PASSWORD", "")
    if not pw or pw.startswith("CHANGE-ME"):
        return {"ok": False, "err": f"no LDAP_BIND_PASSWORD in {SECRETS_ENV} or {app_env}: deploy the nextcloud app first (sudo arisectl app deploy nextcloud)"}
    steps = []
    # 1. The directory account: it binds and searches, it is in no group but Domain Users.
    names = ["create the directory account " + SERVICE_ACCOUNT, "set its password (the one in .env)", "never expire it"]
    for i, argv in enumerate(service_account_plan(pw)):
        r = run(argv, timeout=60)
        if i == 0 and not r["ok"] and "already exists" in (r.get("err", "") + r.get("out", "")):
            r = {"ok": True}
        steps.append(_step(names[i], r))
    # 2. This box's paths and names in .env; the container is re-created when they changed.
    if os.path.isdir(app_dir) and merge_env(app_env, env_keys()):
        r = run(["docker", "compose", "-p", "nextcloud", "-f", os.path.join(app_dir, "compose.yaml"), "--env-file", app_env, "up", "-d"], timeout=900)
        steps.append(_step("apply this box's paths (docker compose up -d)", r))
        for _ in range(30):
            if occ(["status", "--output=json"], timeout=30).get("ok"):
                break
            time.sleep(5)
    # 3. Nextcloud itself: the domain sign-in, locking, the theme.
    if not occ(["ldap:show-config", "s01"]).get("ok"):
        steps.append(_step("ldap:create-empty-config", occ(["ldap:create-empty-config"])))
    for argv in occ_plan(pw):
        shown = "ldap:set-config s01 ldapAgentPassword ***" if argv[:3] == ["ldap:set-config", "s01", "ldapAgentPassword"] else " ".join(argv)
        steps.append(_step(shown, occ(argv)))
    # 4. The mounts: replace ariseOS's own (same mount points), keep anything Bradly added by hand.
    ours = {m["mount_point"] for m in mounts()}
    lst = occ(["files_external:list", "--output=json"])
    try:
        for row in json.loads(lst.get("out") or "[]"):
            if row.get("mount_point") in ours:
                occ(["files_external:delete", "-y", str(row.get("mount_id"))])
    except ValueError:
        steps.append({"step": "read the existing mounts", "ok": False, "err": "files_external:list did not answer in JSON"})
    inbox = os.path.join(app_dir, "arise")
    os.makedirs(inbox, exist_ok=True)
    write_json(os.path.join(inbox, "mounts.json"), import_json())
    steps.append(_step("files_external:import (ariseOS's mounts)", occ(["files_external:import", "/arise/mounts.json"])))
    # 5. Each home is the person's Nextcloud files; Nextcloud may read and write it.
    users = [u["name"] for u in (directory.list_users().get("users") or [])
             if u.get("enabled", True) and u["name"] != SERVICE_ACCOUNT and USER_RE.match(u["name"])]
    for u in users:
        steps.append({"step": f"link {u}'s home", **link_home(u)})
    for argv in acl_plan(users):
        steps.append(_step(" ".join(argv[:4]) + " " + argv[-1], run(argv, timeout=600)))
    ok = all(s.get("ok", True) for s in steps)
    audit.record("arise", "cloud.setup", "", ok=ok, detail=f"{len(users)} homes, {len(ours)} mount points")
    return {"ok": ok, "steps": steps, "url": url()}


# ----- sample data -----------------------------------------------------------------
DEMO_DEVICES = {
    "bradly": {"Media Mac": {"created": "2026-10-20T09:12:00", "sha256": "sample", "revoked": None},
               "iPhone": {"created": "2026-10-21T18:40:00", "sha256": "sample", "revoked": None}},
    "office": {"Office iMac": {"created": "2026-10-22T08:05:00", "sha256": "sample", "revoked": None}},
    "media-mac": {"Media Mac linked": {"created": "2026-10-22T08:30:00", "sha256": "sample", "revoked": None}},
}
DEMO_LAST = {"bradly": "2026-10-29T08:14:00", "office": "2026-10-29T07:58:00", "media-mac": "2026-10-28T21:03:00"}
DEMO_CONFLICTS = [
    {"t": "2026-10-28T10:41:00", "file": "/srv/arise/homes/office/Documents/Bulletin.docx",
     "conflict": "/srv/arise/homes/office/Documents/Bulletin (conflicted copy 2026-10-28 104012).docx",
     "kept": "conflict copy (newer)", "user": "office", "trash": "/srv/arise/homes/office/.Trash/office/Documents/Bulletin.docx"},
]

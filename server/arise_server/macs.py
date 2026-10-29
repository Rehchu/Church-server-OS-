"""The church Macs: the server as their Active Directory, with a helper on each one.

Bradly (Oct 29): "this should run like Active Directory and actually add and remove
user accounts from the local Macs on the network (not the private ones that people
own) ... We don't want to pay for Active Directory, we want the server to be our own
Active Directory." The directory is the box's Samba AD DC; no Microsoft licence is
involved anywhere. docs/MACS.md is the plain-words version of this file.

How it fits together:
  * A Mac is a *church Mac* only once it is enrolled with the helper (the one Terminal
    line from the Macs app, round 6, 37). Enrolment sets church_owned = True. A Mac
    nobody enrolled (the pastors' own, round 1, 34) is never listed and never touched.
  * The helper (mac/helper/arise-mac-helper, a root LaunchDaemon) checks in every five
    minutes over the church network or Tailscale, with its own key. The server answers
    with tasks; never during a service (it answers HOLD then).
  * Accounts: every enabled directory user, minus [macs] exclude, gets a mobile (AD)
    account made on every church Mac (createmobileaccount), so their face is on the
    login window before they ever sign in (round 6, 2, 3, 9). A disabled account's
    profile is removed only through the checked path: the helper sends a list of the
    person's Desktop and Documents, the server confirms each file is on the server and
    not newer on the Mac, and only then is the profile deleted (round 6, 4).
  * Local accounts already on a Mac: for each, an admin chooses Convert (it becomes the
    server user, keeping its home and every file), Link (it stays as it is, and syncs to
    a server user through Nextcloud), or Leave alone. Nothing happens until an admin chooses.
  * A Mac's key is kept only as its sha256 (in the state file). ariseadmin's passwords and
    the FileVault recovery keys live in /etc/arise/secrets/macs/<mac>.json, 0600 root,
    never in a task, a result, a log or git.

The helper speaks a small text protocol (bash 3.2 on macOS has no JSON parser): each
answer is lines, "TASK <id> <kind> k=v k=v" with percent-encoded values.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

from . import audit
from .config import load

_lock = threading.RLock()
TOKEN_TTL = 3600            # an enrol line works for one hour, once (round 6, 37)
ROTATE_DAYS = 30            # ariseadmin's password (round 6, 7)
OFFLINE_AFTER = 20 * 60     # a Mac not heard from in 20 minutes shows as offline
HELPER_VERSION = "1.0.0"
ID_RE = re.compile(r"^mac-[a-f0-9]{12}$")
USER_RE = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
LOCAL_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
KINDS = ("add_account", "remove_profile", "convert_local", "link_local", "unconvert", "login_window", "ariseadmin",
         "filevault", "printers", "bookmarks", "certificate", "updates", "tailscale", "nextcloud", "retire")
# Accounts never made on a Mac, whatever [macs] exclude says: the box's own and the break-glass one.
ALWAYS_EXCLUDE = {"administrator", "krbtgt", "guest", "arise-rescue", "arise", "arise-kiosk", "arise-git", "arise-kb", "ariseadmin"}


# ----- where things live ----------------------------------------------------------------
def _state_file() -> Path:
    return load().state_dir / "macs" / "macs.json"


def _secrets_dir() -> Path:
    return Path(os.environ.get("ARISE_MACS_SECRETS", "/etc/arise/secrets/macs"))


def macs_cfg() -> dict:
    raw = load().raw.get("macs", {}) if isinstance(load().raw, dict) else {}
    return {"exclude": [str(x).lower() for x in (raw.get("exclude") or [])],
            "printers": raw.get("printers") or [],
            "bookmarks": raw.get("bookmarks") or DEFAULT_BOOKMARKS,
            "login_window": raw.get("login_window", "faces"),
            "sync_folders": raw.get("sync_folders") or ["Desktop", "Documents"],
            "server_ip": raw.get("server_ip", "")}


DEFAULT_BOOKMARKS = [
    {"name": "Arise Church", "url": "https://arisecenla.church"},
    {"name": "YouTube Studio", "url": "https://studio.youtube.com"},
    {"name": "The church's files (Nextcloud)", "url": "https://arise-server.{realm}/nextcloud/"},
]


def _blank() -> dict:
    return {"macs": {}, "tokens": {}, "tasks": {}, "seq": 0}


def _read() -> dict:
    if load().demo:
        from . import demo_state
        return demo_state.get("macs", _demo_seed)
    try:
        return json.loads(_state_file().read_text())
    except (OSError, ValueError):
        return _blank()


def _write(d: dict):
    if load().demo:
        return
    p = _state_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1, sort_keys=True))
    os.chmod(tmp, 0o640)
    os.replace(tmp, p)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# ----- secrets: one 0600 file per Mac, root only ---------------------------------------
def _secret_path(mac_id: str) -> Path:
    return _secrets_dir() / f"{mac_id}.json"


def secret_get(mac_id: str) -> dict:
    if load().demo:
        from . import demo_state
        return demo_state.get(f"macs.secret.{mac_id}", lambda: {"ariseadmin": "sample-Admin-Pass-42!", "filevault": "SAMP-LE00-KEY0-0000-0000-0000",
                                                                  "ariseadmin_at": _now(), "filevault_at": _now()})
    try:
        return json.loads(_secret_path(mac_id).read_text())
    except (OSError, ValueError):
        return {}


def secret_put(mac_id: str, **kv):
    if load().demo:
        from . import demo_state
        demo_state.get(f"macs.secret.{mac_id}", dict).update(kv)
        return
    d = _secrets_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    cur = secret_get(mac_id)
    cur.update(kv)
    p = _secret_path(mac_id)
    tmp = p.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(cur, f)
    os.replace(tmp, p)


# ----- the text protocol -----------------------------------------------------------------
def enc(v) -> str:
    return urllib.parse.quote(str(v), safe="")


def task_line(t: dict) -> str:
    args = " ".join(f"{k}={enc(v)}" for k, v in sorted((t.get("args") or {}).items()))
    return f"TASK {t['id']} {t['kind']}" + (f" {args}" if args else "")


def parse_accounts(text: str) -> list[dict]:
    """The helper's account lines: user|kind|uid|admin|home|signed_in|realname|last_login.
    kind is mobile (an AD account cached on the Mac) or local. Bad lines are skipped."""
    out = []
    for line in (text or "").splitlines():
        p = line.split("|")
        if len(p) < 6 or not LOCAL_RE.match(p[0]) or p[1] not in ("mobile", "local"):
            continue
        out.append({"user": p[0], "kind": p[1], "uid": int(p[2]) if p[2].isdigit() else None, "admin": p[3] == "1",
                    "home": p[4][:300], "signed_in": p[5] == "1", "realname": (p[6] if len(p) > 6 else "")[:120],
                    "last_login": (p[7] if len(p) > 7 else "")[:40] or None})
    return out


def parse_manifest(text: str) -> list[tuple[str, int, float]]:
    """rel<TAB>size<TAB>mtime lines -> tuples. A path that tries to leave its folder is dropped."""
    out = []
    for line in (text or "").splitlines():
        if line.startswith("#"):
            continue   # a folder's summary line (parse_folders)
        p = line.split("\t")
        if len(p) != 3:
            continue
        rel = p[0].lstrip("/")
        if not rel or ".." in Path(rel).parts:
            continue
        try:
            out.append((rel, int(p[1]), float(p[2])))
        except ValueError:
            continue
    return out


def parse_folders(text: str) -> list[dict]:
    """The helper's "#folder<TAB>name<TAB>state<TAB>has_items<TAB>odd_names" lines."""
    out = []
    for line in (text or "").splitlines():
        p = line.split("\t")
        if p[0] != "#folder" or len(p) != 5:
            continue
        out.append({"folder": p[1].strip("/"), "state": p[2], "has_items": p[3] == "1",
                    "odd": int(p[4]) if p[4].isdigit() else 1})
    return out


def trust_listing(files: list[tuple[str, int, float]], folders: list[dict]) -> str:
    """Why a listing cannot be trusted, or "" when it can. An empty listing proves nothing by
    itself: macOS hides Desktop and Documents even from root without Full Disk Access, and a
    file name with a tab or line break cannot be listed on one line. Either way the removal waits."""
    if not folders:
        return "the Mac sent no folder summary (an older helper?); nothing removed"
    for f in folders:
        if f["state"] == "unreadable":
            return (f"this Mac's helper could not read {f['folder']} (it needs Full Disk Access: "
                    f"System Settings > Privacy & Security, docs/MACS.md); nothing removed")
        if f["odd"]:
            return f"{f['odd']} name(s) in {f['folder']} hold a tab or a line break; rename them, then it is tried again"
        if f["state"] == "read" and f["has_items"] and not any(rel.startswith(f["folder"] + "/") for rel, _, _ in files):
            return f"{f['folder']} has items but no files were listed (empty folders only, or no Full Disk Access); nothing removed"
    return ""


def verify_manifest(files: list[tuple[str, int, float]], bases: list[str], slack: float = 2.0) -> dict:
    """Is every file the Mac listed already on the server, and not newer on the Mac?
    bases: where to look on the server (their home, or where offboarding moved it).
    A file counts when some base has it at the same relative path with the same size
    and a modification time no older than the Mac's (within two seconds)."""
    missing, newer = [], []
    for rel, size, mtime in files:
        found = None
        for b in bases:
            p = Path(b) / rel
            try:
                st = p.stat()
            except OSError:
                continue
            if p.is_file():
                found = st
                break
        if not found:
            missing.append(rel)
        elif found.st_size != size or found.st_mtime + slack < mtime:
            newer.append(rel)
    return {"ok": not missing and not newer, "checked": len(files), "missing": missing[:50], "newer": newer[:50],
            "missing_count": len(missing), "newer_count": len(newer)}


# ----- matching local accounts to server users -------------------------------------------
def suggest_user(local: str, realname: str, users: list[dict]) -> str | None:
    """A suggestion only (an admin chooses): first.last from the full name, or the same short name."""
    names = {u["name"].lower(): u for u in users}
    if local.lower() in names:
        return names[local.lower()]["name"]
    parts = [re.sub(r"[^a-z]", "", w.lower()) for w in (realname or "").split()]
    parts = [w for w in parts if w]
    if len(parts) >= 2:
        guess = f"{parts[0]}.{parts[-1]}"
        if guess in names:
            return names[guess]["name"]
        return guess
    return None


# ----- enrolment ------------------------------------------------------------------------
def enrol_token(by: str, name: str = "") -> dict:
    """An admin makes a one-time enrol line, good for an hour."""
    tok = secrets.token_urlsafe(24)
    with _lock:
        d = _read()
        now = time.time()
        d["tokens"] = {h: t for h, t in d.get("tokens", {}).items() if t.get("expires", 0) > now and not t.get("used")}
        d["tokens"][_hash(tok)] = {"by": by, "name": (name or "")[:60], "made": _now(), "expires": now + TOKEN_TTL}
        _write(d)
    audit.record(by, "macs.enrol_token", name or "")
    return {"ok": True, "token": tok, "expires_in": TOKEN_TTL, "command": enrol_command(tok, name=name), "demo": load().demo}


def server_names() -> dict:
    cfg = load()
    realm = str(cfg.directory.realm or "AD.ARISECENLA.COM").lower()
    host = str(cfg.system.hostname or "arise-server")
    return {"realm": realm, "host": f"{host}.{realm}", "port": int(cfg.web.port or 4147)}


def lan_ip() -> str:
    """The server's address on the church network. A new Mac cannot resolve the AD name yet
    (the /etc/resolver file is what enrol.sh writes), so the enrol line uses the address.
    [macs] server_ip overrides; otherwise the address the kernel would route from (a UDP
    connect sends nothing)."""
    ip = str(macs_cfg().get("server_ip") or "").strip()
    if ip:
        return ip
    if load().demo:
        return "192.168.1.20"
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 9))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def enrol_command(tok: str, ip: str | None = None, name: str = "") -> str:
    """The one Terminal line (round 6, 37). The church certificate is fetched first and pinned
    by its fingerprint, so the script itself arrives over HTTPS the Mac can check; --resolve
    reaches the AD name by address until the Mac has its resolver file."""
    n = server_names()
    ip = ip or lan_ip()
    fp = ca_fingerprint()
    tail = f"--token {tok} --dns {ip}"
    nm = re.sub(r"[^A-Za-z0-9-]", "", (name or "").replace(" ", "-"))[:15]
    if nm:
        tail += f" --name {nm}"
    if fp:
        return (f"curl -fsSL http://{ip}:{n['port']}/ca.crt -o /tmp/arise-ca.crt && "
                f"[ \"$(shasum -a 256 /tmp/arise-ca.crt | cut -c1-64)\" = \"{fp}\" ] && "
                f"curl -fsSL --cacert /tmp/arise-ca.crt --resolve {n['host']}:443:{ip} https://{n['host']}/mac/enrol.sh"
                f" | sudo bash -s -- {tail} --server https://{n['host']}")
    return f"curl -fsSL http://{ip}:{n['port']}/mac/enrol.sh | sudo bash -s -- {tail} --server http://{ip}:{n['port']}"


def ca_fingerprint() -> str | None:
    try:
        from . import security
        pem = security.ca_cert()
    except Exception:  # noqa: BLE001 - no CA yet: the plain-http line, on the church network only
        pem = None
    if load().demo:
        return "0" * 64
    return hashlib.sha256(pem.encode()).hexdigest() if pem else None


def enrol(token: str, facts: dict) -> dict:
    """The Mac trades the one-time token for its own key. church_owned is set here, and only here."""
    h = _hash(token or "")
    with _lock:
        d = _read()
        t = d.get("tokens", {}).get(h)
        if not t or t.get("used") or t.get("expires", 0) < time.time():
            return {"ok": False, "err": "that enrol line has expired or was used: make a new one in the Macs app"}
        t["used"] = _now()
        mac_id = "mac-" + secrets.token_hex(6)
        key = secrets.token_urlsafe(32)
        m = {"id": mac_id, "name": (facts.get("name") or t.get("name") or "Mac")[:60], "serial": (facts.get("serial") or "")[:40],
             "model": (facts.get("model") or "")[:80], "macos": (facts.get("macos") or "")[:40], "church_owned": True,
             "enrolled": _now(), "enrolled_by": t.get("by"), "status": "active", "key_hash": _hash(key), "last_checkin": None,
             "helper": facts.get("helper") or HELPER_VERSION, "accounts": parse_accounts(facts.get("accounts", "")),
             "choices": {}, "filevault": None, "tailscale": None, "ariseadmin_at": None, "done": {}}
        # The same Mac enrolled again (a reinstall of the helper): the old entry is retired, never merged.
        for other in d["macs"].values():
            if m["serial"] and other.get("serial") == m["serial"] and other.get("status") == "active":
                other["status"] = "replaced"
        d["macs"][mac_id] = m
        d["tasks"][mac_id] = []
        for kind in ("certificate", "login_window", "ariseadmin", "filevault", "printers", "bookmarks", "tailscale"):
            _queue(d, mac_id, kind, {}, by="enrolment")
        _write(d)
    audit.record(t.get("by") or "?", "macs.enrol", m["name"], detail=f"{m['model']} {m['serial']}")
    return {"ok": True, "mac_id": mac_id, "key": key}


def agent_auth(header: str) -> dict | None:
    """X-Arise-Mac: <mac id>:<key>. Only an active, church-owned Mac with the right key."""
    try:
        mac_id, key = (header or "").split(":", 1)
    except ValueError:
        return None
    if not ID_RE.match(mac_id):
        return None
    m = _read()["macs"].get(mac_id)
    if not m or m.get("status") != "active" or not m.get("church_owned"):
        return None
    if not secrets.compare_digest(m.get("key_hash", ""), _hash(key)):
        return None
    return m


# ----- tasks ------------------------------------------------------------------------------
def _queue(d: dict, mac_id: str, kind: str, args: dict, by: str) -> dict:
    assert kind in KINDS, kind
    d["seq"] = int(d.get("seq", 0)) + 1
    t = {"id": f"t{d['seq']}", "kind": kind, "args": args, "state": "queued", "made": _now(), "by": by}
    d["tasks"].setdefault(mac_id, []).append(t)
    return t


def _open(tasks: list[dict], kind: str, key: str | None = None, val: str | None = None) -> bool:
    return any(t["kind"] == kind and t["state"] in ("queued", "sent") and (key is None or t["args"].get(key) == val) for t in tasks)


BACKOFF_FIRST = 15 * 60       # a failed or refused account task waits 15 minutes, then 30, 60... up to a day
BACKOFF_MAX = 24 * 3600
KEEP_FINISHED_DAYS = 30


def backing_off(tasks: list[dict], kind: str, user: str, now: datetime | None = None) -> bool:
    """Has this task kind for this user failed (or been refused) lately enough to wait? Without
    this, a Mac that cannot make accounts (not bound, say) got a fresh copy of every user's task
    at every five-minute check-in, forever."""
    now = now or datetime.now()
    mine = [t for t in tasks if t["kind"] == kind and str(t["args"].get("user", "")).lower() == user.lower() and t.get("finished")]
    n, last = 0, None
    for t in sorted(mine, key=lambda t: t["finished"], reverse=True):
        if t["state"] not in ("failed", "refused"):
            break
        n += 1
        last = last or t["finished"]
    if not n:
        return False
    try:
        since = (now - datetime.fromisoformat(last)).total_seconds()
    except ValueError:
        return False
    return since < min(BACKOFF_MAX, BACKOFF_FIRST * 2 ** (n - 1))


def prune(tasks: list[dict], now: datetime | None = None) -> list[dict]:
    """Finished tasks older than 30 days go; open ones always stay."""
    cut = (now or datetime.now()) - timedelta(days=KEEP_FINISHED_DAYS)
    keep = []
    for t in tasks:
        try:
            old = bool(t.get("finished")) and datetime.fromisoformat(t["finished"]) < cut
        except ValueError:
            old = False
        if not old:
            keep.append(t)
    return keep


def _directory_users() -> list[dict]:
    from . import directory
    try:
        return directory.list_users().get("users", [])
    except Exception:  # noqa: BLE001 - no directory here: nothing to add
        return []


def plan_accounts(m: dict, users: list[dict], exclude: list[str], tasks: list[dict],
                  now: datetime | None = None) -> list[tuple[str, dict]]:
    """Pure: which add_account and remove_profile tasks this Mac needs now.
    Every enabled directory user (minus exclusions) gets a mobile account; a disabled one
    with a mobile account on this Mac gets the checked removal. Local accounts are never
    touched here: they wait for an admin's Convert / Link / Leave choice."""
    ex = ALWAYS_EXCLUDE | {e.lower() for e in exclude}
    have = {a["user"].lower(): a for a in m.get("accounts", []) if a["kind"] == "mobile"}
    converted = {str(c.get("user", "")).lower() for c in (m.get("choices") or {}).values() if c.get("action") == "convert"}
    out = []
    for u in users:
        n = u["name"].lower()
        if n in ex or not USER_RE.match(n):
            continue
        if u.get("enabled", True):
            if n not in have and n not in converted and not _open(tasks, "add_account", "user", u["name"]) \
                    and not backing_off(tasks, "add_account", u["name"], now):
                out.append(("add_account", {"user": u["name"]}))
        elif n in have and not _open(tasks, "remove_profile", "user", u["name"]) and not backing_off(tasks, "remove_profile", u["name"], now):
            out.append(("remove_profile", {"user": u["name"]}))
    return out


def checkin(m: dict, facts: dict, now: datetime | None = None) -> list[str]:
    """The helper's five-minute visit: record the facts, plan, hand out tasks (none during a service)."""
    from . import church
    now = now or datetime.now()
    with _lock:
        d = _read()
        cur = d["macs"][m["id"]]
        cur["last_checkin"] = now.isoformat(timespec="seconds")
        for k in ("macos", "model", "serial", "helper", "filevault", "tailscale", "full_disk_access", "ip"):
            if facts.get(k):
                cur[k] = str(facts[k])[:80]
        if "accounts" in facts:
            cur["accounts"] = parse_accounts(facts["accounts"])
        d["tasks"][m["id"]] = tasks = prune(d["tasks"].get(m["id"], []), now)
        nowts = now.timestamp()
        d["tokens"] = {h: t for h, t in d.get("tokens", {}).items() if t.get("expires", 0) > nowts and not t.get("used")}
        cfgm = macs_cfg()
        for kind, args in plan_accounts(cur, _directory_users(), cfgm["exclude"], tasks, now):
            if kind == "remove_profile":
                args = {**args, **removal_args(args["user"])}
            _queue(d, m["id"], kind, args, by="the directory")
        # ariseadmin's password every 30 days (round 6, 7)
        last = cur.get("ariseadmin_at")
        if not _open(tasks, "ariseadmin") and (not last or datetime.fromisoformat(last) < now - timedelta(days=ROTATE_DAYS)):
            _queue(d, m["id"], "ariseadmin", {}, by="the 30-day rotation")
        # security updates overnight, 01:00 to 05:00 (round 6, 12)
        today = now.date().isoformat()
        if 1 <= now.hour < 5 and cur.get("done", {}).get("updates") != today and not _open(tasks, "updates"):
            _queue(d, m["id"], "updates", {"only": "security"}, by="the overnight window")
            cur.setdefault("done", {})["updates"] = today
        hold = church.in_service_now(now)
        lines = []
        if hold:
            lines.append(f"HOLD {enc(hold.get('name', 'a service'))}")
        else:
            for t in tasks:
                if t["state"] == "queued" or (t["state"] == "sent" and _age(t.get("sent")) > 3600):
                    t["state"] = "sent"
                    t["sent"] = now.isoformat(timespec="seconds")
                    lines.append(task_line(t))
        _write(d)
    return lines


def _age(iso: str | None) -> float:
    if not iso:
        return 1e9
    try:
        return (datetime.now() - datetime.fromisoformat(iso)).total_seconds()
    except ValueError:
        return 1e9


def removal_args(user: str) -> dict:
    """Where the server looks for a leaver's files: their home, or where offboarding moved it."""
    cfg = load()
    homes = cfg.directory.homes_path
    bases = [os.path.join(homes, user)]
    try:
        from . import offboard
        for e in offboard.status().get("entries", []):
            if e.get("name") == user and (e.get("result") or {}).get("files", {}).get("to"):
                bases.insert(0, e["result"]["files"]["to"])
    except Exception:  # noqa: BLE001
        pass
    return {"bases": "|".join(bases), "folders": ",".join(macs_cfg()["sync_folders"])}


def result(m: dict, task_id: str, state: str, detail: str = "", extra: dict | None = None) -> dict:
    """The helper reports a task. Accounts it made or removed are noted on the Mac at once."""
    if state not in ("done", "failed", "refused", "skipped"):
        return {"ok": False, "err": "state is done, failed, refused or skipped"}
    with _lock:
        d = _read()
        t = next((x for x in d["tasks"].get(m["id"], []) if x["id"] == task_id), None)
        if not t:
            return {"ok": False, "err": "no such task"}
        t["state"], t["detail"], t["finished"] = state, (detail or "")[:500], _now()
        cur = d["macs"][m["id"]]
        if state == "done" and t["kind"] == "ariseadmin":
            cur["ariseadmin_at"] = _now()
        if state == "done" and t["kind"] == "retire":
            cur["status"] = "retired"
            cur["retired"] = _now()
        if state == "done" and t["kind"] in ("convert_local", "link_local"):
            ch = cur.setdefault("choices", {}).get(t["args"].get("local"), {})
            ch["state"] = "done"
        _write(d)
    audit.record(f"mac:{m['name']}", f"macs.task.{t['kind']}", t["args"].get("user") or t["args"].get("local") or "",
                 ok=state in ("done", "skipped"), detail=f"{state}: {(detail or '')[:120]}")
    return {"ok": True}


def store_secret(m: dict, kind: str, value: str) -> dict:
    """ariseadmin's new password or the FileVault recovery key, straight into the 0600 file."""
    if kind not in ("ariseadmin", "filevault") or not value or len(value) > 200:
        return {"ok": False, "err": "kind is ariseadmin or filevault"}
    secret_put(m["id"], **{kind: value, f"{kind}_at": _now()})
    with _lock:
        d = _read()
        if kind == "filevault":
            d["macs"][m["id"]]["filevault"] = "on, key escrowed"
        _write(d)
    audit.record(f"mac:{m['name']}", f"macs.escrow.{kind}", m["name"])
    return {"ok": True}


def check(m: dict, user: str, bases_s: str, manifest: str) -> dict:
    """The checked path before a profile is deleted (round 6, 4)."""
    cfg = load()
    if not USER_RE.match((user or "").lower()):
        return {"ok": False, "err": "not a user name"}
    # The server decides where to look, never the Mac: the user's home, where offboarding moved
    # it, and the bases written on this Mac's own removal task for them. And only while such a
    # task (or a retire) is open, so a Mac key is not a way to probe other people's folders.
    d = _read()
    open_ = [t for t in d["tasks"].get(m["id"], []) if t["state"] in ("queued", "sent") and
             (t["kind"] == "retire" or (t["kind"] == "remove_profile" and t["args"].get("user", "").lower() == user.lower()))]
    if not open_:
        return {"ok": False, "err": f"no removal of {user} is waiting on this Mac"}
    known = removal_args(user)["bases"].split("|") + [b for t in open_ for b in str(t["args"].get("bases", "")).split("|")]
    allowed = os.path.realpath(cfg.directory.homes_path)
    bases = []
    for b in known:
        rb = os.path.realpath(b) if b else ""
        if rb and (rb == allowed or rb.startswith(allowed + os.sep)) and rb != allowed and b not in bases:
            bases.append(b)
    del bases_s   # what the Mac sent is not used
    if not bases:
        return {"ok": False, "err": "no place on the server to compare with"}
    files = parse_manifest(manifest)
    if cfg.demo:
        return {"ok": True, "demo": True, "checked": len(files), "missing": [], "newer": []}
    why = trust_listing(files, parse_folders(manifest))
    if why:
        audit.record(f"mac:{m['name']}", "macs.check", user, ok=False, detail=why[:200])
        return {"ok": False, "err": why, "checked": len(files), "missing": [], "newer": []}
    r = verify_manifest(files, bases)
    audit.record(f"mac:{m['name']}", "macs.check", user, ok=r["ok"], detail=f"{r['checked']} files, {r['missing_count']} missing, {r['newer_count']} newer on the Mac")
    return r


# ----- what admins do ---------------------------------------------------------------------
def listing() -> dict:
    d = _read()
    rows = []
    for m in sorted(d["macs"].values(), key=lambda x: x.get("name", "")):
        if not m.get("church_owned") or m.get("status") == "replaced":
            continue
        rows.append(_public(m, d["tasks"].get(m["id"], [])))
    return {"demo": load().demo, "macs": rows, "exclude": sorted(ALWAYS_EXCLUDE | set(macs_cfg()["exclude"])),
            "note": "Only Macs enrolled with the helper are church Macs. A personal Mac is never enrolled and never touched."}


def _public(m: dict, tasks: list[dict]) -> dict:
    online = _age(m.get("last_checkin")) < OFFLINE_AFTER
    acc = m.get("accounts", [])
    return {k: m.get(k) for k in ("id", "name", "serial", "model", "macos", "status", "enrolled", "enrolled_by", "last_checkin",
                                  "helper", "filevault", "tailscale", "full_disk_access", "ariseadmin_at", "church_owned")} | {
        "online": online, "mobile": sum(1 for a in acc if a["kind"] == "mobile"), "local": sum(1 for a in acc if a["kind"] == "local"),
        "pending": sum(1 for t in tasks if t["state"] in ("queued", "sent")),
        "failed": sum(1 for t in tasks if t["state"] in ("failed", "refused"))}


def detail(mac_id: str) -> dict:
    d = _read()
    m = d["macs"].get(mac_id)
    if not m or not m.get("church_owned"):
        return {"ok": False, "err": "no such church Mac"}
    users = _directory_users()
    names = {u["name"].lower() for u in users}
    choices = m.get("choices") or {}
    accounts = []
    for a in m.get("accounts", []):
        row = dict(a)
        if a["kind"] == "local":
            c = choices.get(a["user"])
            row["choice"] = c
            row["suggest"] = suggest_user(a["user"], a.get("realname", ""), users)
            row["suggest_exists"] = bool(row["suggest"] and row["suggest"].lower() in names)
            row["state"] = ("converting to " + c["user"] if c and c["action"] == "convert" and c.get("state") != "done" else
                            "linked to " + c["user"] if c and c["action"] == "link" else
                            "left alone" if c and c["action"] == "leave" else "waiting for your choice")
        accounts.append(row)
    tasks = sorted(d["tasks"].get(mac_id, []), key=lambda t: int(t["id"][1:]), reverse=True)[:80]
    return {"ok": True, "demo": load().demo, **_public(m, d["tasks"].get(mac_id, [])), "accounts": accounts, "tasks": tasks,
            "has_secret": {k: bool(secret_get(mac_id).get(k)) for k in ("ariseadmin", "filevault")}}


def choose_local(mac_id: str, local: str, action: str, user: str, by: str, display: str = "") -> dict:
    """An admin's choice for one local account (Bradly, Oct 29): convert, link or leave.
    A server user that does not exist yet is made first, with a temporary password (round 5, 5)."""
    if action not in ("convert", "link", "leave", "undo"):
        return {"ok": False, "err": "action is convert, link, leave or undo"}
    if not LOCAL_RE.match(local or ""):
        return {"ok": False, "err": "not an account name"}
    made = None
    with _lock:
        d = _read()
        m = d["macs"].get(mac_id)
        if not m or m.get("status") != "active":
            return {"ok": False, "err": "no such church Mac (or it is retired)"}
        acc = next((a for a in m.get("accounts", []) if a["user"] == local and a["kind"] == "local"), None)
        if action != "undo" and not acc:
            return {"ok": False, "err": f"{local} is not a local account on {m['name']}"}
        if action in ("convert", "link"):
            user = (user or "").strip().lower()
            if not USER_RE.match(user):
                return {"ok": False, "err": "the server user is first.last"}
            if acc and acc.get("signed_in") and action == "convert":
                return {"ok": False, "err": f"{local} is signed in on {m['name']}: convert when they are signed out"}
    if action in ("convert", "link") and user not in {u["name"].lower() for u in _directory_users()}:
        from . import directory, profiles
        pw = profiles.temp_password()
        r = directory.add_user(user, pw, display=display or (acc or {}).get("realname", ""), temporary=True)
        if not r.get("ok"):
            return {"ok": False, "err": f"could not make {user} on the server: {r.get('err') or r.get('out')}"}
        made = {"user": user, "temporary_password": pw}
    with _lock:
        d = _read()
        m = d["macs"][mac_id]
        tasks = d["tasks"].setdefault(mac_id, [])
        if action == "undo":
            prev = (m.get("choices") or {}).get(local)
            if not prev or prev.get("action") != "convert":
                return {"ok": False, "err": "only a conversion can be undone"}
            _queue(d, mac_id, "unconvert", {"local": local, "user": prev["user"]}, by=by)
            m["choices"].pop(local, None)
        elif action == "leave":
            m.setdefault("choices", {})[local] = {"action": "leave", "by": by, "at": _now()}
        else:
            m.setdefault("choices", {})[local] = {"action": action, "user": user, "by": by, "at": _now(), "state": "queued"}
            kind = "convert_local" if action == "convert" else "link_local"
            if not _open(tasks, kind, "local", local):
                # Admin rights carry over only if the local account had them (staff are standard users, round 6, 8).
                args = {"local": local, "user": user, "admin": "1" if (acc or {}).get("admin") and action == "convert" else "0"}
                _queue(d, mac_id, kind, args, by=by)
            # Their Desktop and Documents sync to the server user either way (R6-SYNC's nextcloud task).
            _queue(d, mac_id, "nextcloud", {"user": user, "local": local if action == "link" else user}, by=by)
        _write(d)
    audit.record(by, f"macs.local.{action}", f"{mac_id}/{local}", detail=f"-> {user}" if action in ("convert", "link") else "")
    return {"ok": True, "demo": load().demo, "made": made}


def queue_removals(user: str, by: str = "arise-offboard.timer", moved_to: str | None = None) -> dict:
    """Offboarding: the checked removal on every church Mac where this person has a profile.
    moved_to: where the sweep just moved their files (it is not written down yet)."""
    queued = []
    with _lock:
        d = _read()
        args = {"user": user, **removal_args(user)}
        if moved_to:
            args["bases"] = "|".join([moved_to] + [b for b in args["bases"].split("|") if b != moved_to])
        for m in d["macs"].values():
            if m.get("status") != "active" or not m.get("church_owned"):
                continue
            if any(a["user"].lower() == user.lower() and a["kind"] == "mobile" for a in m.get("accounts", [])):
                tasks = d["tasks"].setdefault(m["id"], [])
                if not _open(tasks, "remove_profile", "user", user):
                    _queue(d, m["id"], "remove_profile", args, by=by)
                    queued.append(m["name"])
        _write(d)
    return {"ok": True, "queued": queued}


def run_task(mac_id: str, kind: str, by: str, args: dict | None = None) -> dict:
    """An admin's button: rotate the admin password, printers again, updates now, Tailscale."""
    if kind not in ("ariseadmin", "printers", "bookmarks", "certificate", "updates", "tailscale", "login_window", "filevault"):
        return {"ok": False, "err": "not a task an admin starts by hand"}
    with _lock:
        d = _read()
        m = d["macs"].get(mac_id)
        if not m or m.get("status") != "active":
            return {"ok": False, "err": "no such church Mac"}
        t = _queue(d, mac_id, kind, args or {}, by=by)
        _write(d)
    return {"ok": True, "task": t["id"], "demo": load().demo}


def retire(mac_id: str, confirm: str, by: str) -> dict:
    """The Retire button (round 6, 6): only once every profile on it is known synced."""
    with _lock:
        d = _read()
        m = d["macs"].get(mac_id)
        if not m or m.get("status") != "active":
            return {"ok": False, "err": "no such church Mac"}
        if (confirm or "").strip() != m["name"]:
            return {"ok": False, "err": "type the Mac's name to confirm"}
        unsynced = [a["user"] for a in m.get("accounts", []) if a["kind"] == "mobile" and not a.get("synced", True)]
        unsynced += [a["user"] for a in m.get("accounts", []) if a["kind"] == "local" and not (m.get("choices") or {}).get(a["user"])]
        if unsynced:
            return {"ok": False, "err": "first confirm these are on the server (convert, link or leave each local account): " + ", ".join(unsynced)}
        t = _queue(d, mac_id, "retire", {"folders": ",".join(macs_cfg()["sync_folders"])}, by=by)
        m["status_note"] = "retiring"
        _write(d)
    audit.record(by, "macs.retire", m["name"])
    return {"ok": True, "task": t["id"], "next": "Once it reports back, erase it yourself: System Settings > General > Transfer or Reset > Erase All Content and Settings."}


def cut_off(mac_id: str, confirm: str, by: str) -> dict:
    """A lost or stolen Mac (round 6, 11): its key stops working, its computer account is
    disabled, and Bradly is told what to revoke by hand (Tailscale, Nextcloud sessions)."""
    with _lock:
        d = _read()
        m = d["macs"].get(mac_id)
        if not m:
            return {"ok": False, "err": "no such church Mac"}
        if (confirm or "").strip() != m["name"]:
            return {"ok": False, "err": "type the Mac's name to confirm"}
        m["status"] = "cut_off"
        m["key_hash"] = ""
        m["cut_off"] = _now()
        for t in d["tasks"].get(mac_id, []):
            if t["state"] in ("queued", "sent"):
                t["state"] = "cancelled"
        _write(d)
    disabled = None
    if not load().demo:
        from .util import run
        # A computer account is an AD object like a user's; disabling it by its sAMAccountName (NAME$)
        # stops the Mac's Kerberos and domain logins.
        r = run(["samba-tool", "user", "disable", m["name"].upper() + "$"], timeout=20)
        disabled = bool(r.get("ok"))
    audit.record(by, "macs.cut_off", m["name"], detail=f"key revoked; computer account disabled: {disabled}")
    return {"ok": True, "demo": load().demo, "computer_disabled": disabled,
            "also": ["Tailscale admin console: remove this Mac's machine", "Nextcloud: Settings > Security > revoke this Mac's sessions for each person who used it"]}


def reveal(mac_id: str, kind: str, by: str) -> dict:
    """ariseadmin's password or the FileVault key: admins, password typed again (the route checks), audited."""
    if kind not in ("ariseadmin", "filevault"):
        return {"ok": False, "err": "kind is ariseadmin or filevault"}
    m = _read()["macs"].get(mac_id)
    if not m:
        return {"ok": False, "err": "no such church Mac"}
    s = secret_get(mac_id)
    if not s.get(kind):
        return {"ok": False, "err": "not escrowed yet: it arrives after the Mac's next check-in"}
    audit.record(by, f"macs.reveal.{kind}", m["name"])
    return {"ok": True, "value": s[kind], "since": s.get(f"{kind}_at"), "demo": load().demo}


def config_for_helper() -> dict:
    """What the configuration tasks need: printers, bookmarks, login window mode."""
    c = macs_cfg()
    realm = server_names()["realm"]
    return {"printers": c["printers"], "login_window": c["login_window"],
            "bookmarks": [{"name": b["name"], "url": b["url"].replace("{realm}", realm)} for b in c["bookmarks"]]}


def config_lines() -> str:
    c = config_for_helper()
    out = [f"LOGIN {enc(c['login_window'])}"]
    for p in c["printers"]:
        if isinstance(p, dict) and p.get("name") and p.get("uri"):
            out.append(f"PRINTER {enc(p['name'])} {enc(p['uri'])} {enc(p.get('driver', 'everywhere'))} {enc(p.get('location', ''))}")
    for b in c["bookmarks"]:
        out.append(f"BOOKMARK {enc(b['name'])} {enc(b['url'])}")
    return "\n".join(out) + "\n"


# ----- sample Macs (ARISE_DEMO=1 and the preview) ------------------------------------------
def _demo_seed() -> dict:
    ago = lambda **k: (datetime.now() - timedelta(**k)).isoformat(timespec="seconds")  # noqa: E731
    d = _blank()
    d["macs"] = {
        "mac-0000000000a1": {"id": "mac-0000000000a1", "name": "MEDIA-MAC-01", "serial": "C02SAMPLE01", "model": "iMac (24-inch, M3)", "macos": "macOS 15.3",
                              "church_owned": True, "enrolled": ago(days=3), "enrolled_by": "bradly", "status": "active", "key_hash": "",
                              "last_checkin": ago(minutes=2), "helper": HELPER_VERSION, "filevault": "on, key escrowed", "tailscale": "up",
                              "ariseadmin_at": ago(days=3), "done": {},
                              "accounts": [{"user": "bradly", "kind": "mobile", "uid": 1104, "admin": False, "home": "/Users/bradly", "signed_in": False, "realname": "Bradly Dyer", "last_login": ago(days=1)},
                                           {"user": "media", "kind": "local", "uid": 501, "admin": True, "home": "/Users/media", "signed_in": True, "realname": "Media Team", "last_login": ago(hours=3)}],
                              "choices": {"media": {"action": "link", "user": "media-mac", "by": "bradly", "at": ago(days=2), "state": "done"}}},
        "mac-0000000000b2": {"id": "mac-0000000000b2", "name": "OFFICE-MAC-01", "serial": "C02SAMPLE02", "model": "MacBook Air (M2)", "macos": "macOS 14.7",
                              "church_owned": True, "enrolled": ago(days=1), "enrolled_by": "bradly", "status": "active", "key_hash": "",
                              "last_checkin": ago(minutes=4), "helper": HELPER_VERSION, "filevault": "on, key escrowed", "tailscale": "up",
                              "ariseadmin_at": ago(days=1), "done": {},
                              "accounts": [{"user": "office", "kind": "mobile", "uid": 1110, "admin": False, "home": "/Users/office", "signed_in": False, "realname": "Church Office", "last_login": ago(days=2)},
                                           {"user": "levi", "kind": "local", "uid": 501, "admin": True, "home": "/Users/levi", "signed_in": False, "realname": "Levi Mercer", "last_login": ago(days=5)},
                                           {"user": "guest", "kind": "local", "uid": 502, "admin": False, "home": "/Users/guest", "signed_in": False, "realname": "Guest", "last_login": None}],
                              "choices": {}},
        "mac-0000000000c3": {"id": "mac-0000000000c3", "name": "KIDS-MAC", "serial": "C02SAMPLE03", "model": "Mac mini (M1)", "macos": "macOS 15.2",
                              "church_owned": True, "enrolled": ago(days=9), "enrolled_by": "bradly", "status": "active", "key_hash": "",
                              "last_checkin": ago(hours=6), "helper": HELPER_VERSION, "filevault": "on, key escrowed", "tailscale": "down",
                              "ariseadmin_at": ago(days=9), "done": {},
                              "accounts": [{"user": "childrens.department", "kind": "mobile", "uid": 1120, "admin": False, "home": "/Users/childrens.department", "signed_in": False, "realname": "Children's Department", "last_login": ago(days=4)}],
                              "choices": {}},
    }
    d["tasks"] = {"mac-0000000000a1": [{"id": "t1", "kind": "add_account", "args": {"user": "bradly"}, "state": "done", "made": ago(days=3), "by": "the directory", "finished": ago(days=3), "detail": "mobile account made"},
                                       {"id": "t2", "kind": "link_local", "args": {"local": "media", "user": "media-mac"}, "state": "done", "made": ago(days=2), "by": "bradly", "finished": ago(days=2), "detail": "linked; Nextcloud signs in as media-mac"}],
                  "mac-0000000000b2": [{"id": "t3", "kind": "add_account", "args": {"user": "office"}, "state": "done", "made": ago(days=1), "by": "the directory", "finished": ago(days=1), "detail": "mobile account made"},
                                       {"id": "t4", "kind": "printers", "args": {}, "state": "done", "made": ago(days=1), "by": "enrolment", "finished": ago(days=1), "detail": "1 printer"}],
                  "mac-0000000000c3": [{"id": "t5", "kind": "updates", "args": {"only": "security"}, "state": "failed", "made": ago(hours=20), "by": "the overnight window", "finished": ago(hours=19), "detail": "softwareupdate: no network"}]}
    d["seq"] = 5
    return d

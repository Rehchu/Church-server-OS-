"""Round 5 (docs/ANSWERS.md, rows 12-20, 23, 36): who reaches which folder, over SMB first.

Staff and volunteers live on their Macs, with their files syncing over SMB; the
dashboard is mostly the administrators' view (Bradly, Oct 28). So every rule here
is written into the server's own permissions first, Samba share definitions and
POSIX ACLs, and the dashboard checks the same rule on top:

  * the Church folder: every account writes (row 16);
  * a department's folder: all staff write, the department's own account writes,
    people in the department read, admins all; nobody else sees it (row 17);
  * the Pastors folder: Apostle Bryant and Pastor Vanessa only, hidden from every
    other account, admins included, and an auditd watch logs root reading it (row 18);
  * Shared with me: a person shares a file or folder with a person or a group; an
    ACL on the item (and traverse on the folders above it) is the grant, and a
    link in <shared>/<person>/ makes it appear in their [shared] share on the Mac
    and in the dashboard's sidebar. Push and email tell them (row 19);
  * an administrator opening someone else's home is written to the audit log,
    once per folder per ten minutes (row 20);
  * a 50 GB quota per home (row 13), the 90-day Previous Versions (row 14) and the
    live backup target, the Synology or Arise-Home over Tailscale (row 15).

Names (realm, NetBIOS, host) come from arise.toml, never from this file.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import threading
import time
from datetime import datetime, timedelta

from . import audit
from .config import load
from .util import run, which

_lock = threading.RLock()
_seen_home: dict = {}          # (admin, folder) -> last audit time
HOME_AUDIT_EVERY = 600         # seconds: once per folder per ten minutes per admin
PERMS = ("read", "write")


# ---- who is who -----------------------------------------------------------------
def _groups(user: str) -> list[str]:
    from . import directory
    try:
        return directory.user_groups(user)
    except Exception:  # noqa: BLE001 - no domain: no groups
        return []


def is_admin(who: dict | None) -> bool:
    return who is None or who.get("role", "admin") == "admin"


def is_pastor(who: dict | None) -> bool:
    if not who:
        return False
    pastors = {p.lower() for p in (load().storage.pastors or [])}
    return str(who.get("user", "")).lower() in pastors


def is_staff(user: str, groups: list[str] | None = None) -> bool:
    groups = groups if groups is not None else _groups(user)
    staff = str(load().storage.staff_group).lower()
    return any(g.lower() in (staff, "domain admins") for g in groups)


def _under(path: str, base: str) -> bool:
    path, base = os.path.normpath(path), os.path.normpath(base)
    return path == base or path.startswith(base.rstrip(os.sep) + os.sep)


# ---- the Pastors folder: hidden from everyone else, admins included (row 18) ----------
def pastors_path() -> str:
    return str(load().storage.pastors_path)


def hidden(abs_path: str | None, who: dict | None) -> bool:
    """True when this viewer must not see this path. who=None is the system itself (CLI, backups)."""
    if not abs_path or who is None:
        return False
    return _under(abs_path, pastors_path()) and not is_pastor(who)


def hidden_demo(key: str, who: dict | None) -> bool:
    """The same rule on the sample tree, whose keys start at the data root."""
    if who is None:
        return False
    rel = "/" + os.path.relpath(pastors_path(), load().system.data_root).strip("/")
    return (key == rel or key.startswith(rel + "/")) and not is_pastor(who)


# ---- department folders (rows 16-17) ---------------------------------------------
def departments() -> list[str]:
    return [str(d) for d in (load().storage.departments or [])]


def group_of(dept: str) -> str:
    """childrens-department -> Childrens-Department (the group the installer makes)."""
    return "-".join(p[:1].upper() + p[1:] for p in dept.split("-"))


def department_accounts(dept: str) -> set[str]:
    """The department's own login: named like its folder (media, inedge, childrens.department)."""
    extra = (load().storage.department_accounts or {}).get(dept)
    names = {dept, dept.replace("-", ".")}
    if extra:
        names |= set([extra] if isinstance(extra, str) else extra)
    return {n.lower() for n in names}


def folder_access(folder: str, user: str, groups: list[str], admin: bool) -> str | None:
    """Pure: 'write', 'read' or None for one of the round-5 folders under shares/."""
    f = folder.lower()
    if f == str(load().storage.church_folder).lower():
        return "write"                                    # row 16: every account writes
    if f in [d.lower() for d in departments()]:
        if admin or is_staff(user, groups) or user.lower() in department_accounts(f):
            return "write"                                # row 17
        if any(g.lower() == group_of(f).lower() for g in groups):
            return "read"
        return None
    return None


def smb_conf(netbios: str | None = None) -> str:
    """Pure-ish: /etc/samba/arise-folders.conf, the round-5 share definitions. testparm decides."""
    cfg = load()
    nb = netbios or cfg.directory.netbios
    root = os.path.join(cfg.system.data_root, "shares")
    q = lambda g: f'@"{nb}\\{g}"'  # noqa: E731
    recycle = ["  vfs objects = acl_xattr fruit streams_xattr recycle", "  recycle:repository = .Trash/%U", "  recycle:keeptree = yes",
               "  recycle:versions = yes", "  recycle:touch = yes", "  recycle:directory_mode = 0770",
               "  recycle:exclude = *.tmp,*.temp,~$*,.DS_Store,._*,*.part,*.crdownload", "  recycle:exclude_dir = .Trash,/tmp",
               "  fruit:metadata = stream", "  fruit:model = MacSamba", "  fruit:posix_rename = yes"]
    out = ["# Written by ariseOS (server/arise_server/sharing.py, round 5). Regenerate: sudo arisectl share folders",
           "# The POSIX ACLs on each folder are the truth; these lines say who connects and who writes.",
           "[global]", "  # [shared] follows links into the items shared with a person; their own permissions still apply.",
           "  allow insecure wide links = yes", ""]
    church = str(cfg.storage.church_folder)
    out += [f"[{church}]", "  comment = The Church folder: everyone reads and writes", f"  path = {root}/{church}",
            f"  valid users = {q('Domain Users')}", "  read only = no", "  browseable = yes", '  force group = "Domain Users"',
            "  inherit acls = yes", *recycle, ""]
    for d in departments():
        g = group_of(d)
        accts = " ".join(sorted(department_accounts(d)))
        out += [f"[{d}]", f"  comment = {g.replace('-', ' ')}: staff and the department write, the department reads", f"  path = {root}/{d}",
                f"  valid users = {q(g)} {q(cfg.storage.staff_group)} {q('Domain Admins')} {accts}",
                f"  write list = {q(cfg.storage.staff_group)} {q('Domain Admins')} {accts}",
                "  read only = yes", "  browseable = yes", f'  force group = "{g}"', "  inherit acls = yes",
                "  access based share enum = yes", *recycle, ""]
    pastors = " ".join(p for p in (cfg.storage.pastors or []) if str(p).strip())
    if not pastors:
        # an empty "valid users =" lets every domain user connect: no section at all instead
        out += ["# [pastors] is left out: [storage] pastors names nobody.", ""]
    else:
        out += ["[pastors]", "  comment = Pastors only", f"  path = {pastors_path()}", f"  valid users = {pastors}",
                "  read only = no", "  browseable = no", "  access based share enum = yes", '  force group = "Pastors"',
                "  inherit acls = yes", *recycle, ""]
    out += ["[shared]", "  comment = Shared with me", f"  path = {cfg.storage.shared_path}/%U", "  valid users = %U",
            "  read only = no", "  browseable = yes", "  wide links = yes", "  follow symlinks = yes", "  inherit acls = yes",
            "  vfs objects = acl_xattr fruit streams_xattr", "  fruit:metadata = stream", "  fruit:model = MacSamba",
            "  root preexec = /bin/sh -c 'mkdir -p \"" + str(cfg.storage.shared_path) + "/%U\" && chmod 0755 \"" + str(cfg.storage.shared_path) + "/%U\"'", ""]
    return "\n".join(out)


def _account_exists(name: str) -> bool:
    """Does the OS see this login (getent, through winbind)? Unknown when getent is missing: keep it."""
    if load().demo or not which("getent"):
        return True
    return run(["getent", "passwd", name], timeout=10)["ok"]


def acl_plan(exists=None) -> list[list[str]]:
    """Pure given exists(): the setfacl/chgrp/chmod commands that make each round-5 folder's rule true on disk.
    A department account that does not exist is left out: setfacl refuses a whole line over one unknown name."""
    exists = exists or _account_exists
    cfg = load()
    root = os.path.join(cfg.system.data_root, "shares")
    staff = cfg.storage.staff_group
    church = os.path.join(root, str(cfg.storage.church_folder))
    cmds = [["mkdir", "-p", church], ["chgrp", "Domain Users", church], ["chmod", "2775", church],
            ["setfacl", "-m", "g::rwx,d:g::rwx,d:o::r-x", church]]
    for d in departments():
        p, g = os.path.join(root, d), group_of(d)
        ents = [f"g:{staff}:rwx", "g:Domain Admins:rwx", "g::r-x", "o::---"] + [f"u:{a}:rwx" for a in sorted(department_accounts(d)) if exists(a)]
        cmds += [["mkdir", "-p", p], ["chgrp", g, p], ["chmod", "2750", p],
                 ["setfacl", "-m", ",".join(ents + ["d:" + e for e in ents] + ["m::rwx", "d:m::rwx"]), p]]
    pp = pastors_path()
    ents = [f"u:{u}:rwx" for u in cfg.storage.pastors if exists(u)] + ["g::---", "o::---"]
    cmds += [["mkdir", "-p", pp], ["chown", "root:Pastors", pp], ["chmod", "2770", pp],
             ["setfacl", "-m", ",".join(ents + ["d:" + e for e in ents] + ["m::rwx", "d:m::rwx"]), pp],
             ["mkdir", "-p", str(cfg.storage.shared_path)], ["chmod", "0755", str(cfg.storage.shared_path)]]
    return cmds


AUDIT_RULE = "-w {path} -p rwxa -k arise-pastors"


def audit_rule() -> str:
    return AUDIT_RULE.format(path=pastors_path())


def apply_folders(dry_run: bool = False) -> dict:
    """arisectl share folders: write arise-folders.conf (testparm-checked, put back if refused), set the ACLs."""
    from . import shares
    if load().demo:
        return {"ok": True, "demo": True, "conf": smb_conf(), "acls": acl_plan()}
    conf = "/etc/samba/arise-folders.conf"
    plan = acl_plan()
    if dry_run:
        return {"ok": True, "dry_run": True, "conf": smb_conf(), "acls": plan}
    done, failed = [], []
    for c in plan:
        if c[0] == "setfacl" and not which("setfacl"):
            failed.append(" ".join(c) + "  (setfacl missing: apt install acl)"); continue
        r = run(c, timeout=30)
        (done if r["ok"] else failed).append(" ".join(c) + ("" if r["ok"] else "  -> " + (r["err"] or r["out"]).strip()[:160]))
    old = None
    try:
        old = open(conf, encoding="utf-8").read()
    except OSError:
        pass
    with open(conf, "w", encoding="utf-8") as f:
        f.write(smb_conf() + "\n")
    try:
        text = open(shares.SMB_CONF, encoding="utf-8").read()
        if conf not in text:
            shutil.copy2(shares.SMB_CONF, f"{shares.SMB_CONF}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
            with open(shares.SMB_CONF, "a", encoding="utf-8") as f:
                f.write(f"\ninclude = {conf}\n")
    except OSError as e:
        return {"ok": False, "err": f"could not include {conf}: {e}", "acls_done": done, "acls_failed": failed}
    t = run(["testparm", "-s", "--suppress-prompt"], timeout=20)
    if not t["ok"]:
        if old is None:
            os.remove(conf)
        else:
            open(conf, "w", encoding="utf-8").write(old)
        return {"ok": False, "err": "testparm refused arise-folders.conf, so it was put back", "acls_done": done, "acls_failed": failed}
    run(["smbcontrol", "all", "reload-config"], timeout=15)
    return {"ok": not failed, "conf": conf, "acls_done": done, "acls_failed": failed}


# ---- an administrator opening someone else's home (row 20) --------------------------
def note_access(abs_path: str | None, who: dict | None, action: str = "open"):
    if not abs_path or not who or who.get("role") != "admin":
        return
    cfg = load()
    homes = cfg.directory.homes_path
    if not _under(abs_path, homes) or os.path.normpath(abs_path) == os.path.normpath(homes):
        return
    owner = os.path.relpath(abs_path, homes).split(os.sep)[0]
    me = str(who.get("user", ""))
    if not owner or owner.lower() == me.lower():
        return
    folder = abs_path if os.path.isdir(abs_path) else os.path.dirname(abs_path)
    k = (me.lower(), os.path.normpath(folder))
    now = time.time()
    with _lock:
        if now - _seen_home.get(k, 0) < HOME_AUDIT_EVERY:
            return
        _seen_home[k] = now
    audit.record(me, "files.home.open", owner, detail=f"{action} {os.path.relpath(abs_path, homes)}")


def note_access_demo(key: str, who: dict | None, action: str = "open"):
    """Demo keys are rooted at the data root: /homes/<owner>/..."""
    if not who or who.get("role") != "admin" or not key.startswith("/homes/"):
        return
    parts = key.strip("/").split("/")
    if len(parts) < 2 or parts[1].lower() == str(who.get("user", "")).lower():
        return
    k = (str(who.get("user")).lower(), "/".join(parts[:3]))
    now = time.time()
    with _lock:
        if now - _seen_home.get(k, 0) < HOME_AUDIT_EVERY:
            return
        _seen_home[k] = now
    audit.record(str(who.get("user")), "files.home.open", parts[1], detail=f"{action} {'/'.join(parts[1:])}")


# ---- the home quota (row 13) ------------------------------------------------------
_usage_cache: dict = {}


def quota_bytes() -> int:
    return int(float(load().storage.home_quota_gb or 0) * 1024 ** 3)


def home_of(abs_path: str) -> str | None:
    homes = load().directory.homes_path
    if not _under(abs_path, homes) or os.path.normpath(abs_path) == os.path.normpath(homes):
        return None
    return os.path.relpath(abs_path, homes).split(os.sep)[0]


def home_usage(user: str, fresh: bool = False) -> int:
    from .util import dir_size
    if load().demo:
        return int(_demo_usage().get(user, 0))
    now = time.time()
    hit = _usage_cache.get(user)
    if hit and not fresh and now - hit[0] < 60:
        return hit[1]
    n = dir_size(os.path.join(load().directory.homes_path, user)) or 0
    _usage_cache[user] = (now, n)
    return n


def _demo_usage() -> dict:
    from . import demo_state
    return demo_state.get("storage.home_usage", {"bradly": 41_800_000_000, "office": 6_200_000_000, "media-mac": 18_900_000_000})


def quota_of(user: str) -> dict:
    q = quota_bytes()
    used = home_usage(user)
    pct = round(used * 100 / q, 1) if q else None
    return {"user": user, "used": used, "quota": q or None, "pct": pct,
            "warn": bool(q) and pct is not None and pct >= float(load().storage.quota_warn_pct), "full": bool(q) and used >= q}


def quota_refusal(abs_folder: str, add_bytes: int) -> str | None:
    """None, or why an upload into this folder is refused."""
    user = home_of(abs_folder)
    q = quota_bytes()
    if not user or not q:
        return None
    used = home_usage(user, fresh=True)
    if used + int(add_bytes or 0) > q:
        gb = lambda b: f"{b / 1024 ** 3:.1f} GB"  # noqa: E731
        return f"that would put {user}'s home over its {gb(q)} quota ({gb(used)} used); free some space or ask Bradly"
    return None


def quota_refusal_demo(key: str, add_bytes: int) -> str | None:
    if not key.startswith("/homes/"):
        return None
    user = key.strip("/").split("/")[1]
    q = quota_bytes()
    if q and home_usage(user) + int(add_bytes or 0) > q:
        return f"that would put {user}'s home over its {q // 1024 ** 3} GB quota"
    return None


def demo_add_usage(key: str, n: int):
    if key.startswith("/homes/"):
        u = key.strip("/").split("/")[1]
        d = _demo_usage()
        d[u] = d.get(u, 0) + int(n or 0)


def quotas() -> dict:
    """Every home's use against the quota, for Storage (admins)."""
    cfg = load()
    users = sorted(_demo_usage()) if cfg.demo else sorted(u for u in (os.listdir(cfg.directory.homes_path) if os.path.isdir(cfg.directory.homes_path) else []) if not u.startswith("."))
    rows = [quota_of(u) for u in users]
    return {"demo": cfg.demo, "quota": quota_bytes() or None, "warn_pct": cfg.storage.quota_warn_pct, "homes": rows,
            "enforced_by": "the dashboard" + (" and the filesystem (setquota)" if fs_quota_on() else ""),
            "homes_on": cfg.storage.homes_on, "homes_path": cfg.directory.homes_path}


def fs_quota_on() -> bool:
    if load().demo or not which("quotaon"):
        return False
    r = run(["quotaon", "-pu", load().directory.homes_path], timeout=10)
    return r["ok"] and "is on" in (r["out"] or "")


def setquota_cmd(user: str, mount: str) -> list[str]:
    """Pure: the filesystem quota for one home (soft = hard = the quota, in 1 KiB blocks)."""
    kb = str(quota_bytes() // 1024)
    return ["setquota", "-u", user, kb, kb, "0", "0", mount]


# ---- Previous Versions reach (row 14) ----------------------------------------------
def versions_days() -> int:
    return int(load().storage.versions_days or 0)


def within_versions(rows: list[dict], now: datetime | None = None) -> list[dict]:
    days = versions_days()
    if not days:
        return rows
    cut = ((now or datetime.now()) - timedelta(days=days)).isoformat(timespec="seconds")
    return [r for r in rows if (r.get("time") or "")[:19] >= cut[:19]]


# ---- the live backup target (row 15) -----------------------------------------------
_target_cache: dict = {}


def _synology_ready() -> bool:
    cfg = load()
    return os.path.ismount(cfg.nas.mount) if os.path.isdir(cfg.nas.mount) else False


def _sftp_host(repo: str) -> str | None:
    m = re.match(r"^sftp:(?:([^@/:]+)@)?([^:/]+)(?::|/)", repo or "")
    return ((m.group(1) + "@") if m and m.group(1) else "") + m.group(2) if m else None


def _home_ready(repo: str) -> bool:
    host = _sftp_host(repo)
    if not host or not which("ssh"):
        return False
    r = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=yes", host, "true"], timeout=12)
    return r["ok"]


def backup_targets(probe=None) -> dict:
    """{live, repo, targets:[{id, repo, ready, why}]}. The first ready target is live; none ready = red."""
    cfg = load()
    now = time.time()
    if probe is None and _target_cache.get("t", 0) > now - 300:
        return _target_cache["v"]
    syn_repo = cfg.backups.synology_repo or cfg.backups.restic_repo
    home_repo = cfg.backups.arise_home_repo
    probe = probe or {"synology": lambda: _synology_ready(), "arise-home": lambda: bool(home_repo) and _home_ready(home_repo)}
    rows = []
    for t in cfg.backups.targets or ["synology"]:
        if t == "synology":
            ok = bool(probe["synology"]())
            rows.append({"id": t, "name": "the Synology", "repo": syn_repo, "ready": ok, "why": "mounted" if ok else f"{cfg.nas.mount} is not mounted"})
        elif t == "arise-home":
            ok = bool(home_repo) and bool(probe["arise-home"]())
            rows.append({"id": t, "name": "Arise-Home over Tailscale", "repo": home_repo or None, "ready": ok,
                         "why": "reachable" if ok else ("set [backups] arise_home_repo in arise.toml" if not home_repo else "not reachable over Tailscale")})
    live = next((r for r in rows if r["ready"]), None)
    v = {"live": live["id"] if live else None, "repo": live["repo"] if live else None, "name": live["name"] if live else None, "targets": rows,
         "error": None if live else "no backup target is ready: the Synology is not mounted and Arise-Home is not reachable"}
    if cfg.demo:
        v = {"live": "arise-home", "repo": home_repo or "sftp:arise-backup@arise-home:/srv/arise/backups/restic-pineville", "name": "Arise-Home over Tailscale",
             "targets": [{"id": "synology", "name": "the Synology", "repo": syn_repo, "ready": False, "why": "no drives yet (sample)"},
                         {"id": "arise-home", "name": "Arise-Home over Tailscale", "repo": home_repo or "sftp:arise-backup@arise-home:/srv/arise/backups/restic-pineville", "ready": True, "why": "reachable (sample)"}],
             "error": None, "demo": True}
    _target_cache.update(t=now, v=v)
    return v


# ---- Shared with me (row 19) -------------------------------------------------------
def _store_path() -> str:
    return str(load().state_dir / "shared-with.json")


def _read() -> list[dict]:
    if load().demo:
        from . import demo_state
        return demo_state.get("sharing.grants", list)
    try:
        return json.load(open(_store_path(), encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _write(rows: list[dict]):
    if load().demo:
        from . import demo_state
        demo_state.put("sharing.grants", rows)
        return
    p = _store_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    os.replace(p + ".tmp", p)


def _members(group: str) -> list[str]:
    from . import directory
    try:
        g = next((x for x in directory.list_groups().get("groups", []) if x["name"].lower() == group.lower()), None)
    except Exception:  # noqa: BLE001
        g = None
    return list(g["members"]) if g else []


def _known(name: str) -> bool:
    from . import directory
    try:
        if name.startswith("@"):
            return any(g["name"].lower() == name[1:].lower() for g in directory.list_groups().get("groups", []))
        return any(u["name"].lower() == name.lower() for u in directory.list_users().get("users", []))
    except Exception:  # noqa: BLE001
        return False


def link_name(name: str, owner: str, taken) -> str:
    """'Setlist.pdf' from bradly -> 'Setlist (from bradly).pdf', numbered if that is taken."""
    stem, ext = os.path.splitext(name) if "." in name[1:] else (name, "")
    cand = f"{stem} (from {owner}){ext}"
    n = 2
    while taken(cand):
        cand = f"{stem} (from {owner} {n}){ext}"; n += 1
    return cand


def acl_cmds(abs_path: str, principal: str, perm: str, stop_at: str, is_dir: bool, remove: bool = False) -> list[list[str]]:
    """Pure: the setfacl lines that grant (or take back) one principal's access to one item,
    plus traverse (x) on each folder above it up to stop_at. principal: 'u:name' or 'g:name'."""
    mode = "rwX" if perm == "write" else "rX"
    cmds = []
    if remove:
        cmds.append(["setfacl"] + (["-R"] if is_dir else []) + ["-x", principal, abs_path])
        if is_dir:
            cmds.append(["setfacl", "-R", "-d", "-x", principal, abs_path])
    else:
        cmds.append(["setfacl"] + (["-R"] if is_dir else []) + ["-m", f"{principal}:{mode}", abs_path])
        if is_dir:
            cmds.append(["setfacl", "-R", "-d", "-m", f"{principal}:{mode}", abs_path])
        p = os.path.dirname(os.path.normpath(abs_path))
        stop = os.path.normpath(stop_at)
        while _under(p, stop):
            cmds.append(["setfacl", "-m", f"{principal}:--x", p])
            if p == stop:
                break
            p = os.path.dirname(p)
    return cmds


def _stop_for(abs_path: str) -> str:
    """The top folder whose traverse matters: the person's home, or the share folder."""
    cfg = load()
    homes = cfg.directory.homes_path
    if _under(abs_path, homes):
        return os.path.join(homes, os.path.relpath(abs_path, homes).split(os.sep)[0])
    shares_root = os.path.join(cfg.system.data_root, "shares")
    if _under(abs_path, shares_root):
        return os.path.join(shares_root, os.path.relpath(abs_path, shares_root).split(os.sep)[0])
    return os.path.dirname(abs_path)


def has_entry(acl_text: str, principal: str) -> bool:
    """Pure: does getfacl output carry a named entry for 'u:name' / 'g:name'?"""
    kind, name = principal.split(":", 1)
    tag = "user" if kind == "u" else "group"
    return any(ln.strip().startswith(f"{tag}:{name}:") for ln in (acl_text or "").splitlines())


def _had(principal: str, path: str) -> bool:
    """True when the principal already has its own entry here (a department ACL, say):
    a share must neither change nor, on revoke, take away what was there before it."""
    if load().demo or not which("getfacl"):
        return False
    r = run(["getfacl", "-cp", path], timeout=15)
    return r["ok"] and has_entry(r["out"], principal)


def plan_grant(abs_path: str, principal: str, perm: str, stop_at: str, is_dir: bool, had=_had) -> tuple[list[list[str]], list[str]]:
    """The setfacl lines for one grant, minus every path where the principal already had an entry,
    and the paths this grant adds (kept on the share, so revoke takes back exactly those)."""
    cmds, added = [], []
    for c in acl_cmds(abs_path, principal, perm, stop_at, is_dir):
        path = c[-1]
        if had(principal, path):
            continue
        cmds.append(c)
        if path not in added:
            added.append(path)
    return cmds, added


def plan_revoke(g: dict, principal: str, others: list[dict]) -> list[list[str]]:
    """Pure: take back only what this share added, and the traverse on a folder above only
    when no other share for the same principal added it too."""
    added = (g.get("acl_added") or {}).get(principal, [])
    still = {p for r in others for p in (r.get("acl_added") or {}).get(principal, [])}
    cmds = []
    for path in added:
        if path == g["abs"]:
            cmds += [c for c in acl_cmds(g["abs"], principal, g["perm"], g["abs"], g["dir"], remove=True)]
        elif path not in still:
            cmds.append(["setfacl", "-x", principal, path])
    # The removal above is recursive, so another live share to the same principal of this item,
    # or of something inside it, lost its entries too: put those back, with the traverse on the
    # folders between it and this item.
    for r in others:
        to = {("g:" + t[1:]) if t.startswith("@") else ("u:" + t) for t in r.get("to", [])}
        if principal in to and _under(r["abs"], g["abs"]):
            cmds += acl_cmds(r["abs"], principal, r["perm"], g["abs"], r["dir"])
    return cmds


def _apply_acls(cmds: list[list[str]]) -> list[str]:
    if load().demo or not which("setfacl"):
        return []
    errs = []
    for c in cmds:
        r = run(c, timeout=60)
        if not r["ok"]:
            errs.append(" ".join(c[:-1]) + ": " + (r["err"] or r["out"]).strip()[:160])
    return errs


def _place_links(g: dict) -> None:
    """<shared>/<person>/<item (from owner)> -> the item, for each person the grant reaches."""
    if load().demo:
        return
    base = str(load().storage.shared_path)
    for u in g["users"]:
        d = os.path.join(base, u)
        try:
            os.makedirs(d, exist_ok=True)
            os.chmod(d, 0o755)
            link = os.path.join(d, g["link"])
            if not os.path.lexists(link):
                os.symlink(g["abs"], link)
        except OSError:
            pass


def _drop_links(g: dict) -> None:
    if load().demo:
        return
    base = str(load().storage.shared_path)
    for u in g["users"]:
        link = os.path.join(base, u, g["link"])
        try:
            if os.path.islink(link):
                os.remove(link)
        except OSError:
            pass


def notify(users: list[str], title: str, body: str) -> dict:
    """Push to their devices and, where the profile has a personal email, a short email (row 19)."""
    from . import push
    sent = {"push": None, "email": []}
    try:
        sent["push"] = push.send(title, body, url="/#files", tag="", users=users)
    except Exception as e:  # noqa: BLE001 - a notice never blocks the share
        sent["push"] = {"ok": False, "err": str(e)}
    from . import mail
    for u in users:
        addr = personal_email(u)
        if not addr:
            continue
        try:
            sent["email"].append({"user": u, **mail.send_notice(addr, title, body)})
        except Exception as e:  # noqa: BLE001
            sent["email"].append({"user": u, "ok": False, "err": str(e)})
    return sent


def personal_email(user: str) -> str | None:
    """The profile's personal email (round 5, rows 6 and 9; the accounts worker adds the field)."""
    from . import directory
    for fn in ("personal_email", "profile_of", "profile"):
        f = getattr(directory, fn, None)
        if f:
            try:
                v = f(user)
                v = v.get("personal_email") if isinstance(v, dict) else v
                if v:
                    return str(v)
            except Exception:  # noqa: BLE001
                pass
    return None


def share_with(root_id: str, rel: str, to: list[str], perm: str, who: dict) -> dict:
    from . import files
    perm = perm if perm in PERMS else "read"
    to = [t.strip() for t in (to or []) if t and t.strip()]
    if not to:
        return {"ok": False, "err": "pick a person or a group to share with"}
    me = str(who.get("user", ""))
    bad = [t for t in to if not re.fullmatch(r"@?[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}", t) or not _known(t)]
    if bad:
        return {"ok": False, "err": "not a person or group in the directory: " + ", ".join(bad)}
    if any(t.lower() == me.lower() for t in to):
        return {"ok": False, "err": "you already have it"}
    cfg = load()
    if cfg.demo:
        key = files._demo_rel(root_id, "/" + rel.strip("/") if rel.strip("/") else "/", who)
        if key is None or key == "/" or not files.demo_find(key):
            return {"ok": False, "err": "no such file"}
        if not is_admin(who) and not key.startswith(f"/homes/{me}/"):
            return {"ok": False, "err": "you can share only your own files"}
        if hidden_demo(key, who):
            return {"ok": False, "err": "no such file"}
        e = files.demo_find(key)
        absp, is_dir, name = key, bool(e[1]), e[0]
    else:
        rs = {r["id"]: r for r in files.roots(who)}
        if root_id not in rs:
            return {"ok": False, "err": "not a place you can share from"}
        absp = files._resolve(rs[root_id], rel, who, "share")
        if not absp or not os.path.exists(absp) or absp == os.path.realpath(rs[root_id]["path"]):
            return {"ok": False, "err": "no such file"}
        if not is_admin(who) and not _under(absp, os.path.join(cfg.directory.homes_path, me)):
            return {"ok": False, "err": "you can share only your own files"}
        is_dir, name = os.path.isdir(absp), os.path.basename(absp)
    users = sorted({m for t in to for m in (_members(t[1:]) if t.startswith("@") else [t])} - {me})
    with _lock:
        rows = _read()
        taken = {r["link"] for r in rows if set(r["users"]) & set(users)}
        g = {"id": secrets.token_hex(6), "owner": me, "abs": absp, "root": root_id, "rel": "/" + rel.strip("/"), "name": name,
             "dir": is_dir, "to": to, "users": users, "perm": perm, "at": datetime.now().isoformat(timespec="seconds"),
             "link": link_name(name, me, lambda n: n in taken)}
        errs, g["acl_added"] = [], {}
        for t in to:
            principal = ("g:" + t[1:]) if t.startswith("@") else ("u:" + t)
            cmds, g["acl_added"][principal] = plan_grant(absp, principal, perm, _stop_for(absp), is_dir)
            errs += _apply_acls(cmds)
        rows.append(g)
        _write(rows)
    _place_links(g)
    audit.record(me, "files.share", ", ".join(to), detail=f"{perm} {g['rel']} ({root_id})")
    n = notify(users, f"{me} shared “{name}” with you", f"{'Edit' if perm == 'write' else 'Open'} it from Shared with me on your Mac (the 'shared' share) or in Finder.")
    return {"ok": True, "demo": cfg.demo, "share": _public(g), "acl_errors": errs, "notified": n}


def _public(g: dict) -> dict:
    return {k: g[k] for k in ("id", "owner", "name", "dir", "to", "perm", "at", "link", "root", "rel")}


def revoke(share_id: str, who: dict) -> dict:
    me = str(who.get("user", ""))
    with _lock:
        rows = _read()
        g = next((r for r in rows if r["id"] == share_id), None)
        if not g:
            return {"ok": False, "err": "no such share"}
        if g["owner"].lower() != me.lower() and not is_admin(who):
            return {"ok": False, "err": "only the person who shared it, or an admin, can stop sharing it"}
        rows.remove(g)
        errs = []
        for t in g["to"]:
            principal = ("g:" + t[1:]) if t.startswith("@") else ("u:" + t)
            errs += _apply_acls(plan_revoke(g, principal, rows))
        _write(rows)
    _drop_links(g)
    audit.record(me, "files.share.revoke", ", ".join(g["to"]), detail=g["rel"])
    return {"ok": True, "demo": load().demo, "acl_errors": errs}


def shared_with(who: dict) -> list[dict]:
    me = str(who.get("user", "")).lower()
    return [_public(r) for r in _read() if me in [u.lower() for u in r["users"]]]


def grants_for(who: dict | None) -> list[dict]:
    if not who:
        return []
    me = str(who.get("user", "")).lower()
    return [r for r in _read() if me in [u.lower() for u in r["users"]]]


def listing(who: dict) -> dict:
    """GET /api/files/shared: what others shared with me, and what I share."""
    return {"demo": load().demo, "with_me": shared_with(who), "by_me": [_public(r) for r in _read() if r["owner"].lower() == str(who.get("user", "")).lower()],
            "all": [_public(r) for r in _read()] if is_admin(who) else None}

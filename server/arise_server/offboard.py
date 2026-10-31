"""Offboarding (round 2, 24; round 4, 82).

"Disable the login after 30 days. Move the files to the next appropriate
member or account." An admin marks someone as leaving and picks who takes
their files. Nothing happens for 30 days (the person may still need in, or
the admin may change their mind: Cancel). On the day, the daily sweep
disables the account and moves the home folder's contents into the chosen
person's home under "From <name> (<date>)". The account itself is never
deleted here: deleting is Bradly's click (CLAUDE.md rule 1). Their mailbox
goes with the account when the internal mail server exists (82), and only
after its mail is exported as an mbox file into the same "From <name>"
folder (round 5, 38: profiles.mailbox_export). There is no mail server yet,
which the result says.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
from datetime import datetime, timedelta
from pathlib import Path

from . import audit, directory
from .config import load

GRACE_DAYS = 30
_lock = threading.Lock()
_DEMO: dict = {"entries": []}


def _file() -> Path:
    return load().state_dir / "leaving.json"


def _read() -> list[dict]:
    if load().demo:
        return _DEMO["entries"]
    try:
        return json.loads(_file().read_text()).get("entries", [])
    except (FileNotFoundError, ValueError):
        return []


def _write(entries: list[dict]):
    if load().demo:
        _DEMO["entries"] = entries
        return
    p = _file()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"entries": entries}, indent=1))
    os.replace(tmp, p)


def plan(name: str, move_to: str, by: str, now: datetime | None = None, days: int = GRACE_DAYS) -> dict:
    """Pure: validate and shape a leaving entry."""
    now = now or datetime.now()
    if not directory._ok_name(name):
        return {"ok": False, "err": "bad user name"}
    if not move_to or not directory._ok_name(move_to):
        return {"ok": False, "err": "pick who takes the files"}
    if move_to == name:
        return {"ok": False, "err": "the files cannot move to the person who is leaving"}
    days = int(days)
    if not 0 <= days <= 365:
        return {"ok": False, "err": "the grace period is 0 to 365 days"}
    return {"ok": True, "entry": {"name": name, "move_to": move_to, "by": by, "since": now.isoformat(timespec="seconds"),
                                  "disable_on": (now + timedelta(days=days)).date().isoformat(), "done": None}}


def due(entries: list[dict], now: datetime | None = None) -> list[dict]:
    """Pure: the entries whose day has come and that are not done."""
    today = (now or datetime.now()).date().isoformat()
    return [e for e in entries if not e.get("done") and e.get("disable_on", "9999") <= today]


def status() -> dict:
    return {"entries": _read(), "grace_days": GRACE_DAYS, "demo": load().demo}


def start(name: str, move_to: str, by: str, days: int = GRACE_DAYS) -> dict:
    p = plan(name, move_to, by, days=days)
    if not p["ok"]:
        return p
    with _lock:
        entries = [e for e in _read() if e["name"] != name or e.get("done")]
        entries.append(p["entry"])
        _write(entries)
    audit.record(by, "directory.leaving", name, detail=f"files to {move_to}; disabled on {p['entry']['disable_on']}")
    return {"ok": True, "entry": p["entry"], "demo": load().demo}


def cancel(name: str, by: str) -> dict:
    with _lock:
        entries = _read()
        keep = [e for e in entries if e["name"] != name or e.get("done")]
        if len(keep) == len(entries):
            return {"ok": False, "err": f"{name} is not marked as leaving"}
        _write(keep)
    audit.record(by, "directory.leaving.cancel", name)
    return {"ok": True}


def dest_dir(homes: str, move_to: str, name: str, now: datetime | None = None) -> str:
    """Pure: where the leaver's files land in the next person's home."""
    return os.path.join(homes, move_to, f"From {name} ({(now or datetime.now()).date().isoformat()})")


# ----- round 7, 60: a copy on the Synology first, kept forever --------------------------
def archive_root() -> str:
    cfg = load()
    return str(cfg.people.leavers_archive or os.path.join(cfg.nas.mount, "arise", "leavers"))


def archive_dir(root: str, name: str, now: datetime | None = None) -> str:
    """Pure: where one leaver's copy lands: <archive>/<name> (<date>)."""
    return os.path.join(root, f"{name} ({(now or datetime.now()).date().isoformat()})")


def tally(folder: str) -> tuple[int, int]:
    """(regular files, bytes) under a folder; links are not followed."""
    n = size = 0
    for root, dirs, fls in os.walk(folder):
        for f in fls:
            p = os.path.join(root, f)
            if os.path.isfile(p) and not os.path.islink(p):
                n += 1
                size += os.path.getsize(p)
    return n, size


def same_tally(src: tuple[int, int], dst: tuple[int, int]) -> bool:
    """Pure: every file and every byte arrived."""
    return src[0] == dst[0] and src[1] == dst[1]


def copy_to_archive(name: str, now: datetime) -> dict:
    """Copy the leaver's home to the Synology and check it arrived whole. Nothing is moved until it
    has: a missing Synology holds the move for tomorrow's sweep (the account is already off)."""
    from .util import run, which
    cfg = load()
    src = os.path.join(cfg.directory.homes_path, name)
    if not os.path.isdir(src):
        return {"ok": True, "copied": 0, "note": f"{name} had no home folder"}
    root = archive_root()
    nas = cfg.nas.mount
    if root.startswith(nas.rstrip("/") + "/") and not os.path.ismount(nas):
        return {"ok": False, "held": True, "err": f"the Synology is not mounted at {nas}: the files stay where they are until it is"}
    dst = archive_dir(root, name, now)
    os.makedirs(dst, exist_ok=True)
    if which("rsync"):
        # -rt: files and times; no owners or modes (a Synology share keeps neither); links are skipped
        r = run(["rsync", "-rt", "--no-perms", "--no-owner", "--no-group", src.rstrip("/") + "/", dst.rstrip("/") + "/"], timeout=6 * 3600)
        if not r["ok"]:
            return {"ok": False, "err": "rsync: " + (r["err"] or r["out"]).strip()[-200:]}
    else:
        shutil.copytree(src, dst, symlinks=False, dirs_exist_ok=True, copy_function=shutil.copyfile,
                        ignore=lambda d, names: [n for n in names if os.path.islink(os.path.join(d, n))])
    a, b = tally(src), tally(dst)
    if not same_tally(a, b):
        return {"ok": False, "err": f"the copy is short: {b[0]} of {a[0]} files, {b[1]} of {a[1]} bytes; nothing moved", "to": dst}
    return {"ok": True, "copied": a[0], "bytes": a[1], "to": dst}


def _move_home(name: str, move_to: str, now: datetime) -> dict:
    homes = load().directory.homes_path
    src = os.path.join(homes, name)
    if not os.path.isdir(src):
        return {"ok": True, "moved": 0, "note": f"{name} had no home folder"}
    dst = dest_dir(homes, move_to, name, now)
    os.makedirs(dst, exist_ok=True)
    moved = 0
    for item in sorted(os.listdir(src)):
        target = os.path.join(dst, item)
        if os.path.exists(target):
            target += " (moved)"
        shutil.move(os.path.join(src, item), target)
        moved += 1
    try:
        import pwd
        pw = pwd.getpwnam(move_to)
        for root, dirs, fls in os.walk(dst):
            for n in [root] + [os.path.join(root, d) for d in dirs] + [os.path.join(root, f) for f in fls]:
                try:
                    os.chown(n, pw.pw_uid, pw.pw_gid)
                except OSError:
                    pass
    except KeyError:
        pass
    return {"ok": True, "moved": moved, "to": dst}


def sweep(now: datetime | None = None, dry_run: bool = False, by: str = "arise-offboard.timer") -> dict:
    """The daily run: for each entry whose day has come, disable, then move the files."""
    now = now or datetime.now()
    cfg = load()
    results = []
    with _lock:
        entries = _read()
        for e in due(entries, now):
            r = {"name": e["name"], "move_to": e["move_to"]}
            if dry_run:
                r["would"] = f"disable {e['name']}, move their files to {e['move_to']}"
                results.append(r)
                continue
            d = directory.enable_user(e["name"], False)
            r["disabled"] = bool(d.get("ok"))
            if not d.get("ok"):
                r["err"] = d.get("err") or d.get("out") or "samba-tool refused"
                results.append(r)
                audit.record(by, "directory.leaving.sweep", e["name"], ok=False, detail=r["err"])
                continue   # files stay put until the account is really off; tomorrow's sweep tries again
            try:
                from . import accounts
                if not e.get("alerted_off"):
                    accounts.switched(e["name"], False, by)   # round 7, 86
                    e["alerted_off"] = True
            except Exception:  # noqa: BLE001
                pass
            if cfg.demo:
                r["archive"] = {"ok": True, "demo": True, "to": archive_dir(archive_root(), e["name"], now)}
                r["files"] = {"ok": True, "demo": True, "moved": 0}
            else:
                # Round 7, 60: a copy on the Synology, checked, before anything moves; kept forever.
                try:
                    r["archive"] = e.get("archived") or copy_to_archive(e["name"], now)
                except OSError as ex:
                    r["archive"] = {"ok": False, "err": str(ex)}
                if not r["archive"].get("ok"):
                    r["files"] = {"ok": False, "held": True, "err": "not moved: " + str(r["archive"].get("err", ""))}
                    results.append(r)
                    audit.record(by, "directory.leaving.archive", e["name"], ok=False, detail=str(r["archive"].get("err", ""))[:200])
                    try:
                        from . import accounts
                        accounts.alert(f"Leaving: {e['name']}'s files were not copied to the Synology ({r['archive'].get('err', '')}). Tried again tomorrow.")
                    except Exception:  # noqa: BLE001
                        pass
                    continue
                e["archived"] = r["archive"]
                try:
                    r["files"] = _move_home(e["name"], e["move_to"], now)
                except OSError as ex:
                    r["files"] = {"ok": False, "err": str(ex)}
            # Round 5, 38: their mail is saved into the next person's folder before the mailbox can go.
            # The mailbox is never deleted here; whatever deletes it later checks mailbox_exported first.
            if cfg.demo:
                r["mailbox"] = {"ok": True, "demo": True, "exported": 0, "note": "(sample) no mail server in the sample"}
            else:
                from . import profiles
                r["mailbox"] = profiles.mailbox_export(e["name"], dest_dir(cfg.directory.homes_path, e["move_to"], e["name"], now))
            e["mailbox_exported"] = bool(r["mailbox"].get("ok"))
            # Round 6, 4: their profile comes off every church Mac, through the checked path
            # (the helper proves each file is on the server first; macs.py, docs/MACS.md).
            try:
                from . import macs
                r["macs"] = macs.queue_removals(e["name"], by=by, moved_to=(r.get("files") or {}).get("to"))
            except Exception as ex:  # noqa: BLE001 - a Mac problem never stops the leaving sweep
                r["macs"] = {"ok": False, "err": str(ex)}
            e["done"] = now.isoformat(timespec="seconds")
            e["result"] = r
            results.append(r)
            audit.record(by, "directory.leaving.sweep", e["name"], ok=bool(r["files"].get("ok")),
                         detail=f"disabled; files to {e['move_to']}")
        if not dry_run:
            _write(entries)
    return {"ok": all(r.get("disabled", True) and r.get("files", {}).get("ok", True) for r in results),
            "results": results, "dry_run": dry_run, "demo": cfg.demo}

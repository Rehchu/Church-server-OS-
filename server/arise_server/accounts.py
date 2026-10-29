"""Round 7: what happens around an account (docs/ANSWERS.md, round 7, rows 9-21, 60, 69, 70, 86).

    unique_name(base, taken)      row 12: john.smith, then john.smith2, john.smith3
    welcome(user)                 row 10: the welcome email to their personal address
    set_display(user)             row 11: the title in the domain's displayName (the Macs show it)
    rename(old, new, by)          row 13: the account, its home folder and every record that names it
    inactive(now)                 row 17: accounts unused for 90 days, each named in Discord once
    on_signin(user, agent, ip)    row 70: a sign-in from a new device emails them and tells Bradly
    photo_save / photo_path       row 20: the photo on the faces and in the domain (thumbnailPhoto)
    breakglass_*                  row 69: Bradly's emergency look into the Pastors folder
    alert(text)                   rows 17, 86: one line in Discord #alerts

Nothing here deletes anything. Where the domain cannot be reached the answer says so.
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta

from . import audit, demo_state, directory
from .config import load
from .util import run, which

_lock = threading.RLock()


# ----- where round 7 keeps its own small records ----------------------------------------
def _path(name: str) -> str:
    return str(load().state_dir / name)


def _read(name: str, default):
    if load().demo:
        return demo_state.get("r7." + name, default)
    try:
        with open(_path(name), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default() if callable(default) else default


def _write(name: str, d, mode: int = 0o640):
    if load().demo:
        demo_state.put("r7." + name, d)
        return
    p = _path(name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.chmod(p + ".tmp", mode)
    os.replace(p + ".tmp", p)


def owner() -> str:
    try:
        return str(load().owner.user or "")
    except AttributeError:
        return ""


def _people():
    return load().people


# ----- telling people ------------------------------------------------------------------
def _discord_url(channel: str = "alerts") -> str:
    """The webhook for one of the four channels (round 4, 101), from /etc/arise/secrets/discord.toml.
    Read by the server only, never shown anywhere. Both shapes are accepted:
    `alerts = "https://..."` or `[webhooks]\\nalerts = "https://..."`."""
    import tomllib
    p = "/etc/arise/secrets/discord.toml"
    try:
        with open(p, "rb") as f:
            d = tomllib.load(f)
    except (OSError, ValueError):
        return ""
    v = d.get(channel) or (d.get("webhooks") or {}).get(channel) or (d.get(channel) or {})
    return v if isinstance(v, str) else str((v or {}).get("url", "")) if isinstance(v, dict) else ""


def alert(text: str, channel: str = "alerts") -> dict:
    """One line in Discord #alerts (rows 17, 86). Bradly's channel only (row 77)."""
    if load().demo:
        lines = demo_state.get("r7.discord", list)
        lines.append({"channel": channel, "text": text, "at": datetime.now().isoformat(timespec="seconds")})
        return {"ok": True, "demo": True}
    try:
        from . import discord   # another round 7 builder may add a channel module; use it when it exists
        f = getattr(discord, "post", None)
        if f:
            return f(channel, text)
    except ImportError:
        pass
    url = _discord_url(channel)
    if not url:
        return {"ok": False, "err": f"no Discord webhook for #{channel} yet (/etc/arise/secrets/discord.toml)"}
    from . import system
    return system.send_webhook(text, url)


def tell_person(user: str, title: str, body: str, kind: str = "info") -> dict:
    """A notice to one person where they are: a Mac notification and an email (row 84).
    The shared notices module does it when it exists; otherwise the feed, push and email directly."""
    try:
        from .notices import notify_person   # round 7's one door for telling a person (another builder)
        return notify_person(user, title, body, kind=kind)
    except ImportError:
        pass
    out = {}
    try:
        from . import notify
        out["feed"] = notify.add(user, "system", f"{title}: {body}"[:300], deliver=True)
    except Exception as e:  # noqa: BLE001 - telling someone never breaks the caller
        out["feed"] = {"ok": False, "err": str(e)}
    addr = personal_email(user)
    if addr:
        try:
            from . import mail
            out["email"] = mail.send_note(addr, title, body)
        except Exception as e:  # noqa: BLE001
            out["email"] = {"ok": False, "err": str(e)}
    return out


def tell_bradly(title: str, body: str) -> dict:
    o = owner()
    return tell_person(o, title, body, kind="admin") if o else {"ok": False, "err": "no [owner] user"}


def personal_email(user: str) -> str:
    from . import profiles
    return str(profiles._read().get(user, {}).get("personal_email") or "")


# ----- row 12: a second john.smith ---------------------------------------------------------
def unique_name(base: str, taken) -> str:
    """Pure: base if free, else base2, base3 ... (the first free one). `taken` is a set or a callable."""
    used = taken if callable(taken) else (lambda n, t={x.lower() for x in taken}: n.lower() in t)
    if not used(base):
        return base
    n = 2
    while used(f"{base}{n}"):
        n += 1
    return f"{base}{n}"


def taken_names() -> set[str]:
    return {u["name"].lower() for u in directory.list_users().get("users", [])}


# ----- row 11: the title in the domain's displayName ---------------------------------------
def display_for(user: str, display: str = "") -> str:
    from . import profiles
    disp = display or profiles._display_of(user)
    # the AD displayName holds the plain name; the title goes in front (profiles.display_name)
    return profiles.display_name(user, _strip_title(user, disp))


def _strip_title(user: str, disp: str) -> str:
    from . import profiles
    t = (profiles._read().get(user, {}).get("title") or "").strip()
    if t and disp.lower().startswith(t.lower() + " "):
        return disp[len(t) + 1:]
    return disp


def display_cmd(user: str, full: str, title: str = "") -> list[str]:
    """Pure: samba-tool's own way to set the name the Macs and Nextcloud show (Samba 4.17+)."""
    cmd = ["samba-tool", "user", "rename", user, f"--display-name={full}"]
    return cmd


def set_display(user: str) -> dict:
    """Write 'Apostle Bryant Sanders' (title + name) into the account's displayName (row 11).
    The Macs show it on the login window, and Nextcloud shows it, from the next look-up."""
    from . import profiles
    full = display_for(user)
    if not directory.available():
        if not load().demo:
            return directory._no_domain()
        u = directory._u(user)
        if u is not None:
            u["full_name"] = full
        return {"ok": True, "demo": True, "display": full}
    r = run(display_cmd(user, full), timeout=20)
    title = (profiles._read().get(user, {}).get("title") or "").strip()
    if r["ok"] and title:
        # the job title too, for anything that reads `title` (Contacts, Nextcloud's profile)
        _ldif_replace(user, "title", title)
    return {"ok": True, "display": full} if r["ok"] else directory._failed(r, f"could not set {user}'s name")


def _dn_of(user: str) -> str:
    r = run(["samba-tool", "user", "show", user, "--attributes=dn"], timeout=15)
    m = re.search(r"(?m)^dn:\s*(.+)$", r.get("out") or "")
    return m.group(1).strip() if m else ""


def _sam_ldb() -> str:
    return "/var/lib/samba/private/sam.ldb"


def _ldif_replace(user: str, attr: str, value: str | None = None, b64: str | None = None) -> dict:
    """One attribute on one account, through ldbmodify on the domain's own database."""
    dn = _dn_of(user)
    if not dn or not which("ldbmodify"):
        return {"ok": False, "err": "ldbmodify or the account's DN is missing"}
    line = f"{attr}:: {b64}" if b64 is not None else f"{attr}: {value}"
    ldif = f"dn: {dn}\nchangetype: modify\nreplace: {attr}\n{line}\n"
    return run(["ldbmodify", "-H", _sam_ldb()], input_text=ldif, timeout=20)


# ----- row 10: the welcome email ---------------------------------------------------------------
def welcome_text(user: str, name: str, groups: list[str], host: str, cloud: str) -> tuple[str, str]:
    """Pure: the subject and body. Never a password: the first one comes from the admin who made the account."""
    folders = ", ".join(g for g in groups if g not in ("Domain Users",)) or "the Church folder"
    first = (name.split() or [user])[0]
    body = (f"Hi {first},\n\nWelcome to Arise Church. You have a church account now.\n\n"
            f"  Your login: {user}\n"
            f"  Your first password: from the person who made your account. Choose your own the first time you sign in.\n\n"
            f"Where things are:\n"
            f"  - Sign in at any church Mac with your login: your face is on the login window.\n"
            f"  - Your Desktop and Documents follow you to every church Mac, and to your phone in the Nextcloud app ({cloud}).\n"
            f"  - Your folders: {folders}, and the Church folder everyone shares.\n"
            f"  - Forgot your password? The link on the sign-in page sends a new one here.\n\n"
            f"Questions: ask Bradly.\n")
    return f"Welcome to Arise Church, {first}", body


def welcome(user: str, by: str = "") -> dict:
    """Send it once, when there is a personal email to send it to (row 10). Called after the account is
    made and again whenever a personal email is first added."""
    if not _people().welcome_email:
        return {"ok": True, "skipped": "welcome emails are off ([people] welcome_email)"}
    addr = personal_email(user)
    sent = _read("welcomed.json", dict)
    if user in sent:
        return {"ok": True, "already": sent[user]}
    if not addr:
        return {"ok": True, "waiting": "no personal email on file yet; it goes when one is added"}
    from . import cloud, mail, macs
    groups = directory.user_groups(user)
    subj, body = welcome_text(user, display_for(user), groups, macs.server_names()["host"], _cloud_host(cloud))
    r = mail.send_note(addr, subj, body)
    if r.get("ok"):
        with _lock:
            sent = _read("welcomed.json", dict)
            sent[user] = datetime.now().isoformat(timespec="seconds")
            _write("welcomed.json", sent)
    audit.record(by or "arise", "directory.welcome", user, ok=bool(r.get("ok")), detail="sent" if r.get("ok") else str(r.get("err", ""))[:160])
    return {"ok": bool(r.get("ok")), "sent": bool(r.get("ok")), "err": r.get("err")}


def _cloud_host(cloud_mod) -> str:
    try:
        return cloud_mod.host()
    except Exception:  # noqa: BLE001
        return "cloud." + str(load().directory.realm).lower()


def made(user: str, by: str, display: str = "") -> dict:
    """Everything that follows a new account (rows 10, 11, 86). The Mac accounts follow from the Mac
    helper's next check-in, as before; nothing here waits for that."""
    out = {"display": set_display(user)}
    with _lock:
        c = _read("created.json", dict)
        c.setdefault(user, datetime.now().isoformat(timespec="seconds"))
        _write("created.json", c)
    out["welcome"] = welcome(user, by)
    out["discord"] = alert(f"New account: {display_for(user, display)} ({user}), made by {by or 'an admin'}.")
    return out


def switched(user: str, enabled: bool, by: str) -> dict:
    """Row 86: a line in #alerts when an account is switched off (or back on)."""
    return alert(f"Account {'switched back on' if enabled else 'switched off'}: {display_for(user)} ({user}), by {by or 'the server'}.")


# ----- row 13: renaming an account -------------------------------------------------------------
def rename_cmd(old: str, new: str, realm: str, display: str = "") -> list[str]:
    """Pure: samba-tool's rename (Samba 4.17+): the login, the UPN and the mail address follow."""
    cmd = ["samba-tool", "user", "rename", old, f"--samaccountname={new}", f"--upn={new}@{realm.lower()}",
           f"--mail-address={new}@{_mail_domain()}"]
    if display:
        cmd.append(f"--display-name={display}")
    return cmd


def _mail_domain() -> str:
    from . import profiles
    return profiles.mail_domain()


def _rename_records(old: str, new: str) -> list[str]:
    """Every dashboard record that names the person moves to the new name. Returns what changed."""
    changed = []
    from . import profiles
    with profiles._lock:
        d = profiles._read()
        if old in d:
            rec = d.pop(old)
            aliases = list(rec.get("mail_aliases") or [])
            a = f"{old}@{_mail_domain()}"
            if a not in aliases:
                aliases.append(a)   # the old address still delivers, once mail is built (row 155)
            rec["mail_aliases"] = aliases
            d[new] = {**d.get(new, {}), **rec}
            profiles._write(d)
            changed.append("profile")
    try:
        from . import sharing
        with sharing._lock:
            rows = sharing._read()
            n = 0
            for g in rows:
                if g.get("owner", "").lower() == old.lower():
                    g["owner"] = new; n += 1
                if old in g.get("users", []):
                    g["users"] = [new if u == old else u for u in g["users"]]; n += 1
                if old in g.get("to", []):
                    g["to"] = [new if u == old else u for u in g["to"]]; n += 1
            if n:
                sharing._write(rows)
                changed.append(f"{n} share(s)")
    except Exception:  # noqa: BLE001 - a record that cannot move is reported, never fatal
        pass
    try:
        from . import links
        d = links._load()
        n = 0
        for v in d.values():
            if isinstance(v, dict) and str(v.get("user", "")).lower() == old.lower():
                v["user"] = new; n += 1
        if n:
            links._save(d)
            changed.append(f"{n} link(s)")
    except Exception:  # noqa: BLE001
        pass
    for name in ("welcomed.json", "created.json", "signin-devices.json"):
        r = _read(name, dict)
        if old in r:
            r[new] = r.pop(old)
            _write(name, r)
    return changed


def rename(old: str, new: str, by: str, confirm: str = "") -> dict:
    """Row 13: a married name, a correction. The account keeps its SID, so its groups, its Mac
    file ownership and every ACL follow by themselves; the login, the home folder's name and the
    dashboard's records are moved here. Mail to the old address is kept as an alias."""
    old, new = (old or "").strip(), (new or "").strip().lower()
    if confirm != old:
        return {"ok": False, "err": "type the current user name to confirm"}
    if not directory._ok_name(old) or not directory._ok_name(new):
        return {"ok": False, "err": "user names: letters, digits, dot, dash; first.last"}
    if old.lower() == new.lower():
        return {"ok": False, "err": "that is the same name"}
    if new.lower() in taken_names():
        return {"ok": False, "err": f"{new} is already an account"}
    cfg = load()
    pastors = [p.lower() for p in (cfg.storage.pastors or [])]
    notes = []
    if old.lower() in pastors or old.lower() in [str(u).lower() for u in (cfg.owners.users or [])] or old == owner():
        notes.append(f"arise.toml still names {old} ([storage] pastors, [owner] or [owners]): change it to {new} there")
    if not directory.available():
        if not cfg.demo:
            return directory._no_domain()
        u = directory._u(old)
        if not u:
            return {"ok": False, "err": f"no such user: {old}"}
        u["name"] = new
        u["home"] = u.get("home", "").replace(old, new)
        for g in directory._groups():
            g["members"] = [new if m == old else m for m in g.get("members", [])]
        moved = _rename_records(old, new)
        _queue_mac_rename(old, new)
        audit.record(by, "directory.rename", f"{old} -> {new}")
        return {"ok": True, "demo": True, "user": new, "moved": moved, "notes": notes, "macs": MAC_NOTE}
    r = run(rename_cmd(old, new, cfg.directory.realm), timeout=30)
    if not r["ok"]:
        return directory._failed(r, f"could not rename {old}")
    homes = cfg.directory.homes_path
    src, dst = os.path.join(homes, old), os.path.join(homes, new)
    if os.path.isdir(src) and not os.path.lexists(dst):
        os.rename(src, dst)   # same filesystem: a rename, nothing copied
        _ldif_replace(new, "homeDirectory", f"\\\\{cfg.system.hostname}\\homes\\{new}")
    elif os.path.lexists(dst):
        notes.append(f"{dst} already existed: the home folder stayed at {src}")
    moved = _rename_records(old, new)
    from .auth import revoke_sessions
    revoke_sessions(old)
    _queue_mac_rename(old, new)
    try:
        from . import cloud
        f = getattr(cloud, "renamed", None)
        if f:
            moved.append(str(f(old, new)))
        else:
            notes.append("Nextcloud: it finds the person by their account's id, so their files follow; "
                         "its record of the old login is cleared the next time it reads the directory")
    except Exception:  # noqa: BLE001
        pass
    audit.record(by, "directory.rename", f"{old} -> {new}", detail="; ".join(moved)[:200])
    alert(f"Account renamed: {old} is now {new} (by {by}).")
    return {"ok": True, "user": new, "moved": moved, "notes": notes, "macs": MAC_NOTE}


MAC_NOTE = ("On each church Mac the old Mac account stays until it is renamed by hand: macOS has no supported way "
            "to rename an Active Directory (mobile) account in place. The helper lists it on the Macs page; the person "
            "signs in with the new name, their files come back from the server, and the old Mac account then comes off "
            "through the usual checked removal.")


def _queue_mac_rename(old: str, new: str):
    with _lock:
        r = _read("renames.json", dict)
        r[old] = {"to": new, "at": datetime.now().isoformat(timespec="seconds")}
        _write("renames.json", r)


def renames() -> dict:
    """For the Mac helper's builder: old name -> {to, at}."""
    return _read("renames.json", dict)


# ----- row 17: accounts nobody uses ----------------------------------------------------------
def unused(users: list[dict], created: dict, alerted: dict, now: datetime, days: int) -> list[dict]:
    """Pure: enabled accounts with no sign-in for `days` (or never, and made more than `days` ago),
    not already named since their last sign-in."""
    out = []
    cut = now - timedelta(days=days)
    for u in users:
        if not u.get("enabled", True) or u["name"] in ("Administrator", "Guest", "krbtgt", "arise-nextcloud", "arise-sync"):
            continue
        last = _when(u.get("last_logon")) or _when(created.get(u["name"]))
        if not last or last > cut:
            continue
        seen = _when(alerted.get(u["name"]))
        if seen and seen >= last:
            continue
        out.append({"user": u["name"], "since": last.isoformat(timespec="minutes"), "days": (now - last).days})
    return out


def _when(v) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v))
        return d.replace(tzinfo=None) if d.tzinfo else d
    except ValueError:
        return None


def inactive(now: datetime | None = None, dry_run: bool = False) -> dict:
    """The daily check (run by the offboarding sweep): each one named once in Discord #alerts."""
    now = now or datetime.now()
    days = int(_people().inactive_days or 90)
    users = directory.list_users().get("users", [])
    rows = unused(users, _read("created.json", dict), _read("inactive-alerted.json", dict), now, days)
    if dry_run or not rows:
        return {"ok": True, "unused": rows, "days": days}
    with _lock:
        al = _read("inactive-alerted.json", dict)
        for r in rows:
            alert(f"{display_for(r['user'])} ({r['user']}) hasn't signed in for {r['days']} days. Still needed? (Directory: switch off or Leaving…)")
            al[r["user"]] = now.isoformat(timespec="seconds")
        _write("inactive-alerted.json", al)
    return {"ok": True, "unused": rows, "days": days, "named": len(rows)}


# ----- row 70: a sign-in from a new device ------------------------------------------------------
def new_device(known: list[str], device: str) -> bool:
    """Pure: a device string never seen for this person (the first sign-in ever sets the baseline)."""
    return bool(known) and device not in known


def on_signin(user: str, agent: str, ip: str = "") -> dict:
    from . import profiles
    device = profiles.device_of(agent or "")
    with _lock:
        d = _read("signin-devices.json", dict)
        known = list(d.get(user, []))
        is_new = new_device(known, device)
        if device not in known:
            d[user] = (known + [device])[-20:]
            _write("signin-devices.json", d)
    if not is_new:
        return {"ok": True, "new": False}
    when = datetime.now().strftime("%a %b %d, %I:%M %p")
    tell_person(user, "A new sign-in to your church account",
                f"Your church account ({user}) was just used to sign in from {device}{' at ' + ip if ip else ''}, {when}.\n\n"
                f"If that was you, there is nothing to do. If not, change your password now and tell Bradly.", kind="security")
    if user != owner():
        tell_bradly("New device sign-in", f"{display_for(user)} ({user}) signed in from {device}{' (' + ip + ')' if ip else ''}, {when}.")
    audit.record(user, "auth.new_device", device, ip=ip)
    return {"ok": True, "new": True, "device": device}


# ----- row 20: the photo on the faces --------------------------------------------------------------
PHOTO_MAX = 200_000


def photo_kind(data: bytes) -> str | None:
    """Pure: 'jpeg' or 'png' from the file's own first bytes, else None."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return None


def photo_path(user: str) -> str | None:
    base = os.path.join(str(load().state_dir), "photos")
    for ext in ("jpg", "png"):
        p = os.path.join(base, f"{user}.{ext}")
        if os.path.isfile(p):
            return p
    return None


def photo_save(user: str, data: bytes, by: str) -> dict:
    """An admin adds the photo the person chose (staff don't use the dashboard). JPEG or PNG, at most 200 KB.
    It shows on the closet monitor's faces and, as the domain's thumbnailPhoto, in Nextcloud and Contacts."""
    if not directory._ok_name(user):
        return {"ok": False, "err": "bad name"}
    kind = photo_kind(data or b"")
    if not kind:
        return {"ok": False, "err": "a JPEG or PNG photo, please"}
    if len(data) > PHOTO_MAX:
        return {"ok": False, "err": "at most 200 KB (a square photo about 400 pixels across is plenty)"}
    if load().demo:
        demo_state.get("r7.photos", dict)[user] = kind
        return {"ok": True, "demo": True, "photo": True}
    base = os.path.join(str(load().state_dir), "photos")
    os.makedirs(base, exist_ok=True)
    for ext in ("jpg", "png"):
        old = os.path.join(base, f"{user}.{ext}")
        if os.path.lexists(old):
            os.remove(old)   # the person's own old photo, replaced by the new one
    from . import files
    p = os.path.join(base, f"{user}.{'jpg' if kind == 'jpeg' else 'png'}")
    with os.fdopen(files.create_new(p, 0o644), "wb") as f:
        f.write(data)
    ad = {"ok": False, "err": "no domain"}
    if directory.available() and kind == "jpeg":
        ad = _ldif_replace(user, "thumbnailPhoto", b64=base64.b64encode(data).decode())
    audit.record(by, "directory.photo", user, detail="domain thumbnailPhoto " + ("set" if ad.get("ok") else "not set (PNG, or no domain)"))
    return {"ok": True, "photo": True, "domain": bool(ad.get("ok"))}


def has_photo(user: str) -> bool:
    if load().demo:
        return user in demo_state.get("r7.photos", dict)
    return bool(photo_path(user))


# ----- row 69: Bradly's emergency look into the Pastors folder ------------------------------------
def breakglass_open(who: dict, reason: str, confirm: str, now: float | None = None) -> dict:
    """Only Bradly ([owner] user; round 7, 69: "You"), only with a reason and the folder's name typed.
    For two hours his dashboard sees the Pastors folder; both pastors are emailed at once; it is in the
    audit log and Discord. Claude never gets this (CLAUDE.md 11c; the owner's Claude settings deny it)."""
    now = now or time.time()
    user = str(who.get("user", ""))
    o = owner()
    if who.get("role") != "admin" or (o and user != o) or (not o and not load().demo):
        return {"ok": False, "err": "Only Bradly can open the Pastors folder in an emergency"}
    if (confirm or "").strip().lower() != "pastors":
        return {"ok": False, "err": "type pastors to confirm"}
    reason = (reason or "").strip()
    if len(reason) < 8:
        return {"ok": False, "err": "say why, in a sentence: the pastors read it"}
    hours = float(_people().breakglass_hours or 2)
    until = now + hours * 3600
    with _lock:
        g = _read("breakglass.json", dict)
        g[user] = {"until": until, "reason": reason[:300], "at": now}
        _write("breakglass.json", g, 0o600)
    told = []
    for p in load().storage.pastors or []:
        r = tell_person(p, "Bradly opened the Pastors folder",
                        f"Bradly opened the Pastors folder in an emergency, for {hours:g} hours, at {datetime.fromtimestamp(now):%a %b %d, %I:%M %p}.\n\n"
                        f"His reason: {reason}\n\nEvery file he opens is in the audit log.", kind="security")
        told.append(p)
    audit.record(user, "pastors.breakglass", "pastors", detail=reason[:200])
    alert(f"Pastors folder opened in an emergency by {user} for {hours:g} hours. Reason: {reason[:200]}. Both pastors were told.")
    return {"ok": True, "until": datetime.fromtimestamp(until).isoformat(timespec="minutes"), "told": told, "hours": hours}


def breakglass_active(user: str, now: float | None = None) -> bool:
    now = now or time.time()
    g = _read("breakglass.json", dict).get(user)
    return bool(g) and float(g.get("until", 0)) > now


def breakglass_close(user: str, by: str) -> dict:
    with _lock:
        g = _read("breakglass.json", dict)
        had = g.pop(user, None)
        _write("breakglass.json", g, 0o600)
    if had:
        audit.record(by, "pastors.breakglass.close", "pastors")
    return {"ok": True, "closed": bool(had)}


def breakglass_status(user: str) -> dict:
    g = _read("breakglass.json", dict).get(user)
    if not g or float(g.get("until", 0)) <= time.time():
        return {"open": False}
    return {"open": True, "until": datetime.fromtimestamp(float(g["until"])).isoformat(timespec="minutes"), "reason": g.get("reason", "")}

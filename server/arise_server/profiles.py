"""People's profiles, settings that follow the account, sign-in history, the day-one
people list, and the self-service password reset (round 5: 5 to 11, 22).

Where the profile lives: <state_dir>/profiles.json, one record per user name.
Samba's AD has title, mobile and department attributes, but not a birthday or a
"personal email" that means what it means here, and every write would be an
ldbmodify against the domain's database for data only the dashboard reads.
The domain keeps what the domain enforces (the account, its password, its
groups, "must change at next logon"); the dashboard's own file keeps the rest,
is backed up with /var/lib/arise, and is a plain file the tests can read.

Who sees what (round 5, 10): a person always sees and edits their own phone,
personal email and birthday; staff and admins see everyone's details; members
(everyone else) never do, which the server enforces, not the page. Titles and
departments are set by admins.

Staff and volunteers use their Macs, not ariseOS (Oct 28): the reset link opens
a page of its own (/reset) that needs no desktop, and a temporary password is
changed at the Mac's login window as well as here, because the domain itself
asks for it (directory.add_user/set_password with temporary=True).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import secrets
import threading
import time
import unicodedata
from datetime import datetime

from . import audit, demo_state, directory
from .config import load

_lock = threading.RLock()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+()\-. ]{7,25}$")
BIRTHDAY_RE = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
TITLE_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{0,39}$")
SELF_FIELDS = ("personal_email", "mobile", "birthday")
ADMIN_FIELDS = SELF_FIELDS + ("title", "departments")
DAYS_IN = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
# Settings that follow the account (round 5, 11): the dashboard's own localStorage keys.
PREF_KEY_RE = re.compile(r"^(theme|sounds|wallpaper|textsize|dock\.(hide|admin|member|staff)|a11y\.(contrast|motion|text))$")


# ----- where things are kept ------------------------------------------------------
def _path():
    return load().state_dir / "profiles.json"


def _read() -> dict:
    if load().demo:
        return demo_state.get("profiles", _demo_seed)
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def _write(d: dict):
    if load().demo:
        demo_state.put("profiles", d)
        return
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.chmod(tmp, 0o640)
    os.replace(tmp, p)


def _demo_seed() -> dict:
    # Titles as Bradly writes them (CLAUDE.md). No phone, email or birthday is made up.
    return {"bradly": {"title": "", "departments": ["Media"], "personal_email": "", "mobile": "", "birthday": "",
                       "prefs": {}},
            "office": {"title": "", "departments": ["Staff"], "personal_email": "", "mobile": "", "birthday": "", "prefs": {}}}


def mail_domain() -> str:
    """first.last@<this>: [mail] domain, else the directory's realm in lower case. Never written out by hand."""
    raw = (load().raw.get("mail") or {}) if isinstance(load().raw, dict) else {}
    return str(raw.get("domain") or load().directory.realm).lower()


def staff_groups() -> list[str]:
    raw = (load().raw.get("web") or {}) if isinstance(load().raw, dict) else {}
    return list(raw.get("staff_groups") or ["Staff", "Media"])


def is_staff(who: dict) -> bool:
    """Admins, and members of the staff groups (round 4, 99: admin, staff, member by group)."""
    if who.get("role") == "admin":
        return True
    if who.get("user") in (None, "", "demo"):
        return False
    mine = {g.lower() for g in directory.user_groups(who["user"])}
    return any(g.lower() in mine for g in staff_groups())


# ----- names ---------------------------------------------------------------------
def display_name(user: str, display: str = "", prof: dict | None = None) -> str:
    """'Apostle Bryant Sanders': the title, then the name the account shows (round 5, 7)."""
    prof = prof if prof is not None else _read().get(user, {})
    name = (display or "").strip() or user
    title = (prof.get("title") or "").strip()
    if title and not name.lower().startswith(title.lower() + " "):
        return f"{title} {name}"
    return name


def greeting_name(user: str, display: str = "", prof: dict | None = None) -> str:
    """'Apostle Bryant', or 'Bradly' when there is no title: the greeting's form."""
    prof = prof if prof is not None else _read().get(user, {})
    name = (display or "").strip() or user.split(".")[0].capitalize()
    first = name.split()[0]
    title = (prof.get("title") or "").strip()
    return f"{title} {first}" if title else first


def _display_of(user: str) -> str:
    u = directory._u(user) if load().demo else None
    if u:
        return u.get("display") or user
    try:
        for row in directory.list_users().get("users", []):
            if row["name"].lower() == user.lower():
                return row.get("display") or user
    except Exception:  # noqa: BLE001 - a name is a nicety, never a failure
        pass
    return user


# ----- profile fields ----------------------------------------------------------------
def clean(fields: dict, allowed: tuple) -> tuple[dict, list[str]]:
    """Pure: the fields a caller may set, checked. Returns (good, errors)."""
    out, errs = {}, []
    for k in allowed:
        if k not in fields:
            continue
        v = fields[k]
        if k == "departments":
            vals = v if isinstance(v, list) else [x.strip() for x in re.split(r"[;|,]", str(v or ""))]
            vals = [x for x in (str(x).strip() for x in vals) if x]
            bad = [x for x in vals if not directory._ok_group(x)]
            if bad:
                errs.append(f"not a department name: {', '.join(bad)}")
            else:
                out[k] = vals[:12]
            continue
        v = str(v or "").strip()
        if not v:
            out[k] = ""
        elif k == "personal_email" and not EMAIL_RE.match(v):
            errs.append("personal email: that is not an email address")
        elif k == "personal_email" and v.lower().endswith("@" + mail_domain()):
            errs.append("personal email: use their own address, not the church one (mail forwards to it)")
        elif k == "mobile" and not PHONE_RE.match(v):
            errs.append("mobile: digits, spaces, + - ( ) only")
        elif k == "birthday":
            b = normalize_birthday(v)
            if not b:
                errs.append("birthday: month and day, like 03-14 or March 14")
            else:
                out[k] = b
            continue
        elif k == "title" and not TITLE_RE.match(v):
            errs.append("title: letters only, like Apostle, Pastor, Minister")
        else:
            out[k] = v
    return out, errs


MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                     "september", "october", "november", "december"], 1)}


def normalize_birthday(v: str) -> str | None:
    """Pure: '03-14', '3/14', 'March 14', '1985-03-14' -> '03-14'. The year is never kept."""
    v = (v or "").strip().lower()
    m = re.fullmatch(r"(?:\d{4}-)?(\d{1,2})[-/](\d{1,2})(?:[-/]\d{2,4})?", v)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
    else:
        m = re.fullmatch(r"([a-z]+)\.?\s+(\d{1,2})(?:,?\s*\d{4})?", v)
        if not m:
            return None
        key = next((k for k in MONTHS if k.startswith(m.group(1)[:3])), None)
        if not key:
            return None
        mo, d = MONTHS[key], int(m.group(2))
    if mo not in DAYS_IN or not 1 <= d <= DAYS_IN[mo]:
        return None
    return f"{mo:02d}-{d:02d}"


def profile(user: str, viewer: dict) -> dict:
    """One person's profile, as far as the viewer may see it."""
    if not directory._ok_name(user):
        return {"ok": False, "err": "bad name"}
    p = dict(_read().get(user, {}))
    p.pop("prefs", None)
    disp = _display_of(user)
    out = {"ok": True, "user": user, "display": disp, "title": p.get("title", ""), "name": display_name(user, disp, p),
           "mail": f"{user}@{mail_domain()}", "departments": p.get("departments", [])}
    mine = viewer.get("user") == user
    if mine or is_staff(viewer):
        out.update({k: p.get(k, "") for k in SELF_FIELDS})
        out["can_edit"] = list(ADMIN_FIELDS if viewer.get("role") == "admin" else SELF_FIELDS if mine else ())
    else:
        out["can_edit"] = []
    return out


def update(user: str, fields: dict, viewer: dict) -> dict:
    """A person edits their own phone, personal email and birthday; admins edit everything."""
    if not directory._ok_name(user):
        return {"ok": False, "err": "bad name"}
    admin = viewer.get("role") == "admin"
    if not admin and viewer.get("user") != user:
        return {"ok": False, "err": "You can change only your own profile"}
    allowed = ADMIN_FIELDS if admin else SELF_FIELDS
    refused = [k for k in fields if k not in allowed and k in ADMIN_FIELDS]
    good, errs = clean(fields, allowed)
    if refused:
        errs.append(f"only an administrator sets: {', '.join(refused)}")
    if errs:
        return {"ok": False, "err": "; ".join(errs)}
    with _lock:
        d = _read()
        rec = d.setdefault(user, {})
        rec.update(good)
        _write(d)
    audit.record(viewer.get("user", "?"), "profile.edit", user, detail=", ".join(sorted(good)) or "nothing")
    return {"ok": True, "profile": profile(user, viewer), "demo": load().demo}


def people(viewer: dict) -> dict:
    """Everyone's profile, for staff and admins only (round 5, 10)."""
    if not is_staff(viewer):
        return {"ok": False, "err": "Only staff and administrators see the people list", "people": []}
    rows = directory.list_users().get("users", [])
    d = _read()
    out = []
    for r in rows:
        p = d.get(r["name"], {})
        out.append({"user": r["name"], "display": r.get("display") or r["name"], "name": display_name(r["name"], r.get("display", ""), p),
                    "title": p.get("title", ""), "departments": p.get("departments", []), "enabled": r.get("enabled", True),
                    **{k: p.get(k, "") for k in SELF_FIELDS}})
    out.sort(key=lambda x: x["name"].lower())
    return {"ok": True, "people": out, "demo": load().demo}


def decorate(users: list[dict]) -> list[dict]:
    """The Directory list with each person's title and full name."""
    d = _read()
    for u in users:
        p = d.get(u["name"], {})
        u["title"] = p.get("title", "")
        u["full_name"] = display_name(u["name"], u.get("display", ""), p)
        u["has_personal_email"] = bool(p.get("personal_email"))
    return users


def birthdays(month: int | None = None) -> list[dict]:
    """For the Monday weekly (round 4, 94): month and day only, never a year or an age."""
    d = _read()
    out = []
    for user, p in d.items():
        b = p.get("birthday") or ""
        if BIRTHDAY_RE.match(b) and (month is None or int(b[:2]) == month):
            out.append({"user": user, "name": display_name(user, _display_of(user), p), "birthday": b})
    return sorted(out, key=lambda x: x["birthday"])


# ----- settings that follow the account (round 5, 11) ---------------------------------
def prefs(user: str) -> dict:
    return {"ok": True, "prefs": dict(_read().get(user, {}).get("prefs", {})), "demo": load().demo}


def save_prefs(user: str, values: dict) -> dict:
    if not isinstance(values, dict):
        return {"ok": False, "err": "prefs: an object of setting -> value"}
    bad = [k for k in values if not PREF_KEY_RE.match(str(k))]
    if bad:
        return {"ok": False, "err": f"not a setting that follows the account: {', '.join(map(str, bad[:5]))}"}
    clean_vals = {}
    for k, v in values.items():
        v = "" if v is None else str(v)
        if len(v) > 2000:
            return {"ok": False, "err": f"{k}: too long"}
        clean_vals[k] = v
    with _lock:
        d = _read()
        rec = d.setdefault(user, {})
        rec.setdefault("prefs", {}).update(clean_vals)
        _write(d)
    return {"ok": True, "prefs": dict(d[user]["prefs"])}


# ----- one's own sign-ins (round 5, 22) -------------------------------------------------
def device_of(agent: str) -> str:
    """Pure: a user-agent in a few words: 'Safari on a Mac', 'Firefox on Linux (the closet monitor)'."""
    a = agent or ""
    browser = ("Edge" if "Edg/" in a else "Firefox" if "Firefox/" in a else "Chrome" if "Chrome/" in a or "CriOS" in a
               else "Safari" if "Safari/" in a else "a browser")
    system = ("an iPhone" if "iPhone" in a else "an iPad" if "iPad" in a else "Android" if "Android" in a
              else "a Mac" if "Macintosh" in a or "Mac OS X" in a else "Windows" if "Windows" in a
              else "Linux" if "Linux" in a or "X11" in a else "")
    return f"{browser} on {system}" if system else browser


def signins(user: str, limit: int = 10) -> dict:
    ev = audit.recent(limit=400, q="auth.login", who=user).get("events", [])
    rows = [{"t": e["t"], "ok": e.get("ok", True), "how": e.get("detail", ""), "ip": e.get("ip", "")}
            for e in ev if e.get("action") in ("auth.login", "auth.login.code", "auth.login.newpassword")]
    return {"ok": True, "signins": rows[:max(1, min(limit, 50))], "demo": load().demo}


# ----- the day-one people list (round 5, 8) -----------------------------------------------
WORDS = ["Anchor", "Beacon", "Candle", "Cedar", "Crown", "Dove", "Ember", "Garden", "Harbor", "Harvest", "Lamp", "Meadow",
         "Morning", "Olive", "Psalm", "River", "Shepherd", "Shore", "Sparrow", "Stone", "Summit", "Valley", "Vine", "Willow"]


def temp_password() -> str:
    """A first password a person can read off a sheet: two words, two digits, a mark (12+ characters,
    three kinds of character, as the domain's complexity rule asks). They change it at first login."""
    a, b = secrets.choice(WORDS), secrets.choice(WORDS)
    while b == a:
        b = secrets.choice(WORDS)
    return f"{a}-{b}-{secrets.randbelow(90) + 10}{secrets.choice('!#%+=?')}"


def username_of(first: str, last: str) -> str:
    """Pure: 'Bryant', 'Sanders' -> 'bryant.sanders' (accents dropped, spaces and marks out)."""
    def part(x):
        x = unicodedata.normalize("NFKD", x or "").encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9-]", "", x.replace(" ", "-")).strip("-")
    return ".".join(p for p in (part(first), part(last)) if p)


ROLE_GROUPS = {"admin": ["Domain Admins"], "staff": ["Staff"], "member": []}
COLUMNS = ("first", "last", "title", "departments", "personal_email", "mobile", "birthday", "role")


def import_people(csv_text: str, apply: bool, by: str) -> dict:
    """Check every row (and, with apply, create the accounts). A temporary password is made per person
    and returned once, in this answer only: never logged, never written to disk."""
    try:
        rows = list(csv.DictReader(io.StringIO((csv_text or "").lstrip("﻿"))))
    except csv.Error as e:
        return {"ok": False, "err": f"not a CSV file: {e}"}
    if not rows:
        return {"ok": False, "err": "no rows (the first line names the columns: " + ", ".join(COLUMNS) + ")"}
    head = {k.strip().lower() for k in (rows[0].keys() if rows else []) if k}
    missing = [c for c in ("first", "last") if c not in head]
    if missing:
        return {"ok": False, "err": f"missing columns: {', '.join(missing)} (expected: {', '.join(COLUMNS)})"}
    existing = {u["name"].lower() for u in directory.list_users().get("users", [])}
    groups = {g["name"].lower(): g["name"] for g in directory.list_groups().get("groups", [])}
    seen, out = set(), []
    for i, raw in enumerate(rows, start=2):
        r = {str(k).strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        row = {"line": i, "first": r.get("first", ""), "last": r.get("last", "")}
        name = username_of(row["first"], row["last"])
        row["user"] = name
        role = (r.get("role") or "member").lower()
        problems = []
        if not row["first"] or not row["last"]:
            problems.append("needs a first and a last name")
        elif not directory._ok_name(name):
            problems.append(f"{name or '(empty)'} is not a usable user name")
        if name in seen:
            problems.append("the same person twice in the list")
        elif name.lower() in existing:
            problems.append("already has an account")
        if role not in ROLE_GROUPS:
            problems.append(f"role is admin, staff or member, not {role}")
        fields, errs = clean({k: r[k] for k in ("title", "departments", "personal_email", "mobile", "birthday") if r.get(k)}, ADMIN_FIELDS)
        problems += errs
        want = ROLE_GROUPS.get(role, []) + fields.get("departments", [])
        absent = [g for g in want if g.lower() not in groups]
        grp = [groups[g.lower()] for g in want if g.lower() in groups]
        row.update({"role": role, "title": fields.get("title", ""), "groups": grp,
                    "display": f"{row['first']} {row['last']}".strip(), "warnings": [f"no group {g} yet (made in the Directory app)" for g in absent]})
        seen.add(name)
        if problems:
            row.update(ok=False, err="; ".join(problems))
            out.append(row)
            continue
        row["ok"] = True
        if apply:
            pw = temp_password()
            res = directory.add_user(name, pw, row["display"], grp, temporary=True)
            if not res.get("ok") and not res.get("created"):
                row.update(ok=False, err=res.get("err", "the domain refused"))
                out.append(row)
                continue
            if res.get("err"):
                row["warnings"].append(res["err"])
            with _lock:
                d = _read()
                d.setdefault(name, {}).update(fields)
                _write(d)
            row["temporary_password"] = pw
            row["created"] = True
        out.append(row)
    made = sum(1 for r in out if r.get("created"))
    if apply:
        audit.record(by, "directory.import", f"{made} accounts", ok=all(r["ok"] for r in out),
                     detail=f"{made} created, {sum(1 for r in out if not r['ok'])} refused")
    return {"ok": True, "apply": bool(apply), "rows": out, "created": made, "refused": sum(1 for r in out if not r["ok"]),
            "mail_domain": mail_domain(), "realm": load().directory.realm.upper(), "demo": load().demo}


# ----- the self-service reset (round 5, 6) ---------------------------------------------
RESET_MINUTES = 30
_rate: dict = {}


def _resets_path():
    return load().state_dir / "password-resets.json"


def _resets() -> dict:
    if load().demo:
        return demo_state.get("pw.resets", {})
    try:
        with open(_resets_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _save_resets(d: dict):
    if load().demo:
        demo_state.put("pw.resets", d)
        return
    p = _resets_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def _limited(key: str, most: int, per: float, now: float) -> bool:
    hits = [t for t in _rate.get(key, []) if now - t < per]
    _rate[key] = hits
    if len(hits) >= most:
        return True
    hits.append(now)
    return False


SAME_ANSWER = "If that account has a personal email on file, a link to choose a new password is on its way. It works for 30 minutes."


def forgot(user: str, base_url: str, ip: str = "", now: float | None = None) -> dict:
    """Always the same answer, whether or not the account exists (round 5, 6)."""
    now = now or time.time()
    user = (user or "").strip().lower()
    out = {"ok": True, "message": SAME_ANSWER}
    if _limited("ip:" + ip, 10, 3600, now) or _limited("u:" + user, 3, 3600, now):
        audit.record(user[:64] or "?", "auth.forgot", ok=False, ip=ip, detail="too many requests")
        return out
    if not directory._ok_name(user):
        return out
    email = _read().get(user, {}).get("personal_email", "")
    u_ok = bool(directory._u(user)) if load().demo else any(r["name"].lower() == user for r in directory.list_users().get("users", []))
    if not u_ok or not email:
        audit.record(user, "auth.forgot", ok=False, ip=ip, detail="no account or no personal email on file")
        return out
    token = secrets.token_urlsafe(32)
    with _lock:
        d = {k: v for k, v in _resets().items() if v.get("exp", 0) > now and not v.get("used")}
        for k in [k for k, v in d.items() if v.get("user") == user]:
            d.pop(k)   # one live link per person: the newest
        d[hashlib.sha256(token.encode()).hexdigest()] = {"user": user, "exp": now + RESET_MINUTES * 60, "used": False}
        _save_resets(d)
    link = f"{base_url.rstrip('/')}/reset?t={token}"
    from . import mail
    disp = display_name(user, _display_of(user))
    body = (f"Hi {greeting_name(user, _display_of(user))},\n\nSomeone (we hope you) asked to reset the password for {user} at "
            f"{load().church.name}. Choose a new one here within 30 minutes:\n\n{link}\n\nThe same password works on your Mac and "
            f"everywhere else at church. The link opens on church Wi-Fi, or anywhere with Tailscale on; "
            f"the server is not on the internet.\n\nIf you did not ask, ignore this: nothing changes.\n")
    sent = mail.send_one(email, f"Choose a new password, {disp}", body)
    audit.record(user, "auth.forgot", ok=bool(sent.get("ok")), ip=ip, detail="link sent" if sent.get("ok") else f"not sent: {sent.get('err', '')}"[:200])
    if load().demo:
        out["sample_link"] = link   # the preview has no mail: the link is shown, labelled sample
    return out


def check_reset(token: str, now: float | None = None) -> dict:
    now = now or time.time()
    rec = _resets().get(hashlib.sha256((token or "").encode()).hexdigest())
    if not rec or rec.get("used") or rec.get("exp", 0) < now:
        return {"ok": False, "err": "This link has expired or was already used. Ask for a new one."}
    return {"ok": True, "user": rec["user"], "name": display_name(rec["user"], _display_of(rec["user"]))}


def finish_reset(token: str, new: str, ip: str = "", now: float | None = None) -> dict:
    now = now or time.time()
    if _limited("reset:" + ip, 20, 3600, now):
        return {"ok": False, "err": "Too many tries. Wait a while and ask for a new link."}
    h = hashlib.sha256((token or "").encode()).hexdigest()
    with _lock:
        d = _resets()
        rec = d.get(h)
        if not rec or rec.get("used") or rec.get("exp", 0) < now:
            return {"ok": False, "err": "This link has expired or was already used. Ask for a new one."}
        rules = directory.password_rules()
        if len(new or "") < int(rules.get("min_length") or 8):
            return {"ok": False, "err": f"At least {rules.get('min_length') or 8} characters", "rules": rules.get("words", [])}
        r = directory.set_password(rec["user"], new, temporary=False)
        if not r.get("ok"):
            return {"ok": False, "err": r.get("err", "the domain refused that password"), "rules": rules.get("words", [])}
        rec["used"] = True
        rec["used_at"] = now
        _save_resets(d)
    audit.record(rec["user"], "auth.reset", ok=True, ip=ip, detail="new password from the emailed link")
    return {"ok": True, "user": rec["user"], "message": "Your new password works now: on your Mac, here, everywhere."}


def admin_reset(name: str, password: str, temporary: bool, by: str) -> dict:
    """An admin's reset (they can still reset, round 5, 6). Temporary by default: AD asks for a new one at next login."""
    return directory.set_password(name, password, temporary=temporary)   # the request is in the audit log (main.py's middleware); the password never is


def mailbox_export(user: str, dest_dir: str) -> dict:
    """Round 5, 38: before a leaver's mailbox goes, their mail is saved as one mbox file into the
    folder of whoever takes their files. Reads the Maildir the internal mail server keeps
    ([mail] maildir_root/<domain>/<user>, or .../<user>/Maildir). No mail server yet: says so."""
    import mailbox
    raw = (load().raw.get("mail") or {}) if isinstance(load().raw, dict) else {}
    root = str(raw.get("maildir_root") or "/srv/arise/mail")
    candidates = [os.path.join(root, mail_domain(), user), os.path.join(root, mail_domain(), user, "Maildir"),
                  os.path.join(root, user, "Maildir"), os.path.join(root, user)]
    src = next((c for c in candidates if os.path.isdir(os.path.join(c, "cur")) or os.path.isdir(os.path.join(c, "new"))), None)
    if not src:
        return {"ok": True, "exported": 0, "note": "no mailbox on this server (no internal mail server yet, or none for this person)"}
    os.makedirs(dest_dir, exist_ok=True)
    out = os.path.join(dest_dir, f"Mail of {user} ({datetime.now().date().isoformat()}).mbox")
    n = 0
    try:
        md = mailbox.Maildir(src, factory=None, create=False)
        box = mailbox.mbox(out, create=True)
        box.lock()
        try:
            folders = [md] + [md.get_folder(f) for f in md.list_folders()]
            for f in folders:
                for msg in f:
                    box.add(mailbox.mboxMessage(msg))
                    n += 1
            box.flush()
        finally:
            box.unlock()
            box.close()
    except (OSError, mailbox.Error) as e:
        return {"ok": False, "err": f"could not export the mailbox: {e}", "exported": n}
    return {"ok": True, "exported": n, "file": out, "source": src}

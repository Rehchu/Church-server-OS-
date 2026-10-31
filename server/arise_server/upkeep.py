"""Upkeep (round 7): the hourly checks, the January jobs, the change record, the closet card.

    hourly()          a missed backup night (64), a church Mac silent three days (82),
                      a disk whose health check warns (137/138), the CPU at 80 C (137):
                      each goes to Discord #alerts once, and to the Needs You list while true
    january()         the Google export reminder (63) and the clean-up report (139):
                      unused accounts, the biggest files, empty shares, removed-profile disk
                      images. It lists; it never deletes (deleting is Bradly's click)
    changes()         what changed on the box, by whom: Bradly, Kristina or Claude (140)
    closet_card()     the card taped inside the closet (57, 58, 59, 73, 141)

Every check is a pure function first, so the tests pin the rules without a box.
"""
from __future__ import annotations

import html
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from .config import load
from .util import read_json, run, which, write_json

CPU_HOT_C = 80.0          # round 7, 137: the defaults (SMART's own verdict, 80 C)
MAC_SILENT_DAYS = 3       # round 7, 82
UNUSED_DAYS = 90          # round 7, 17: the clean-up report's "unused" too
IT_PORTAL = "https://itportal.myfaithtech.com"   # AriseHub's IT portal (lib/it-portal: NEXT_PUBLIC_IT_PORTAL_URL)
# Round 7, 141: who to call. Names only: phone numbers are written on the card by hand.
CALL = [{"name": "Bradly Dyer", "role": "media and IT"},
        {"name": "Minister Kristina Robinson", "role": "knows the disk passphrase and the backup password (round 7, 58)"},
        {"name": "Ronnie", "role": "when neither answers"}]


def cfg_upkeep() -> dict:
    raw = load().raw
    u = dict((raw.get("upkeep") if isinstance(raw, dict) else None) or {})
    u.setdefault("cpu_hot_c", CPU_HOT_C)
    u.setdefault("mac_silent_days", MAC_SILENT_DAYS)
    u.setdefault("it_portal_url", IT_PORTAL)
    u.setdefault("call", CALL)
    return u


def it_portal() -> str:
    """Round 7, 118/119: where staff ask for help and look up equipment."""
    return str(cfg_upkeep().get("it_portal_url") or IT_PORTAL)


# ----- disk health and heat (137/138) ------------------------------------------------
def parse_smart(doc: dict) -> dict:
    """Pure: one `smartctl --json -H -A` answer -> {dev, model, passed, temp, reallocated, pending, wear, why}.
    Replace the disk when its own health check warns (138): a failed overall check, any
    pending or reallocated sector growth, or an SSD that says it is worn out."""
    dev = (doc.get("device") or {}).get("name") or "?"
    model = doc.get("model_name") or doc.get("model_family") or ""
    passed = (doc.get("smart_status") or {}).get("passed")
    temp = (doc.get("temperature") or {}).get("current")
    attrs = {a.get("id"): a for a in ((doc.get("ata_smart_attributes") or {}).get("table") or [])}
    raw = lambda i: int(((attrs.get(i) or {}).get("raw") or {}).get("value") or 0)
    nvme = doc.get("nvme_smart_health_information_log") or {}
    reallocated = raw(5)
    pending = raw(197) + raw(198)
    wear = nvme.get("percentage_used")
    why = []
    if passed is False:
        why.append("its own health check FAILED")
    if pending:
        why.append(f"{pending} unreadable sectors waiting")
    if reallocated:
        why.append(f"{reallocated} sectors already replaced")
    if nvme.get("critical_warning"):
        why.append("the drive reports a critical warning")
    if wear is not None and int(wear) >= 100:
        why.append(f"{wear}% of its rated life used")
    return {"dev": dev, "model": model, "passed": passed, "temp": temp, "reallocated": reallocated,
            "pending": pending, "wear": wear, "why": why}


def disks_health() -> list[dict]:
    if load().demo:
        return [{"dev": "/dev/sda", "model": "Samsung SSD 870 EVO 1TB (sample)", "passed": True, "temp": 34, "reallocated": 0, "pending": 0, "wear": None, "why": []}]
    if not which("smartctl"):
        return []
    scan = run(["smartctl", "--scan-open", "--json"], timeout=30)
    try:
        devs = [d["name"] for d in json.loads(scan["out"] or "{}").get("devices", [])]
    except (ValueError, KeyError):
        devs = []
    out = []
    for d in devs[:8]:
        r = run(["smartctl", "--json", "-H", "-A", d], timeout=30)
        try:
            out.append(parse_smart(json.loads(r["out"] or "{}")))
        except ValueError:
            continue
    return out


def health_items(disks: list[dict], cpu_temp: float | None, hot: float = CPU_HOT_C) -> list[dict]:
    """Pure: Needs You items for disks that warn and a CPU at or above `hot`."""
    items = []
    for d in disks:
        if d.get("why"):
            items.append({"level": "bad", "key": f"disk:{d['dev']}",
                          "text": f"Replace the disk {d['dev']} ({d.get('model') or 'unknown model'}): {', '.join(d['why'])}. The backups are the safety net until then."})
    if cpu_temp is not None and float(cpu_temp) >= hot:
        items.append({"level": "warn", "key": "cpu-hot", "text": f"The CPU is at {float(cpu_temp):.0f}°C (the warning is {hot:.0f}°C): check the closet's airflow and the fans."})
    return items


_health_cache: dict = {"t": 0.0, "v": []}


def health(fresh: bool = False) -> list[dict]:
    """Cached ten minutes: smartctl wakes every disk, the overview asks often."""
    if not fresh and time.time() - _health_cache["t"] < 600:
        return _health_cache["v"]
    from . import metrics
    try:
        cpu = metrics._temps()
    except Exception:  # noqa: BLE001
        cpu = None
    v = health_items(disks_health(), cpu, float(cfg_upkeep()["cpu_hot_c"]))
    _health_cache.update(t=time.time(), v=v)
    return v


# ----- silent Macs (82) ----------------------------------------------------------------
def silent_macs(macs: list[dict], now: datetime | None = None, days: int = MAC_SILENT_DAYS) -> list[dict]:
    """Pure: active church Macs not heard from in `days` days. Retired and cut-off Macs are not missed."""
    now = now or datetime.now()
    out = []
    for m in macs:
        if not m.get("church_owned", True) or m.get("status", "active") != "active":
            continue
        try:
            last = datetime.fromisoformat(str(m.get("last_checkin") or "")[:19])
        except ValueError:
            last = None
        if last is None or now - last >= timedelta(days=days):
            out.append({"id": m.get("id"), "name": m.get("name") or m.get("id"), "last": last.isoformat(timespec="minutes") if last else None,
                        "days": (now - last).days if last else None})
    return out


def _macs() -> list[dict]:
    try:
        from . import macs as _m
        return list((_m._read().get("macs") or {}).values())
    except Exception:  # noqa: BLE001
        return []


# ----- the Needs You items and the hourly posts -----------------------------------------
def attention(now: datetime | None = None, hist: list[dict] | None = None, macs: list[dict] | None = None,
              health_v: list[dict] | None = None) -> list[dict]:
    """Every upkeep item that is true right now. The overview adds these to Needs You."""
    from . import backups
    now = now or datetime.now()
    items = []
    rows = hist if hist is not None else backups.history(limit=400)["rows"]
    miss = backups.missed_night(rows, now)
    if miss:
        items.append({"level": "bad", "key": f"backup-missed:{miss.get('since') or 'never'}",
                      "text": "No backup ran last night" + (f" (the last good one was {miss['last_ok'].replace('T', ' ')})" if miss.get("last_ok") else "")
                              + ". Backups shows why.", "fix": "sudo arisectl backup run"})
    for m in silent_macs(macs if macs is not None else _macs(), now, int(cfg_upkeep()["mac_silent_days"])):
        items.append({"level": "warn", "key": f"mac-silent:{m['id']}:{m['last']}",
                      "text": f"{m['name']} hasn't checked in for {m['days']} days" if m["days"] is not None else f"{m['name']} has never checked in",
                      "fix": "turn it on, or Retire it in Macs if it is gone"})
    items.extend(health_v if health_v is not None else health())
    return items


def hourly(now: datetime | None = None, post=None) -> dict:
    """arise-upkeep.timer, hourly: each item goes to Discord #alerts once (its key), never twice."""
    from . import discord
    now = now or datetime.now()
    post = post or discord.post
    items = attention(now)
    sent = []
    for it in items:
        key = it["key"] if not it["key"].startswith(("disk:", "cpu-hot")) else f"{it['key']}:{now.date().isoformat()}"   # health: once a day while true
        r = post("alerts", it["text"], key=key, fix=it.get("fix", ""))
        if r.get("ok") and not r.get("duplicate"):
            sent.append(it["key"])
    # The weekly YouTube sign-in: Saturday evening and Sunday after the service, once each (Oct 29).
    try:
        from . import ytauth
        sent += ytauth.reminders(now, post=post)
    except Exception:  # noqa: BLE001 - a reminder never stops the hourly round
        pass
    return {"ok": True, "items": len(items), "posted": sent}


# ----- January (63, 139) ---------------------------------------------------------------
def unused_accounts(users: list[dict], now: datetime | None = None, days: int = UNUSED_DAYS) -> list[dict]:
    """Pure: enabled accounts not signed in for `days` (or never)."""
    now = now or datetime.now()
    out = []
    for u in users:
        if not u.get("enabled", True):
            continue
        try:
            last = datetime.fromisoformat(str(u.get("last_logon") or "")[:19])
        except ValueError:
            last = None
        if last is None or now - last >= timedelta(days=days):
            out.append({"name": u["name"], "last": last.date().isoformat() if last else "never"})
    return out


def biggest_files(roots: list[str], n: int = 20, walk=os.walk) -> list[dict]:
    """The n largest files under these folders (the Trash and the Pastors folder skipped: 11c)."""
    top: list[tuple[int, str]] = []
    for root in roots:
        for d, subdirs, files in walk(root):
            subdirs[:] = [s for s in subdirs if s not in (".Trash", ".snapshots", "@eaDir")]
            for f in files:
                p = os.path.join(d, f)
                try:
                    sz = os.lstat(p).st_size
                except OSError:
                    continue
                top.append((sz, p))
                if len(top) > n * 4:
                    top = sorted(top, reverse=True)[:n]
    return [{"path": p, "bytes": s} for s, p in sorted(top, reverse=True)[:n]]


def empty_shares(base: str, listdir=os.listdir) -> list[str]:
    """Share folders with nothing in them but a Trash."""
    out = []
    try:
        names = sorted(listdir(base))
    except OSError:
        return out
    for name in names:
        p = os.path.join(base, name)
        if not os.path.isdir(p):
            continue
        try:
            inside = [x for x in listdir(p) if x not in (".Trash", ".DS_Store")]
        except OSError:
            continue
        if not inside:
            out.append(name)
    return out


KEPT_RE = re.compile(r"kept in (/Users/Deleted Users/[^\s;]+\.dmg)")


def removed_images(macs_d: dict) -> list[dict]:
    """Pure: the disk images removals kept on each Mac (round 6, 4; round 7, 154: kept forever)."""
    names = {k: (v.get("name") or k) for k, v in (macs_d.get("macs") or {}).items()}
    out = []
    for mac_id, tasks in (macs_d.get("tasks") or {}).items():
        for t in tasks:
            if t.get("kind") == "remove_profile" and t.get("state") == "done":
                m = KEPT_RE.search(t.get("detail") or "")
                if m:
                    out.append({"mac": names.get(mac_id, mac_id), "image": m.group(1), "when": t.get("finished")})
    return out


GOOGLE_EXPORT = ("January: export the Google accounts (soundmedia.arise@gmail.com and the church's others) with Google Takeout "
                 "(takeout.google.com, signed in as each account) and drop the files in the Synology's backups folder.")


def january_report(now: datetime | None = None) -> dict:
    cfg = load()
    now = now or datetime.now()
    if cfg.demo:
        return {"demo": True, "year": now.year, "reminder": GOOGLE_EXPORT,
                "unused": [{"name": "guest-speaker", "last": "never"}],
                "biggest": [{"path": "/srv/arise/shares/media/Outpour 2026 full.mov", "bytes": 38_200_000_000}],
                "empty_shares": ["alexandria"], "images": [{"mac": "OFFICE-MAC-01", "image": "/Users/Deleted Users/old.timer-20261103-0212.dmg", "when": "2026-11-03T02:12:00"}]}
    from . import directory, macs as _m
    try:
        users = directory.list_users().get("users", [])
    except Exception:  # noqa: BLE001
        users = []
    try:
        macs_d = _m._read()
    except Exception:  # noqa: BLE001
        macs_d = {}
    data_root = str(cfg.system.data_root)
    homes = str(cfg.directory.homes_path)
    rep = {"year": now.year, "made": now.isoformat(timespec="minutes"), "reminder": GOOGLE_EXPORT,
           "unused": unused_accounts(users, now), "biggest": biggest_files([homes, os.path.join(data_root, "shares")]),
           "empty_shares": empty_shares(os.path.join(data_root, "shares")), "images": removed_images(macs_d)}
    write_json(cfg.state_dir / f"january-{now.year}.json", rep)
    return rep


def january_text(rep: dict) -> str:
    from .util import human_bytes
    lines = [f"January clean-up {rep['year']} (it lists; nothing is deleted)"]
    lines.append(f"• Unused 90+ days: {', '.join(u['name'] for u in rep['unused']) or 'none'}")
    if rep["biggest"]:
        b = rep["biggest"][0]
        lines.append(f"• Biggest file: {b['path']} ({human_bytes(b['bytes'])}); the top {len(rep['biggest'])} are in Storage")
    lines.append(f"• Empty shares: {', '.join(rep['empty_shares']) or 'none'}")
    lines.append(f"• Removed-profile disk images kept on the Macs: {len(rep['images'])}")
    lines.append("• " + rep["reminder"])
    return "\n".join(lines)


def january(now: datetime | None = None, post=None) -> dict:
    """arise-january.timer (Jan 5): the report to Discord #weekly and Bradly's notifications, once a year."""
    from . import discord, notify
    now = now or datetime.now()
    post = post or discord.post
    rep = january_report(now)
    text = january_text(rep)
    r = post("weekly", text, key=f"january:{now.year}")
    owner = str((load().raw.get("owner") or {}).get("user", "") if isinstance(load().raw, dict) else "") or "bradly"
    try:
        notify.add(owner, "system", f"The January clean-up report is ready: {len(rep['unused'])} unused accounts, {len(rep['images'])} kept disk images.",
                   "/#storage", key=f"january:{now.year}", now=now)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "posted": r, "report": rep}


# ----- the change record (140) ---------------------------------------------------------
READS = ("auth.", "macs.check", "files.view", "files.list", "search", "macs.task.", "macs.escrow", "cloud.agent")


def is_change(ev: dict) -> bool:
    """Pure: an audit event that changed something (not a sign-in, a read, or a Mac's own report)."""
    a = str(ev.get("action") or "")
    return bool(a) and not a.startswith(READS) and ev.get("ok", True) is not False


def actor(who: str, owner: str, owners: list[str]) -> str:
    """Pure: the name the change record shows. Claude acts as Bradly's account; arisectl marks
    what it ran with "+claude" (CLAUDECODE in its environment)."""
    w = str(who or "?")
    if w.endswith("+claude"):
        return "Claude"
    base = w.split("+")[0]
    if (owner and base == owner) or base in ("bradly", "bradly.dyer"):
        return "Bradly"
    if base in (owners or []):
        return "Kristina" if base.startswith("kristina") else base
    if base.startswith("mac:"):
        return base[4:]
    return base


def changes(limit: int = 100) -> dict:
    from . import audit
    cfg = load()
    raw = cfg.raw if isinstance(cfg.raw, dict) else {}
    owner = str((raw.get("owner") or {}).get("user", ""))
    owners = [str(x) for x in ((raw.get("owners") or {}).get("users") or [])]
    evs = audit.recent(limit=2000).get("events", [])
    rows = [{"when": e["t"], "who": actor(e.get("who", ""), owner, owners), "what": e.get("action"), "target": e.get("target", ""),
             "detail": e.get("detail", "")} for e in evs if is_change(e)][:limit]
    last = read_json(cfg.state_dir / "updates-last.json", default=None) if not cfg.demo else None
    if last:
        rows.insert(0, {"when": last.get("when"), "who": "Software Update", "what": "updates.apply", "target": "", "detail": last.get("summary", "")})
    return {"demo": cfg.demo, "changes": rows}


# ----- the closet card (57, 58, 59, 73, 141) -------------------------------------------
def _card_facts() -> dict:
    cfg = load()
    host = str(cfg.system.hostname or "arise-server")
    realm = str(cfg.directory.realm or "AD.ARISECENLA.COM").lower()
    try:
        from . import macs
        ip = macs.lan_ip()
    except Exception:  # noqa: BLE001
        ip = ""
    try:
        from . import sharing
        tg = sharing.backup_targets()
        repo = tg.get("repo") or cfg.backups.restic_repo
    except Exception:  # noqa: BLE001
        repo = cfg.backups.restic_repo
    return {"host": host, "fqdn": f"{host}.{realm}", "ip": ip, "repo": str(repo), "home": str(cfg.backups.arise_home_repo or "")}


def closet_card(private: bool, rescue_password: str = "", facts: dict | None = None, call: list[dict] | None = None,
                now: datetime | None = None) -> str:
    """The card, as a printable page. private=True is the one taped INSIDE the closet (round 7, 57):
    it carries arise-rescue's password (73). The copy on the staff share never does: it leaves
    the line blank and says the printed card has it."""
    f = facts or _card_facts()
    call = call if call is not None else cfg_upkeep()["call"]
    now = now or datetime.now()
    e = html.escape
    rescue = (f"<code>{e(rescue_password)}</code>" if private and rescue_password
              else ("(not set yet: <code>sudo arisectl rescue rotate</code>)" if private else
                    "on the printed card inside the closet, and with Kristina. Not in this copy."))
    who = "".join(f"<tr><td>{e(c.get('name', ''))}</td><td>{e(c.get('role', ''))} &nbsp;·&nbsp; phone: ______________________</td></tr>" for c in call)
    head = ("Tape this INSIDE the closet. It holds the break-glass password: never on the door, never in a photo."
            if private else "The staff-share copy: the same card with the password left out. The printed one is inside the closet.")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>ariseOS: if the server dies</title>
<style>@page{{margin:14mm}}body{{font-family:Oswald,"Helvetica Neue",Arial,sans-serif;color:#0A0A0C;margin:0;max-width:760px}}
.hd{{background:#0A0A0C;color:#fff;padding:18px 24px;border-top:6px solid #D6222D}}.hd h1{{font-family:Anton,Impact,"Arial Black",sans-serif;font-size:30px;margin:0;letter-spacing:.04em;text-transform:uppercase}}
.hd p{{margin:4px 0 0;font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#bbb}}h2{{font-size:13px;letter-spacing:.16em;text-transform:uppercase;color:#D6222D;margin:22px 24px 6px;border-bottom:2px solid #D6222D;padding-bottom:4px}}
table{{border-collapse:collapse;margin:0 24px;width:calc(100% - 48px)}}td{{padding:6px 0;border-bottom:1px solid #e4e1dd;font-size:14px;vertical-align:top}}td:first-child{{width:210px;color:#6A6A6E;text-transform:uppercase;letter-spacing:.08em;font-size:11px;padding-top:9px}}
code{{font-family:Menlo,Consolas,monospace;font-size:13px;background:#F4F2F0;padding:1px 5px}}.ft{{margin:26px 24px 0;font-size:11px;color:#6A6A6E}}</style></head><body>
<div class="hd"><h1>ariseOS: if the server dies</h1><p>{e(head)}</p></div>
<h2>Bradly can't be reached?</h2><table><tr><td>Kristina follows this card</td><td>Round 7, 59. She knows the disk passphrase and the backup password (58). If neither of you answers, call the next name below.</td></tr></table>
<h2>This box</h2><table><tr><td>Name</td><td>{e(f['host'])} &nbsp;(<code>{e(f['fqdn'])}</code>)</td></tr><tr><td>Address on the wire</td><td><code>{e(f['ip'] or 'see arisectl info')}</code> &nbsp;pinned on the box, not on the router</td></tr>
<tr><td>Dashboard</td><td><code>https://{e(f['fqdn'])}</code> &nbsp;and the desktop on this monitor</td></tr><tr><td>Over Tailscale</td><td>the same address from any signed-in admin laptop or phone</td></tr></table>
<h2>Three commands (Alt+F2 for a text login)</h2><table><tr><td>What is wrong?</td><td><code>sudo arisectl doctor</code></td></tr><tr><td>Dashboard stuck</td><td><code>sudo systemctl restart arise-web</code> &nbsp;(logins and shares keep working meanwhile)</td></tr><tr><td>Everything stuck</td><td><code>sudo reboot</code> &nbsp;about a minute; Macs keep working on cached accounts</td></tr></table>
<h2>Getting in when the domain is down</h2><table><tr><td>Break-glass login</td><td><code>arise-rescue</code> at this monitor only (Alt+F2), never SSH. Every use is logged and reaches Bradly.</td></tr><tr><td>Its password</td><td>{rescue}</td></tr></table>
<h2>The backups</h2><table><tr><td>Tonight's copy</td><td><code>{e(f['repo'])}</code> at 03:00; restore: <code>sudo arisectl backup restore latest --target /srv/arise/restore</code></td></tr>
<tr><td>Off-site copy</td><td>Arise-Home (Bradly's house){(' &nbsp;<code>' + e(f['home']) + '</code>') if f.get('home') else ''}, every snapshot but the raw recordings</td></tr>
<tr><td>Backup password (restic)</td><td>Write it here by hand: ______________________________ &nbsp;Kristina has it too.</td></tr>
<tr><td>Disk passphrase</td><td>Asked at every start ("Please unlock disk"): type it on this keyboard, or <code>ssh -p 2222 root@arise-server</code> from a church computer. It is on the safe card, and Bradly and Kristina know it. Not written here.</td></tr>
<tr><td>Rebuild</td><td><code>sudo arisectl reinstall</code> from the Synology or Arise-Home (docs/REINSTALL.md)</td></tr></table>
<h2>Who to call</h2><table>{who}</table>
<h2>Staff with a Mac problem</h2><table><tr><td>The IT portal</td><td><code>{e(it_portal())}</code> &nbsp;a ticket reaches Bradly</td></tr></table>
<p class="ft">Printed {now:%Y-%m-%d} by <code>sudo arisectl rescue card</code>. Nothing on this page changes a router. Arise Church · Pineville, LA.</p></body></html>
"""


def write_cards(rescue_file: str = "/etc/arise/secrets/rescue-password") -> dict:
    """The private card (root only) and the staff-share copy (no password)."""
    cfg = load()
    if cfg.demo:
        return {"ok": True, "demo": True}
    try:
        pw = Path(rescue_file).read_text(encoding="utf-8").strip()
    except OSError:
        pw = ""
    priv = Path("/etc/arise/CLOSET-CARD.html")
    pub = Path(str(cfg.system.data_root)) / "shares" / "staff" / "CLOSET-CARD.html"
    out = {"ok": True, "private": str(priv), "public": str(pub)}
    try:
        priv.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(priv, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(closet_card(True, pw))
        os.chmod(priv, 0o600)
    except OSError as e:
        out.update(ok=False, err=f"could not write {priv}: {e}")
    try:
        pub.parent.mkdir(parents=True, exist_ok=True)
        pub.write_text(closet_card(False), encoding="utf-8")
        os.chmod(pub, 0o644)
    except OSError as e:
        out["public_err"] = str(e)
    return out

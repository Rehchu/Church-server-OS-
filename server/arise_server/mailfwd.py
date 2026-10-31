"""Staff addresses, forwarding only (round 7, 155; round 6, 28; round 5, 38).

first.last@arisecenla.com (Bradly, Oct 31, ANSWERS H10; it was @ad.arisecenla.com) reaches
each person at the personal email on their profile. Nothing on this box listens to the
internet (rule 7), so the box cannot be anyone's mail server. Instead:

  1. The public MX for arisecenla.com (Wix: @ -> receive.forge.rmta.net, set up Oct 31)
     points at Resend's receiving servers. Resend keeps each message.
  2. Every five minutes (arise-mailfwd.timer) the box ASKS Resend, over an
     outgoing HTTPS call like any other, for mail that has arrived, and sends each
     message on to the person's personal address through Resend. The box opens
     no port. The domain sign-in inside the church stays ad.arisecenla.com.
  3. No mailbox is kept here: a forwarded message is not stored. The forwarding
     log keeps who, from whom, the subject and when (never the body), root only.

"Exporting a leaver's mail" (round 5, 38) therefore means their alias and their
forwarding log: the messages themselves went to their personal address, and
Resend's own copies age out on Resend's schedule.

Off until Bradly turns it on ([mailfwd] enabled = true) after the Wix record and
Resend's receiving are set up. The Resend receiving API was in beta when this was
written; RECEIVED_LIST and RECEIVED_ONE are the two calls this uses, kept in one
place so a renamed endpoint is a one-line fix.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
from datetime import datetime

from .config import load
from .util import read_json, write_json

RECEIVED_LIST = "/emails/receiving?limit=100"     # list what arrived (newest first, 100 at most)
RECEIVED_ONE = "/emails/receiving/{id}"           # one message in full: text, html, headers, attachments
DOMAIN = "arisecenla.com"            # Bradly, Oct 31 (H10): first.last@arisecenla.com
SEEN_KEEP = 5000
ADDR_RE = re.compile(r"<?([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+)>?")


def cfg_fwd() -> dict:
    raw = load().raw
    d = dict((raw.get("mailfwd") if isinstance(raw, dict) else None) or {})
    d.setdefault("enabled", False)
    d.setdefault("domain", DOMAIN)
    return d


def addresses(field) -> list[str]:
    """Pure: the bare addresses in a to/cc field (a string, a list, or {email: ...} objects)."""
    items = field if isinstance(field, list) else [field]
    out = []
    for it in items:
        if isinstance(it, dict):
            it = it.get("email") or it.get("address") or ""
        for m in ADDR_RE.finditer(str(it or "")):
            out.append(m.group(1).lower())
    return out


def aliases(users: list[dict], emails: dict[str, str]) -> dict[str, dict]:
    """Pure: alias -> {to, enabled}. Every account with a personal email has one; a switched-off
    account keeps its alias row (for the export) but nothing is forwarded to it."""
    out = {}
    for u in users:
        name = str(u.get("name") or "").lower()
        if not name:
            continue
        out[name] = {"to": (emails.get(name) or "").strip(), "enabled": bool(u.get("enabled", True))}
    return out


def route(msg_to: list[str], als: dict[str, dict], domain: str = DOMAIN) -> list[dict]:
    """Pure: where one arrived message goes. [{alias, to}|{alias, why}] per address at our domain."""
    out, seen = [], set()
    for a in msg_to:
        local, _, dom = a.partition("@")
        if dom != domain.lower() or local in seen:
            continue
        seen.add(local)
        al = als.get(local)
        if not al:
            out.append({"alias": local, "why": "no such person"})
        elif not al["enabled"]:
            out.append({"alias": local, "why": "account switched off"})
        elif not al["to"]:
            out.append({"alias": local, "why": "no personal email on their profile"})
        else:
            out.append({"alias": local, "to": al["to"]})
    return out


def forward_body(msg: dict, dest: str, from_email: str, server_name: str = "Arise Church IT") -> dict:
    """Pure: the Resend send for one forward. From the church's verified sending address (a
    forward cannot claim to be the original sender), Reply-To the original sender so a reply
    goes straight back to them, the subject unchanged."""
    orig = (addresses(msg.get("from")) or [""])[0]
    name = ""
    if isinstance(msg.get("from"), str) and "<" in msg["from"]:
        name = msg["from"].split("<")[0].strip().strip('"')
    who = name or orig or "someone"
    body = {"from": f"{who} via {server_name} <{from_email}>", "to": [dest], "subject": (msg.get("subject") or "(no subject)")[:250]}
    if orig:
        body["reply_to"] = orig
    note = f"Forwarded by the church server from {orig or 'an unknown sender'} to your church address."
    if msg.get("text"):
        body["text"] = msg["text"] + f"\n\n--\n{note}"
    if msg.get("html"):
        body["html"] = msg["html"] + f"<hr><p style=\"font-size:12px;color:#666\">{note}</p>"
    if not body.get("text") and not body.get("html"):
        body["text"] = f"(this message had no text)\n\n--\n{note}"
    atts = []
    for a in msg.get("attachments") or []:
        url = a.get("download_url") or a.get("url")
        if url and a.get("filename"):
            atts.append({"filename": a["filename"], "path": url})
    if atts:
        body["attachments"] = atts
    return body


def _log_path():
    return load().state_dir / "mail-forward.log.jsonl"


def _state_path():
    return load().state_dir / "mail-forward.json"


def _log(row: dict) -> None:
    p = _log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def log(limit: int = 200, alias: str = "") -> list[dict]:
    if load().demo:
        rows = [{"t": "2026-10-28T14:02:00", "alias": "bryant.sanders", "from": "guest.speaker@example.org", "subject": "Notes for Sunday (sample)", "ok": True},
                {"t": "2026-10-27T09:40:00", "alias": "old.timer", "from": "vendor@example.com", "subject": "Invoice (sample)", "ok": False, "why": "account switched off"}]
        return [r for r in rows if not alias or r["alias"] == alias]
    rows = []
    try:
        with open(_log_path(), encoding="utf-8") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if not alias or r.get("alias") == alias:
                    rows.append(r)
    except OSError:
        pass
    return list(reversed(rows))[:limit]


def _users_and_emails() -> tuple[list[dict], dict[str, str]]:
    from . import directory, notify
    try:
        users = directory.list_users().get("users", [])
    except Exception:  # noqa: BLE001
        users = []
    emails = {}
    for u in users:
        e = notify.personal_email(u["name"])
        if e:
            emails[u["name"].lower()] = e
    return users, emails


def status() -> dict:
    c = cfg_fwd()
    if load().demo:
        return {"demo": True, "enabled": False, "domain": c["domain"], "aliases": [
            {"alias": "bryant.sanders", "to": "b***@gmail.com", "enabled": True}, {"alias": "kristina.robinson", "to": "k***@gmail.com", "enabled": True},
            {"alias": "office", "to": "", "enabled": True, "why": "no personal email on their profile"}],
            "last_run": None, "how": "off until the Wix record and Resend's receiving are set up (docs/WIX-DNS.md, part 2)"}
    users, emails = _users_and_emails()
    als = aliases(users, emails)
    st = read_json(_state_path(), default={}) or {}
    return {"demo": False, "enabled": bool(c["enabled"]), "domain": c["domain"], "last_run": st.get("last_run"), "last_error": st.get("last_error"),
            "aliases": [{"alias": k, "to": mask(v["to"]), "enabled": v["enabled"], **({} if v["to"] else {"why": "no personal email on their profile"})} for k, v in sorted(als.items())]}


def mask(email: str) -> str:
    """Pure: b***@gmail.com. The dashboard shows enough to recognise an address, not to copy it."""
    if "@" not in (email or ""):
        return ""
    local, dom = email.split("@", 1)
    return (local[:1] + "***@" + dom) if local else "***@" + dom


def run_once(call=None) -> dict:
    """One poll: what arrived since last time goes on. Never raises."""
    from . import mail
    c = cfg_fwd()
    if load().demo:
        return {"ok": True, "demo": True, "forwarded": 0}
    if not c["enabled"]:
        return {"ok": True, "skipped": "forwarding is off ([mailfwd] enabled = false)"}
    call = call or mail._call
    m = mail.cfg_mail()
    if not m.get("from_email"):
        return {"ok": False, "err": "set [mail] from_email first (an address at mail.arisecenla.com)"}
    st = read_json(_state_path(), default={}) or {}
    seen = list(st.get("seen") or [])
    seen_set = set(seen)
    r = call("GET", RECEIVED_LIST)
    if not r.get("ok"):
        st.update(last_run=datetime.now().isoformat(timespec="seconds"), last_error=str(r.get("err"))[:200])
        write_json(_state_path(), st)
        return {"ok": False, "err": r.get("err")}
    items = (r.get("data") or {}).get("data") or []
    new = [x for x in reversed(items) if x.get("id") and x["id"] not in seen_set]   # oldest first
    users, emails = _users_and_emails()
    als = aliases(users, emails)
    fwd = 0
    for it in new:
        targets = route(addresses(it.get("to")) + addresses(it.get("cc")), als, c["domain"])
        full = None
        for t in targets:
            row = {"t": datetime.now().isoformat(timespec="seconds"), "id": it["id"], "alias": t["alias"],
                   "from": (addresses(it.get("from")) or [""])[0], "subject": str(it.get("subject") or "")[:200]}
            if "to" not in t:
                _log({**row, "ok": False, "why": t["why"]})
                continue
            if full is None:
                g = call("GET", RECEIVED_ONE.format(id=it["id"]))
                full = (g.get("data") or {}) if g.get("ok") else {}
                if not full:
                    _log({**row, "ok": False, "why": "could not fetch the message: " + str(g.get("err"))[:120]})
                    continue
            s = call("POST", "/emails", forward_body(full, t["to"], m["from_email"], m.get("server_from_name") or "Arise Church IT"))
            _log({**row, "ok": bool(s.get("ok")), **({} if s.get("ok") else {"why": str(s.get("err"))[:160]})})
            fwd += 1 if s.get("ok") else 0
        seen.append(it["id"])
        seen_set.add(it["id"])
    st.update(seen=seen[-SEEN_KEEP:], last_run=datetime.now().isoformat(timespec="seconds"), last_error=None)
    write_json(_state_path(), st)
    return {"ok": True, "arrived": len(new), "forwarded": fwd}


def export(user: str) -> dict:
    """A leaver's mail, with forwarding only: their alias and their forwarding log (round 5, 38)."""
    user = (user or "").strip().lower()
    rows = log(limit=100000, alias=user)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["when", "from", "subject", "forwarded", "note"])
    for r in reversed(rows):
        w.writerow([r.get("t", ""), r.get("from", ""), r.get("subject", ""), "yes" if r.get("ok") else "no", r.get("why", "")])
    return {"ok": True, "user": user, "address": f"{user}@{cfg_fwd()['domain']}", "messages": len(rows), "csv": buf.getvalue(),
            "note": "Forwarding only: the messages themselves went to their personal address and are not kept on the server. This is the record of what arrived and where it went."}

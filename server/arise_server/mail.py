"""Mass email to the church family through Resend.

Contacts live in a Resend Audience (so unsubscribe links work and the law is
kept), imported from a CSV exported from Wix. A newsletter is a Resend
Broadcast: written here in the house template, sent to everyone with one
typed word, or to one address as a test. The API key is a root-only file.

Config, [mail] in arise.toml:
  provider = "resend"; api_key_file; from_name; from_email (a domain verified
  in Resend: NOT gmail.com); reply_to (the Gmail is fine here); audience_id
  (made on first use and written to <state_dir>/mail.json).
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

from .config import load

API = "https://api.resend.com"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_import_state: dict = {"running": False}


def cfg_mail() -> dict:
    cfg = load()
    raw = (cfg.raw.get("mail") if isinstance(cfg.raw, dict) else None) or {}
    st = _state()
    return {"provider": raw.get("provider", "resend"), "api_key_file": raw.get("api_key_file", "/etc/arise/secrets/resend-api-key"),
            "from_name": raw.get("from_name", "Arise Church"), "from_email": raw.get("from_email", ""), "reply_to": raw.get("reply_to", ""),
            "audience_id": raw.get("audience_id") or st.get("audience_id", ""), "audience_name": raw.get("audience_name", "Arise Church family")}


def _state_path() -> str:
    return str(load().state_dir / "mail.json")


def _state() -> dict:
    try:
        with open(_state_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(d: dict):
    p = _state_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(p + ".tmp", p)


def _key() -> str:
    try:
        return open(cfg_mail()["api_key_file"], encoding="utf-8").read().strip()
    except OSError:
        return ""


def _call(method: str, path: str, body: dict | None = None) -> dict:
    key = _key()
    if not key:
        return {"ok": False, "err": f"no Resend API key at {cfg_mail()['api_key_file']}"}
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "arise-server"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode() or "{}")
            return {"ok": True, "data": data}
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("message", str(e))
        except Exception:
            msg = str(e)
        return {"ok": False, "err": f"Resend {e.code}: {msg}"}
    except (urllib.error.URLError, TimeoutError) as e:
        return {"ok": False, "err": f"could not reach Resend: {e}"}


# ---- contacts ----------------------------------------------------------------
def parse_contacts(text: str) -> dict:
    """A CSV (Wix's export, or anything with an email column) -> clean contacts.
    Finds the email/first/last columns by header name, drops bad addresses and
    duplicates (case-insensitive). Pure: nothing is sent."""
    text = text.lstrip("﻿")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        return {"contacts": [], "skipped": 0, "columns": {}}
    head = [h.strip().lower() for h in rows[0]]

    def col(*names):
        for i, h in enumerate(head):
            if any(n == h or n in h for n in names):
                return i
        return None
    ie, ifn, iln = col("email", "e-mail"), col("first name", "firstname", "first"), col("last name", "lastname", "surname", "last")
    iname = col("name", "full name", "contact") if ifn is None else None
    if ie is None:
        return {"contacts": [], "skipped": len(rows) - 1, "columns": {}, "err": "no email column found in the header"}
    seen, out, skipped = set(), [], 0
    for r in rows[1:]:
        if len(r) <= ie:
            skipped += 1; continue
        email = r[ie].strip().lower()
        if not EMAIL_RE.match(email) or email in seen:
            skipped += 1; continue
        seen.add(email)
        first = r[ifn].strip() if ifn is not None and len(r) > ifn else ""
        last = r[iln].strip() if iln is not None and len(r) > iln else ""
        if not first and iname is not None and len(r) > iname and r[iname].strip():
            parts = r[iname].strip().split()
            first, last = parts[0], " ".join(parts[1:])
        out.append({"email": email, "first_name": first, "last_name": last})
    return {"contacts": out, "skipped": skipped, "columns": {"email": head[ie], "first": head[ifn] if ifn is not None else "", "last": head[iln] if iln is not None else ""}}


def ensure_audience() -> dict:
    m = cfg_mail()
    if m["audience_id"]:
        return {"ok": True, "id": m["audience_id"]}
    if load().demo:
        return {"ok": True, "id": "demo-audience", "demo": True}
    r = _call("POST", "/audiences", {"name": m["audience_name"]})
    if not r["ok"]:
        return r
    st = _state(); st["audience_id"] = r["data"]["id"]; _save_state(st)
    return {"ok": True, "id": r["data"]["id"], "created": True}


def import_contacts(contacts: list[dict]) -> dict:
    """Adds contacts to the audience in a background thread (Resend's rate limit
    is a couple of requests a second). Progress: import_status()."""
    if _import_state.get("running"):
        return {"ok": False, "err": "an import is already running"}
    if load().demo:
        have = _sample_contacts()
        seen = {c["email"].lower() for c in have}
        added = 0
        for c in contacts:
            e = (c.get("email") or "").strip().lower()
            if not e or e in seen:
                continue
            seen.add(e); added += 1
            have.append({"id": f"c{len(have) + 1}", "email": e, "first_name": c.get("first_name", ""), "last_name": c.get("last_name", ""),
                         "created_at": datetime.now().isoformat(timespec="seconds"), "unsubscribed": False})
        now = datetime.now().isoformat(timespec="minutes")
        _import_state.update({"running": False, "total": len(contacts), "done": added, "failed": 0, "skipped": len(contacts) - added, "errors": [], "started": now, "finished": now, "demo": True})
        return {"ok": True, "demo": True, "queued": len(contacts), "added": added}
    a = ensure_audience()
    if not a["ok"]:
        return a
    _import_state.update({"running": True, "total": len(contacts), "done": 0, "failed": 0, "errors": [], "started": datetime.now().isoformat(timespec="minutes"), "finished": ""})

    def work():
        for c in contacts:
            r = _call("POST", f"/audiences/{a['id']}/contacts", {"email": c["email"], "first_name": c.get("first_name", ""), "last_name": c.get("last_name", ""), "unsubscribed": False})
            if r["ok"]:
                _import_state["done"] += 1
            else:
                _import_state["failed"] += 1
                if len(_import_state["errors"]) < 20:
                    _import_state["errors"].append(f"{c['email']}: {r['err']}")
            time.sleep(0.6)
        _import_state["running"] = False
        _import_state["finished"] = datetime.now().isoformat(timespec="minutes")
    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "queued": len(contacts)}


def import_status() -> dict:
    return dict(_import_state)


def _sample_contacts() -> list[dict]:
    from . import demo, demo_state
    return demo_state.get("mail.contacts", demo.MAIL_CONTACTS)


def _sample_broadcasts() -> list[dict]:
    from . import demo, demo_state
    return demo_state.get("mail.broadcasts", demo.MAIL_BROADCASTS)


def contacts(limit: int = 2000) -> dict:
    if load().demo:
        rows = _sample_contacts()
        return {"demo": True, "audience": "demo-audience", "contacts": rows[:limit], "count": len(rows)}
    a = ensure_audience()
    if not a["ok"]:
        return {"contacts": [], "count": 0, "err": a["err"]}
    r = _call("GET", f"/audiences/{a['id']}/contacts")
    if not r["ok"]:
        return {"contacts": [], "count": 0, "err": r["err"]}
    rows = r["data"].get("data", [])[:limit]
    return {"demo": False, "audience": a["id"], "contacts": rows, "count": len(rows)}


# ---- the newsletter ------------------------------------------------------------
def render(subject: str, body_md: str, church_name: str = "Arise Church", city: str = "Pineville, LA") -> str:
    """The house template: ink header with the name, the body, a footer with the
    unsubscribe link Resend fills in. Body is light Markdown (paragraphs, **bold**,
    links, lists, ## headings)."""
    import html as H
    def inline(t):
        t = H.escape(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"\[(.+?)\]\((https?://[^\s)]+)\)", r'<a href="\2" style="color:#D6222D">\1</a>', t)
        return t
    parts, buf, lst = [], [], []
    def flush():
        nonlocal buf, lst
        if lst:
            parts.append("<ul style='margin:0 0 16px 20px;padding:0'>" + "".join(f"<li style='margin:4px 0'>{inline(x)}</li>" for x in lst) + "</ul>"); lst = []
        if buf:
            parts.append(f"<p style='margin:0 0 16px;line-height:1.55'>{inline(' '.join(buf))}</p>"); buf = []
    for line in body_md.splitlines():
        s = line.strip()
        if not s:
            flush(); continue
        if s.startswith("## "):
            flush(); parts.append(f"<h2 style='font-family:Impact,Anton,Arial Black,sans-serif;font-size:22px;margin:24px 0 10px;letter-spacing:.02em;text-transform:uppercase'>{inline(s[3:])}</h2>"); continue
        if s.startswith(("- ", "* ")):
            if buf: flush()
            lst.append(s[2:]); continue
        if lst: flush()
        buf.append(s)
    flush()
    return f"""<!doctype html><html><body style="margin:0;background:#F4F2F0;font-family:Helvetica,Arial,sans-serif;color:#0A0A0C">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#F4F2F0;padding:24px 0"><tr><td align="center">
<table role="presentation" width="600" cellspacing="0" cellpadding="0" style="max-width:600px;width:100%;background:#fff">
<tr><td style="background:#0A0A0C;color:#fff;padding:22px 28px;border-top:4px solid #D6222D"><div style="font-family:Impact,Anton,Arial Black,sans-serif;font-size:26px;letter-spacing:.04em;text-transform:uppercase">{H.escape(church_name)}</div><div style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#bbb;margin-top:4px">{H.escape(city)}</div></td></tr>
<tr><td style="padding:28px;font-size:16px"><p style="margin:0 0 16px;line-height:1.55">Hi {{{{{{FIRST_NAME|there}}}}}},</p>{''.join(parts)}</td></tr>
<tr><td style="padding:18px 28px;border-top:1px solid #e4e1dd;font-size:12px;color:#6A6A6E;line-height:1.5">{H.escape(church_name)} · {H.escape(city)}<br>You are getting this because you are part of the {H.escape(church_name)} family. <a href="{{{{{{RESEND_UNSUBSCRIBE_URL}}}}}}" style="color:#6A6A6E">Unsubscribe</a></td></tr>
</table></td></tr></table></body></html>"""


def send_test(to: str, subject: str, body_md: str) -> dict:
    m = cfg_mail()
    if not EMAIL_RE.match(to or ""):
        return {"ok": False, "err": "that is not an email address"}
    if load().demo:
        return {"ok": True, "demo": True, "out": f"(sample) would send a test to {to}"}
    if not m["from_email"]:
        return {"ok": False, "err": "set [mail] from_email in arise.toml first (an address at a domain verified in Resend)"}
    html = render(subject, body_md).replace("{{{FIRST_NAME|there}}}", "there").replace("{{{RESEND_UNSUBSCRIBE_URL}}}", "#")
    body = {"from": f"{m['from_name']} <{m['from_email']}>", "to": [to], "subject": "[test] " + subject, "html": html}
    if m["reply_to"]:
        body["reply_to"] = m["reply_to"]
    return _call("POST", "/emails", body)


def send_notice(to: str, subject: str, text: str) -> dict:
    """One plain notice to one person (round 5: "a file was shared with you"). Never a newsletter."""
    m = cfg_mail()
    if not EMAIL_RE.match(to or ""):
        return {"ok": False, "err": "that is not an email address"}
    if load().demo:
        return {"ok": True, "demo": True, "out": f"(sample) would email {to}"}
    if not m["from_email"]:
        return {"ok": False, "err": "no [mail] from_email yet; the notice went by push only"}
    body = {"from": f"{m['from_name']} <{m['from_email']}>", "to": [to], "subject": subject, "text": text}
    return _call("POST", "/emails", body)


def create_broadcast(subject: str, body_md: str, name: str = "") -> dict:
    m = cfg_mail()
    if not (subject or "").strip():
        return {"ok": False, "err": "a subject first"}
    if load().demo:
        bc = {"id": "demo-bc-" + str(int(time.time() * 1000)), "name": name or subject, "subject": subject, "status": "draft",
              "created_at": datetime.now().isoformat(timespec="seconds"), "sent_at": None, "audience_id": "demo-audience"}
        _sample_broadcasts().append(bc)
        return {"ok": True, "demo": True, "id": bc["id"], "broadcast": bc}
    if not m["from_email"]:
        return {"ok": False, "err": "set [mail] from_email in arise.toml first"}
    a = ensure_audience()
    if not a["ok"]:
        return a
    body = {"audience_id": a["id"], "from": f"{m['from_name']} <{m['from_email']}>", "subject": subject, "html": render(subject, body_md), "name": name or subject}
    if m["reply_to"]:
        body["reply_to"] = m["reply_to"]
    r = _call("POST", "/broadcasts", body)
    if r.get("ok"):
        r["id"] = (r.get("data") or {}).get("id", "")
    return r


def send_broadcast(bc_id: str, confirm: str) -> dict:
    if confirm != "send":
        return {"ok": False, "err": "type send to confirm: this goes to everyone on the list"}
    if load().demo:
        bc = next((b for b in _sample_broadcasts() if b["id"] == bc_id), None)
        if not bc:
            return {"ok": False, "err": f"no broadcast {bc_id}"}
        if bc["status"] == "sent":
            return {"ok": False, "err": "that one has already gone"}
        bc.update({"status": "sent", "sent_at": datetime.now().isoformat(timespec="seconds")})
        return {"ok": True, "demo": True, "out": "(sample) sent to the sample list"}
    if not (bc_id or "").strip():
        return {"ok": False, "err": "no broadcast id"}
    return _call("POST", f"/broadcasts/{bc_id}/send", {})


def broadcasts() -> dict:
    if load().demo:
        return {"demo": True, "broadcasts": sorted(_sample_broadcasts(), key=lambda b: b.get("created_at") or "", reverse=True)}
    r = _call("GET", "/broadcasts")
    if not r["ok"]:
        return {"broadcasts": [], "err": r["err"]}
    return {"demo": False, "broadcasts": r["data"].get("data", [])}


def status() -> dict:
    m = cfg_mail()
    key = bool(_key()) or load().demo
    out = {"provider": "Resend", "configured": bool(key and m["from_email"]) or load().demo, "key": key, "from_name": m["from_name"], "from_email": m["from_email"] or ("news@mail.arisecenla.com" if load().demo else ""),
           "reply_to": m["reply_to"] or ("arisenow.church@gmail.com" if load().demo else ""), "audience_id": m["audience_id"] or ("demo-audience" if load().demo else ""), "demo": load().demo,
           "gmail_warning": m["from_email"].lower().endswith("@gmail.com") if m["from_email"] else False}
    return out

"""A person's own church inbox on the dashboard (Bradly, Nov 1, ANSWERS H11).

Kristina wanted "her own inbox she can login to", with Bradly still able to see every inbox in
Resend. Resend Inboxes has no per-inbox logins (every member of the Resend team sees all of
them), so the inbox is shown here instead: the person signs in to the dashboard with their own
church account and sees only first.last@arisecenla.com's mail. The inbox ID is always worked out
on the server from the signed-in account, never taken from the browser, so nobody can open
someone else's inbox by changing a link.

Mail lives in Resend (nothing is stored on this box). Reading needs a Resend key with full
access: a sending-only key gets 401 here, and the page says so.

Who has one: [inbox] users = ["kristina.robinson"]. `sudo arisectl mail inbox create <user>`
makes the inbox in Resend. People with an inbox are left out of forwarding (mailfwd), so their
mail arrives once, here.

The Resend Inboxes API was new when this was written (Oct 2026) and resend.com's docs could not
be read from the build machine, so every path is in PATHS, one place: a renamed endpoint is a
one-line fix. `sudo arisectl mail inbox check` tries them on install day.
"""
from __future__ import annotations

import re
import urllib.parse

from .config import load

PATHS = {
    "inboxes": "/inboxes?limit=100",
    "create": "/inboxes",
    "threads": "/inboxes/{inbox}/threads?limit={limit}&folders={folder}",
    "thread": "/inboxes/{inbox}/threads/{thread}",
    "email": "/inboxes/{inbox}/threads/{thread}/emails/{email}",
    "reply": "/inboxes/{inbox}/threads/{thread}/emails/{email}/reply",
    "send": "/inboxes/{inbox}/emails",
}
FOLDERS = ("inbox", "archive", "sent", "spam", "trash")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
ADDR_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def cfg_inbox() -> dict:
    raw = load().raw
    d = dict((raw.get("inbox") if isinstance(raw, dict) else None) or {})
    d.setdefault("users", ["kristina.robinson"])   # H11: Kristina asked for one
    d["users"] = [str(u).strip().lower() for u in d["users"] if str(u).strip()]
    return d


def users() -> list[str]:
    return cfg_inbox()["users"]


def address_for(user: str, domain: str) -> str:
    """Pure: the inbox address of an account, first.last@<mail domain>."""
    return f"{(user or '').strip().lower()}@{(domain or '').strip().lower()}"


def has_inbox(user: str) -> bool:
    return (user or "").strip().lower() in users()


def pick(inboxes: list[dict], address: str) -> dict | None:
    """Pure: this person's inbox among the account's, by address (case-insensitive)."""
    want = (address or "").lower()
    for i in inboxes or []:
        if str(i.get("email_address") or i.get("address") or "").lower() == want:
            return i
    return None


def path(name: str, **kw) -> str:
    """Pure: an API path with every part URL-quoted (an ID can never add a path segment)."""
    return PATHS[name].format(**{k: urllib.parse.quote(str(v), safe="") for k, v in kw.items()})


def _domain() -> str:
    from .profiles import mail_domain
    return mail_domain()


def _call(method: str, p: str, body: dict | None = None) -> dict:
    from . import mail
    return mail._call(method, p, body)


def _rows(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("data", "inboxes", "threads", "emails"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


def _mine(user: str) -> dict:
    """{ok, inbox} for the signed-in person, or {ok: False, err}. Never from the browser."""
    if not has_inbox(user):
        return {"ok": False, "err": "no church inbox for this account (Bradly adds people to [inbox] users)", "none": True}
    addr = address_for(user, _domain())
    r = _call("GET", path("inboxes"))
    if not r.get("ok"):
        err = r.get("err", "")
        if "401" in err or "403" in err or "restricted" in err.lower():
            err += " (the server's Resend key needs full access to read inboxes, not sending only)"
        return {"ok": False, "err": err, "address": addr}
    box = pick(_rows(r.get("data")), addr)
    if not box:
        return {"ok": False, "err": f"Resend has no inbox for {addr} yet: sudo arisectl mail inbox create {user}", "address": addr}
    return {"ok": True, "inbox": box, "address": addr}


# ---- sample mail for the preview (demo mode) ----------------------------------------
def _sample(user: str) -> dict:
    # The sample is Kristina's inbox whoever is signed in to the preview (the demo account has no inbox of its own).
    addr = address_for("kristina.robinson" if (user or "demo") in ("demo", "") else user, _domain() or "arisecenla.com")
    return {
        "address": addr,
        "threads": [
            {"id": "t-1", "subject": "Women's conference rooms", "from": "Hotel Bookings <events@example.org>", "read": False,
             "email_count": 2, "received_at": "2026-11-01T09:14:00Z", "has_attachment": True, "folder": "inbox"},
            {"id": "t-2", "subject": "Thank you for Sunday", "from": "A visitor <visitor@example.com>", "read": True,
             "email_count": 1, "received_at": "2026-10-31T18:02:00Z", "has_attachment": False, "folder": "inbox"},
        ],
        "thread": {"t-1": [{"id": "e-1", "direction": "inbound", "from": "Hotel Bookings <events@example.org>", "to": [addr],
                            "subject": "Women's conference rooms", "received_at": "2026-11-01T09:14:00Z",
                            "text": "Hello Minister Robinson,\n\nWe are holding twelve rooms for the weekend. The contract is attached.\n\nThank you,\nEvents team",
                            "attachments": [{"filename": "contract.pdf", "size": 182044}]},
                           {"id": "e-2", "direction": "outbound", "from": addr, "to": ["events@example.org"],
                            "subject": "Re: Women's conference rooms", "received_at": "2026-11-01T10:30:00Z",
                            "text": "Thank you! I will send the signed copy Monday.", "attachments": []}],
                   "t-2": [{"id": "e-3", "direction": "inbound", "from": "A visitor <visitor@example.com>", "to": [addr],
                            "subject": "Thank you for Sunday", "received_at": "2026-10-31T18:02:00Z",
                            "text": "We visited for the first time and felt so welcome.", "attachments": []}]},
    }


# ---- what the dashboard calls --------------------------------------------------------
def overview(user: str, folder: str = "inbox", limit: int = 50) -> dict:
    folder = folder if folder in FOLDERS else "inbox"
    limit = max(1, min(int(limit or 50), 100))
    if load().demo:
        s = _sample(user)
        return {"ok": True, "demo": True, "address": s["address"], "folder": folder,
                "threads": s["threads"] if folder == "inbox" else []}
    m = _mine(user)
    if not m["ok"]:
        return {**m, "threads": [], "folder": folder}
    r = _call("GET", path("threads", inbox=m["inbox"]["id"], limit=limit, folder=folder))
    if not r.get("ok"):
        return {"ok": False, "err": r.get("err"), "address": m["address"], "threads": [], "folder": folder}
    return {"ok": True, "address": m["address"], "folder": folder, "unread": m["inbox"].get("unread"), "threads": _rows(r.get("data"))}


def thread(user: str, thread_id: str) -> dict:
    if not ID_RE.match(thread_id or ""):
        return {"ok": False, "err": "bad thread"}
    if load().demo:
        s = _sample(user)
        msgs = s["thread"].get(thread_id)
        return {"ok": True, "demo": True, "emails": msgs} if msgs else {"ok": False, "err": "no such thread"}
    m = _mine(user)
    if not m["ok"]:
        return m
    t = _call("GET", path("thread", inbox=m["inbox"]["id"], thread=thread_id))
    if not t.get("ok"):
        return {"ok": False, "err": t.get("err")}
    d = t.get("data") or {}
    emails = []
    for e in _rows(d.get("emails") if isinstance(d, dict) and "emails" in d else d)[:100]:
        if not ID_RE.match(str(e.get("id", ""))):
            continue
        full = _call("GET", path("email", inbox=m["inbox"]["id"], thread=thread_id, email=e["id"]))
        emails.append(full.get("data") if full.get("ok") and isinstance(full.get("data"), dict) else e)
    return {"ok": True, "subject": d.get("subject") if isinstance(d, dict) else "", "emails": emails}


def reply(user: str, thread_id: str, email_id: str, text: str, reply_all: bool = False) -> dict:
    text = (text or "").strip()
    if not text:
        return {"ok": False, "err": "write something first"}
    if len(text) > 50000:
        return {"ok": False, "err": "that reply is too long"}
    if not (ID_RE.match(thread_id or "") and ID_RE.match(email_id or "")):
        return {"ok": False, "err": "bad message"}
    if load().demo:
        return {"ok": True, "demo": True, "out": "(sample) reply sent"}
    m = _mine(user)
    if not m["ok"]:
        return m
    r = _call("POST", path("reply", inbox=m["inbox"]["id"], thread=thread_id, email=email_id),
              {"text": text, "reply_all": bool(reply_all)})
    return {"ok": True, "id": (r.get("data") or {}).get("id")} if r.get("ok") else {"ok": False, "err": r.get("err")}


def send(user: str, to: list[str] | str, subject: str, text: str) -> dict:
    to = [t.strip() for t in (to if isinstance(to, list) else str(to or "").replace(";", ",").split(",")) if t.strip()]
    bad = [t for t in to if not ADDR_RE.match(t)]
    subject = (subject or "").strip()
    if not to or bad:
        return {"ok": False, "err": "check the To addresses" + (f": {', '.join(bad[:3])}" if bad else "")}
    if len(to) > 50:
        return {"ok": False, "err": "50 recipients at most"}
    if not subject or "\n" in subject or len(subject) > 2000:
        return {"ok": False, "err": "a subject, on one line"}
    if not (text or "").strip():
        return {"ok": False, "err": "write something first"}
    if load().demo:
        return {"ok": True, "demo": True, "out": f"(sample) sent to {', '.join(to)}"}
    m = _mine(user)
    if not m["ok"]:
        return m
    r = _call("POST", path("send", inbox=m["inbox"]["id"]), {"to": to, "subject": subject, "text": text})
    return {"ok": True, "id": (r.get("data") or {}).get("id")} if r.get("ok") else {"ok": False, "err": r.get("err")}


# ---- arisectl -------------------------------------------------------------------------
def create(user: str, display: str = "") -> dict:
    """Make the Resend inbox for an account in [inbox] users (Bradly runs it on the box)."""
    user = (user or "").strip().lower()
    if not has_inbox(user):
        return {"ok": False, "err": f"{user} is not in [inbox] users in /etc/arise/arise.toml; add them there first"}
    addr = address_for(user, _domain())
    if load().demo:
        return {"ok": True, "demo": True, "out": f"(sample) inbox {addr}"}
    have = _call("GET", path("inboxes"))
    if have.get("ok") and pick(_rows(have.get("data")), addr):
        return {"ok": True, "out": f"{addr} already has an inbox"}
    body = {"email_address": addr, "name": user}
    if display:
        body["from_name"] = display[:78]
    r = _call("POST", path("create"), body)
    return {"ok": True, "out": f"inbox made: {addr}"} if r.get("ok") else {"ok": False, "err": r.get("err")}


def check() -> dict:
    """Install-day probe: can this key list inboxes, and does every [inbox] user have one?"""
    if load().demo:
        return {"ok": True, "demo": True, "rows": [{"user": u, "address": address_for(u, "arisecenla.com"), "inbox": True} for u in users()]}
    r = _call("GET", path("inboxes"))
    if not r.get("ok"):
        return {"ok": False, "err": r.get("err"), "rows": []}
    boxes = _rows(r.get("data"))
    rows = [{"user": u, "address": address_for(u, _domain()), "inbox": bool(pick(boxes, address_for(u, _domain())))} for u in users()]
    return {"ok": all(x["inbox"] for x in rows), "rows": rows}

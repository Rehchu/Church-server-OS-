"""The church contacts, as a read-only CardDAV address book (round 7, rows 21 and 152).

One book, "Arise Church", for staff and admins, holding:
  - the staff directory: every enabled account, with its title, departments, church email
    and the mobile number from the profile (row 21: staff phone numbers are visible to all staff);
  - the church contacts list: the Mail app's contacts (round 2, 39: one source, staff keep it).

Staff don't use the dashboard, so the book goes where they are: Contacts on a church Mac and
on their phone (Settings > Contacts > Accounts > Add Account > Other > CardDAV), with their own
church login. Nobody edits it there: admins keep the people in Directory and the list in Mail.

Why the server serves it itself rather than Nextcloud: Nextcloud's own sharing is off (round 6,
the server's Share with... is the only way to share), and a shared Nextcloud address book needs
that sharing; its system address book holds only accounts, not the church list. This is the
small read-only subset of CardDAV (RFC 6352) that Contacts and iOS use: discovery,
PROPFIND, addressbook-multiget and addressbook-query (both answered with every card), and GET.
Not yet tried against a real Mac or iPhone (no Apple device where this was built).
"""
from __future__ import annotations

import hashlib
import time
from xml.sax.saxutils import escape as _x

from .config import load

BOOK = "church"
NS = 'xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav" xmlns:cs="http://calendarserver.org/ns/"'
SYSTEM = {"administrator", "guest", "krbtgt", "arise-nextcloud", "arise-sync", "arise-rescue"}
_cache: dict = {}


# ----- the cards --------------------------------------------------------------------------
def esc(v: str) -> str:
    """Pure: a vCard 3.0 text value (backslash, comma, semicolon, newline escaped)."""
    return (v or "").replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def fold(line: str) -> str:
    """Pure: lines over 75 octets folded with CRLF + space (RFC 2425)."""
    b = line.encode("utf-8")
    if len(b) <= 75:
        return line
    out, cur = [], b""
    for ch in line:
        e = ch.encode("utf-8")
        if len(cur) + len(e) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += e
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def vcard(uid: str, full: str, first: str = "", last: str = "", title: str = "", emails: list[str] | None = None,
          phone: str = "", categories: list[str] | None = None, note: str = "") -> str:
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"UID:{esc(uid)}", f"FN:{esc(full)}",
             f"N:{esc(last)};{esc(first)};;;", "ORG:Arise Church"]
    if title:
        lines.append(f"TITLE:{esc(title)}")
    for i, e in enumerate(emails or []):
        lines.append(f"EMAIL;TYPE=INTERNET{',WORK' if i == 0 else ''}:{esc(e)}")
    if phone:
        lines.append(f"TEL;TYPE=CELL:{esc(phone)}")
    if categories:
        lines.append("CATEGORIES:" + ",".join(esc(c) for c in categories))
    if note:
        lines.append(f"NOTE:{esc(note)}")
    lines.append("END:VCARD")
    return "\r\n".join(fold(x) for x in lines) + "\r\n"


def staff_cards() -> list[tuple[str, str]]:
    """(uid, vcard) for every enabled account that is a person or a department."""
    from . import directory, profiles
    d = profiles._read()
    out = []
    for u in directory.list_users().get("users", []):
        name = u["name"]
        if not u.get("enabled", True) or name.lower() in SYSTEM or name.endswith("$"):
            continue
        p = d.get(name, {})
        disp = (u.get("display") or name).strip()
        parts = disp.split()
        first, last = (parts[0], " ".join(parts[1:])) if len(parts) > 1 else (disp, "")
        full = profiles.display_name(name, disp, p)
        emails = [f"{name}@{profiles.mail_domain()}"]
        cats = ["Staff directory"] + [str(x) for x in (p.get("departments") or [])]
        out.append((f"staff-{name}", vcard(f"staff-{name}", full, first, last, p.get("title", ""), emails, p.get("mobile", ""), cats)))
    return out


def list_cards() -> list[tuple[str, str]]:
    """The church contacts list (the Mail app's, round 2, 39)."""
    from . import mail
    out = []
    r = mail.contacts(limit=5000)
    for c in r.get("contacts", []):
        email = str(c.get("email") or "").strip().lower()
        if not email:
            continue
        first, last = str(c.get("first_name") or ""), str(c.get("last_name") or "")
        full = (first + " " + last).strip() or email
        uid = "c-" + hashlib.sha1(email.encode()).hexdigest()[:16]
        out.append((uid, vcard(uid, full, first, last, "", [email], "", ["Church contacts"])))
    return out


def cards(fresh: bool = False) -> dict:
    """uid -> vcard, both sources, cached ten minutes (the Mail list comes from Resend)."""
    now = time.time()
    if not fresh and _cache.get("t", 0) > now - 600 and not load().demo:
        return _cache["v"]
    v = dict(staff_cards())
    try:
        v.update(list_cards())
    except Exception:  # noqa: BLE001 - the staff directory still answers when the Mail list can't
        pass
    _cache.update(t=now, v=v)
    return v


def etag(card: str) -> str:
    return '"' + hashlib.sha1(card.encode()).hexdigest()[:20] + '"'


def ctag(all_cards: dict) -> str:
    h = hashlib.sha1()
    for k in sorted(all_cards):
        h.update(k.encode()); h.update(all_cards[k].encode())
    return h.hexdigest()[:20]


# ----- who may read it -----------------------------------------------------------------------
def may_read(user: str) -> bool:
    """Staff and admins (round 5, 10: staff and admins see everyone's details)."""
    from . import directory, profiles
    role = "admin" if directory.is_admin(user) else "member"
    return profiles.is_staff({"user": user, "role": role})


# ----- the DAV answers ---------------------------------------------------------------------------
def _resp(href: str, props: str) -> str:
    return f"<d:response><d:href>{_x(href)}</d:href><d:propstat><d:prop>{props}</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"


def multistatus(responses: list[str]) -> str:
    return f'<?xml version="1.0" encoding="utf-8"?>\n<d:multistatus {NS}>' + "".join(responses) + "</d:multistatus>"


def principal(user: str) -> str:
    return f"/carddav/principals/{user}/"


def home(user: str) -> str:
    return f"/carddav/books/{user}/"


def book(user: str) -> str:
    return f"/carddav/books/{user}/{BOOK}/"


READ_ONLY = "<d:current-user-privilege-set><d:privilege><d:read/></d:privilege></d:current-user-privilege-set>"


def propfind(path: str, user: str, depth: str) -> tuple[int, str]:
    """Pure enough to test: what a PROPFIND on `path` answers for `user`."""
    p = "/" + path.strip("/") + "/" if path.strip("/") else "/"
    base = f"<d:current-user-principal><d:href>{principal(user)}</d:href></d:current-user-principal>"
    if p in ("/", "/carddav/"):
        return 207, multistatus([_resp("/carddav/", base + "<d:resourcetype><d:collection/></d:resourcetype>")])
    if p == principal(user):
        return 207, multistatus([_resp(p, base + f"<d:resourcetype><d:collection/><d:principal/></d:resourcetype>"
                                          f"<d:displayname>{_x(user)}</d:displayname>"
                                          f"<card:addressbook-home-set><d:href>{home(user)}</d:href></card:addressbook-home-set>"
                                          f"<d:principal-URL><d:href>{principal(user)}</d:href></d:principal-URL>")])
    all_cards = cards()
    book_props = (f"<d:resourcetype><d:collection/><card:addressbook/></d:resourcetype><d:displayname>Arise Church</d:displayname>"
                  f"<cs:getctag>{ctag(all_cards)}</cs:getctag>{READ_ONLY}"
                  "<d:supported-report-set><d:supported-report><d:report><card:addressbook-multiget/></d:report></d:supported-report>"
                  "<d:supported-report><d:report><card:addressbook-query/></d:report></d:supported-report></d:supported-report-set>")
    if p == home(user):
        rs = [_resp(p, base + "<d:resourcetype><d:collection/></d:resourcetype>" + READ_ONLY)]
        if depth != "0":
            rs.append(_resp(book(user), book_props))
        return 207, multistatus(rs)
    if p == book(user):
        rs = [_resp(p, book_props)]
        if depth != "0":
            rs += [_resp(book(user) + f"{uid}.vcf", f"<d:getetag>{_x(etag(c))}</d:getetag><d:getcontenttype>text/vcard; charset=utf-8</d:getcontenttype>"
                                                       "<d:resourcetype/>") for uid, c in sorted(all_cards.items())]
        return 207, multistatus(rs)
    uid = _card_uid(p.rstrip("/"), user)
    if uid and uid in all_cards:
        return 207, multistatus([_resp(book(user) + f"{uid}.vcf", f"<d:getetag>{_x(etag(all_cards[uid]))}</d:getetag>"
                                                                   "<d:getcontenttype>text/vcard; charset=utf-8</d:getcontenttype><d:resourcetype/>")])
    return 404, ""


def _card_uid(path: str, user: str) -> str | None:
    pre = book(user)
    if path.startswith(pre) and path.endswith(".vcf"):
        return path[len(pre):-4]
    return None


def report(path: str, user: str, body: str) -> tuple[int, str]:
    """addressbook-multiget (the hrefs asked for) and addressbook-query (every card: the book is small)."""
    import re
    if "/" + path.strip("/") + "/" != book(user):
        return 404, ""
    all_cards = cards()
    hrefs = re.findall(r"<(?:\w+:)?href>\s*([^<]+?)\s*</(?:\w+:)?href>", body or "")
    if "addressbook-multiget" in (body or "") and hrefs:
        uids = [_card_uid(h.strip(), user) for h in hrefs]
    else:
        uids = sorted(all_cards)
    rs = []
    for uid in uids:
        if uid and uid in all_cards:
            c = all_cards[uid]
            rs.append(_resp(book(user) + f"{uid}.vcf", f"<d:getetag>{_x(etag(c))}</d:getetag><card:address-data>{_x(c)}</card:address-data>"))
        elif uid:
            rs.append(f"<d:response><d:href>{_x(book(user) + uid + '.vcf')}</d:href><d:status>HTTP/1.1 404 Not Found</d:status></d:response>")
    return 207, multistatus(rs)


def get(path: str, user: str) -> tuple[int, str, str]:
    uid = _card_uid("/" + path.strip("/"), user)
    c = cards().get(uid or "")
    return (200, c, etag(c)) if c else (404, "", "")


# ----- the one-tap setup for a Mac or an iPhone -----------------------------------------------------
def mobileconfig(host: str) -> str:
    """Pure: an Apple configuration profile that adds the CardDAV account. No user name and no
    password in it: the Mac or iPhone asks for the church login when it is installed."""
    uid = "org.arisechurch.contacts"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>PayloadContent</key><array><dict>
<key>CardDAVAccountDescription</key><string>Arise Church</string>
<key>CardDAVHostName</key><string>{_x(host)}</string>
<key>CardDAVPort</key><integer>443</integer>
<key>CardDAVUseSSL</key><true/>
<key>CardDAVPrincipalURL</key><string>/carddav/</string>
<key>PayloadType</key><string>com.apple.carddav.account</string>
<key>PayloadIdentifier</key><string>{uid}.carddav</string>
<key>PayloadUUID</key><string>5D1E2A8C-7F3B-4C1A-9E2D-6A1B2C3D4E5F</string>
<key>PayloadVersion</key><integer>1</integer>
<key>PayloadDisplayName</key><string>Arise Church contacts</string>
</dict></array>
<key>PayloadDisplayName</key><string>Arise Church contacts</string>
<key>PayloadDescription</key><string>The church's contacts and staff directory, read-only, with your church login.</string>
<key>PayloadIdentifier</key><string>{uid}</string>
<key>PayloadOrganization</key><string>Arise Church</string>
<key>PayloadType</key><string>Configuration</string>
<key>PayloadUUID</key><string>9B4C6E2A-1D3F-4A5B-8C7D-0E1F2A3B4C5D</string>
<key>PayloadVersion</key><integer>1</integer>
</dict></plist>
"""


def info(host: str) -> dict:
    n = len(cards())
    return {"ok": True, "url": f"https://{host}/carddav/", "host": host, "cards": n, "profile": "/contacts.mobileconfig",
            "how_mac": "Contacts > Settings > Accounts > + > Other Contacts Account > CardDAV: Manual, the church login, server " + host,
            "how_phone": "Settings > Contacts > Accounts > Add Account > Other > Add CardDAV Account: server " + host + ", the church login",
            "note": "Read-only. Admins keep the people in Directory and the church list in Mail.", "demo": load().demo}

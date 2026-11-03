"""The server's own YouTube sign-in, renewed each week (Bradly, Oct 29).

Bradly keeps the Google OAuth app in Testing mode on purpose, so a refresh token dies seven
days after it is issued. He renews the PC's every Sunday; the server renews its own the same
way the handoff's authorize_headless.py does, from the dashboard (Automator -> Sign-in) or
`arisectl automator renew`:

  1. start(): a Google sign-in link for the server's own "ariseOS server" Desktop client,
     with state and a PKCE verifier kept here (root only) for ten minutes.
  2. Bradly opens it on his phone, approves, and Google sends the browser to
     http://localhost:8765/?state=...&code=... , which fails to load (nothing listens there).
  3. finish(address): the state must match; the code is swapped for a token (the verifier
     proves it was this server that asked); ONE channels.list?mine=true (1 quota unit) must
     say Arise Church (UCGS9j7B_prcJkbTNgzlGrKg) before anything is written; then token.json
     is written the way authorize_headless.py writes it (google-auth's Credentials.to_json),
     0600, owned by the [owner] account, swapped in atomically.

The token never leaves this module: not in an answer, a log, the audit log or git. The audit
log says "renewed, expires <when>" and nothing more. The pasted address carries a one-time
code that is useless without the verifier, which never leaves this box either.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from . import audit, demo_state
from .config import load

CHANNEL_ID = "UCGS9j7B_prcJkbTNgzlGrKg"       # Arise Church (the handoff's CHANNEL_ID)
CHANNEL_TITLE = "Arise Church"
REDIRECT = "http://localhost:8765/"          # authorize_headless.py's default --port
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true"
PENDING_TTL = 600                            # the sign-in link works ten minutes
TESTING_DAYS = 7                             # Google Testing mode: refresh tokens die after 7 days
REMIND_HOURS = 30                            # remind when the sign-in ends within this
_lock = threading.Lock()


# ----- which scopes: the handoff's, never a guess ---------------------------------------
def scopes(repo: str | None = None) -> list[str]:
    """The scopes authorize_headless.py asks for: its MANAGE constant, read from the automator
    checkout. If the checkout has no such script, SERVER_HANDOFF.md's documented scope
    ("Scope is youtube.force-ssl only"). Anything else is refused rather than guessed."""
    from . import automator
    root = Path(repo or automator._paths()["root"])
    try:
        src = (root / "authorize_headless.py").read_text(encoding="utf-8")
        m = re.search(r'^MANAGE\s*=\s*"(https://www\.googleapis\.com/auth/[a-z.\-]+)"', src, re.M)
        if m:
            return [m.group(1)]
    except OSError:
        pass
    try:
        doc = (root / "SERVER_HANDOFF.md").read_text(encoding="utf-8")
        if re.search(r"Scope is `?youtube\.force-ssl`? only", doc):
            return ["https://www.googleapis.com/auth/youtube.force-ssl"]
    except OSError:
        pass
    raise ValueError(f"the sign-in's scopes can't be read: neither {root}/authorize_headless.py nor "
                     f"{root}/SERVER_HANDOFF.md says them (sudo arisectl automator setup brings the checkout)")


# ----- small helpers ---------------------------------------------------------------------
def _state_dir() -> Path:
    return Path(load().state_dir)


def _pending_path() -> Path:
    return _state_dir() / "ytauth-pending.json"


def _issued_path() -> Path:
    return _state_dir() / "ytauth.json"


def _read(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def _write_private(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name("." + p.name + ".tmp")
    try:
        tmp.unlink()
    except FileNotFoundError:
        pass
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, p)


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def pkce_pair() -> tuple[str, str]:
    """(verifier, S256 challenge), RFC 7636."""
    v = _b64url(secrets.token_bytes(64))
    return v, _b64url(hashlib.sha256(v.encode()).digest())


def _client(path: str) -> dict:
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"no client at {path}: the server's \"ariseOS server\" Desktop client JSON goes there (docs/AUTOMATOR.md, Setting it up)")
    except (OSError, ValueError) as e:
        raise ValueError(f"{path} could not be read as JSON ({type(e).__name__})")
    if "installed" not in cfg:
        raise ValueError(f"{path} is a '{next(iter(cfg), '?')}' client; the sign-in needs a Desktop app client (its JSON starts with \"installed\")")
    c = cfg["installed"]
    if not c.get("client_id") or not c.get("client_secret"):
        raise ValueError(f"{path} has no client_id or client_secret")
    return c


def _held() -> str:
    try:
        from . import church
        svc = church.in_service_now()
        if svc:
            return f"{svc['name']} is on: renew the sign-in after the service"
    except Exception:  # noqa: BLE001
        pass
    return ""


def _fmt(dt: datetime) -> str:
    return dt.strftime("%a %b %-d, %-I:%M %p")


# ----- the weekly clock (Testing mode) ----------------------------------------------------
def _last_sunday_renewal(now: datetime) -> datetime:
    """The preview's sample: renewed last Sunday at 12:14, after the service (Bradly's rhythm)."""
    d = (now - timedelta(days=(now.weekday() + 1) % 7)).replace(hour=12, minute=14, second=0, microsecond=0)
    return d if d <= now else d - timedelta(days=7)


def testing() -> bool:
    try:
        return bool(load().automator.get("oauth_testing", True))
    except AttributeError:
        return True


def expiry(now: datetime | None = None) -> dict:
    """When the server's sign-in ends. Known only from a renewal this module recorded (the
    02:05 job rewrites token.json every night, so its date says nothing about when Google
    issued it). Testing mode only; a Published app's token does not end after a week."""
    now = now or datetime.now()
    if not testing():
        return {"testing": False, "known": False}
    if load().demo:
        d = demo_state.get("ytauth.issued", lambda: {"issued": _last_sunday_renewal(now).isoformat(timespec="minutes"), "by": "bradly"})
    else:
        d = _read(_issued_path())
    if not d.get("issued"):
        return {"testing": True, "known": False,
                "note": "the server's sign-in date isn't known: renew it once in Automator → Sign-in to start the weekly clock"}
    issued = datetime.fromisoformat(d["issued"])
    ends = issued + timedelta(days=TESTING_DAYS)
    left = (ends - now).total_seconds()
    return {"testing": True, "known": True, "issued": issued.isoformat(timespec="minutes"), "expires": ends.isoformat(timespec="minutes"),
            "expires_text": _fmt(ends), "hours_left": round(left / 3600, 1), "days_left": round(left / 86400, 1),
            "expired": left <= 0, "soon": 0 < left <= REMIND_HOURS * 3600, "by": d.get("by", "")}


def attention(now: datetime | None = None) -> list[dict]:
    """The Needs You line (and so the morning note's): ended, or ending within 30 hours."""
    e = expiry(now)
    if not e.get("known"):
        return []
    if e["expired"]:
        return [{"level": "bad", "key": f"ytauth-expired:{e['expires']}",
                 "text": f"The server's YouTube sign-in expired on {e['expires_text']}; renew it from the Media Mac: Automator → Sign-in. The 02:05 job can't read or change the channel until then."}]
    if e["soon"]:
        return [{"level": "warn", "key": f"ytauth-soon:{e['expires']}",
                 "text": f"The server's YouTube sign-in ends {e['expires_text']}; renew it from the Media Mac: Automator → Sign-in."}]
    return []


def reminders(now: datetime | None = None, post=None, push=None) -> list[str]:
    """From the hourly upkeep timer: Saturday evening (19:00-21:59) and Sunday after the service
    (12:00-14:59, never while a service is on), each once a week, when the sign-in ends within
    30 hours (or already has). Discord #alerts and a push to the owner."""
    now = now or datetime.now()
    e = expiry(now)
    if not e.get("known") or not (e["expired"] or e["soon"]):
        return []
    sat = now.weekday() == 5 and 19 <= now.hour <= 21
    sun = now.weekday() == 6 and 12 <= now.hour <= 14 and not _held()
    if not (sat or sun):
        return []
    year, week, _ = now.isocalendar()
    key = f"ytauth-remind:{'sat' if sat else 'sun'}:{year}-W{week:02d}"
    text = (f"The server's YouTube sign-in {'ended' if e['expired'] else 'ends'} {e['expires_text']}. "
            "Renew from the Media Mac: Automator → Sign-in (it is the Mac signed in to the channel's Google account).")
    if post is None:
        from . import discord
        post = discord.post
    r = post("alerts", text, key=key)
    sent = []
    if r.get("ok") and not r.get("duplicate"):
        sent.append(key)
        try:
            if push is None:
                from . import push as _push
                from .automator import job_user
                owner = job_user()
                if owner:
                    _push.send_to([owner], "YouTube sign-in", text, url="/?app=automator", tag="ytauth")
            else:
                push(text)
        except Exception:  # noqa: BLE001 - a push outage never stops the Discord line
            pass
    return sent


# ----- the sign-in --------------------------------------------------------------------------
def start(by: str, now: float | None = None) -> dict:
    """A fresh Google sign-in link. Only the link goes back; the verifier stays here."""
    now = now or time.time()
    held = _held()
    if held:
        return {"ok": False, "err": held}
    if load().demo:
        st = secrets.token_urlsafe(16)
        demo_state.put("ytauth.pending", {"state": st, "made": now})
        return {"ok": True, "demo": True, "redirect": REDIRECT, "expires_in": PENDING_TTL, "channel": CHANNEL_TITLE,
                "url": "https://accounts.google.com/o/oauth2/auth?client_id=sample&response_type=code&state=" + st + "&redirect_uri=" + urllib.parse.quote(REDIRECT, safe="")}
    from . import automator
    p = automator._paths()
    try:
        client = _client(p["secret"])
        sc = scopes()
    except ValueError as e:
        return {"ok": False, "err": str(e)}
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)
    q = {"response_type": "code", "client_id": client["client_id"], "redirect_uri": REDIRECT, "scope": " ".join(sc),
         "state": state, "code_challenge": challenge, "code_challenge_method": "S256", "access_type": "offline",
         "prompt": "consent select_account", "include_granted_scopes": "false"}
    url = (client.get("auth_uri") or AUTH_URI) + "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)
    with _lock:
        _write_private(_pending_path(), {"state": state, "verifier": verifier, "made": now, "by": by, "scopes": sc})
    audit.record(by, "automator.signin.start", "youtube", detail="a sign-in link was made (it works ten minutes)")
    return {"ok": True, "url": url, "redirect": REDIRECT, "expires_in": PENDING_TTL, "channel": CHANNEL_TITLE}


def parse_answer(raw: str) -> dict:
    """Pure: the pasted address (or the bare code) -> {code, state} or {error}."""
    raw = (raw or "").strip().strip('"').strip("'")
    if not raw:
        return {"error": "Nothing was pasted."}
    if "://" in raw or raw.startswith("localhost") or "code=" in raw or "error=" in raw:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(raw if "://" in raw else "http://" + raw).query)
        if "error" in q:
            e = q["error"][0]
            return {"error": "Google sent back an error instead of a code (" + e + ")"
                    + ("; access_denied usually means the account is not a Test user on the consent screen, or Cancel was pressed" if e == "access_denied" else "")}
        if not q.get("code"):
            return {"error": "That address has no code= in it. Copy the address Google sent the browser to after you approved, not the sign-in link."}
        return {"code": q["code"][0], "state": (q.get("state") or [""])[0]}
    return {"code": raw, "state": ""}


def _post_form(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:   # Google's error bodies carry only error / error_description
        try:
            b = json.loads(e.read().decode() or "{}")
        except ValueError:
            b = {}
        return {"error": str(b.get("error") or f"HTTP {e.code}"), "error_description": str(b.get("error_description") or "")[:200]}


def _get_json(url: str, bearer: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + bearer})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return {"error": {"code": e.code, "message": f"YouTube answered {e.code}"}}


def token_json(tok: dict, client: dict, sc: list[str], now: datetime | None = None) -> str:
    """token.json exactly as authorize_headless.py writes it: google-auth's Credentials.to_json()
    (when google-auth is installed, which the venv has, it IS that call)."""
    expiry = (now or datetime.utcnow()) + timedelta(seconds=int(tok.get("expires_in") or 3599))
    granted = (tok.get("scope") or " ".join(sc)).split()
    try:
        from google.oauth2.credentials import Credentials
        return Credentials(token=tok.get("access_token"), refresh_token=tok.get("refresh_token"), token_uri=client.get("token_uri") or TOKEN_URI,
                           client_id=client["client_id"], client_secret=client["client_secret"], scopes=granted, expiry=expiry).to_json()
    except ImportError:
        d = {"token": tok.get("access_token"), "refresh_token": tok.get("refresh_token"), "token_uri": client.get("token_uri") or TOKEN_URI,
             "client_id": client["client_id"], "client_secret": client["client_secret"], "scopes": granted,
             "universe_domain": "googleapis.com", "account": "", "expiry": expiry.isoformat() + "Z"}
        return json.dumps(d)


def write_token(path: str, text: str, owner: str = "") -> None:
    """Swapped in atomically, 0600, owned by the [owner] account (the 02:05 job reads it as him)."""
    p = Path(path)
    if not p.parent.is_dir():
        raise ValueError(f"{p.parent} does not exist: sudo arisectl automator setup makes it")
    tmp = p.with_name("." + p.name + ".renew")
    try:
        tmp.unlink()
    except FileNotFoundError:
        pass
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if owner and os.geteuid() == 0:
            import pwd
            pw = pwd.getpwnam(owner)
            os.chown(tmp, pw.pw_uid, pw.pw_gid)
        os.chmod(tmp, 0o600)
        os.replace(tmp, p)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def finish(answer: str, by: str, post=None, get=None, now: float | None = None) -> dict:
    """Swap the pasted address for a token, prove it is Arise Church, then keep it.
    post(url, form) and get(url, bearer) stand in for Google in the tests."""
    now = now or time.time()
    a = parse_answer(answer)
    if a.get("error"):
        return {"ok": False, "err": a["error"]}
    if load().demo:
        pend = demo_state.get("ytauth.pending", lambda: {})
        if not pend or (a["state"] and a["state"] != pend.get("state")):
            return {"ok": False, "err": "That address is from a different sign-in (the state does not match). Press Renew again and use the new link."}
        demo_state.put("ytauth.pending", {})
        demo_state.put("ytauth.issued", {"issued": datetime.now().isoformat(timespec="minutes"), "by": by})
        e = expiry()
        return {"ok": True, "demo": True, "channel": CHANNEL_TITLE, "expires": e.get("expires"), "expires_text": e.get("expires_text"),
                "note": "Sample: nothing was sent to Google and no token was written."}
    with _lock:
        pend = _read(_pending_path())
        try:
            _pending_path().unlink()          # one try per link, right or wrong: the code is spent either way
        except FileNotFoundError:
            pass
    if not pend.get("state"):
        return {"ok": False, "err": "No sign-in is waiting. Press Renew for the week first, then paste the address within ten minutes."}
    if now - float(pend.get("made", 0)) > PENDING_TTL:
        return {"ok": False, "err": "That sign-in link is more than ten minutes old. Press Renew again."}
    if not a["state"] or a["state"] != pend["state"]:
        return {"ok": False, "err": "That address is from a different sign-in (the state does not match). Press Renew again and use the new link."}
    from . import automator
    p = automator._paths()
    try:
        client = _client(p["secret"])
    except ValueError as e:
        return {"ok": False, "err": str(e)}
    post = post or _post_form
    get = get or _get_json
    tok = post(client.get("token_uri") or TOKEN_URI, {"code": a["code"], "client_id": client["client_id"], "client_secret": client["client_secret"],
                                                       "code_verifier": pend["verifier"], "grant_type": "authorization_code", "redirect_uri": REDIRECT})
    if tok.get("error") or not tok.get("access_token"):
        audit.record(by, "automator.signin", "youtube", ok=False, detail=f"Google would not swap the code: {str(tok.get('error') or 'no answer')[:60]}")
        return {"ok": False, "err": f"Google would not swap that code for a sign-in ({tok.get('error') or 'no answer'}). Codes work once and only for minutes: press Renew again and paste promptly."}
    if not tok.get("refresh_token"):
        return {"ok": False, "err": "Google gave no refresh token, so the 02:05 job could not stay signed in. Press Renew again (it asks with prompt=consent)."}
    sc = pend.get("scopes") or []
    granted = set((tok.get("scope") or " ".join(sc)).split())
    if sc and not set(sc) <= granted:
        return {"ok": False, "err": "The 'manage your YouTube account' permission was not granted. Press Renew again and tick every box."}
    ch = get(CHANNELS_URL, tok["access_token"])
    items = ch.get("items") or []
    if ch.get("error") or not items:
        audit.record(by, "automator.signin", "youtube", ok=False, detail="signed in but the channel could not be read; nothing kept")
        return {"ok": False, "err": "Signed in, but the channel could not be read" + (f" ({ch['error'].get('message')})" if isinstance(ch.get("error"), dict) else "") + ". Nothing was kept."}
    if items[0].get("id") != CHANNEL_ID:
        title = str((items[0].get("snippet") or {}).get("title") or "?")[:80]
        audit.record(by, "automator.signin", "youtube", ok=False, detail=f"wrong channel ({title}); nothing kept")
        return {"ok": False, "err": f"That signed in as '{title}', not Arise Church. Nothing was kept. Press Renew again and choose the Arise Church channel."}
    from .automator import job_user
    try:
        write_token(p["token"], token_json(tok, client, sc), owner=job_user())
    except (OSError, ValueError, KeyError) as e:
        return {"ok": False, "err": f"Signed in as Arise Church, but token.json could not be written: {type(e).__name__}: {str(e)[:120]}"}
    issued = datetime.fromtimestamp(now)
    with _lock:
        _write_private(_issued_path(), {"issued": issued.isoformat(timespec="minutes"), "by": by, "channel": CHANNEL_ID})
    e = expiry(issued)
    audit.record(by, "automator.signin", "youtube", detail=f"renewed, expires {e.get('expires_text') or (issued + timedelta(days=TESTING_DAYS)).isoformat(timespec='minutes')}")
    return {"ok": True, "channel": CHANNEL_TITLE, "expires": e.get("expires"), "expires_text": e.get("expires_text"),
            "note": "Signed in as Arise Church. The token was written for the 02:05 job and never shown."}


def mark_issued(by: str, when: datetime | None = None) -> None:
    """`arisectl automator signin` (the handoff's own script) records its renewal here too."""
    when = when or datetime.now()
    with _lock:
        _write_private(_issued_path(), {"issued": when.isoformat(timespec="minutes"), "by": by, "channel": CHANNEL_ID})

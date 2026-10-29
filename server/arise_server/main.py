"""The FastAPI app: /api/* JSON routes and the dashboard at /.

Routes follow docs/ARCHITECTURE.md. Every mutating route needs a session
(or demo mode). Every module answers with sample data when its tool is
missing, so this app runs anywhere Python runs.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import asyncio
import os
import re

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import VERSION, CODENAME, apps, automator, backups, bible, channel, church, profiles, songs, devices, directory, files, mail, metrics, nas, push, remote, routers, security, sermons, services, shares, sites, system, twofa
from . import activity, automations, monitor, storage, updates
from . import auth as _auth
from . import links
from . import calendar as churchcal
from . import help as helpdocs
from . import weather
from . import finder
from . import audit, offboard
from . import sharing
from . import repos as arise_repos
from .auth import COOKIE, check_password_for, current_user, login, reauth_token, require_admin, require_recent_auth, staff_access
from .config import load
from .util import human_bytes
from .util import run as system_run

cfg = load()
app = FastAPI(title="Arise Server", version=VERSION, docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
metrics.start()
_started = time.time()
if not cfg.demo:
    push.watch(lambda: overview.__wrapped__() if hasattr(overview, "__wrapped__") else _attention_now())
    security.rescue_watch()  # a push the moment the break-glass account signs in
    from . import notify as _notify
    _notify.start_reminders()  # calendar 30 minutes ahead, the Sunday 9:30 nudge, department nudges (round 5, 28 to 30)

from . import demo_state


def _demo_hooks():
    """Modules that keep their own sample dicts clear them on a reset."""
    from . import calendar as _cal, links as _links, mail as _mail
    demo_state.on_reset(_links._DEMO.clear)
    demo_state.on_reset(_cal._DEMO.clear)
    demo_state.on_reset(church._DEMO_STATE.clear)
    demo_state.on_reset(lambda: (_mail._import_state.clear(), _mail._import_state.update({"running": False})))
    demo_state.on_reset(automator._last_manual.clear)
    demo_state.on_reset(finder._recent_cache.clear)
    demo_state.on_reset(files._search_cache.clear)


_demo_hooks()

auth = Depends(current_user)      # any signed-in person; members are limited to the portal routes by auth._check_path
admin = Depends(require_admin)    # the administrator only
recent = Depends(require_recent_auth)  # typed the password again within five minutes (delete a user, empty a Trash, shut down)


# ----- the audit log: every change, who and when, kept forever (round 2, 23; round 4, 79) -----
def _who_from_cookie(request: Request) -> str:
    tok = request.cookies.get(COOKIE)
    if not tok:
        return "demo" if load().demo else "?"
    try:
        return _auth._serializer().loads(tok, max_age=int(load().web.session_hours) * 3600).get("u", "?")
    except Exception:  # noqa: BLE001 - an expired cookie is still worth a line
        return "?"


@app.middleware("http")
async def _headers_mw(request: Request, call_next):
    """Every answer: never sniffed into another type, and the dashboard is not framed by
    another site (a sibling app could otherwise dress up a click on the real buttons)."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.middleware("http")
async def _origin_mw(request: Request, call_next):
    """A change made with the session cookie must come from this dashboard's own pages
    (round 7 security review: SameSite=Lax still sends the cookie from sibling sites)."""
    if (request.method in ("POST", "PUT", "DELETE", "PATCH") and request.url.path.startswith("/api/")
            and COOKIE in request.cookies and not _auth.origin_ok(request.headers.get("origin"), request.headers.get("host"))):
        return JSONResponse({"error": {"message": "That request came from another site, so it was refused"}}, status_code=403)
    return await call_next(request)


@app.middleware("http")
async def _audit_mw(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if (request.method in ("POST", "PUT", "DELETE", "PATCH") and path.startswith("/api/")
            and not path.startswith(audit.QUIET) and not path.startswith("/api/auth/login") and not path.endswith("/leaving")):
        try:
            audit.record(_who_from_cookie(request), audit.action_of(request.method, path), audit.target_of(path),
                         ok=response.status_code < 400, status=response.status_code,
                         ip=request.client.host if request.client else "")
        except Exception:  # noqa: BLE001 - logging must never break the request
            pass
    return response


@app.exception_handler(HTTPException)
async def _http_exc(_req, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    return JSONResponse({"error": detail}, status_code=exc.status_code)


# ----- the sample server (demo mode only) -------------------------------------
@app.post("/api/demo/reset")
def api_demo_reset(_=Depends(require_admin)):
    """Put the sample back the way it started. Refused on a real server."""
    if not load().demo:
        raise HTTPException(404, {"message": "Not found"})
    return demo_state.reset()


# ----- auth ------------------------------------------------------------------
class Login(BaseModel):
    user: str
    password: str


@app.post("/api/auth/login")
def api_login(body: Login, response: Response, request: Request):
    c = load()
    if not c.demo and not c.web.admin_password_hash:
        raise HTTPException(401, {"setup": True, "message": "No admin password yet. On the server run: sudo arisectl admin set-password"})
    keys = [f"ip:{_ip(request)}"]   # the guessing device waits, never the account: no lockout (round 4, 27)
    if not c.demo and _auth.too_many(keys):
        audit.record(body.user[:64], "auth.login", ok=False, ip=_ip(request), detail="too many wrong passwords: waiting")
        raise HTTPException(429, {"message": "Too many wrong passwords. Wait fifteen minutes, or reset it with Forgot your password?"})
    got = login(body.user, body.password)
    if not c.demo:
        (_auth.clear_failures if got else _auth.note_failure)(keys)
    if not got and c.demo and directory._u((body.user or "").strip().lower()):
        raise HTTPException(401, {"message": "Wrong user or password (or the account is disabled)"})
    if not got:
        if c.demo:  # sample mode: names the sample does not know become the admin, as before
            got = (None, {"user": "demo", "role": "admin", "via": "demo"})
        else:
            time.sleep(0.8)  # slow down guessing
            audit.record(body.user[:64], "auth.login", ok=False, detail="wrong user or password")
            raise HTTPException(401, {"message": "Wrong user or password"})
    tok, who = got
    if who.get("expired"):
        # A temporary password (round 5, 5): right, but the domain asks for their own first. The page asks for
        # a new one and posts old + new to /api/auth/login/new-password; nothing is held on the server meanwhile.
        audit.record(who["user"], "auth.login", ok=False, ip=_ip(request), detail="temporary password: a new one is needed")
        return {"ok": True, "need_new_password": True, "user": who["user"], "rules": directory.password_rules().get("words", [])}
    if tok and not c.demo and twofa.enrolled(who["user"]):
        # Two-step is on for this person: the session token waits behind a code (five minutes, three tries).
        return {"ok": True, "need_code": True, "pending": twofa.pending_token(tok, who["user"]), "user": who["user"]}
    if tok:
        response.set_cookie(COOKIE, tok, httponly=True, samesite="lax", secure=_https(request), max_age=int(c.web.session_hours) * 3600)
    audit.record(who["user"], "auth.login", ip=_ip(request), detail=f"{who.get('via', '')} · {profiles.device_of(request.headers.get('user-agent', ''))}")
    _new_device(who.get("user", ""), request)
    if not c.demo and who.get("via") != "demo":
        files.ensure_home(who["user"])   # Documents, Photos, Videos, Music, Downloads from the first sign-in
    return {"ok": True, "user": who["user"], "role": who["role"], "demo": c.demo}


class LoginCode(BaseModel):
    pending: str
    code: str


@app.post("/api/auth/login/code")
def api_login_code(body: LoginCode, response: Response, request: Request):
    """The second step: the six digits from Microsoft Authenticator."""
    c = load()
    if c.demo:
        return {"ok": True, "demo": True, "user": "demo", "role": "admin"}
    r = twofa.finish(body.pending, body.code)
    if not r.get("ok"):
        time.sleep(0.5)
        audit.record(r.get("user", "?"), "auth.login.code", ok=False, detail=r.get("err", "wrong code"))
        raise HTTPException(401, {"message": r.get("err", "wrong code"), "left": r.get("left", 0), "expired": r.get("expired", False)})
    response.set_cookie(COOKIE, r["token"], httponly=True, samesite="lax", secure=_https(request), max_age=int(c.web.session_hours) * 3600)
    _new_device(r["user"], request)
    return {"ok": True, "user": r["user"]}


def _new_device(user: str, request: Request):
    """Round 7, 70: a sign-in from a device never seen for this person emails them and tells Bradly."""
    if not user or user == "demo" or load().demo:
        return
    try:
        from . import accounts
        accounts.on_signin(user, request.headers.get("user-agent", ""), _ip(request))
    except Exception:  # noqa: BLE001 - a notice never blocks a sign-in
        pass


class Reauth(BaseModel):
    password: str


@app.post("/api/auth/reauth")
def api_reauth(body: Reauth, request: Request, response: Response, who=auth):
    """The dangerous clicks ask for the password again; a yes is remembered five minutes (the 'ra' stamp in the cookie)."""
    c = load()
    if c.demo:
        return {"ok": True, "demo": True, "until": 300}
    keys = ["reauth:" + who["user"].lower()]
    if _auth.too_many(keys):
        raise HTTPException(429, {"message": "Too many wrong passwords. Wait fifteen minutes"})
    if not check_password_for(who["user"], body.password):
        _auth.note_failure(keys)
        time.sleep(0.8)
        raise HTTPException(401, {"message": "That is not your password"})
    _auth.clear_failures(keys)
    tok = reauth_token(request)
    if not tok:
        raise HTTPException(401, {"message": "Sign in again"})
    response.set_cookie(COOKIE, tok, httponly=True, samesite="lax", secure=_https(request), max_age=int(c.web.session_hours) * 3600)
    return {"ok": True, "until": 300}


@app.post("/api/auth/logout")
def api_logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _https(request: Request) -> bool:
    """The session cookie is Secure whenever the page came over HTTPS (Caddy, whose
    X-Forwarded-Proto uvicorn believes from 127.0.0.1 only). Plain http on :4147 on the
    church network still works, without the flag, as it must before Caddy exists."""
    return request.url.scheme == "https"


class NewPassword(BaseModel):
    user: str
    old: str
    new: str


@app.post("/api/auth/login/new-password")
def api_login_new_password(body: NewPassword, response: Response, request: Request):
    """The temporary password is replaced by their own, then the sign-in carries on (two-step if it is on).
    The same change a Mac's login window asks for; the domain's rules apply."""
    c = load()
    user = (body.user or "").strip().lower()
    keys = [f"ip:{_ip(request)}"]   # the device waits, never the account (round 4, 27)
    if not c.demo and _auth.too_many(keys):
        raise HTTPException(429, {"message": "Too many wrong passwords. Wait fifteen minutes"})
    r = directory.change_expired(user, body.old, body.new)
    if not r.get("ok"):
        if not c.demo:
            _auth.note_failure(keys)
        time.sleep(0.5)
        audit.record(user[:64], "auth.login.newpassword", ok=False, ip=_ip(request), detail=r.get("err", "")[:120])
        return {"ok": False, "err": r.get("err", "the domain refused that password"), "rules": directory.password_rules().get("words", [])}
    got = login(user, body.new)
    if not got or not got[0]:
        return {"ok": False, "err": "The new password is set; sign in with it"}
    tok, who = got
    audit.record(user, "auth.login.newpassword", ip=_ip(request), detail=f"temporary password replaced · {profiles.device_of(request.headers.get('user-agent', ''))}")
    if not c.demo and twofa.enrolled(user):
        return {"ok": True, "need_code": True, "pending": twofa.pending_token(tok, user), "user": user}
    response.set_cookie(COOKIE, tok, httponly=True, samesite="lax", secure=_https(request), max_age=int(c.web.session_hours) * 3600)
    if not c.demo:
        files.ensure_home(user)
    return {"ok": True, "user": user, "role": who["role"], "demo": c.demo}


class Forgot(BaseModel):
    user: str


def _base_url(request: Request) -> str:
    """Never the request's own Host header: anyone could post /api/auth/forgot with a forged
    one and get a real email whose link carries a valid token to their own site. The link is
    the dashboard's fixed name behind Caddy (or public_url, if it is ever set)."""
    pub = (load().web.get("public_url") or "").strip()
    if pub:
        return pub.rstrip("/")
    from . import macs
    return f"https://{macs.server_names()['host']}"


@app.post("/api/auth/forgot")
def api_forgot(body: Forgot, request: Request):
    """A reset link to the personal email on file (round 5, 6). The answer never says whether the account exists."""
    return profiles.forgot(body.user, _base_url(request), _ip(request))


@app.get("/api/auth/reset/check")
def api_reset_check(t: str = ""):
    return profiles.check_reset(t)


class Reset(BaseModel):
    token: str
    new: str


@app.post("/api/auth/reset")
def api_reset(body: Reset, request: Request):
    return profiles.finish_reset(body.token, body.new, _ip(request))


# ----- profiles, settings that follow the account, sign-ins (round 5) ----------------
class ProfileEdit(BaseModel):
    personal_email: str | None = None
    mobile: str | None = None
    birthday: str | None = None
    title: str | None = None
    departments: list[str] | None = None


@app.get("/api/me/profile")
def api_me_profile(who=auth):
    return profiles.profile(who["user"], who)


@app.put("/api/me/profile")
def api_me_profile_edit(body: ProfileEdit, who=auth):
    return profiles.update(who["user"], body.model_dump(exclude_none=True), who)


@app.get("/api/me/signins")
def api_me_signins(who=auth):
    return profiles.signins(who["user"])


@app.get("/api/me/prefs")
def api_me_prefs(who=auth):
    return profiles.prefs(who["user"])


class Prefs(BaseModel):
    prefs: dict


@app.put("/api/me/prefs")
def api_me_prefs_save(body: Prefs, who=auth):
    return profiles.save_prefs(who["user"], body.prefs)


@app.get("/api/people")
def api_people(who=auth):
    """Staff and admins only (round 5, 10); members get a refusal, from here, not from the page."""
    r = profiles.people(who)
    if not r.get("ok"):
        raise HTTPException(403, {"message": r["err"]})
    return r


@app.get("/api/auth/me")
def api_me(request: Request):
    try:
        who = dict(current_user(request))
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    who["groups"] = directory.user_groups(who["user"]) if who["user"] != "demo" else ["Domain Admins"]
    who["roots"] = files.roots(who)
    who["links_days"] = load().links.days
    who["claude"] = who["user"] in church.claude_users()  # Claude on the box is Bradly's (round 4, 44)
    if who["user"] != "demo":   # the title and the full name (round 5, 7): faces, the greeting, mail
        p = profiles.profile(who["user"], who)
        who.update(display=p.get("display", who["user"]), name=p.get("name", who["user"]), title=p.get("title", ""),
                   greeting=profiles.greeting_name(who["user"], p.get("display", "")), staff=profiles.is_staff(who))
    who["staff_access"] = staff_access()   # "none": a staff or member sign-in gets the "your files are on your Mac" page
    return who


class PasswordChange(BaseModel):
    old: str
    new: str


@app.post("/api/me/password")
def api_me_password(body: PasswordChange, request: Request, response: Response, who=auth):
    """Anyone changes their own directory password; the local admin password is arisectl's."""
    c = load()
    if len(body.new) < 8:
        return {"ok": False, "err": "at least 8 characters"}
    if c.demo:
        if not directory._u(who["user"]):
            return {"ok": True, "demo": True, "out": "(sample) the sample admin has no directory password"}
        if not directory.authenticate(who["user"], body.old):
            return {"ok": False, "err": "current password is wrong"}
        return directory.set_password(who["user"], body.new)
    if who["user"] == c.web.admin_user and not directory.authenticate(who["user"], body.old):
        if c.web.admin_password_hash and __import__("arise_server.auth", fromlist=["verify_password"]).verify_password(body.old, c.web.admin_password_hash):
            return {"ok": False, "err": "That is the local dashboard password: change it on the server with sudo arisectl admin set-password"}
    keys = ["reauth:" + who["user"].lower()]
    if _auth.too_many(keys):
        return {"ok": False, "err": "too many wrong passwords: wait fifteen minutes"}
    if not directory.authenticate(who["user"], body.old):
        _auth.note_failure(keys)
        time.sleep(0.8)
        return {"ok": False, "err": "current password is wrong"}
    r = directory.set_password(who["user"], body.new)
    if r.get("ok"):
        # every other device is signed out (set_password moved the mark); this one carries on
        tok = _auth.fresh_token(request)
        if tok:
            response.set_cookie(COOKIE, tok, httponly=True, samesite="lax", secure=_https(request), max_age=int(c.web.session_hours) * 3600)
    return r


# ----- two-step sign-in, optional per person (round 2, 11; Oct 28) -----------------
class Code(BaseModel):
    code: str = ""
    password: str = ""


@app.get("/api/me/2fa")
def api_2fa_status(who=auth):
    return twofa.status(who["user"])


@app.post("/api/me/2fa/setup")
def api_2fa_setup(who=auth):
    """A fresh secret, shown once as a QR and as text. Not on until a code confirms it."""
    return twofa.setup(who["user"])


@app.post("/api/me/2fa/enable")
def api_2fa_enable(body: Code, who=auth):
    return twofa.enable(who["user"], body.code)


@app.post("/api/me/2fa/disable")
def api_2fa_disable(body: Code, who=auth):
    return twofa.disable(who["user"], body.password, body.code)


@app.get("/api/directory/2fa")
def api_dir_2fa(_=admin):
    """Who has two-step on. Names only."""
    return {"users": twofa.who_has(), "demo": load().demo}
@app.get("/api/me/password/rules")
def api_password_rules(_=auth):
    """The domain's password rules in plain words, read from the domain itself (not invented)."""
    return directory.password_rules()


# ----- overview + stats --------------------------------------------------------
@app.get("/api/overview")
def overview(_=admin):
    c = load()
    st = metrics.static_info()
    svc = services.list_services()
    bad = [s["unit"] for s in svc["services"] if s["active"] not in ("active", "activating")]
    auto = automator.overview()
    hist = backups.history(limit=20)
    last_backup = hist["rows"][0] if hist["rows"] else None
    failed_backups = [r for r in hist["rows"][:10] if not r.get("ok")]
    n = nas.status()
    d = directory.status()
    a = apps.list_apps()
    return {
        "demo": c.demo, "version": VERSION, "codename": CODENAME, "profile": c.system.profile,
        "hostname": c.system.hostname, "machine": st, "web_uptime": int(time.time() - _started),
        "realm": d.get("realm"), "directory_ok": bool(d.get("ldap_ok")), "directory_demo": d.get("demo", False),
        "counts": {"users": d.get("users", 0), "groups": d.get("groups", 0), "computers": d.get("computers", 0),
                   "shares": len(shares.list_shares()["shares"]), "apps": len(a["apps"]), "apps_running": sum(1 for x in a["apps"] if x["status"] == "running"),
                   "backups": len(backups.jobs()["jobs"])},
        "services_bad": bad,
        "automator": {k: auto.get(k) for k in ("last_run", "last_ok", "last_summary", "next_run", "quota_today", "quota_daily", "token_ok", "token_days_left", "holds")},
        "backup": {"last": last_backup, "failed_recent": len(failed_backups), "running": hist["running"]},
        "nas": {"mounted": n.get("mounted"), "free": n.get("free"), "total": n.get("total"), "reachable": n.get("reachable", n.get("mounted"))},
        "attention": _attention(c, bad, auto, failed_backups, n, d),
    }


def _attention_now() -> list[dict]:
    """The Needs You list, computed without a request (for the push watcher)."""
    c = load()
    svc = services.list_services()
    bad = [s["unit"] for s in svc["services"] if s["active"] not in ("active", "activating")]
    hist = backups.history(limit=20)
    return _attention(c, bad, automator.overview(), [r for r in hist["rows"][:10] if not r.get("ok")], nas.status(), directory.status())


def _attention(c, bad, auto, failed_backups, n, d) -> list[dict]:
    items = []
    if not c.found:
        items.append({"level": "warn", "text": f"No config at {c.path}: running on defaults with sample data. Run the installer or `arisectl doctor`."})
    if not c.web.admin_password_hash and not c.demo:
        items.append({"level": "bad", "text": "No admin password set. Run: sudo arisectl admin set-password"})
    if os.path.exists("/etc/arise/staging"):
        items.append({"level": "warn", "text": "STAGING: this box is not at the church yet. The domain listens on this box only and no network scan runs. At the church: sudo bash /opt/arise/installer/install.sh (without --staging)."})
    for u in bad:
        items.append({"level": "bad", "text": f"{u} is not running."})
    if auto.get("token_ok") is False:
        items.append({"level": "bad", "text": auto.get("token_note") or "token.json missing."})
    elif auto.get("token_days_left") is not None and auto["token_days_left"] <= 2:
        items.append({"level": "warn", "text": f"YouTube sign-in token expires in about {auto['token_days_left']} day(s). {auto.get('token_note') or ''}".strip()})
    if auto.get("last_ok") is False:
        items.append({"level": "bad", "text": f"Last automator run had failures: {auto.get('last_summary')}"})
    for r in failed_backups[:3]:
        items.append({"level": "bad", "text": f"Backup '{r.get('name', r.get('job'))}' failed {str(r.get('started', ''))[:16]}: {str(r.get('error') or '')[:140]}"})
    if n.get("enabled") and n.get("mounted") is False:
        items.append({"level": "warn", "text": f"Synology not mounted at {n.get('mount')}. Backups will fail until it is: `arisectl nas mount`."})
    if d.get("enabled", True) and d.get("error"):
        items.append({"level": "bad", "text": f"Directory: {d['error'][:160]}"})
    # The church Macs: watch mode, a full disk, a Mac silent three days, no Full Disk Access (round 7).
    try:
        from . import macs as _macs
        items.extend(_macs.attention())
    except Exception:  # noqa: BLE001
        pass
    # Disks at 75 % say so (Bradly, Oct 28); the sample box has room, so the preview shows none.
    if not c.demo:
        try:
            items.extend(storage.disk_alerts())
        except Exception:  # noqa: BLE001
            pass
    # Round 7: a missed backup night (64), a church Mac silent three days (82), a disk to replace or
    # a hot CPU (137/138). The hourly timer posts each to Discord #alerts once; here they stay while true.
    try:
        from . import upkeep
        for it in upkeep.attention():
            items.append({"level": it["level"], "text": it["text"] + (f" ({it['fix']})" if it.get("fix") else "")})
    except Exception:  # noqa: BLE001
        pass
    return items


@app.get("/api/stats/stream")
async def stats_stream(_=admin):
    return StreamingResponse(metrics.sse(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/stats/history")
def stats_history(_=admin):
    return {"history": metrics.history(), "latest": metrics.latest(), "machine": metrics.static_info()}


# ----- services + logs -------------------------------------------------------
@app.get("/api/services")
def api_services(_=admin):
    return services.list_services()


@app.post("/api/services/{unit}/{action}")
def api_service_act(unit: str, action: str, _=admin):
    if unit.startswith("samba-ad-dc") and action != "status":
        svc = church.in_service_now()
        if svc:
            return {"ok": False, "err": f"Not during {svc['name']}: the domain stays up until about {svc['ends_at']}."}
    return services.act(unit, action)


@app.get("/api/logs/sources")
def api_log_sources(_=admin):
    return services.log_sources()


@app.get("/api/logs/file/{name}")
def api_log_file(name: str, lines: int = 300, _=admin):
    return services.log_file(name, lines)


@app.get("/api/logs/{unit}")
def api_logs(unit: str, lines: int = 200, _=admin):
    return services.journal(unit, lines)


# ----- v0.8 Exodus: the system apps (Software Update, Activity Monitor, Automations, Storage, the monitor) ----
class QueueBody(BaseModel):
    packages: Optional[list[str]] = None
    apps: Optional[list[str]] = None
    reboot: Optional[bool] = None


class ApplyBody(BaseModel):
    confirm: str = ""
    no_snapshot: bool = False


@app.get("/api/updates")
def api_updates_status(_=admin):
    return updates.status()


@app.post("/api/updates/refresh")
def api_updates_refresh(_=admin):
    r = updates.refresh()
    r["status"] = updates.status()
    return r


@app.post("/api/updates/check-apps")
def api_updates_check_apps(_=admin):
    return updates.check_apps()


@app.post("/api/updates/queue")
def api_updates_queue(body: QueueBody, who=admin):
    return updates.set_queue(body.packages, body.apps, body.reboot, who.get("user", ""))


@app.post("/api/updates/apply")
def api_updates_apply(body: ApplyBody, _=admin):
    if body.confirm != "install":
        return {"ok": False, "err": "type install to confirm"}
    return updates.apply(no_snapshot=body.no_snapshot, log=lambda *_a: None)


@app.get("/api/activity")
def api_activity(_=admin):
    return activity.snapshot()


class KillBody(BaseModel):
    pid: int
    confirm: str = ""


@app.post("/api/activity/kill")
def api_activity_kill(body: KillBody, _=admin):
    return activity.kill(body.pid, body.confirm)


@app.get("/api/automations")
def api_automations(_=admin):
    return automations.list_automations()


class TimerBody(BaseModel):
    confirm: str = ""


@app.post("/api/automations/{timer}/{action}")
def api_automations_act(timer: str, action: str, body: TimerBody, _=admin):
    if action not in ("pause", "resume"):
        return {"ok": False, "err": "action must be pause or resume"}
    return automations.pause(timer, action == "resume", body.confirm)


@app.get("/api/storage")
def api_storage(_=admin):
    r = storage.status()
    for m in r.get("mounts", []):
        m["total_h"], m["used_h"], m["free_h"] = human_bytes(m.get("total")), human_bytes(m.get("used")), human_bytes(m.get("free"))
    return r


@app.post("/api/storage/scan")
def api_storage_scan(_=admin):
    return storage.scan()


@app.get("/api/monitor")
def api_monitor(_=admin):
    return monitor.status()


class MonitorBody(BaseModel):
    on: bool = True


@app.post("/api/monitor/power")
def api_monitor_power(body: MonitorBody, _=admin):
    return monitor.power(body.on)


# ----- directory ---------------------------------------------------------------
class NewUser(BaseModel):
    name: str
    password: str
    display: str = ""
    groups: list[str] = []
    title: str = ""
    temporary: bool = True     # round 5, 5: they choose their own at the first login, on a Mac or here


class Password(BaseModel):
    password: str
    temporary: bool = True


class Confirm(BaseModel):
    confirm: str = ""


class NewGroup(BaseModel):
    name: str
    description: str = ""


class Member(BaseModel):
    user: str


@app.get("/api/directory/status")
def dir_status(_=admin):
    return directory.status()


@app.get("/api/directory/users")
def dir_users(_=admin):
    r = directory.list_users()
    profiles.decorate(r.get("users", []))
    return r


@app.post("/api/directory/users")
def dir_user_add(body: NewUser, who=admin):
    if body.title:
        _good, errs = profiles.clean({"title": body.title}, ("title",))
        if errs:
            return {"ok": False, "err": "; ".join(errs)}
    from . import accounts
    name = (body.name or "").strip()
    asked = name
    if directory._ok_name(name):
        name = accounts.unique_name(name, accounts.taken_names())   # round 7, 12: john.smith2, without asking
    r = directory.add_user(name, body.password, body.display, body.groups, temporary=body.temporary)
    if (r.get("ok") or r.get("created")) and body.title:
        profiles.update(name, {"title": body.title}, who)
    if r.get("ok") or r.get("created"):
        r["must_change"] = body.temporary
        r["user"] = name
        if name != asked:
            r["renamed"] = f"{asked} was taken, so the new account is {name}"
        try:
            r["after"] = accounts.made(name, who["user"], body.display)
        except Exception as e:  # noqa: BLE001 - the account is made either way
            r["after"] = {"err": str(e)[:200]}
    return r


@app.post("/api/directory/users/{name}/reset-password")
def dir_user_pw(name: str, body: Password, who=admin):
    return profiles.admin_reset(name, body.password, body.temporary, who["user"])


@app.get("/api/directory/users/{name}/profile")
def dir_user_profile(name: str, who=admin):
    return profiles.profile(name, who)


@app.put("/api/directory/users/{name}/profile")
def dir_user_profile_edit(name: str, body: ProfileEdit, who=admin):
    return profiles.update(name, body.model_dump(exclude_none=True), who)


class PeopleImport(BaseModel):
    csv: str
    apply: bool = False


@app.post("/api/directory/import")
def dir_import(body: PeopleImport, who=admin):
    """The day-one people list (round 5, 8): checked first; with apply, the accounts are made with
    temporary passwords, which come back in this answer only (never logged, never kept)."""
    return profiles.import_people(body.csv, body.apply, who["user"])


@app.post("/api/directory/users/{name}/enable")
def dir_user_enable(name: str, who=admin):
    r = directory.enable_user(name, True)
    if r.get("ok"):
        from . import accounts
        accounts.switched(name, True, who["user"])   # round 7, 86
    return r


@app.post("/api/directory/users/{name}/disable")
def dir_user_disable(name: str, who=admin):
    if name.lower() == str(who.get("user", "")).lower():
        return {"ok": False, "err": "You cannot disable the account you are signed in with"}
    r = directory.enable_user(name, False)
    if r.get("ok"):
        from . import accounts
        accounts.switched(name, False, who["user"])   # round 7, 86
    return r


class Rename(BaseModel):
    new: str
    confirm: str


@app.post("/api/directory/users/{name}/rename")
def dir_user_rename(name: str, body: Rename, who=recent):
    """Round 7, 13: a married name. The account keeps its identity (groups, files, permissions);
    the login, the home folder's name and every record follow; the old address stays an alias."""
    if who.get("role") != "admin":
        raise HTTPException(403, {"message": "Administrator only"})
    from . import accounts
    return accounts.rename(name, body.new, who["user"], body.confirm)


class Photo(BaseModel):
    data: str          # base64 of a JPEG or PNG


@app.post("/api/directory/users/{name}/photo")
def dir_user_photo(name: str, body: Photo, who=admin):
    """Round 7, 20: the photo the person chose, added by an admin (staff don't use the dashboard)."""
    import base64 as _b64
    from . import accounts
    try:
        raw = _b64.b64decode((body.data or "").split(",", 1)[-1], validate=True)
    except ValueError:
        return {"ok": False, "err": "that is not a photo file"}
    return accounts.photo_save(name, raw, who["user"])


@app.get("/api/photos/{name}")
def api_photo(name: str, request: Request):
    """The photo on the faces: to the closet monitor itself or a signed-in person, never the network."""
    from . import accounts
    host = (request.client.host if request.client else "") or ""
    if not (host in ("127.0.0.1", "::1", "localhost") or _who_from_cookie(request) not in ("", "?", None)):
        raise HTTPException(404, {"message": "Not found"})
    p = accounts.photo_path(name) if directory._ok_name(name) else None
    if not p:
        raise HTTPException(404, {"message": "no photo"})
    return FileResponse(p, headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


class BreakGlass(BaseModel):
    reason: str
    confirm: str


@app.get("/api/pastors/breakglass")
def api_breakglass_status(who=admin):
    from . import accounts
    return {**accounts.breakglass_status(who["user"]), "allowed": (who["user"] == accounts.owner()) if accounts.owner() else load().demo,
            "hours": float(load().people.breakglass_hours or 2)}


@app.post("/api/pastors/breakglass")
def api_breakglass(body: BreakGlass, who=recent):
    """Round 7, 69: Bradly only, a reason the pastors read, two hours, both pastors told at once."""
    from . import accounts
    return accounts.breakglass_open(who, body.reason, body.confirm)


@app.delete("/api/pastors/breakglass")
def api_breakglass_close(who=admin):
    from . import accounts
    return accounts.breakglass_close(who["user"], who["user"])


@app.get("/api/directory/unused")
def api_unused(_=admin):
    """Round 7, 17: accounts with no sign-in for 90 days (the daily check names each in Discord once)."""
    from . import accounts
    return accounts.inactive(dry_run=True)


@app.delete("/api/directory/users/{name}")
def dir_user_del(name: str, body: Confirm, who=recent):
    if who.get("role") != "admin":
        raise HTTPException(403, {"message": "Administrator only"})
    if name.lower() == str(who.get("user", "")).lower():
        return {"ok": False, "err": "You cannot delete the account you are signed in with"}
    return directory.delete_user(name, body.confirm)


@app.get("/api/directory/groups")
def dir_groups(_=admin):
    return directory.list_groups()


@app.post("/api/directory/groups")
def dir_group_add(body: NewGroup, _=admin):
    return directory.add_group(body.name, body.description)


@app.post("/api/directory/groups/{group}/members")
def dir_group_member(group: str, body: Member, _=admin):
    return directory.add_member(group, body.user)


@app.delete("/api/directory/groups/{group}/members/{user}")
def dir_group_member_del(group: str, user: str, _=admin):
    return directory.remove_member(group, user)


@app.get("/api/directory/computers")
def dir_computers(_=admin):
    return directory.list_computers()


# ----- shares ------------------------------------------------------------------
class NewShare(BaseModel):
    name: str
    path: str
    comment: str = ""
    group: str = "Domain Users"
    mac: bool = True


@app.get("/api/shares")
def api_shares(_=admin):
    r = shares.list_shares()
    for s in r["shares"]:
        s["used_h"] = human_bytes(s.get("used"))
    return r


@app.post("/api/shares")
def api_share_add(body: NewShare, _=admin):
    return shares.add_share(body.name, body.path, body.comment, body.group, body.mac)


@app.delete("/api/shares/{name}")
def api_share_del(name: str, body: Confirm, _=admin):
    return shares.remove_share(name, body.confirm)


# ----- backups -----------------------------------------------------------------
@app.get("/api/backups/jobs")
def bk_jobs(_=admin):
    return backups.jobs()


@app.get("/api/backups/history")
def bk_history(limit: int = 200, _=admin):
    return backups.history(limit)


@app.get("/api/backups/snapshots")
def bk_snapshots(limit: int = 100, _=admin):
    return backups.snapshots(limit)


@app.get("/api/backups/offsite")
def bk_offsite(_=admin):
    """Round 7, 53/54: tonight's off-site plan (Arise-Home) and its last run."""
    from . import sharing
    plan = backups.offsite_plan(sharing.backup_targets(), getattr(load().backups, "offsite", "arise-home"))
    last = next((r for r in backups.history(limit=400)["rows"] if r.get("job") == "offsite"), None)
    return {"demo": load().demo, "plan": plan, "last": last, "skip_tags": list(getattr(load().backups, "offsite_skip_tags", ["recordings"]) or [])}


# ----- round 7: upkeep, Discord, mail forwarding ------------------------------------
@app.get("/api/upkeep/changes")
def api_upkeep_changes(limit: int = 100, _=admin):
    """The change record in About (round 7, 140): what changed, by Bradly, Kristina or Claude."""
    from . import upkeep
    return upkeep.changes(limit=max(1, min(int(limit or 100), 500)))


@app.get("/api/upkeep/january")
def api_upkeep_january(_=admin):
    """The January clean-up report (round 7, 139): the latest one kept, or this year's as of now."""
    from . import upkeep
    from .util import read_json
    from datetime import datetime
    y = datetime.now().year
    for yr in (y, y - 1):
        rep = read_json(load().state_dir / f"january-{yr}.json", default=None) if not load().demo else None
        if rep:
            return {"demo": False, "report": rep, "kept": True}
    return {"demo": load().demo, "report": upkeep.january_report(), "kept": False}


@app.get("/api/upkeep/health")
def api_upkeep_health(_=admin):
    """Disks (SMART) and the CPU's heat (round 7, 137/138)."""
    from . import upkeep, metrics
    try:
        cpu = metrics._temps()
    except Exception:  # noqa: BLE001
        cpu = None
    return {"demo": load().demo, "disks": upkeep.disks_health(), "cpu_temp": cpu, "cpu_hot_c": upkeep.cfg_upkeep()["cpu_hot_c"],
            "items": upkeep.health(fresh=True)}


@app.get("/api/help/contacts")
def api_help_contacts(_=auth):
    """Who to call and where staff ask for help (round 7, 118, 141): names and the IT portal, no numbers."""
    from . import upkeep
    u = upkeep.cfg_upkeep()
    return {"call": u["call"], "it_portal": upkeep.it_portal()}


@app.get("/api/discord")
def api_discord(_=admin):
    """Which of the four channels are set: names only, never the webhook addresses."""
    from . import discord
    return discord.status()


class DiscordTest(BaseModel):
    channel: str


@app.post("/api/discord/test")
def api_discord_test(body: DiscordTest, _=admin):
    from . import discord
    return discord.test(body.channel)


@app.get("/api/mail/forwarding")
def api_mail_forwarding(_=admin):
    """Staff addresses, forwarding only (round 7, 155): who forwards where (masked), and the log."""
    from . import mailfwd
    return {**mailfwd.status(), "log": mailfwd.log(limit=50)}


@app.get("/api/mail/forwarding/export/{name}")
def api_mail_forwarding_export(name: str, who=admin):
    """A leaver's mail: their alias and forwarding log, as CSV text (round 5, 38)."""
    from . import mailfwd
    if not directory._ok_name(name):
        return {"ok": False, "err": "not a user name"}
    audit.record(who.get("user", "?"), "mail.forwarding.export", name)
    return mailfwd.export(name)


@app.get("/api/backups/repo")
def bk_repo(_=admin):
    return backups.repo()


@app.post("/api/backups/run/{job}")
def bk_run(job: str, _=admin):
    return backups.run_job(job)


@app.post("/api/backups/mirror")
def bk_mirror(_=admin):
    return backups.mirror_github()


@app.post("/api/backups/check")
def bk_check(_=admin):
    return backups.check()


# ----- automator ---------------------------------------------------------------
@app.get("/api/automator")
def auto_overview(_=admin):
    return automator.overview()


@app.get("/api/automator/reports")
def auto_reports(_=admin):
    return {"reports": automator.overview().get("reports", [])}


@app.get("/api/automator/reports/{name}")
def auto_report(name: str, _=admin):
    return automator.report(name)


@app.get("/api/automator/worklist")
def auto_worklist(_=admin):
    return automator.worklist()


@app.get("/api/automator/holds")
def auto_holds(_=admin):
    return automator.holds()


@app.get("/api/automator/cutover")
def api_automator_cutover(_=admin):
    """The handoff's section 9: what must be true before Bradly hands the job to this server."""
    return automator.cutover()


@app.get("/api/automator/quota")
def auto_quota(_=admin):
    return automator.quota()


@app.post("/api/automator/run")
def auto_run(_=admin):
    return automator.start("run")


@app.post("/api/automator/preview")
def auto_preview(_=admin):
    return automator.start("preview")


# The channel side of the Automator app: every video, its thumbnails and links, and a
# search of the transcripts and the toolkit's files (server/arise_server/channel.py).
@app.get("/api/automator/channel")
def auto_channel(_=admin):
    return channel.status()


@app.get("/api/automator/videos")
def auto_videos(q: str = "", kind: str = "", has: str = "", page: int = 1, _=admin):
    return channel.videos(q, kind, has, page)


@app.get("/api/automator/videos/{vid}")
def auto_video(vid: str, who=admin):
    return channel.video(vid, who)


@app.get("/api/automator/videos/{vid}/transcript")
def auto_video_transcript(vid: str, source: str = "", who=admin):
    return channel.transcript(vid, source, who)


@app.get("/api/automator/search")
def auto_search(q: str = "", kind: str = "transcript", history: bool = False, private: bool = False, who=admin):
    return channel.search(q, kind, history, private, who)


@app.get("/api/automator/archive/doc")
def auto_archive_doc(repo: str, path: str, start: int | None = None, who=admin):
    return channel.document(repo, path, start, who)


# The song list (song_bank.json, read-only) and the lyrics Bradly adds (server/arise_server/songs.py).
@app.get("/api/songs")
def api_songs(q: str = "", has: str = "", _=admin):
    return songs.listing(q, has)


@app.get("/api/songs/{key}")
def api_song(key: str, _=admin):
    return songs.song(key)


class Lyrics(BaseModel):
    text: str
    source: str = "pasted"


@app.put("/api/songs/{key}/lyrics")
def api_song_lyrics(key: str, body: Lyrics, who=admin):
    return songs.save(key, body.text, who["user"], source=body.source)


class LyricsRemove(BaseModel):
    confirm: str = ""


@app.delete("/api/songs/{key}/lyrics")
def api_song_lyrics_remove(key: str, body: LyricsRemove, who=admin):
    """Moved to .removed/, never deleted; the song's title typed to confirm."""
    return songs.remove(key, body.confirm, who["user"])


class LyricsFile(BaseModel):
    name: str
    text: str


class LyricsImport(BaseModel):
    files: list[LyricsFile]


@app.post("/api/songs/import")
def api_songs_import(body: LyricsImport, who=admin):
    return songs.import_files([f.model_dump() for f in body.files], who["user"])


@app.get("/api/automator/archive/file")
def auto_archive_file(repo: str, path: str, who=admin):
    """A thumbnail or other image from the archive, read-only."""
    f, ctype, err = channel.image(repo, path, who)
    if not f:
        raise HTTPException(404, {"message": err})
    return FileResponse(f, media_type=ctype, headers={"Cache-Control": "private, max-age=86400"})


# ----- apps --------------------------------------------------------------------
class Deploy(BaseModel):
    template: str
    name: Optional[str] = None
    env: dict = {}


@app.get("/api/apps")
def api_apps(_=admin):
    r = apps.list_apps()
    for a in r["apps"]:
        a["mem_h"] = human_bytes(a.get("mem"))
    return r


@app.get("/api/apps/templates")
def api_templates(_=admin):
    return apps.templates()


@app.get("/api/apps/catalog")
def api_catalog(_=admin):
    return apps.catalog()


@app.get("/api/apps/theme/{name}")
def api_app_theme(name: str, _=admin):
    return apps.theme_for(name)


# Members may ask where Notes (Trilium) and Photos (Immich) answer; nothing else about apps.
_auth.MEMBER_OK = tuple(_auth.MEMBER_OK) + ("/api/apps/open/",)


@app.get("/api/apps/open/{name}")
def api_app_open(name: str, _=auth):
    if name not in ("trilium", "immich"):
        return {"ok": False, "err": "only the Notes and Photos apps open this way"}
    return apps.open_url(name)


@app.post("/api/apps/deploy")
def api_deploy(body: Deploy, _=admin):
    return apps.deploy(body.template, body.name, body.env)


class AutostartBody(BaseModel):
    on: bool = True


@app.post("/api/apps/{name}/autostart")
def api_app_autostart(name: str, body: AutostartBody, _=admin):
    return apps.set_autostart(name, body.on)


@app.post("/api/apps/{name}/{action}")
def api_app_act(name: str, action: str, body: Confirm | None = None, _=admin):
    return apps.act(name, action, (body.confirm if body else ""))


@app.get("/api/apps/{name}/logs")
def api_app_logs(name: str, lines: int = 200, _=admin):
    return apps.logs(name, lines)


# ----- nas + settings ----------------------------------------------------------
@app.get("/api/nas")
def api_nas(_=admin):
    r = nas.status()
    for k in ("total", "used", "free"):
        r[k + "_h"] = human_bytes(r.get(k))
    return r


@app.post("/api/nas/mount")
def api_nas_mount(_=admin):
    return nas.mount()


@app.post("/api/nas/unmount")
def api_nas_unmount(_=admin):
    return nas.unmount()


@app.get("/api/settings")
def api_settings(_=admin):
    return load().public()


@app.get("/api/health")
def api_health():
    return {"ok": True, "version": VERSION, "demo": load().demo}



# ----- v0.2: campuses, remote access, bible, sermons, files, system, terminal ----
@app.get("/api/sites")
def api_sites(_=auth):
    return sites.status(directory.list_computers()["computers"])


@app.get("/api/remote")
def api_remote(_=admin):
    return remote.overview()


class PeerName(BaseModel):
    name: str


@app.post("/api/remote/wireguard/peers")
def api_remote_peer(body: PeerName, _=admin):
    return remote.add_wireguard_peer(body.name)


@app.get("/api/bible")
def api_bible(ref: str = "", translation: str = "web", _=auth):
    return bible.lookup(ref, translation)


@app.get("/api/bible/translations")
def api_bible_translations(_=auth):
    return {"translations": [{"id": i, "name": n} for i, n in bible.TRANSLATIONS]}


@app.get("/api/sermons")
def api_sermons(limit: int = 60, _=auth):
    return sermons.videos(limit)


@app.get("/api/files/roots")
def api_files_roots(who=auth):
    return {"roots": files.roots(who)}


@app.get("/api/files/list")
def api_files_list(root: str = "data", path: str = "/", who=auth):
    return files.listing(root, path, who)


@app.get("/api/files/download")
def api_files_download(root: str, path: str, who=auth):
    p = files.file_path(root, path, who)
    if not p:
        raise HTTPException(404, {"message": "no such file"})
    return FileResponse(p, filename=os.path.basename(p), headers={"X-Content-Type-Options": "nosniff"})


@app.get("/api/files/view")
def api_files_view(root: str, path: str, who=auth):
    """Inline (for Quick Look); download sets an attachment header, this does not.
    Never as a page: see files.view_headers."""
    p = files.file_path(root, path, who)
    if not p:
        raise HTTPException(404, {"message": "no such file"})
    media, headers = files.view_headers(os.path.basename(p))
    return FileResponse(p, media_type=media, headers=headers)


class NewFolder(BaseModel):
    root: str = "data"
    path: str = "/"
    name: str


@app.post("/api/files/mkdir")
def api_files_mkdir(body: NewFolder, who=auth):
    return files.make_folder(body.root, body.path, body.name, who)


@app.get("/api/search")
def api_search(q: str = "", who=auth):
    out = files.search(q, who=who)
    out["transcripts"] = files.search_transcripts(q)
    ql = q.strip().lower()
    if who.get("role") == "admin":
        out["users"] = [u for u in directory.list_users()["users"] if ql and (ql in u["name"].lower() or ql in (u.get("display") or "").lower())][:8]
        out["computers"] = [c for c in directory.list_computers()["computers"] if ql and ql in c["name"].lower()][:8]
    else:
        out["users"], out["computers"] = [], []
    return out


# ---- round 5: sharing, quotas, folders, backup targets (server/arise_server/sharing.py) ----
class ShareWith(BaseModel):
    root: str = "home"
    path: str
    to: list[str]
    perm: str = "read"


@app.get("/api/files/shared")
def api_files_shared(who=auth):
    """Shared with me, and what I share (round 5, row 19)."""
    return sharing.listing(who)


@app.post("/api/files/share")
def api_files_share(body: ShareWith, who=auth):
    """Share a file or folder with a person or a group: an ACL on the server, a link in their [shared] share."""
    return sharing.share_with(body.root, body.path, body.to, body.perm, who)


@app.delete("/api/files/share/{sid}")
def api_files_unshare(sid: str, who=auth):
    return sharing.revoke(sid, who)


@app.get("/api/files/share/people")
def api_files_share_people(who=auth):
    """Who can be picked in Share with…: staff and admins see the list; members type a name (round 4, 50)."""
    if who.get("role") != "admin" and not sharing.is_staff(who.get("user", "")):
        return {"people": [], "groups": [], "typed": True}
    us = [{"name": u["name"], "display": u.get("display") or u["name"]} for u in directory.list_users().get("users", []) if u.get("enabled", True)]
    gs = [g["name"] for g in directory.list_groups().get("groups", []) if g["name"] not in ("Domain Admins", "Pastors")]
    return {"people": us, "groups": gs, "typed": False}


@app.get("/api/files/quota")
def api_files_quota(user: str = "", who=auth):
    """One home against its quota (row 13). Members see their own; admins any."""
    me = who.get("user", "")
    if user and user != me and who.get("role") != "admin":
        raise HTTPException(403, {"message": "Administrator only"})
    return sharing.quota_of(user or me)


@app.get("/api/storage/quotas")
def api_storage_quotas(_=admin):
    return sharing.quotas()


@app.get("/api/backups/targets")
def api_backups_targets(_=admin):
    """Where tonight's backup goes: the Synology, else Arise-Home over Tailscale (row 15)."""
    return sharing.backup_targets()


class FoldersApply(BaseModel):
    dry_run: bool = True


@app.post("/api/shares/folders")
def api_shares_folders(body: FoldersApply, who=recent):
    """Write the Church, department, Pastors and Shared-with-me share definitions and their ACLs (testparm-checked)."""
    if who.get("role") != "admin":
        raise HTTPException(403, {"message": "Administrator only"})
    return sharing.apply_folders(dry_run=body.dry_run)


@app.get("/api/files/all")
def api_files_all(folder: str = "Documents", who=admin):
    """Everyone's Documents (Photos, …) side by side, for the administrator only."""
    return files.all_of(folder, who)


class UploadStart(BaseModel):
    root: str = "data"
    path: str = "/"
    name: str
    size: int
    fingerprint: str = ""


@app.post("/api/files/upload/start")
def api_upload_start(body: UploadStart, who=auth):
    return finder.upload_start(body.root, body.path, body.name, body.size, body.fingerprint, who)


@app.put("/api/files/upload/chunk")
async def api_upload_chunk(request: Request, token: str, offset: int, who=auth):
    data = await request.body()
    if len(data) > 2 * finder.UPLOAD_CHUNK:
        return {"ok": False, "err": "chunk too big"}
    return finder.upload_chunk(token, offset, data, who)


@app.get("/api/files/upload/status")
def api_upload_status(token: str, who=auth):
    return finder.upload_status(token, who)


class UploadFinish(BaseModel):
    token: str


@app.post("/api/files/upload/finish")
def api_upload_finish(body: UploadFinish, who=auth):
    return finder.upload_finish(body.token, who)


@app.post("/api/files/upload")
async def api_files_upload(root: str = Form("data"), path: str = Form("/"), file: UploadFile = File(...), who=auth):
    data = await file.read()
    if len(data) > 2 * 1024 ** 3:
        return {"ok": False, "err": "2 GB limit here; use the share for bigger files"}
    return files.save_upload(root, path, file.filename or "", data, who)


# ----- the Finder's everyday pieces (v0.8): Trash, versions, info, recents, text, zip ----
@app.get("/api/files/info")
def api_files_info(root: str = "data", path: str = "/", who=auth):
    return finder.info(root, path, who)


@app.get("/api/files/recent")
def api_files_recent(who=auth):
    return finder.recent(who)


@app.get("/api/files/zip")
def api_files_zip(root: str = "data", path: str = "/", who=auth):
    r = finder.zip_path(root, path, who)
    if r.get("demo"):
        return JSONResponse({"ok": True, "demo": True, "message": f"(sample) would download {r['name']}"})
    if not r.get("ok"):
        raise HTTPException(413 if "GB" in (r.get("err") or "") else 404, {"message": r.get("err", "could not zip")})
    return FileResponse(r["zip"], filename=r["name"], media_type="application/zip")


@app.get("/api/files/text")
def api_files_text(root: str = "data", path: str = "/", who=auth):
    return finder.read_text(root, path, who)


class TextBody(BaseModel):
    root: str = "data"
    path: str
    text: str
    mtime: Optional[str] = None


@app.put("/api/files/text")
def api_files_text_save(body: TextBody, who=auth):
    return finder.write_text(body.root, body.path, body.text, who, body.mtime)


class MdBody(BaseModel):
    text: str


@app.post("/api/files/text/preview")
def api_files_text_preview(body: MdBody, who=auth):
    return {"html": finder.render_markdown(body.text[:finder.TEXT_MAX])}


@app.get("/api/files/trash")
def api_files_trash(who=auth):
    return finder.trash_list(who)


class TrashPut(BaseModel):
    root: str = "data"
    path: str
    confirm: str = ""


@app.post("/api/files/trash")
def api_files_trash_put(body: TrashPut, who=auth):
    return finder.trash_put(body.root, body.path, who, body.confirm)


class TrashRestore(BaseModel):
    base: str
    user: str
    rel: str


@app.post("/api/files/trash/restore")
def api_files_trash_restore(body: TrashRestore, who=auth):
    return finder.trash_restore(body.base, body.user, body.rel, who)


class TrashEmpty(BaseModel):
    share: str
    confirm: str = ""


@app.post("/api/files/trash/empty")
def api_files_trash_empty(body: TrashEmpty, who=recent):
    """Emptying a Trash is permanent: an admin who typed the share's name AND the password again (round 4, 54)."""
    if who.get("role") != "admin":
        raise HTTPException(403, {"message": "Administrator only"})
    return finder.trash_empty(body.share, body.confirm, who)


@app.get("/api/files/versions")
def api_files_versions(root: str = "data", path: str = "/", who=auth):
    """The nightly copies the backup holds of one file this person may reach."""
    got = finder._abs(root, path, who)
    if load().demo:
        if not got and sharing.hidden(load().system.data_root + path, who):
            return {"error": "no such file", "versions": [], "backed_up": False}
        return backups.versions_of(got[1] if got else ("/srv/arise" + path))
    if not got:
        return {"error": "no such file", "versions": [], "backed_up": False}
    return backups.versions_of(got[1])


class VersionRestore(BaseModel):
    root: str = "data"
    path: str
    snapshot: str


@app.post("/api/files/versions/restore")
def api_files_versions_restore(body: VersionRestore, who=auth):
    got = finder._abs(body.root, body.path, who)
    rs = {r["id"]: r for r in files.roots(who)}
    if body.root in rs and not files._writable(rs, body.root):
        return {"ok": False, "err": "that share is read-only for you; ask the media team to put it back"}
    if load().demo:
        key = files._demo_rel(body.root, "/" + body.path.strip("/"), who)
        hit = files.demo_find(key) if key else None
        if not hit:
            return {"ok": False, "err": "not a file you can reach"}
        parent, name = files._split(key)
        have = {e[0] for e in files.tree().get(parent, [])}
        from datetime import datetime as _dt
        final = backups.restored_name(name, _dt.now().strftime("%Y-%m-%d"), lambda n: n in have)
        files.demo_add(parent, final, bool(hit[1]), hit[2] if len(hit) > 2 else None)
        return {"ok": True, "demo": True, "restored": final}
    if not got:
        return {"ok": False, "err": "not a file you can reach"}
    return backups.restore_version(got[1], body.snapshot, who)


# ----- share links -------------------------------------------------------------
class NewLink(BaseModel):
    root: str
    path: str
    days: Optional[int] = None
    note: str = ""


@app.get("/api/links")
def api_links(who=auth):
    return links.mine(who)


@app.post("/api/links")
def api_links_new(body: NewLink, request: Request, who=auth):
    r = links.create(body.root, body.path, who, body.days, body.note)
    if r.get("ok"):
        base = (load().web.get("public_url") or "").rstrip("/") or f"{request.url.scheme}://{request.headers.get('host', request.url.netloc)}"
        r["url"] = f"{base}/s/{r['token']}"
    return r


@app.delete("/api/links/{token}")
def api_links_revoke(token: str, who=auth):
    return links.revoke(token, who)


@app.get("/s/{token}")
def public_link(token: str):
    """No login: the file behind a live share link, or a zip of the folder."""
    got = links.resolve(token)
    if not got:
        raise HTTPException(404, {"message": "That link has expired or was removed"})
    if got.get("demo"):
        return JSONResponse({"ok": True, "demo": True, "message": f"(sample) would download {got['name']}"})
    if got["dir"]:
        z = links.zip_folder(got["path"])
        if not z:
            raise HTTPException(413, {"message": "That folder is too big to zip; ask for the files another way"})
        return FileResponse(z, filename=got["name"] + ".zip", media_type="application/zip")
    return FileResponse(got["path"], filename=got["name"])


# ----- the phone: manifest, service worker, push -----------------------------------
@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(str(cfg.web_dir / "manifest.webmanifest"), media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(str(cfg.web_dir / "sw.js"), media_type="application/javascript", headers={"Service-Worker-Allowed": "/"})


class PushSub(BaseModel):
    subscription: dict
    label: str = ""


@app.get("/api/push/key")
def api_push_key(who=auth):
    k = push.public_key()
    k["enabled_for_me"] = who["user"] in push.who_gets()
    return k


@app.post("/api/push/subscribe")
def api_push_subscribe(body: PushSub, who=auth):
    if who["user"] not in push.who_gets():
        return {"ok": False, "err": "push goes to the administrator only (answer 10); add names under [push] users to widen it"}
    return push.subscribe(who["user"], body.subscription, body.label)


@app.post("/api/push/test")
def api_push_test(who=auth):
    return push.send("ariseOS", "This is what a push from the server looks like.", "/#overview", tag="test", throttle_s=0)


@app.get("/api/about/week")
def api_about_week(_=auth):
    """The About window's week: the verse, the services, what the channel did (from the inventory, nothing invented)."""
    from datetime import datetime, timedelta
    c = church.info()
    vids = sermons.videos(40).get("videos", [])
    since = (datetime.now() - timedelta(days=7)).date().isoformat()
    week = [v for v in vids if (v.get("published") or "") >= since]
    def mins(d):
        try:
            parts = [int(x) for x in str(d).split(":")]
            return parts[0] * 60 + parts[1] if len(parts) == 3 else (parts[0] if len(parts) == 2 else 0)
        except (ValueError, TypeError):
            return 0
    return {"verse": church.verse_of_day(), "services": len(c["services"]), "published_this_week": len(week), "minutes_this_week": sum(mins(v.get("duration")) for v in week),
            "latest": (vids[0]["title"] if vids else ""), "latest_date": (vids[0].get("published") if vids else ""), "name": "ariseOS", "codename": CODENAME, "version": VERSION}


# ----- the church: services, verse, the Sunday checklist, the monitor, signage ---
@app.get("/api/church")
def api_church(_=auth):
    i = church.info()
    return {**i, "next": church.next_service(), "verse": church.verse_of_day(), "assistants": church.ASSISTANTS}


@app.get("/api/sunday")
def api_sunday(_=auth):
    return church.checklist()


@app.post("/api/sunday/{i}")
def api_sunday_toggle(i: int, who=auth):
    return church.toggle(i, who["user"])


class OpenUrl(BaseModel):
    url: str


class DesktopAction(BaseModel):
    action: str = "open"


@app.post("/api/kiosk/claude-desktop")
def api_kiosk_claude_desktop(body: DesktopAction, who=auth):
    """Claude Desktop on the closet monitor: Bradly opens it; the screen lock closes it."""
    return church.claude_desktop(body.action, who["user"])


@app.post("/api/kiosk/open")
def api_kiosk_open(body: OpenUrl, request: Request, who=auth):
    """Only the kiosk itself (localhost) may ask the monitor to open a site."""
    host = (request.client.host if request.client else "") or ""
    # Not through Caddy either: it proxies from 127.0.0.1 too, and always adds X-Forwarded-For.
    if not kiosk_profiles.on_monitor(host, request.headers.get("x-forwarded-for", "")) and not load().demo:
        return {"ok": False, "err": "only the closet monitor can open windows on itself; from a browser the site opens in a new tab"}
    return church.open_on_kiosk(body.url)


@app.get("/api/public/sign-in")
def api_public_sign_in():
    """No login: what the sign-in screen and the reset page say about this box, read from the config
    (the realm and mail domain are never written into a page by hand), and the password rules in words."""
    c = load()
    return {"church": c.church.name, "host": c.system.hostname, "realm": c.directory.realm.upper(),
            "mail_domain": profiles.mail_domain(), "rules": directory.password_rules().get("words", []), "demo": c.demo}


@app.get("/api/public/signage")
def api_signage():
    """No login: the lobby screen's feed (service times, the next one, the verse, the latest titles)."""
    return church.signage()


@app.get("/signage")
def signage_page():
    return FileResponse(str(cfg.web_dir / "signage.html"))


# ----- the church calendar, the weather, help, what's new (v0.8 Exodus) ------------
class CalEvent(BaseModel):
    title: str
    start: str
    end: str = ""
    where: str = ""
    note: str = ""
    people: list[str] = []      # who is in it: users and @groups (round 5, 28: reminded 30 minutes before)


@app.get("/api/calendar")
def api_calendar(year: int = 0, month: int = 0, _=auth):
    from datetime import datetime as _dt
    now = _dt.now()
    y, m = (year or now.year), (month or now.month)
    if not 1 <= m <= 12 or not 2000 <= y <= 2100:
        raise HTTPException(400, {"message": "year/month out of range"})
    out = {**churchcal.month(y, m), "upcoming": churchcal.upcoming(14), "services": church.info()["services"]}
    if _.get("role") == "admin":
        # Round 7, 18: staff birthdays on the admins' calendar (month and day only; never a year or an age).
        out["items"] = sorted(out["items"] + churchcal.birthday_items(y, m, profiles.birthdays(m)), key=lambda x: x["start"])
    return out


@app.get("/api/calendar/subscribe")
def api_calendar_subscribe(request: Request, _=auth):
    host = (load().web.public_url or "").replace("https://", "").replace("http://", "").rstrip("/") or request.headers.get("host", "arise-server")
    return churchcal.subscribe_info(host)


@app.post("/api/calendar")
def api_calendar_add(body: CalEvent, who=admin):
    return churchcal.add(body.model_dump(), who["user"])


@app.put("/api/calendar/{ev_id}")
def api_calendar_update(ev_id: str, body: CalEvent, who=admin):
    return churchcal.update(ev_id, body.model_dump(), who["user"])


@app.delete("/api/calendar/{ev_id}")
def api_calendar_remove(ev_id: str, _=admin):
    return churchcal.remove(ev_id)


@app.get("/api/public/calendar.ics")
@app.get("/calendar.ics", include_in_schema=False)
def calendar_ics(request: Request):
    """No login: the subscribable feed every Mac and phone reads (round 3, 10)."""
    host = request.headers.get("host", "arise-server").split(":")[0]
    return Response(churchcal.ics(host), media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": 'inline; filename="arise-church.ics"', "Cache-Control": "max-age=600"})


@app.get("/api/weather")
def api_weather(_=auth):
    return weather.fetch()


@app.get("/api/help")
def api_help(q: str = "", who=auth):
    d = helpdocs.docs(who["role"])
    if q:
        d["search"] = helpdocs.search(q, who["role"])
    return d


@app.get("/api/help/{name}")
def api_help_doc(name: str, who=auth):
    r = helpdocs.doc(name, who["role"])
    if not r.get("ok"):
        raise HTTPException(404, {"message": r.get("err", "no such document")})
    return r


@app.get("/api/about/whatsnew")
def api_whatsnew(_=auth):
    """The top of CHANGELOG.md, ten lines at most (round 3, 34)."""
    from .util import read_text
    text = read_text(load().repo_root / "CHANGELOG.md", "")
    return {"version": VERSION, "codename": CODENAME, "lines": whatsnew_lines(text)}


def whatsnew_lines(text: str, limit: int = 10) -> list[str]:
    """The first '## ' section of a changelog as plain lines. Pure."""
    out, started = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            if started:
                break
            started = True
            continue
        if started and line.strip() and not line.startswith("#"):
            out.append(line.strip().lstrip("-* ").strip())
        if len(out) >= limit:
            break
    return out


# ----- mail: the church family list, through Resend --------------------------------
class MailDraft(BaseModel):
    subject: str
    body: str
    name: str = ""


class MailTest(MailDraft):
    to: str


class MailSend(BaseModel):
    confirm: str = ""


class MailImport(BaseModel):
    csv: str


@app.get("/api/mail")
def api_mail(_=admin):
    return {**mail.status(), "import": mail.import_status()}


@app.get("/api/mail/contacts")
def api_mail_contacts(_=admin):
    return mail.contacts()


@app.post("/api/mail/import/preview")
def api_mail_import_preview(body: MailImport, _=admin):
    r = mail.parse_contacts(body.csv)
    return {"count": len(r["contacts"]), "skipped": r["skipped"], "columns": r.get("columns"), "err": r.get("err"), "sample": r["contacts"][:5]}


@app.post("/api/mail/import")
def api_mail_import(body: MailImport, _=admin):
    r = mail.parse_contacts(body.csv)
    if r.get("err"):
        return {"ok": False, "err": r["err"]}
    return mail.import_contacts(r["contacts"])


@app.post("/api/mail/preview")
def api_mail_preview(body: MailDraft, _=admin):
    c = church.info()
    # the merge tags are Resend's; show the preview the way a reader named nobody sees it
    return {"html": mail.render(body.subject, body.body, c["name"], c["city"]).replace("{{{FIRST_NAME|there}}}", "there").replace("{{{RESEND_UNSUBSCRIBE_URL}}}", "#")}


@app.post("/api/mail/test")
def api_mail_test(body: MailTest, _=admin):
    return mail.send_test(body.to, body.subject, body.body)


@app.post("/api/mail/broadcasts")
def api_mail_broadcast(body: MailDraft, _=admin):
    return mail.create_broadcast(body.subject, body.body, body.name)


@app.post("/api/mail/broadcasts/{bc_id}/send")
def api_mail_broadcast_send(bc_id: str, body: MailSend, _=admin):
    return mail.send_broadcast(bc_id, body.confirm)


@app.get("/api/mail/broadcasts")
def api_mail_broadcasts(_=admin):
    return mail.broadcasts()


# ----- everything on the switch --------------------------------------------------
class DeviceLabel(BaseModel):
    name: Optional[str] = None
    note: Optional[str] = None
    kind: Optional[str] = None


@app.get("/api/devices")
def api_devices(_=admin):
    return devices.list_devices()


@app.get("/api/devices/behind")
def api_devices_behind(_=admin):
    """What the other routers report as attached, read from them (never written)."""
    return routers.behind()


@app.post("/api/devices/scan")
def api_devices_scan(wide: int = 0, _=admin):
    return devices.scan(wide=bool(wide))


@app.get("/api/devices/cameras")
def api_devices_cameras(_=admin):
    """ONVIF discovery: which cameras answer on the wire, and whether this network can reach them."""
    return devices.find_cameras()


@app.post("/api/devices/{mac}")
def api_devices_label(mac: str, body: DeviceLabel, _=admin):
    return devices.label(mac, body.name, body.note, body.kind)


@app.delete("/api/devices/{mac}")
def api_devices_forget(mac: str, _=admin):
    return devices.forget(mac)


# ----- the safety basics (round 3) ----------------------------------------------------
@app.get("/api/security")
def api_security(_=admin):
    return security.overview()


@app.get("/api/security/scan")
def api_security_scan(_=admin):
    return security.scan_status()


@app.post("/api/security/scan/run")
def api_security_scan_run(_=admin):
    """The weekly ClamAV scan, now. Refused during a service. Takes a while; runs in a thread."""
    import threading
    c = load()
    if c.demo:
        return {"ok": True, "demo": True, "started": True}
    bad = security._refuse_in_service("The virus scan")
    if bad:
        return bad
    threading.Thread(target=security.scan_run, daemon=True).start()
    return {"ok": True, "started": True}


class Named(BaseModel):
    name: str
    confirm: str = ""


@app.post("/api/security/scan/restore")
def api_security_scan_restore(body: Named, _=admin):
    return security.scan_restore(body.name, body.confirm)


@app.get("/api/security/snapshots")
def api_security_snapshots(_=admin):
    return security.snapshot_list()


@app.get("/api/public/ca.crt")
@app.get("/ca.crt")
def api_ca_crt():
    """The church root certificate (Caddy's internal CA), for a Mac or phone to trust once. Public: a root certificate is not a secret."""
    pem = security.ca_cert()
    if not pem:
        return JSONResponse({"error": {"message": "No certificate yet: Caddy has not run on this box (install.sh puts it in front of the dashboard)."}}, status_code=404)
    return Response(pem, media_type="application/x-pem-file", headers={"Content-Disposition": 'attachment; filename="arise-church-root.crt"'})


@app.get("/api/system/updates")
def api_updates(_=admin):
    return system.updates()


@app.post("/api/system/update")
def api_update(who=admin):
    """Round 7, 135: any admin may install it; the ring (136) decides which version arrives."""
    r = system.update_arise()
    audit.record(who.get("user", "?"), "system.update_arise", system.ring(), ok=bool(r.get("ok")), detail=str(r.get("out") or r.get("err") or "")[:200])
    return r


@app.post("/api/system/apt-upgrade")
def api_apt_upgrade(_=admin):
    return system.apt_upgrade()


class Power(BaseModel):
    action: str
    confirm: str = ""


@app.post("/api/system/power")
def api_power(body: Power, _=recent):
    svc = church.in_service_now()
    if svc:
        return {"ok": False, "err": f"Not during {svc['name']}: it ends about {svc['ends_at']}. Try again then."}
    return system.power(body.action, body.confirm)


@app.post("/api/notify/test")
def api_notify_test(_=admin):
    c = load()
    if c.demo:
        return {"ok": True, "demo": True}
    return system.send_webhook("Arise Server: test note from the dashboard. If you can read this, the daily 07:00 note will arrive here.")


@app.get("/api/notify")
def api_notify(_=admin):
    from .util import read_json
    n = system.notify_config()
    st = read_json(load().state_dir / "state.json", default={}) or {}
    return {"configured": bool(n["webhook_url"]), "hour": n["hour"], "only_when_attention": n["only_when_attention"], "last": st.get("last_notify")}


@app.websocket("/api/terminal")
async def api_terminal(ws: WebSocket):
    """A pty over a websocket. Text frames in = keystrokes; JSON {"resize":[cols,rows]} resizes."""
    try:
        current_user(ws)  # same cookie check as every other route
    except HTTPException:
        await ws.close(code=4401)
        return
    # A root shell: the page opening it must be this dashboard, never a sibling site that
    # the cookie would also be sent from. Browsers always send Origin on a websocket.
    if not ws.headers.get("origin") or not _auth.origin_ok(ws.headers.get("origin"), ws.headers.get("host")):
        await ws.close(code=4403)
        return
    await ws.accept()
    c = load()
    if c.demo or os.name == "nt":
        await ws.send_text(system.DEMO_BANNER + "\x1b[31marise-server\x1b[0m:~# ")
        buf = ""
        try:
            while True:
                msg = await ws.receive_text()
                if msg.startswith("{"):
                    continue
                for ch in msg:
                    if ch in ("\r", "\n"):
                        cmd = buf.strip(); buf = ""
                        out = "" if not cmd else ("\x1b[2J\x1b[H" if cmd == "clear" else system.DEMO_COMMANDS.get(cmd, f"bash: {cmd}: not in the preview (type help)"))
                        await ws.send_text("\r\n" + (out + "\r\n" if out and cmd != "clear" else out) + "\x1b[31marise-server\x1b[0m:~# ")
                    elif ch == "\x7f":
                        if buf:
                            buf = buf[:-1]; await ws.send_text("\b \b")
                    elif ch == "\x03":
                        buf = ""; await ws.send_text("^C\r\n\x1b[31marise-server\x1b[0m:~# ")
                    elif ch >= " ":
                        buf += ch; await ws.send_text(ch)
        except WebSocketDisconnect:
            return
    pid, fd = system.spawn_shell()
    loop = asyncio.get_event_loop()

    async def pump():
        try:
            while True:
                data = await loop.run_in_executor(None, _read_fd, fd)
                if not data:
                    break
                await ws.send_text(data.decode("utf-8", "replace"))
        except Exception:
            pass
        try:
            await ws.close()
        except Exception:
            pass

    task = asyncio.create_task(pump())
    try:
        while True:
            msg = await ws.receive_text()
            if msg.startswith("{"):
                try:
                    import json as _json
                    j = _json.loads(msg)
                    if "resize" in j:
                        system.resize(fd, int(j["resize"][0]), int(j["resize"][1]))
                except Exception:
                    pass
                continue
            os.write(fd, msg.encode())
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        system.kill(pid)
        try:
            os.close(fd)
        except OSError:
            pass


def _read_fd(fd):
    try:
        return os.read(fd, 65536)
    except OSError:
        return b""

# ----- the Arise repos, two-way with GitHub (docs/REPOS.md) ----------------------
@app.get("/api/repos")
def api_repos(_=admin):
    return arise_repos.status()


@app.post("/api/repos/sync")
def api_repos_sync(_=admin):
    """Runs the unit (as arise-git, with the token as a systemd credential), never git as root here."""
    if load().demo:
        return {"ok": True, "demo": True, "started": True}
    r = system_run(["systemctl", "start", "--no-block", "arise-repos.service"])
    return {"ok": r["ok"], "started": r["ok"], **({} if r["ok"] else {"err": (r.get("err") or r.get("out") or "").strip()[-300:]})}


# ----- audit log and offboarding (round 2, 23 and 24) ----------------------------
@app.get("/api/audit")
def api_audit(limit: int = 200, q: str = "", who: str = "", failed: bool = False, _=admin):
    """Newest first; admins only; nothing here deletes or edits it."""
    return audit.recent(limit=limit, q=q, who=who, failed_only=failed)


class Leaving(BaseModel):
    move_to: str
    days: int = offboard.GRACE_DAYS


@app.get("/api/directory/leaving")
def api_leaving(_=admin):
    return offboard.status()


@app.post("/api/directory/users/{name}/leaving")
def api_leaving_start(name: str, body: Leaving, who=admin):
    return offboard.start(name, body.move_to, who["user"], days=body.days)


@app.delete("/api/directory/users/{name}/leaving")
def api_leaving_cancel(name: str, who=admin):
    return offboard.cancel(name, who["user"])



# ----- the reset page: on its own, no desktop (staff use their Macs, Oct 28) ------
@app.get("/reset", include_in_schema=False)
def reset_page():
    p = cfg.web_dir / "reset.html"
    if not p.is_file():
        raise HTTPException(404, {"message": "Not found"})
    return FileResponse(p, media_type="text/html", headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
# ----- round 5: the desktop, notifications, department checklists, the guided setup -----
from . import checklists, desktop as arise_desktop, notify, setup_wizard  # noqa: E402


@app.get("/api/notifications")
def api_notifications(limit: int = 50, who=auth):
    return notify.feed(who["user"], limit)


class NotifyRead(BaseModel):
    ids: list[str] | None = None


@app.post("/api/notifications/read")
def api_notifications_read(body: NotifyRead, who=auth):
    return notify.mark_read(who["user"], body.ids)


class NotifyAdd(BaseModel):
    user: str
    kind: str = "system"
    text: str
    link: str = ""


@app.post("/api/notifications")
def api_notifications_add(body: NotifyAdd, who=admin):
    """For admins and the hooks (the internal mail server's delivery, arisectl notify add)."""
    return notify.add(body.user, body.kind, body.text, body.link)


@app.get("/api/desktop")
def api_desktop(who=auth):
    return {**arise_desktop.location(who), "positions": arise_desktop.positions(who["user"])}


class DesktopPositions(BaseModel):
    positions: dict


@app.put("/api/desktop/positions")
def api_desktop_positions(body: DesktopPositions, who=auth):
    return arise_desktop.save_positions(who["user"], body.positions)


class FileMove(BaseModel):
    root: str
    path: str
    to: str


@app.post("/api/files/move")
def api_files_move(body: FileMove, who=auth):
    """Same place only: Finder onto the Desktop, a desktop icon into a folder (round 5, 24)."""
    return arise_desktop.move(body.root, body.path, body.to, who)


@app.get("/api/checklists")
def api_checklists(who=admin):
    """Department checklists. Admins only while [web] staff_access is "none" (after round 5)."""
    return checklists.all_lists(who)


class ChecklistTick(BaseModel):
    i: int


@app.post("/api/checklists/{dept}/tick")
def api_checklist_tick(dept: str, body: ChecklistTick, who=admin):
    return checklists.tick(dept, body.i, who)


class ChecklistEdit(BaseModel):
    items: list[str] | None = None
    leader: str | None = None
    nudge: dict | None = None
    services: list[str] | None = None


@app.put("/api/checklists/{dept}")
def api_checklist_edit(dept: str, body: ChecklistEdit, who=admin):
    return checklists.edit(dept, who, body.items, body.leader, body.nudge, body.services)


@app.get("/api/setup")
def api_setup(who=admin):
    return setup_wizard.state(who)


class SetupMark(BaseModel):
    status: str


@app.post("/api/setup/dismiss")
def api_setup_dismiss(who=admin):
    return setup_wizard.dismiss(who, True)


@app.post("/api/setup/reopen")
def api_setup_reopen(who=admin):
    return setup_wizard.dismiss(who, False)


@app.post("/api/setup/{step}")
def api_setup_mark(step: str, body: SetupMark, who=admin):
    return setup_wizard.mark(step, body.status, who)


KIOSK_SCALES = (1.0, 1.15, 1.25, 1.4, 1.5)


def _kiosk_scale_file():
    return load().state_dir / "kiosk-scale"


@app.get("/api/kiosk/scale")
def api_kiosk_scale(_=admin):
    """The closet monitor's text size (round 5, 27). 1.25 until someone changes it."""
    try:
        v = float(_kiosk_scale_file().read_text().strip())
    except (OSError, ValueError):
        v = 1.25
    return {"scale": v, "choices": list(KIOSK_SCALES), "demo": load().demo}


class KioskScale(BaseModel):
    scale: float


@app.post("/api/kiosk/scale")
def api_kiosk_scale_set(body: KioskScale, who=admin):
    """Saves the size and restarts the monitor's browser (about five seconds), never during a service."""
    if body.scale not in KIOSK_SCALES:
        return {"ok": False, "err": "pick one of " + ", ".join(f"{int(s * 100)}%" for s in KIOSK_SCALES)}
    svc = church.in_service_now()
    if svc:
        return {"ok": False, "err": f"not during {svc['name']}: the monitor stays as it is until {svc['ends_at']}"}
    if load().demo:
        return {"ok": True, "demo": True, "scale": body.scale}
    p = _kiosk_scale_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"{body.scale}\n")
    os.chmod(p, 0o644)
    audit.record(who["user"], "kiosk.scale", f"{int(body.scale * 100)}%")
    r = system_run(["systemctl", "restart", "--no-block", "arise-kiosk.service"], timeout=20)
    return {"ok": True, "scale": body.scale, "restarted": r["ok"]}


@app.get("/api/public/faces")
def api_public_faces(request: Request):
    """The sign-in faces on the closet monitor (round 4, 14 and 16; round 5, 31). Only to the monitor
    itself (a request from this box): nobody on the network can list who has an account."""
    host = (request.client.host if request.client else "") or ""
    if not (load().demo or host in ("127.0.0.1", "::1", "localhost")):
        return {"faces": [], "note": "faces are shown on the closet monitor only"}
    try:
        users = directory.list_users().get("users", [])
    except Exception:  # noqa: BLE001
        users = []
    faces = []
    for u in users:
        if not u.get("enabled", True) or "Domain Admins" not in (u.get("groups") or []):
            continue
        plain = u.get("display") or u["name"]
        name = profiles.display_name(u["name"], plain)   # round 7, 11: the title everywhere
        try:
            from . import accounts
            photo = accounts.has_photo(u["name"])
        except Exception:  # noqa: BLE001
            photo = False
        faces.append({"user": u["name"], "name": name, "initials": "".join(w[0] for w in plain.split()[:2] if w).upper(),
                      "photo": f"/api/photos/{u['name']}" if photo else None})
    return {"faces": faces}


# ----- round 6: the closet OS for the four admins, Firefox per admin, two-step for staff ---------
from . import kiosk_profiles  # noqa: E402


@app.get("/api/kiosk/profile")
def api_kiosk_profile(who=auth):
    """Whose Firefox profile the monitor is running now ("neutral" when locked)."""
    return {"current": kiosk_profiles.current(), "user": who["user"], "demo": load().demo}


class KioskProfile(BaseModel):
    action: str = "switch"


@app.post("/api/kiosk/profile")
def api_kiosk_profile_set(body: KioskProfile, request: Request, who=auth):
    """switch: an admin who just signed in at the monitor gets their own Firefox profile.
    neutral: the screen locked. Only from the monitor itself."""
    if not kiosk_profiles.on_monitor(_ip(request), request.headers.get("x-forwarded-for", "")):
        raise HTTPException(403, {"message": "Only the closet monitor switches its own browser"})
    if body.action == "neutral":
        return kiosk_profiles.neutral()
    if body.action != "switch":
        return {"ok": False, "err": "action is switch or neutral"}
    if who.get("role") != "admin":
        raise HTTPException(403, {"message": "The closet desktop is the administrators'"})
    r = kiosk_profiles.switch(who["user"], request.cookies.get(COOKIE) or "")
    if r.get("ok") and not r.get("already"):
        audit.record(who["user"], "kiosk.profile", who["user"], detail="Firefox profile on the monitor")
    return r


class Handoff(BaseModel):
    token: str


@app.post("/api/auth/handoff")
def api_auth_handoff(body: Handoff, request: Request, response: Response):
    """The restarted Firefox trades its one-time token for the admin's session (one minute, once)."""
    if not kiosk_profiles.on_monitor(_ip(request), request.headers.get("x-forwarded-for", "")):
        raise HTTPException(403, {"message": "Only on the closet monitor"})
    got = kiosk_profiles.handoff_take(body.token)
    if not got:
        raise HTTPException(401, {"message": "That hand-over has expired; sign in again"})
    session, user = got
    if session:
        response.set_cookie(COOKIE, session, httponly=True, samesite="lax", secure=_https(request), max_age=int(load().web.session_hours) * 3600)
    return {"ok": True, "user": user}


def _directory_user(name: str) -> bool:
    try:
        return any(u.get("name") == name for u in directory.list_users().get("users", []))
    except Exception:  # noqa: BLE001
        return False


@app.post("/api/directory/users/{name}/2fa/setup")
def api_dir_user_2fa_setup(name: str, who=admin):
    """Staff don't use the OS (round 6, 20): an admin starts two-step for them and shows them the code
    to scan in Microsoft Authenticator, then types the six digits the person reads off their phone."""
    if not _directory_user(name):
        return {"ok": False, "err": "no such user"}
    r = twofa.setup(name)
    if r.get("ok"):
        audit.record(who["user"], "twofa.setup.for", name)
    return r


@app.post("/api/directory/users/{name}/2fa/enable")
def api_dir_user_2fa_enable(name: str, body: Code, who=admin):
    if not _directory_user(name):
        return {"ok": False, "err": "no such user"}
    r = twofa.enable(name, body.code)
    if r.get("ok"):
        audit.record(who["user"], "twofa.on.for", name)
    return r


@app.post("/api/directory/users/{name}/2fa/disable")
def api_dir_user_2fa_disable(name: str, who=recent):
    """Off again, by an admin who just typed their own password again."""
    if who.get("role") != "admin":
        raise HTTPException(403, {"message": "Administrator only"})
    if not _directory_user(name):
        return {"ok": False, "err": "no such user"}
    r = twofa.disable(name, "", "", by_admin=True)
    if r.get("ok"):
        audit.record(who["user"], "twofa.off.for", name)
    return r
# ----- round 6: the church Macs (server/arise_server/macs.py, docs/MACS.md) --------
from . import macs as church_macs  # noqa: E402


@app.get("/api/macs")
def api_macs(_=admin):
    return church_macs.listing()


class MacToken(BaseModel):
    name: str = ""


@app.post("/api/macs/enrol-token")
def api_macs_token(body: MacToken, who=admin):
    """The one Terminal line for a new church Mac (round 6, 37): good for an hour, once."""
    return church_macs.enrol_token(who["user"], body.name)


@app.get("/api/macs/{mac_id}")
def api_mac(mac_id: str, _=admin):
    return church_macs.detail(mac_id)


class MacLocal(BaseModel):
    local: str
    action: str            # convert | link | leave | undo
    user: str = ""
    display: str = ""


@app.post("/api/macs/{mac_id}/local")
def api_mac_local(mac_id: str, body: MacLocal, who=admin):
    """An existing local account: convert it to the server user, link it, or leave it alone."""
    return church_macs.choose_local(mac_id, body.local, body.action, body.user, who["user"], body.display)


class MacTask(BaseModel):
    kind: str
    mode: str = ""        # dnsfilter: "on" or "off"


@app.post("/api/macs/{mac_id}/task")
def api_mac_task(mac_id: str, body: MacTask, who=admin):
    return church_macs.run_task(mac_id, body.kind, who["user"], {"mode": body.mode} if body.mode else None)


class MacLive(BaseModel):
    on: bool


@app.post("/api/macs/live")
def api_macs_live(body: MacLive, who=recent):
    """Round 7, 4: the Mac helper's Switch on (tasks go out), or back to watch mode. Password again, audited."""
    if who.get("role") != "admin":
        raise HTTPException(403, {"message": "Administrator only"})
    return church_macs.set_live(body.on, who["user"])


class MacMedia(BaseModel):
    on: bool


@app.post("/api/macs/{mac_id}/media")
def api_mac_media(mac_id: str, body: MacMedia, who=admin):
    """Round 7, 31 and 96: this is the media Mac, the one that gets Proclaim."""
    return church_macs.set_media(mac_id, body.on, who["user"])


class MacTemp(BaseModel):
    user: str


@app.post("/api/macs/{mac_id}/temp-password")
def api_mac_temp(mac_id: str, body: MacTemp, who=recent):
    """A server user the default link made (round 7, 23): its temporary password, shown once."""
    if who.get("role") != "admin":
        raise HTTPException(403, {"message": "Administrator only"})
    r = church_macs.temp_take(mac_id, body.user, who["user"])
    if r.pop("code", None) == 400:
        raise HTTPException(400, {"message": r["err"]})
    return r


class MacConfirm(BaseModel):
    confirm: str = ""


@app.post("/api/macs/{mac_id}/retire")
def api_mac_retire(mac_id: str, body: MacConfirm, who=recent):
    if who.get("role") != "admin":
        raise HTTPException(403, {"message": "Administrator only"})
    return church_macs.retire(mac_id, body.confirm, who["user"])


@app.post("/api/macs/{mac_id}/cutoff")
def api_mac_cutoff(mac_id: str, body: MacConfirm, who=recent):
    if who.get("role") != "admin":
        raise HTTPException(403, {"message": "Administrator only"})
    return church_macs.cut_off(mac_id, body.confirm, who["user"])


class MacReveal(BaseModel):
    kind: str


@app.post("/api/macs/{mac_id}/reveal")
def api_mac_reveal(mac_id: str, body: MacReveal, who=recent):
    """ariseadmin's password or the FileVault key: an admin who typed the password again, audited."""
    if who.get("role") != "admin":
        raise HTTPException(403, {"message": "Administrator only"})
    return church_macs.reveal(mac_id, body.kind, who["user"])


# The helper's own door: no session, its Mac key in X-Arise-Mac. Plain text both ways.
def _mac_or_401(request: Request) -> dict:
    m = church_macs.agent_auth(request.headers.get("x-arise-mac", ""))
    if not m:
        raise HTTPException(401, {"message": "not an enrolled church Mac"})
    return m


def _txt(s: str, code: int = 200) -> Response:
    return Response(s if s.endswith("\n") else s + "\n", status_code=code, media_type="text/plain")


@app.post("/api/macs/agent/enrol")
async def api_mac_agent_enrol(request: Request):
    f = await request.form()
    r = church_macs.enrol(str(f.get("token", "")), {k: str(f.get(k, "")) for k in ("name", "ad_name", "serial", "model", "macos", "helper", "accounts")})
    if not r["ok"]:
        return _txt("ERROR " + church_macs.enc(r["err"]), 403)
    return _txt(f"MAC_ID={r['mac_id']}\nKEY={r['key']}")


@app.post("/api/macs/agent/checkin")
async def api_mac_agent_checkin(request: Request):
    m = _mac_or_401(request)
    f = await request.form()
    facts = {k: str(f.get(k)) for k in ("macos", "model", "serial", "helper", "filevault", "tailscale", "full_disk_access", "disk_used", "accounts")
             if f.get(k) is not None}
    facts["ip"] = request.client.host if request.client else ""
    return _txt("\n".join(church_macs.checkin(m, facts)) or "NONE")


@app.post("/api/macs/agent/result")
async def api_mac_agent_result(request: Request):
    m = _mac_or_401(request)
    f = await request.form()
    r = church_macs.result(m, str(f.get("id", "")), str(f.get("state", "")), str(f.get("detail", "")))
    return _txt("OK" if r["ok"] else "ERROR " + church_macs.enc(r["err"]), 200 if r["ok"] else 400)


@app.post("/api/macs/agent/secret")
async def api_mac_agent_secret(request: Request):
    m = _mac_or_401(request)
    f = await request.form()
    r = church_macs.store_secret(m, str(f.get("kind", "")), str(f.get("value", "")))
    return _txt("OK" if r["ok"] else "ERROR " + church_macs.enc(r["err"]), 200 if r["ok"] else 400)


@app.post("/api/macs/agent/check")
async def api_mac_agent_check(request: Request):
    """Before a profile is removed: is everything in this list already on the server?"""
    m = _mac_or_401(request)
    f = await request.form()
    r = church_macs.check(m, str(f.get("user", "")), str(f.get("bases", "")), str(f.get("manifest", "")))
    if r.get("ok"):
        return _txt(f"OK {r.get('checked', 0)}")
    lines = [f"REFUSE {church_macs.enc(r.get('err') or str(r.get('missing_count', 0)) + ' missing, ' + str(r.get('newer_count', 0)) + ' newer on the Mac')}"]
    lines += [f"MISSING {church_macs.enc(x)}" for x in r.get("missing", [])] + [f"NEWER {church_macs.enc(x)}" for x in r.get("newer", [])]
    return _txt("\n".join(lines))


@app.get("/api/macs/agent/config")
def api_mac_agent_config(request: Request):
    m = _mac_or_401(request)
    return _txt(church_macs.config_lines(m))


# The helper's files, for the one Terminal line. Not secret: the one-time token is.
MAC_FILES = {"enrol.sh": "enrol.sh", "arise-mac-helper": "arise-mac-helper", "com.arisechurch.helper.plist": "com.arisechurch.helper.plist",
             "bind-mac.sh": "../bind-mac.sh", "migrate-mac-user.sh": "../migrate-mac-user.sh", "nextcloud.sh": "tasks/nextcloud.sh"}


@app.get("/mac/{name}", include_in_schema=False)
def mac_file(name: str):
    rel = MAC_FILES.get(name)
    p = (cfg.repo_root / "mac" / "helper" / rel).resolve() if rel else None
    if not p or not p.is_file():
        raise HTTPException(404, {"message": "Not found"})
    return FileResponse(p, media_type="text/plain", headers={"Cache-Control": "no-store"})

# ===== R6-SYNC: Mac and phone syncing (round 6, rows 13-19, 39, 40; docs/SYNC.md) =====
from . import cloud  # noqa: E402


class CloudDevice(BaseModel):
    user: str
    device: str = ""


@app.get("/api/cloud")
def api_cloud(_=admin):
    """Nextcloud at a glance: its address, running or not, the mounts, devices signed in."""
    return cloud.status()


@app.get("/api/cloud/people")
def api_cloud_people(_=admin):
    """The Sync panel: per person, last sync, devices, conflicts settled, storage against the quota."""
    return cloud.people()


@app.get("/api/cloud/conflicts")
def api_cloud_conflicts(limit: int = 100, _=admin):
    """Newest wins (row 15): what each conflict kept and which Trash the older copy is in."""
    return cloud.conflicts(max(1, min(int(limit), 1000)))


@app.post("/api/cloud/app-password")
def api_cloud_app_password(body: CloudDevice, who=admin):
    """A device app password for a phone or a Mac set up by hand: shown once, never stored."""
    return cloud.app_password(body.user, body.device.strip(), by=who["user"])


@app.post("/api/cloud/revoke")
def api_cloud_revoke(body: CloudDevice, who=admin):
    """Cut off one device of a person, or (no device) every sign-in they have. Round 7, 74: the person is told."""
    r = cloud.revoke(body.user, body.device.strip() or None, by=who["user"])
    if r.get("ok") and body.user != who["user"]:
        from . import accounts
        dev = body.device.strip()
        r["told"] = bool(accounts.tell_person(body.user, "A device was cut off from your church files",
                                              (f"{dev} no longer syncs your church files" if dev else "Every device you had signed in to church files was cut off")
                                              + f" (by {who['user']}). If you still have it, ask Bradly for a new device password.", kind="security"))
    return r


@app.post("/api/cloud/sweep")
def api_cloud_sweep(who=admin):
    """Settle the conflict copies now (the hourly timer does the same). Never during a service."""
    svc = church.in_service_now()
    if svc:
        return {"ok": False, "err": f"not during {svc['name']}: the sweep runs again after {svc['ends_at']}"}
    r = cloud.sweep()
    audit.record(who["user"], "cloud.sweep", "", detail=f"{len(r.get('moved', []))} settled")
    return r


@app.post("/api/cloud/agent/app-password")
async def api_cloud_agent_app_password(request: Request):
    """The Mac helper's nextcloud task (mac/helper/tasks/nextcloud.sh): its Mac key in X-Arise-Mac,
    and only for a task an admin queued on that Mac. Plain text: APP_PASSWORD= and CLOUD_URL=."""
    def txt(s: str, code: int = 200) -> Response:
        return Response(s + "\n", status_code=code, media_type="text/plain", headers={"Cache-Control": "no-store"})
    try:
        from . import macs as church_macs_
    except ImportError:
        return txt("ERROR the Macs app is not on this server", 404)
    mac = church_macs_.agent_auth(request.headers.get("x-arise-mac", ""))
    if not mac:
        return txt("ERROR not an enrolled church Mac", 401)
    f = await request.form()
    r = cloud.agent_app_password(mac, str(f.get("user", "")), str(f.get("local", "")))
    if not r.get("ok"):
        return txt("ERROR " + str(r.get("err", "refused")).replace("\n", " "), 403)
    folders = " ".join(f for f in (cfg.cloud.sync_folders or ["Desktop", "Documents"]) if re.match(r"^[A-Za-z][A-Za-z ]{0,40}$", f) and " " not in f)
    return txt(f"APP_PASSWORD={r['app_password']}\nCLOUD_URL={r['server']}\nLOGIN={r['login']}\nDEVICE={r['device']}\nFOLDERS={folders}")
# ===== end R6-SYNC =====


# ===== Round 7: the church contacts as a read-only CardDAV address book (rows 21 and 152) =====
from . import carddav  # noqa: E402

_dav_ok: dict = {}


def _dav_user(request: Request) -> str | None:
    """Basic auth with the church login (Contacts and iOS speak nothing else). A right answer is
    remembered five minutes, so Contacts' many small requests don't each ask the domain."""
    import base64 as _b64
    import hashlib as _h
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("basic "):
        return None
    try:
        user, _, pw = _b64.b64decode(h[6:].strip()).decode("utf-8").partition(":")
    except (ValueError, UnicodeDecodeError):
        return None
    user = user.strip().lower().split("@")[0]
    key = _h.sha256(f"{user}:{pw}".encode()).hexdigest()
    now = time.time()
    if _dav_ok.get(key, 0) > now:
        return user
    keys = [f"ip:{_ip(request)}"]
    if not load().demo and _auth.too_many(keys):
        return None
    if not directory._ok_name(user) or not directory.authenticate(user, pw):
        if not load().demo:
            _auth.note_failure(keys)
        return None
    if not carddav.may_read(user):
        return None
    _dav_ok[key] = now + 300
    return user


def _dav_401() -> Response:
    return Response("church login needed\n", status_code=401, media_type="text/plain",
                    headers={"WWW-Authenticate": 'Basic realm="Arise Church contacts", charset="UTF-8"'})


@app.api_route("/.well-known/carddav", methods=["GET", "PROPFIND", "HEAD"], include_in_schema=False)
def dav_wellknown():
    return Response(status_code=301, headers={"Location": "/carddav/"})


@app.api_route("/carddav/{path:path}", methods=["OPTIONS", "PROPFIND", "REPORT", "GET", "HEAD", "PUT", "DELETE", "PROPPATCH", "MKCOL", "POST"],
               include_in_schema=False)
async def dav(path: str, request: Request):
    hdr = {"DAV": "1, 3, addressbook", "Allow": "OPTIONS, PROPFIND, REPORT, GET, HEAD"}
    if request.method == "OPTIONS":
        return Response(status_code=200, headers=hdr)
    if not load().people.contacts:
        return Response(status_code=404)
    user = _dav_user(request)
    if not user:
        return _dav_401()
    full = "/carddav/" + path
    if request.method in ("PUT", "DELETE", "PROPPATCH", "MKCOL", "POST"):
        return Response("read-only: the church contacts are kept in Directory and Mail\n", status_code=403, media_type="text/plain", headers=hdr)
    if request.method == "PROPFIND":
        code, xml = carddav.propfind(full, user, request.headers.get("depth", "1"))
    elif request.method == "REPORT":
        code, xml = carddav.report(full, user, (await request.body()).decode("utf-8", "replace"))
    else:
        code, card, tag = carddav.get(full, user)
        if code != 200:
            return Response(status_code=404, headers=hdr)
        return Response(card if request.method == "GET" else b"", media_type="text/vcard; charset=utf-8", headers={**hdr, "ETag": tag})
    if code != 207:
        return Response(status_code=code, headers=hdr)
    return Response(xml, status_code=207, media_type="application/xml; charset=utf-8", headers=hdr)


@app.get("/contacts.mobileconfig", include_in_schema=False)
def dav_profile():
    """The one-tap setup for a Mac or an iPhone: the server's name only; it asks for the church login."""
    from . import macs as _m
    return Response(carddav.mobileconfig(_m.server_names()["host"]), media_type="application/x-apple-aspen-config",
                    headers={"Content-Disposition": 'attachment; filename="Arise Church contacts.mobileconfig"'})


@app.get("/api/contacts")
def api_contacts(_=admin):
    """Where the address book is and how to add it, for Directory (admins hand it to staff)."""
    from . import macs as _m
    return carddav.info(_m.server_names()["host"])
# ===== end round 7 contacts =====


# ----- the dashboard -----------------------------------------------------------
WEB = cfg.web_dir
if WEB.is_dir():
    app.mount("/assets", StaticFiles(directory=str(WEB)), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, {"message": "no such route"})
        f = WEB / path
        if path and f.is_file():
            return FileResponse(str(f))
        return FileResponse(str(WEB / "index.html"))

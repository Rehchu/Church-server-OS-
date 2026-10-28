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

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import VERSION, CODENAME, apps, automator, backups, bible, church, devices, directory, files, mail, metrics, nas, push, remote, routers, security, sermons, services, shares, sites, system, twofa
from . import activity, automations, monitor, storage, updates
from . import auth as _auth
from . import links
from . import calendar as churchcal
from . import help as helpdocs
from . import weather
from . import finder
from .auth import COOKIE, check_password_for, current_user, login, reauth_token, require_admin, require_recent_auth
from .config import load
from .util import human_bytes

cfg = load()
app = FastAPI(title="Arise Server", version=VERSION, docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
metrics.start()
_started = time.time()
if not cfg.demo:
    push.watch(lambda: overview.__wrapped__() if hasattr(overview, "__wrapped__") else _attention_now())
    security.rescue_watch()  # a push the moment the break-glass account signs in

auth = Depends(current_user)      # any signed-in person; members are limited to the portal routes by auth._check_path
admin = Depends(require_admin)    # the administrator only
recent = Depends(require_recent_auth)  # typed the password again within five minutes (delete a user, empty a Trash, shut down)


@app.exception_handler(HTTPException)
async def _http_exc(_req, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    return JSONResponse({"error": detail}, status_code=exc.status_code)


# ----- auth ------------------------------------------------------------------
class Login(BaseModel):
    user: str
    password: str


@app.post("/api/auth/login")
def api_login(body: Login, response: Response):
    c = load()
    if not c.demo and not c.web.admin_password_hash:
        raise HTTPException(401, {"setup": True, "message": "No admin password yet. On the server run: sudo arisectl admin set-password"})
    got = login(body.user, body.password)
    if not got:
        if c.demo:  # sample mode: unknown names become the admin, as before
            got = (None, {"user": "demo", "role": "admin", "via": "demo"})
        else:
            time.sleep(0.8)  # slow down guessing
            raise HTTPException(401, {"message": "Wrong user or password"})
    tok, who = got
    if tok and not c.demo and twofa.enrolled(who["user"]):
        # Two-step is on for this person: the session token waits behind a code (five minutes, three tries).
        return {"ok": True, "need_code": True, "pending": twofa.pending_token(tok, who["user"]), "user": who["user"]}
    if tok:
        response.set_cookie(COOKIE, tok, httponly=True, samesite="lax", max_age=int(c.web.session_hours) * 3600)
    if not c.demo and who.get("via") != "demo":
        files.ensure_home(who["user"])   # Documents, Photos, Videos, Music, Downloads from the first sign-in
    return {"ok": True, "user": who["user"], "role": who["role"], "demo": c.demo}


class LoginCode(BaseModel):
    pending: str
    code: str


@app.post("/api/auth/login/code")
def api_login_code(body: LoginCode, response: Response):
    """The second step: the six digits from Microsoft Authenticator."""
    c = load()
    if c.demo:
        return {"ok": True, "demo": True, "user": "demo", "role": "admin"}
    r = twofa.finish(body.pending, body.code)
    if not r.get("ok"):
        time.sleep(0.5)
        raise HTTPException(401, {"message": r.get("err", "wrong code"), "left": r.get("left", 0), "expired": r.get("expired", False)})
    response.set_cookie(COOKIE, r["token"], httponly=True, samesite="lax", max_age=int(c.web.session_hours) * 3600)
    return {"ok": True, "user": r["user"]}


class Reauth(BaseModel):
    password: str


@app.post("/api/auth/reauth")
def api_reauth(body: Reauth, request: Request, response: Response, who=auth):
    """The dangerous clicks ask for the password again; a yes is remembered five minutes (the 'ra' stamp in the cookie)."""
    c = load()
    if c.demo:
        return {"ok": True, "demo": True, "until": 300}
    if not check_password_for(who["user"], body.password):
        time.sleep(0.8)
        raise HTTPException(401, {"message": "That is not your password"})
    tok = reauth_token(request)
    if not tok:
        raise HTTPException(401, {"message": "Sign in again"})
    response.set_cookie(COOKIE, tok, httponly=True, samesite="lax", max_age=int(c.web.session_hours) * 3600)
    return {"ok": True, "until": 300}


@app.post("/api/auth/logout")
def api_logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
def api_me(request: Request):
    try:
        who = dict(current_user(request))
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    who["groups"] = directory.user_groups(who["user"]) if who["user"] != "demo" else ["Domain Admins"]
    who["roots"] = files.roots(who)
    who["links_days"] = load().links.days
    return who


class PasswordChange(BaseModel):
    old: str
    new: str


@app.post("/api/me/password")
def api_me_password(body: PasswordChange, who=auth):
    """Anyone changes their own directory password; the local admin password is arisectl's."""
    c = load()
    if len(body.new) < 8:
        return {"ok": False, "err": "at least 8 characters"}
    if c.demo:
        return {"ok": True, "demo": True}
    if who["user"] == c.web.admin_user and not directory.authenticate(who["user"], body.old):
        if c.web.admin_password_hash and __import__("arise_server.auth", fromlist=["verify_password"]).verify_password(body.old, c.web.admin_password_hash):
            return {"ok": False, "err": "That is the local dashboard password: change it on the server with sudo arisectl admin set-password"}
    if not directory.authenticate(who["user"], body.old):
        time.sleep(0.8)
        return {"ok": False, "err": "current password is wrong"}
    return directory.set_password(who["user"], body.new)


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
def overview(_=auth):
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
    # Disks at 75 % say so (Bradly, Oct 28); the sample box has room, so the preview shows none.
    if not c.demo:
        try:
            items.extend(storage.disk_alerts())
        except Exception:  # noqa: BLE001
            pass
    return items


@app.get("/api/stats/stream")
async def stats_stream(_=auth):
    return StreamingResponse(metrics.sse(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/stats/history")
def stats_history(_=auth):
    return {"history": metrics.history(), "latest": metrics.latest(), "machine": metrics.static_info()}


# ----- services + logs -------------------------------------------------------
@app.get("/api/services")
def api_services(_=auth):
    return services.list_services()


@app.post("/api/services/{unit}/{action}")
def api_service_act(unit: str, action: str, _=auth):
    if unit.startswith("samba-ad-dc") and action != "status":
        svc = church.in_service_now()
        if svc:
            return {"ok": False, "err": f"Not during {svc['name']}: the domain stays up until about {svc['ends_at']}."}
    return services.act(unit, action)


@app.get("/api/logs/sources")
def api_log_sources(_=auth):
    return services.log_sources()


@app.get("/api/logs/file/{name}")
def api_log_file(name: str, lines: int = 300, _=auth):
    return services.log_file(name, lines)


@app.get("/api/logs/{unit}")
def api_logs(unit: str, lines: int = 200, _=auth):
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
def api_updates_status(_=auth):
    return updates.status()


@app.post("/api/updates/refresh")
def api_updates_refresh(_=auth):
    r = updates.refresh()
    r["status"] = updates.status()
    return r


@app.post("/api/updates/check-apps")
def api_updates_check_apps(_=auth):
    return updates.check_apps()


@app.post("/api/updates/queue")
def api_updates_queue(body: QueueBody, who=auth):
    return updates.set_queue(body.packages, body.apps, body.reboot, who.get("user", ""))


@app.post("/api/updates/apply")
def api_updates_apply(body: ApplyBody, _=auth):
    if body.confirm != "install":
        return {"ok": False, "err": "type install to confirm"}
    return updates.apply(no_snapshot=body.no_snapshot, log=lambda *_a: None)


@app.get("/api/activity")
def api_activity(_=auth):
    return activity.snapshot()


class KillBody(BaseModel):
    pid: int
    confirm: str = ""


@app.post("/api/activity/kill")
def api_activity_kill(body: KillBody, _=auth):
    return activity.kill(body.pid, body.confirm)


@app.get("/api/automations")
def api_automations(_=auth):
    return automations.list_automations()


class TimerBody(BaseModel):
    confirm: str = ""


@app.post("/api/automations/{timer}/{action}")
def api_automations_act(timer: str, action: str, body: TimerBody, _=auth):
    if action not in ("pause", "resume"):
        return {"ok": False, "err": "action must be pause or resume"}
    return automations.pause(timer, action == "resume", body.confirm)


@app.get("/api/storage")
def api_storage(_=auth):
    r = storage.status()
    for m in r.get("mounts", []):
        m["total_h"], m["used_h"], m["free_h"] = human_bytes(m.get("total")), human_bytes(m.get("used")), human_bytes(m.get("free"))
    return r


@app.post("/api/storage/scan")
def api_storage_scan(_=auth):
    return storage.scan()


@app.get("/api/monitor")
def api_monitor(_=auth):
    return monitor.status()


class MonitorBody(BaseModel):
    on: bool = True


@app.post("/api/monitor/power")
def api_monitor_power(body: MonitorBody, _=auth):
    return monitor.power(body.on)


# ----- directory ---------------------------------------------------------------
class NewUser(BaseModel):
    name: str
    password: str
    display: str = ""
    groups: list[str] = []


class Password(BaseModel):
    password: str


class Confirm(BaseModel):
    confirm: str = ""


class NewGroup(BaseModel):
    name: str
    description: str = ""


class Member(BaseModel):
    user: str


@app.get("/api/directory/status")
def dir_status(_=auth):
    return directory.status()


@app.get("/api/directory/users")
def dir_users(_=auth):
    return directory.list_users()


@app.post("/api/directory/users")
def dir_user_add(body: NewUser, _=auth):
    return directory.add_user(body.name, body.password, body.display, body.groups)


@app.post("/api/directory/users/{name}/reset-password")
def dir_user_pw(name: str, body: Password, _=auth):
    return directory.set_password(name, body.password)


@app.post("/api/directory/users/{name}/enable")
def dir_user_enable(name: str, _=auth):
    return directory.enable_user(name, True)


@app.post("/api/directory/users/{name}/disable")
def dir_user_disable(name: str, _=auth):
    return directory.enable_user(name, False)


@app.delete("/api/directory/users/{name}")
def dir_user_del(name: str, body: Confirm, _=recent):
    return directory.delete_user(name, body.confirm)


@app.get("/api/directory/groups")
def dir_groups(_=auth):
    return directory.list_groups()


@app.post("/api/directory/groups")
def dir_group_add(body: NewGroup, _=auth):
    return directory.add_group(body.name, body.description)


@app.post("/api/directory/groups/{group}/members")
def dir_group_member(group: str, body: Member, _=auth):
    return directory.add_member(group, body.user)


@app.delete("/api/directory/groups/{group}/members/{user}")
def dir_group_member_del(group: str, user: str, _=auth):
    return directory.remove_member(group, user)


@app.get("/api/directory/computers")
def dir_computers(_=auth):
    return directory.list_computers()


# ----- shares ------------------------------------------------------------------
class NewShare(BaseModel):
    name: str
    path: str
    comment: str = ""
    group: str = "Domain Users"
    mac: bool = True


@app.get("/api/shares")
def api_shares(_=auth):
    r = shares.list_shares()
    for s in r["shares"]:
        s["used_h"] = human_bytes(s.get("used"))
    return r


@app.post("/api/shares")
def api_share_add(body: NewShare, _=auth):
    return shares.add_share(body.name, body.path, body.comment, body.group, body.mac)


@app.delete("/api/shares/{name}")
def api_share_del(name: str, body: Confirm, _=auth):
    return shares.remove_share(name, body.confirm)


# ----- backups -----------------------------------------------------------------
@app.get("/api/backups/jobs")
def bk_jobs(_=auth):
    return backups.jobs()


@app.get("/api/backups/history")
def bk_history(limit: int = 200, _=auth):
    return backups.history(limit)


@app.get("/api/backups/snapshots")
def bk_snapshots(limit: int = 100, _=auth):
    return backups.snapshots(limit)


@app.get("/api/backups/repo")
def bk_repo(_=auth):
    return backups.repo()


@app.post("/api/backups/run/{job}")
def bk_run(job: str, _=auth):
    return backups.run_job(job)


@app.post("/api/backups/mirror")
def bk_mirror(_=auth):
    return backups.mirror_github()


@app.post("/api/backups/check")
def bk_check(_=auth):
    return backups.check()


# ----- automator ---------------------------------------------------------------
@app.get("/api/automator")
def auto_overview(_=auth):
    return automator.overview()


@app.get("/api/automator/reports")
def auto_reports(_=auth):
    return {"reports": automator.overview().get("reports", [])}


@app.get("/api/automator/reports/{name}")
def auto_report(name: str, _=auth):
    return automator.report(name)


@app.get("/api/automator/worklist")
def auto_worklist(_=auth):
    return automator.worklist()


@app.get("/api/automator/holds")
def auto_holds(_=auth):
    return automator.holds()


@app.get("/api/automator/quota")
def auto_quota(_=auth):
    return automator.quota()


@app.post("/api/automator/run")
def auto_run(_=auth):
    return automator.start("run")


@app.post("/api/automator/preview")
def auto_preview(_=auth):
    return automator.start("preview")


# ----- apps --------------------------------------------------------------------
class Deploy(BaseModel):
    template: str
    name: Optional[str] = None
    env: dict = {}


@app.get("/api/apps")
def api_apps(_=auth):
    r = apps.list_apps()
    for a in r["apps"]:
        a["mem_h"] = human_bytes(a.get("mem"))
    return r


@app.get("/api/apps/templates")
def api_templates(_=auth):
    return apps.templates()


@app.get("/api/apps/catalog")
def api_catalog(_=auth):
    return apps.catalog()


@app.get("/api/apps/theme/{name}")
def api_app_theme(name: str, _=auth):
    return apps.theme_for(name)


# Members may ask where Notes (Trilium) and Photos (Immich) answer; nothing else about apps.
_auth.MEMBER_OK = tuple(_auth.MEMBER_OK) + ("/api/apps/open/",)


@app.get("/api/apps/open/{name}")
def api_app_open(name: str, _=auth):
    if name not in ("trilium", "immich"):
        return {"ok": False, "err": "only the Notes and Photos apps open this way"}
    return apps.open_url(name)


@app.post("/api/apps/deploy")
def api_deploy(body: Deploy, _=auth):
    return apps.deploy(body.template, body.name, body.env)


class AutostartBody(BaseModel):
    on: bool = True


@app.post("/api/apps/{name}/autostart")
def api_app_autostart(name: str, body: AutostartBody, _=auth):
    return apps.set_autostart(name, body.on)


@app.post("/api/apps/{name}/{action}")
def api_app_act(name: str, action: str, body: Confirm | None = None, _=auth):
    return apps.act(name, action, (body.confirm if body else ""))


@app.get("/api/apps/{name}/logs")
def api_app_logs(name: str, lines: int = 200, _=auth):
    return apps.logs(name, lines)


# ----- nas + settings ----------------------------------------------------------
@app.get("/api/nas")
def api_nas(_=auth):
    r = nas.status()
    for k in ("total", "used", "free"):
        r[k + "_h"] = human_bytes(r.get(k))
    return r


@app.post("/api/nas/mount")
def api_nas_mount(_=auth):
    return nas.mount()


@app.post("/api/nas/unmount")
def api_nas_unmount(_=auth):
    return nas.unmount()


@app.get("/api/settings")
def api_settings(_=auth):
    return load().public()


@app.get("/api/health")
def api_health():
    return {"ok": True, "version": VERSION, "demo": load().demo}



# ----- v0.2: campuses, remote access, bible, sermons, files, system, terminal ----
@app.get("/api/sites")
def api_sites(_=auth):
    return sites.status(directory.list_computers()["computers"])


@app.get("/api/remote")
def api_remote(_=auth):
    return remote.overview()


class PeerName(BaseModel):
    name: str


@app.post("/api/remote/wireguard/peers")
def api_remote_peer(body: PeerName, _=auth):
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
    return FileResponse(p, filename=os.path.basename(p))


@app.get("/api/files/view")
def api_files_view(root: str, path: str, who=auth):
    """Inline (for Quick Look); download sets an attachment header, this does not."""
    p = files.file_path(root, path, who)
    if not p:
        raise HTTPException(404, {"message": "no such file"})
    return FileResponse(p)


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
def api_files_trash_empty(body: TrashEmpty, who=admin):
    return finder.trash_empty(body.share, body.confirm, who)


@app.get("/api/files/versions")
def api_files_versions(root: str = "data", path: str = "/", who=auth):
    """The nightly copies the backup holds of one file this person may reach."""
    got = finder._abs(root, path, who)
    if load().demo:
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
        return backups.restore_version("/srv/arise" + body.path, body.snapshot, who)
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


@app.post("/api/kiosk/open")
def api_kiosk_open(body: OpenUrl, request: Request, who=auth):
    """Only the kiosk itself (localhost) may ask the monitor to open a site."""
    host = (request.client.host if request.client else "") or ""
    if host not in ("127.0.0.1", "::1") and not load().demo:
        return {"ok": False, "err": "only the closet monitor can open windows on itself; from a browser the site opens in a new tab"}
    return church.open_on_kiosk(body.url)


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


@app.get("/api/calendar")
def api_calendar(year: int = 0, month: int = 0, _=auth):
    from datetime import datetime as _dt
    now = _dt.now()
    y, m = (year or now.year), (month or now.month)
    if not 1 <= m <= 12 or not 2000 <= y <= 2100:
        raise HTTPException(400, {"message": "year/month out of range"})
    return {**churchcal.month(y, m), "upcoming": churchcal.upcoming(14), "services": church.info()["services"]}


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
def api_mail(_=auth):
    return {**mail.status(), "import": mail.import_status()}


@app.get("/api/mail/contacts")
def api_mail_contacts(_=auth):
    return mail.contacts()


@app.post("/api/mail/import/preview")
def api_mail_import_preview(body: MailImport, _=auth):
    r = mail.parse_contacts(body.csv)
    return {"count": len(r["contacts"]), "skipped": r["skipped"], "columns": r.get("columns"), "err": r.get("err"), "sample": r["contacts"][:5]}


@app.post("/api/mail/import")
def api_mail_import(body: MailImport, _=auth):
    r = mail.parse_contacts(body.csv)
    if r.get("err"):
        return {"ok": False, "err": r["err"]}
    return mail.import_contacts(r["contacts"])


@app.post("/api/mail/preview")
def api_mail_preview(body: MailDraft, _=auth):
    c = church.info()
    # the merge tags are Resend's; show the preview the way a reader named nobody sees it
    return {"html": mail.render(body.subject, body.body, c["name"], c["city"]).replace("{{{FIRST_NAME|there}}}", "there").replace("{{{RESEND_UNSUBSCRIBE_URL}}}", "#")}


@app.post("/api/mail/test")
def api_mail_test(body: MailTest, _=auth):
    return mail.send_test(body.to, body.subject, body.body)


@app.post("/api/mail/broadcasts")
def api_mail_broadcast(body: MailDraft, _=auth):
    return mail.create_broadcast(body.subject, body.body, body.name)


@app.post("/api/mail/broadcasts/{bc_id}/send")
def api_mail_broadcast_send(bc_id: str, body: MailSend, _=auth):
    return mail.send_broadcast(bc_id, body.confirm)


@app.get("/api/mail/broadcasts")
def api_mail_broadcasts(_=auth):
    return mail.broadcasts()


# ----- everything on the switch --------------------------------------------------
class DeviceLabel(BaseModel):
    name: Optional[str] = None
    note: Optional[str] = None
    kind: Optional[str] = None


@app.get("/api/devices")
def api_devices(_=auth):
    return devices.list_devices()


@app.get("/api/devices/behind")
def api_devices_behind(_=auth):
    """What the other routers report as attached, read from them (never written)."""
    return routers.behind()


@app.post("/api/devices/scan")
def api_devices_scan(wide: int = 0, _=auth):
    return devices.scan(wide=bool(wide))


@app.get("/api/devices/cameras")
def api_devices_cameras(_=auth):
    """ONVIF discovery: which cameras answer on the wire, and whether this network can reach them."""
    return devices.find_cameras()


@app.post("/api/devices/{mac}")
def api_devices_label(mac: str, body: DeviceLabel, _=auth):
    return devices.label(mac, body.name, body.note, body.kind)


@app.delete("/api/devices/{mac}")
def api_devices_forget(mac: str, _=auth):
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
def api_updates(_=auth):
    return system.updates()


@app.post("/api/system/update")
def api_update(_=auth):
    return system.update_arise()


@app.post("/api/system/apt-upgrade")
def api_apt_upgrade(_=auth):
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
def api_notify_test(_=auth):
    c = load()
    if c.demo:
        return {"ok": True, "demo": True}
    return system.send_webhook("Arise Server: test note from the dashboard. If you can read this, the daily 07:00 note will arrive here.")


@app.get("/api/notify")
def api_notify(_=auth):
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

"""The FastAPI app: /api/* JSON routes and the dashboard at /.

Routes follow docs/ARCHITECTURE.md. Every mutating route needs a session
(or demo mode). Every module answers with sample data when its tool is
missing, so this app runs anywhere Python runs.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import VERSION, CODENAME, apps, automator, backups, directory, metrics, nas, services, shares
from .auth import COOKIE, current_user, login
from .config import load
from .util import human_bytes

cfg = load()
app = FastAPI(title="Arise Server", version=VERSION, docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
metrics.start()
_started = time.time()

auth = Depends(current_user)


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
    if c.demo:
        return {"ok": True, "user": "demo", "demo": True}
    if not c.web.admin_password_hash:
        raise HTTPException(401, {"setup": True, "message": "No admin password yet. On the server run: sudo arisectl admin set-password"})
    tok = login(body.user, body.password)
    if not tok:
        time.sleep(0.8)  # slow down guessing
        raise HTTPException(401, {"message": "Wrong user or password"})
    response.set_cookie(COOKIE, tok, httponly=True, samesite="lax", max_age=int(c.web.session_hours) * 3600)
    return {"ok": True, "user": body.user, "demo": False}


@app.post("/api/auth/logout")
def api_logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
def api_me(request: Request):
    try:
        return current_user(request)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)


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


def _attention(c, bad, auto, failed_backups, n, d) -> list[dict]:
    items = []
    if not c.found:
        items.append({"level": "warn", "text": f"No config at {c.path}: running on defaults with sample data. Run the installer or `arisectl doctor`."})
    if not c.web.admin_password_hash and not c.demo:
        items.append({"level": "bad", "text": "No admin password set. Run: sudo arisectl admin set-password"})
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
    return services.act(unit, action)


@app.get("/api/logs/{unit}")
def api_logs(unit: str, lines: int = 200, _=auth):
    return services.journal(unit, lines)


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
def dir_user_del(name: str, body: Confirm, _=auth):
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


@app.post("/api/apps/deploy")
def api_deploy(body: Deploy, _=auth):
    return apps.deploy(body.template, body.name, body.env)


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

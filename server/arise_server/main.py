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

from . import VERSION, CODENAME, apps, automator, backups, bible, devices, directory, files, metrics, nas, remote, sermons, services, shares, sites, system
from . import links
from .auth import COOKIE, current_user, login, require_admin
from .config import load
from .util import human_bytes

cfg = load()
app = FastAPI(title="Arise Server", version=VERSION, docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
metrics.start()
_started = time.time()

auth = Depends(current_user)      # any signed-in person; members are limited to the portal routes by auth._check_path
admin = Depends(require_admin)    # the administrator only


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
    if tok:
        response.set_cookie(COOKIE, tok, httponly=True, samesite="lax", max_age=int(c.web.session_hours) * 3600)
    return {"ok": True, "user": who["user"], "role": who["role"], "demo": c.demo}


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
    ql = q.strip().lower()
    if who.get("role") == "admin":
        out["users"] = [u for u in directory.list_users()["users"] if ql and (ql in u["name"].lower() or ql in (u.get("display") or "").lower())][:8]
        out["computers"] = [c for c in directory.list_computers()["computers"] if ql and ql in c["name"].lower()][:8]
    else:
        out["users"], out["computers"] = [], []
    return out


@app.post("/api/files/upload")
async def api_files_upload(root: str = Form("data"), path: str = Form("/"), file: UploadFile = File(...), who=auth):
    data = await file.read()
    if len(data) > 2 * 1024 ** 3:
        return {"ok": False, "err": "2 GB limit here; use the share for bigger files"}
    return files.save_upload(root, path, file.filename or "", data, who)


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


# ----- everything on the switch --------------------------------------------------
class DeviceLabel(BaseModel):
    name: Optional[str] = None
    note: Optional[str] = None
    kind: Optional[str] = None


@app.get("/api/devices")
def api_devices(_=auth):
    return devices.list_devices()


@app.post("/api/devices/scan")
def api_devices_scan(_=auth):
    return devices.scan()


@app.post("/api/devices/{mac}")
def api_devices_label(mac: str, body: DeviceLabel, _=auth):
    return devices.label(mac, body.name, body.note, body.kind)


@app.delete("/api/devices/{mac}")
def api_devices_forget(mac: str, _=auth):
    return devices.forget(mac)


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
def api_power(body: Power, _=auth):
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

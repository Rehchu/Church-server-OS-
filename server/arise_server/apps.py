"""Docker Compose apps from templates/<name>/compose.yaml, like HomeDock's store."""
from __future__ import annotations

import json
import os
import re
import shutil

import yaml

from . import demo
from .config import load
from .util import run, which

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")


def available() -> bool:
    cfg = load()
    return bool(which("docker")) and cfg.apps.docker and not cfg.demo and run(["docker", "info"], timeout=10)["ok"]


def templates() -> dict:
    cfg = load()
    out = []
    tdir = cfg.templates_dir
    if tdir.is_dir():
        for d in sorted(tdir.iterdir()):
            meta = d / "template.yaml"
            if not meta.exists():
                continue
            try:
                m = yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                continue
            out.append({"id": d.name, "name": m.get("title") or m.get("name", d.name), "description": m.get("description", ""), "category": m.get("category", ""),
                        "ports": [str(x) for x in m.get("ports", [])], "icon": m.get("icon", "app"), "data": m.get("data", f"{cfg.apps.root}/{d.name}"), "notes": m.get("notes", "")})
    if not out:
        return {"demo": True, "templates": demo.TEMPLATES}
    return {"demo": False, "templates": out}


def list_apps() -> dict:
    cfg = load()
    if not available():
        return {"demo": True, "apps": demo.APPS, "docker": False}
    r = run(["docker", "compose", "ls", "--all", "--format", "json"], timeout=20)
    rows = []
    try:
        rows = json.loads(r["out"] or "[]")
    except json.JSONDecodeError:
        pass
    apps = []
    stats = _stats()
    for s in rows:
        name = s.get("Name", "")
        if not str(s.get("ConfigFiles", "")).startswith(cfg.apps.root):
            continue
        st = stats.get(name, {})
        ports = _ports(name)
        apps.append({"name": name, "template": name, "status": "running" if "running" in s.get("Status", "") else "exited",
                     "ports": ports, "cpu": st.get("cpu", 0.0), "mem": st.get("mem", 0), "url": _url(ports), "updated": None})
    return {"demo": False, "apps": apps, "docker": True}


def _stats() -> dict:
    r = run(["docker", "stats", "--no-stream", "--format", "{{json .}}"], timeout=20)
    out = {}
    for line in r["out"].splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        proj = d.get("Name", "").rsplit("-", 2)[0] if "-" in d.get("Name", "") else d.get("Name", "")
        cpu = float(d.get("CPUPerc", "0%").rstrip("%") or 0)
        mem = _parse_mem(d.get("MemUsage", "0B / 0B").split("/")[0].strip())
        cur = out.setdefault(proj, {"cpu": 0.0, "mem": 0})
        cur["cpu"] = round(cur["cpu"] + cpu, 1)
        cur["mem"] += mem
    return out


def _parse_mem(s: str) -> int:
    m = re.match(r"([\d.]+)\s*([KMG]i?B)", s or "")
    if not m:
        return 0
    n, u = float(m.group(1)), m.group(2)
    mult = {"B": 1, "KiB": 1024, "KB": 1000, "MiB": 1024 ** 2, "MB": 1000 ** 2, "GiB": 1024 ** 3, "GB": 1000 ** 3}
    return int(n * mult.get(u, 1))


def _ports(project: str) -> list[str]:
    r = run(["docker", "compose", "-p", project, "ps", "--format", "json"], timeout=20)
    ports = []
    for line in r["out"].splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        for p in d.get("Publishers", []) or []:
            if p.get("PublishedPort"):
                ports.append(f"{p['PublishedPort']}:{p.get('TargetPort')}")
    return sorted(set(ports))


def _url(ports: list[str]) -> str:
    cfg = load()
    if not ports:
        return ""
    return f"http://{cfg.system.hostname}:{ports[0].split(':')[0]}"


def _template_env(template: str) -> dict:
    cfg = load()
    meta = cfg.templates_dir / template / "template.yaml"
    try:
        m = yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return {str(k): str(v) for k, v in (m.get("env") or {}).items()}


def _read_env(path: str) -> dict:
    out = {}
    try:
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.startswith("#"):
                k, _, v = line.rstrip("\n").partition("=")
                out[k] = v
    except OSError:
        pass
    return out


def fill_secrets(defaults: dict, given: dict | None = None, existing: dict | None = None) -> tuple[dict, list[str]]:
    """The env a deploy writes. A value that starts with CHANGE-ME becomes a random
    secret, unless the person gave one or an earlier deploy already made one (so a
    re-deploy never rotates a database password out from under the data).
    Returns (env, names of secrets generated now)."""
    import secrets as _s
    given = given or {}
    existing = existing or {}
    out, made = {}, []
    for k, v in defaults.items():
        if k in given and given[k]:
            out[k] = given[k]
        elif str(v).startswith("CHANGE-ME"):
            if existing.get(k) and not str(existing[k]).startswith("CHANGE-ME"):
                out[k] = existing[k]
            else:
                out[k] = _s.token_urlsafe(24)
                made.append(k)
        else:
            out[k] = v
    for k, v in given.items():
        out.setdefault(k, v)
    return out, made


def deploy(template: str, name: str | None = None, env: dict | None = None) -> dict:
    cfg = load()
    name = name or template
    if not NAME_RE.match(name):
        return {"ok": False, "err": "name: lowercase letters, digits, dashes; 2-32 chars"}
    src = cfg.templates_dir / template
    if not (src / "compose.yaml").exists():
        return {"ok": False, "err": f"no template called {template}"}
    if not available():
        return {"ok": True, "demo": True, "out": f"(demo) would deploy {template} as {name}"}
    dest = os.path.join(cfg.apps.root, name)
    os.makedirs(dest, exist_ok=True)
    shutil.copy(src / "compose.yaml", os.path.join(dest, "compose.yaml"))
    values, made = fill_secrets(_template_env(template), env, _read_env(os.path.join(dest, ".env")))
    with open(os.path.join(dest, ".env"), "w", encoding="utf-8") as f:
        f.write(f"APP_NAME={name}\nDATA={dest}/data\nSHARES={cfg.system.data_root}/shares\n")
        for k, v in values.items():
            if re.match(r"^[A-Z_][A-Z0-9_]*$", k):
                f.write(f"{k}={v}\n")
    os.chmod(os.path.join(dest, ".env"), 0o600)
    if made:
        # A copy of every generated secret, root-only, so a person can find it.
        sec_dir = "/etc/arise/secrets/apps"
        try:
            os.makedirs(sec_dir, exist_ok=True)
            with open(os.path.join(sec_dir, f"{name}.env"), "w", encoding="utf-8") as f:
                f.write(f"# {name} ({template}): secrets the deploy generated. Same values are in {dest}/.env\n")
                for k in made:
                    f.write(f"{k}={values[k]}\n")
            os.chmod(os.path.join(sec_dir, f"{name}.env"), 0o600)
        except OSError:
            pass
    os.makedirs(os.path.join(dest, "data"), exist_ok=True)
    pre = _pre_deploy(template, dest, values)
    if pre and not pre.get("ok", True):
        return pre
    r = run(["docker", "compose", "-p", name, "-f", os.path.join(dest, "compose.yaml"), "--env-file", os.path.join(dest, ".env"), "up", "-d"], timeout=1800)
    r["secrets_generated"] = made
    return r


def _pre_deploy(template: str, dest: str, values: dict) -> dict | None:
    """The one-time steps a template's notes describe, done by the machine."""
    if template == "guacamole":
        initdb = os.path.join(dest, "initdb")
        os.makedirs(initdb, exist_ok=True)
        if not os.listdir(initdb):
            img = "guacamole/guacamole:1.5.5"
            r = run(["docker", "run", "--rm", img, "/opt/guacamole/bin/initdb.sh", "--postgresql"], timeout=600)
            if not r["ok"]:
                return {"ok": False, "err": "guacamole initdb failed: " + (r["err"] or r["out"])[:300]}
            with open(os.path.join(initdb, "001-initdb.sql"), "w", encoding="utf-8") as f:
                f.write(r["out"])
        for sub in ("drive", "record", "db"):
            os.makedirs(os.path.join(dest, sub), exist_ok=True)
    if template == "synapse":
        data = os.path.join(dest, "data")
        if not os.path.exists(os.path.join(data, "homeserver.yaml")):
            r = run(["docker", "run", "--rm", "-v", f"{data}:/data", "-e", "SYNAPSE_SERVER_NAME=arise-server", "-e", "SYNAPSE_REPORT_STATS=no", "matrixdotorg/synapse:v1.113.0", "generate"], timeout=600)
            if not r["ok"]:
                return {"ok": False, "err": "synapse generate failed: " + (r["err"] or r["out"])[:300]}
    if template == "nginx-rtmp":
        conf = os.path.join(dest, "nginx.conf")
        if not os.path.exists(conf):
            with open(conf, "w", encoding="utf-8") as f:
                f.write("worker_processes auto;\nevents { worker_connections 1024; }\n"
                        "rtmp { server { listen 1935; chunk_size 4096; application live { live on; record off;\n"
                        "  # push rtmp://a.rtmp.youtube.com/live2/YOUR-KEY;\n  # push rtmp://arise-server:1935/live/OWNCAST-KEY;\n} } }\n"
                        "http { server { listen 80; location /stat { rtmp_stat all; } } }\n")
    return None


def act(name: str, action: str, confirm: str = "") -> dict:
    cfg = load()
    if not NAME_RE.match(name or ""):
        return {"ok": False, "err": "bad app name"}
    if action not in ("start", "stop", "restart", "remove", "update"):
        return {"ok": False, "err": "action must be start|stop|restart|remove|update"}
    if action == "remove" and confirm != name:
        return {"ok": False, "err": "type the app name to confirm; the data folder is kept"}
    if not available():
        return {"ok": True, "demo": True, "out": f"(demo) docker compose {action} {name}"}
    dest = os.path.join(cfg.apps.root, name)
    base = ["docker", "compose", "-p", name, "-f", os.path.join(dest, "compose.yaml"), "--env-file", os.path.join(dest, ".env")]
    if action == "remove":
        return run(base + ["down"], timeout=300)
    if action == "update":
        r = run(base + ["pull"], timeout=1800)
        if not r["ok"]:
            return r
        return run(base + ["up", "-d"], timeout=600)
    return run(base + [action], timeout=300)


def logs(name: str, lines: int = 200) -> dict:
    if not NAME_RE.match(name or ""):
        return {"text": "bad app name"}
    if not available():
        return {"demo": True, "name": name, "text": f"(demo) {name} | server listening on :80\n(demo) {name} | GET / 200"}
    cfg = load()
    dest = os.path.join(cfg.apps.root, name)
    r = run(["docker", "compose", "-p", name, "-f", os.path.join(dest, "compose.yaml"), "logs", "--no-color", "--tail", str(min(lines, 2000))], timeout=30)
    return {"demo": False, "name": name, "text": r["out"] or r["err"]}

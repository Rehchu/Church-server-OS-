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
    with open(os.path.join(dest, ".env"), "w", encoding="utf-8") as f:
        f.write(f"APP_NAME={name}\nDATA={dest}/data\nSHARES={cfg.system.data_root}/shares\n")
        for k, v in (env or {}).items():
            if re.match(r"^[A-Z_][A-Z0-9_]*$", k):
                f.write(f"{k}={v}\n")
    os.makedirs(os.path.join(dest, "data"), exist_ok=True)
    return run(["docker", "compose", "-p", name, "-f", os.path.join(dest, "compose.yaml"), "--env-file", os.path.join(dest, ".env"), "up", "-d"], timeout=900)


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

"""Docker Compose apps: the church's templates (templates/<name>/) and the Store's
catalogue (catalog/catalog.yaml) of further free apps, like HomeDock's store.

v0.8 (round 3, 5 and 40): every template carries autostart, ram_mb and limits;
a deploy writes per-service memory/CPU limits and admits starts using their
aggregate memory caps, leaving core-service headroom. The installer deploys
the selected templates and starts those within this budget; each remembers its autostart choice in
/srv/arise/apps/<name>/arise.json."""
from __future__ import annotations

import json
import os
import re
import shutil
import math
import threading
from functools import wraps
from pathlib import Path

import yaml

from . import demo, demo_state
from .config import load
from .util import now_iso, read_json, run, run_stream, which, write_json

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
RESERVE_MB = 2048          # what the domain, Samba, the dashboard and the kiosk keep for themselves
DEFAULT_LIMITS = {"mem_mb": 512, "cpus": 1.0}
APP_SECRETS_DIR = Path("/etc/arise/secrets/apps")
_mutation_lock = threading.RLock()
_lock_state = threading.local()


def _serialized(fn):
    """Budget decisions and starts are one transaction across CLI/web processes."""
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if load().demo:
            return fn(*args, **kwargs)
        from .maintenance import exclusive, MaintenanceBusy
        try:
            with exclusive("apps"):
                with _mutation_lock:
                    if getattr(_lock_state, "held", False):
                        return fn(*args, **kwargs)
                    root = Path(load().apps.root)
                    root.mkdir(parents=True, exist_ok=True)
                    with (root / ".operations.lock").open("a") as lock:
                        if os.name == "posix":
                            import fcntl
                            fcntl.flock(lock, fcntl.LOCK_EX)
                        _lock_state.held = True
                        try:
                            return fn(*args, **kwargs)
                        finally:
                            _lock_state.held = False
        except MaintenanceBusy as e:
            return {"ok": False, "err": str(e)}
    return wrapped


def compose_cap_mb(doc: dict) -> int:
    """Sum actual per-service hard limits; missing/unparseable caps fail closed."""
    total = 0
    services = doc.get("services") or {}
    if not services:
        raise ValueError("compose has no services")
    for name, service in services.items():
        raw = str(service.get("mem_limit", ""))
        m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([bkmg]?)b?", raw, re.I)
        if not m:
            raise ValueError(f"{name}: a valid positive mem_limit is required")
        size = float(m[1]) * {"": 1, "b": 1, "k": 1024, "m": 1024**2, "g": 1024**3}[m[2].lower()]
        if size <= 0:
            raise ValueError(f"{name}: mem_limit must be positive")
        total += math.ceil(size / 1024**2)
    return total


def _docker_allocations() -> list[dict]:
    """Read only non-secret fields, including stopped containers set to restart."""
    r = run(["docker", "ps", "-aq"], timeout=20)
    if not r["ok"]:
        raise ValueError("cannot inspect Docker's existing memory allocations")
    ids = r["out"].split()
    if not ids:
        return []
    fmt = '{"id":{{json .Id}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},"running":{{json .State.Running}},"restart":{{json .HostConfig.RestartPolicy.Name}},"memory":{{json .HostConfig.Memory}}}'
    r = run(["docker", "inspect", "--format", fmt, *ids], timeout=30)
    if not r["ok"]:
        raise ValueError("cannot inspect Docker's existing memory allocations")
    try:
        rows = [json.loads(line) for line in r["out"].splitlines() if line.strip()]
        if len(rows) != len(ids) or any(not isinstance(c, dict) or not c.get("id")
                                      or not isinstance(c.get("running"), bool)
                                      or not isinstance(c.get("memory"), int)
                                      or not isinstance(c.get("restart"), str) for c in rows):
            raise ValueError("incomplete Docker allocation response")
        return rows
    except (ValueError, TypeError) as e:
        raise ValueError("Docker returned unreadable allocation data") from e


def _budget_guard(name: str, doc: dict) -> dict:
    try:
        wanted = compose_cap_mb(doc)
        others = [c for c in _docker_allocations() if c.get("project") != name
                  and (c.get("running") or c.get("restart") in ("always", "unless-stopped"))]
        if any(int(c.get("memory") or 0) <= 0 for c in others):
            return {"ok": False, "err": "An existing running/autostart container has no memory cap. Set its cap before starting another app."}
        allocated = sum(math.ceil(int(c["memory"]) / 1024**2) for c in others)
    except (ValueError, TypeError, KeyError) as e:
        return {"ok": False, "err": str(e)}
    budget = max(0, ram_total_mb() - RESERVE_MB)
    if allocated + wanted > budget:
        return {"ok": False, "err": f"{name} needs {wanted} MiB of container caps; {allocated} MiB already allocated, {budget} MiB app budget. Stop apps and turn their autostart off, or add RAM. {RESERVE_MB} MiB is reserved for core services."}
    return {"ok": True, "cap_mb": wanted, "allocated_mb": allocated, "budget_mb": budget}


def _restart_policy(doc: dict, enabled: bool) -> None:
    for service in doc.get("services", {}).values():
        service["restart"] = "unless-stopped" if enabled else "no"

# The house look (Bradly, Oct 28: a theme pack per app). What an app can take
# is in its manifest's `theme:` block; these are the values that go in.
HOUSE = {"red": "#D6222D", "redL": "#DB3F48", "ink": "#0A0A0C", "paper": "#F4F2F0", "name": "Arise Church", "city": "Pineville, LA",
         "fonts": "Anton, Oswald", "logo": "/opt/arise/web/icons/icon-512.png", "logo_url": "http://arise-server:4147/icons/icon-512.png"}


def house_css() -> str:
    """The CSS an app with a custom-CSS field gets pasted (Jellyfin, Immich, Owncast,
    BookStack's head, Homepage). Small on purpose: colours and type, not a redesign."""
    return ("/* ariseOS house look: red on ink, Anton for headings, Oswald for text */\n"
            "@import url('https://fonts.googleapis.com/css2?family=Anton&family=Oswald:wght@300;400;500;600&display=swap');\n"
            f":root{{--arise-red:{HOUSE['red']};--arise-ink:{HOUSE['ink']};--arise-paper:{HOUSE['paper']};}}\n"
            "body{font-family:'Oswald',Helvetica,Arial,sans-serif;}\n"
            "h1,h2,h3,.title,.headline{font-family:'Anton',Impact,'Arial Black',sans-serif;letter-spacing:.04em;text-transform:uppercase;}\n"
            f"a,.link,.emby-button-foreground,.primary{{color:{HOUSE['red']};}}\n"
            f"button.primary,.btn-primary,.button-submit,.emby-button.raised.button-submit{{background:{HOUSE['red']};border-color:{HOUSE['red']};color:#fff;}}\n"
            f".skinHeader,.headerTop,.navbar,.app-header{{background:{HOUSE['ink']};border-bottom:3px solid {HOUSE['red']};}}\n")


def _fill(s: str) -> str:
    out = str(s)
    for k, v in HOUSE.items():
        out = out.replace("{{" + k + "}}", v)
    return out.replace("{{css}}", house_css())


def theme_plan(meta: dict) -> dict:
    """What the deploy does for an app's look, from its manifest's `theme:` block. Pure.
    via: none (keeps its own look) | env | files | commands | css | settings."""
    t = meta.get("theme")
    if not t or t == "none":
        return {"via": "none", "accepts": [], "env": {}, "files": {}, "commands": [], "css": None, "note": "keeps its own look"}
    via = str(t.get("via", "settings"))
    accepts = [str(a) for a in (t.get("accepts") or [])]
    plan = {"via": via, "accepts": accepts, "env": {}, "files": {}, "commands": [], "css": None, "note": str(t.get("note", ""))}
    plan["env"] = {str(k): _fill(v) for k, v in (t.get("env") or {}).items()}
    plan["files"] = {str(k): _fill(v) for k, v in (t.get("files") or {}).items()}
    plan["commands"] = [[_fill(x) for x in c] for c in (t.get("commands") or []) if isinstance(c, list)]
    if "css" in accepts or via == "css":
        plan["css"] = house_css()
    return plan


# ----- idle desktop apps (GIMP and friends stop themselves after an hour with nobody connected) -----
def idle_decision(now: float, last_active: float | None, started: float | None, conns: int, minutes: int) -> tuple[bool, float]:
    """Pure: (stop it now?, the new last-active time). A connection, or a start
    inside the window, counts as activity."""
    if minutes <= 0:
        return False, now
    if conns > 0:
        return False, now
    base = max([t for t in (last_active, started) if t is not None], default=None)
    if base is None:
        return False, now
    return (now - base) >= minutes * 60, base


def _established(ports: list[str]) -> int:
    n = 0
    for p in ports:
        host_port = str(p).split(":")[0]
        if not host_port.isdigit():
            continue
        r = run(["ss", "-Htn", "state", "established", f"( sport = :{host_port} )"], timeout=10)
        n += len([l for l in r["out"].splitlines() if l.strip()])
    return n


def idle_sweep(log=print) -> dict:
    """Stop running apps whose manifest set idle_stop_minutes once nobody has been
    connected that long. arise-idle-apps.timer runs this every 15 minutes."""
    import time
    cfg = load()
    if not available():
        if not _sample_mode():
            return {"ok": True, "demo": False, "stopped": [], "out": "Docker is not running: nothing to sweep"}
        return {"ok": True, "demo": True, "stopped": [], "out": "(sample) nothing to sweep"}
    state_p = cfg.state_dir / "idle-apps.json"
    st = read_json(state_p, default=None) or {}
    now = time.time()
    stopped = []
    for a in list_apps()["apps"]:
        meta = _app_meta(a["name"])
        minutes = int(meta.get("idle_stop_minutes") or 0)
        if not minutes or a["status"] != "running":
            st.pop(a["name"], None)
            continue
        conns = _established(a.get("ports") or [])
        started = None
        r = run(["docker", "inspect", "--format", "{{.State.StartedAt}}", f"arise-app-{a['name']}"], timeout=10)
        if r["ok"] and r["out"].strip():
            try:
                from datetime import datetime
                started = datetime.fromisoformat(r["out"].strip().replace("Z", "+00:00")[:26] + "+00:00" if "+" not in r["out"] else r["out"].strip()).timestamp()
            except ValueError:
                started = None
        stop, last = idle_decision(now, st.get(a["name"]), started, conns, minutes)
        st[a["name"]] = last
        if stop:
            res = act(a["name"], "stop")
            stopped.append({"name": a["name"], "ok": res.get("ok", False)})
            log(f"{a['name']}: nobody connected for {minutes} minutes, {'stopped' if res.get('ok') else 'stop FAILED'}")
            st.pop(a["name"], None)
    write_json(state_p, st)
    return {"ok": True, "stopped": stopped}


def available() -> bool:
    cfg = load()
    return bool(which("docker")) and cfg.apps.docker and not cfg.demo and run(["docker", "info"], timeout=10)["ok"]


DOCKER_DOWN = "Docker is not running here (docker info failed), so nothing was done: sudo systemctl start docker, then try again"


def _sample_mode() -> bool:
    """The sample apps are the preview's only. On a real box with Docker down (or Docker off in
    arise.toml) every app call says so instead: the install rehearsal found deploys "succeeding"
    into the sample list, and the Apps page listing sample apps as this box's."""
    return bool(load().demo)


# ----- the templates ----------------------------------------------------------------
def _meta_row(d_name: str, m: dict, root: str, source: str = "template") -> dict:
    lim = dict(DEFAULT_LIMITS)
    lim.update({k: v for k, v in (m.get("limits") or {}).items() if k in lim})
    tp = theme_plan(m)
    return {"id": d_name, "name": m.get("title") or m.get("name", d_name), "description": m.get("description", ""), "category": m.get("category", ""),
            "ports": [str(x) for x in m.get("ports", [])], "icon": m.get("icon", "app"), "data": m.get("data", f"{root}/{d_name}"), "notes": m.get("notes", ""),
            "version": str(m.get("version", "")), "autostart": bool(m.get("autostart", True)), "ram_mb": int(m.get("ram_mb") or lim["mem_mb"]), "limits": lim,
            "source": source, "homepage": m.get("homepage", ""), "kind": m.get("kind", "service"), "idle_stop_minutes": int(m.get("idle_stop_minutes") or 0),
            "experimental": bool(m.get("experimental", False)), "theme": {"via": tp["via"], "accepts": tp["accepts"], "note": tp["note"], "has_css": bool(tp["css"])}}


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
            except yaml.YAMLError as e:
                out.append({"id": d.name, "name": d.name, "description": f"template.yaml does not parse: {str(e).splitlines()[0][:80]}", "category": "broken", "ports": [], "icon": "app", "data": "", "notes": "", "version": "", "autostart": False, "ram_mb": 0, "limits": dict(DEFAULT_LIMITS), "source": "template", "homepage": ""})
                continue
            row = _meta_row(d.name, m, cfg.apps.root)
            try:
                doc = inject_limits(yaml.safe_load((d / "compose.yaml").read_text(encoding="utf-8")), row["limits"])
                row["cap_mb"] = compose_cap_mb(doc)
            except (OSError, ValueError, yaml.YAMLError) as e:
                row.update(category="broken", autostart=False, description=str(e))
            out.append(row)
    if not out:
        return {"demo": True, "templates": demo.TEMPLATES}
    return {"demo": False, "templates": out}


def catalog() -> dict:
    """The Store's catalogue of further free apps (catalog/catalog.yaml)."""
    cfg = load()
    p = cfg.repo_root / "catalog" / "catalog.yaml"
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        return {"demo": False, "apps": [], "error": f"catalog.yaml: {e}"}
    out = []
    for e in raw.get("apps") or []:
        if not NAME_RE.match(str(e.get("name", ""))):
            continue
        row = _meta_row(e["name"], e, cfg.apps.root, source="catalog")
        row["image"] = e.get("image", "")
        row["cap_mb"] = compose_cap_mb(inject_limits(compose_from_catalog(e), row["limits"]))
        row["autostart"] = bool(e.get("autostart", True))
        row["verify"] = True
        out.append(row)
    return {"demo": False, "apps": out}


def catalog_entry(name: str) -> dict | None:
    cfg = load()
    p = cfg.repo_root / "catalog" / "catalog.yaml"
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    return next((e for e in raw.get("apps") or [] if e.get("name") == name), None)


def compose_from_catalog(entry: dict) -> dict:
    """A catalogue entry → a compose document. Pure (the tests pin its shape).
    The main service reads every env key from the app's .env (${KEY}); extra
    services (a database beside the app) come through verbatim."""
    name = entry["name"]
    env_keys = list((entry.get("env") or {}).keys())
    svc = {"image": entry["image"], "container_name": f"arise-app-{name}", "restart": "unless-stopped"}
    if entry.get("ports"):
        svc["ports"] = [str(p) for p in entry["ports"]]
    if entry.get("volumes"):
        svc["volumes"] = list(entry["volumes"])
    if env_keys:
        svc["environment"] = [f"{k}=${{{k}}}" for k in env_keys]
    if entry.get("command"):
        svc["command"] = entry["command"]
    if entry.get("extra_services"):
        svc["depends_on"] = list(entry["extra_services"].keys())
    services = {name: svc}
    for sname, sdef in (entry.get("extra_services") or {}).items():
        services[sname] = dict(sdef)
    return {"services": services}


def inject_limits(doc: dict, limits: dict) -> dict:
    """Apply per-service defaults; admission sums the resulting hard limits."""
    lim = dict(DEFAULT_LIMITS)
    lim.update({k: v for k, v in (limits or {}).items() if k in lim})
    for _, s in (doc.get("services") or {}).items():
        if not isinstance(s, dict):
            continue
        s.setdefault("mem_limit", f"{int(lim['mem_mb'])}m")
        s.setdefault("cpus", float(lim["cpus"]))
    return doc


def autostart_plan(items: list[dict], ram_total_mb: int, reserve_mb: int = RESERVE_MB) -> dict:
    """Plan with aggregate hard caps, prioritizing required sync before optional apps."""
    budget = max(0, int(ram_total_mb) - int(reserve_mb))
    wanted = sorted([i for i in items if i.get("autostart")],
                    key=lambda i: (i["id"] != "nextcloud", int(i.get("cap_mb", i.get("ram_mb", 0)))))
    start, stopped, used = [], [], 0
    for i in wanted:
        r = int(i.get("cap_mb", i.get("ram_mb", 0)) or 0)
        if used + r <= budget:
            start.append(i["id"])
            used += r
        else:
            stopped.append({"id": i["id"], "ram_mb": r, "why": f"would take the box past its {budget} MB app budget ({used} MB already promised)"})
    for i in items:
        if not i.get("autostart"):
            stopped.append({"id": i["id"], "ram_mb": int(i.get("ram_mb") or 0), "why": "heavy or seldom used: deployed, start it from the Store when wanted"})
    return {"budget_mb": budget, "used_mb": used, "start": start, "stopped": stopped}


def ram_total_mb() -> int:
    try:
        import psutil
        return int(psutil.virtual_memory().total / 1024 ** 2)
    except Exception:  # noqa: BLE001
        return 8192


# ----- what is installed -----------------------------------------------------------
def _app_meta(name: str) -> dict:
    cfg = load()
    return read_json(os.path.join(cfg.apps.root, name, "arise.json"), default=None) or {}


@_serialized
def set_autostart(name: str, on: bool) -> dict:
    if not NAME_RE.match(name or ""):
        return {"ok": False, "err": "bad app name"}
    cfg = load()
    if cfg.demo:
        a = _sample_app(name)
        if not a:
            return {"ok": False, "err": f"{name} is not installed"}
        a["autostart"] = bool(on)
        return {"ok": True, "demo": True, "autostart": bool(on), "out": f"(sample) autostart {'on' if on else 'off'} for {name}"}
    p = os.path.join(cfg.apps.root, name, "arise.json")
    if not os.path.isdir(os.path.dirname(p)):
        return {"ok": False, "err": f"{name} is not installed"}
    if not available():
        return {"ok": False, "err": DOCKER_DOWN}
    compose_path = Path(cfg.apps.root) / name / "compose.yaml"
    try:
        previous_compose = compose_path.read_text()
        doc = yaml.safe_load(previous_compose)
        containers = [c["id"] for c in _docker_allocations() if c.get("project") == name]
    except (OSError, ValueError, yaml.YAMLError) as e:
        return {"ok": False, "err": str(e)}
    if on:
        allowed = _budget_guard(name, doc)
        if not allowed["ok"]:
            return allowed
    policy = "unless-stopped" if on else "no"
    if containers and not on:
        r = run(["docker", "update", "--restart=" + policy, *containers], timeout=30)
        if not r["ok"]:
            return r
    _restart_policy(doc, on)
    compose_path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    if on:
        base = ["docker", "compose", "-p", name, "-f", str(compose_path), "--env-file", os.path.join(cfg.apps.root, name, ".env")]
        r = run(base + ["up", "-d"], timeout=600)
        if not r["ok"]:
            compose_path.write_text(previous_compose, encoding="utf-8")
            if containers:
                previous_policy = "unless-stopped" if _app_meta(name).get("autostart", True) else "no"
                run(["docker", "update", "--restart=" + previous_policy, *containers], timeout=30)
            return r
    m = _app_meta(name)
    m["autostart"] = bool(on)
    write_json(p, m)
    return {"ok": True, "autostart": bool(on), "out": "Autostart enabled and app started." if on else "Autostart disabled; currently running containers keep running until stopped."}


def _sample_apps() -> list[dict]:
    return demo_state.get("apps", lambda: [dict(a, autostart=a["status"] == "running", ram_mb=a.get("ram_mb", 150), limit_mb=a.get("limit_mb", 512), source="template") for a in demo.APPS])


def _sample_app(name: str) -> dict | None:
    return next((a for a in _sample_apps() if a["name"] == name), None)


def list_apps() -> dict:
    cfg = load()
    if not available():
        if not _sample_mode():
            return {"demo": False, "apps": [], "docker": False, "error": DOCKER_DOWN, "ram_total_mb": ram_total_mb(), "reserve_mb": RESERVE_MB}
        return {"demo": True, "apps": _sample_apps(), "docker": False, "ram_total_mb": 16384, "reserve_mb": RESERVE_MB}
    r = run(["docker", "compose", "ls", "--all", "--format", "json"], timeout=20)
    rows = []
    try:
        rows = json.loads(r["out"] or "[]")
    except json.JSONDecodeError:
        pass
    if not r["ok"]:
        return {"demo": False, "apps": [], "docker": True, "error": "docker compose ls: " + ((r["err"] or r["out"]).strip()[:200] or "failed"),
                "ram_total_mb": ram_total_mb(), "reserve_mb": RESERVE_MB}
    apps = []
    stats = _stats()
    for s in rows:
        name = s.get("Name", "")
        if not str(s.get("ConfigFiles", "")).startswith(cfg.apps.root):
            continue
        st = stats.get(name, {})
        ports = _ports(name)
        meta = _app_meta(name)
        if not ports:
            # network_mode: host publishes nothing (Netdata, NetAlertX): the template's ports say where it is (scout I-062)
            ports = [str(p) for p in (_template_meta(meta.get("template", name)).get("ports") or [])]
        apps.append({"name": name, "template": meta.get("template", name), "source": meta.get("source", "template"), "status": "running" if "running" in s.get("Status", "") else "exited",
                     "ports": ports, "cpu": st.get("cpu", 0.0), "mem": st.get("mem", 0), "url": _app_url(meta, ports), "updated": meta.get("deployed"),
                     "autostart": meta.get("autostart", True), "ram_mb": meta.get("ram_mb"), "limit_mb": meta.get("cap_mb") or (meta.get("limits") or {}).get("mem_mb")})
    return {"demo": False, "apps": apps, "docker": True, "ram_total_mb": ram_total_mb(), "reserve_mb": RESERVE_MB}


def theme_for(name: str) -> dict:
    """The house-look plan for a template or catalogue app, for the Store's card."""
    if not NAME_RE.match(name or ""):
        return {"ok": False, "err": "bad app name"}
    meta = _template_meta(name) or catalog_entry(name) or {}
    if not meta:
        return {"ok": False, "err": f"no manifest for {name}"}
    tp = theme_plan(meta)
    return {"ok": True, "name": name, "via": tp["via"], "accepts": tp["accepts"], "note": tp["note"], "env": tp["env"], "files": sorted(tp["files"].keys()), "commands": [" ".join(c) for c in tp["commands"]], "css": tp["css"], "house": {k: v for k, v in HOUSE.items() if k != "logo"}}


def open_url(name: str) -> dict:
    """Where an installed app answers (for the Notes and Photos icons; members may ask)."""
    if not NAME_RE.match(name or ""):
        return {"ok": False, "err": "bad app name"}
    a = next((x for x in list_apps()["apps"] if x["name"] == name), None)
    if not a:
        return {"ok": False, "installed": False, "err": f"{name} is not installed: Store → {name} → Install"}
    return {"ok": True, "installed": True, "running": a["status"] == "running", "url": a.get("url", ""), "name": name}


def _stats() -> dict:
    try:
        allocations = _docker_allocations()
    except ValueError:
        return {}
    r = run(["docker", "stats", "--no-stream", "--format", '{"id":{{json .ID}},"cpu":{{json .CPUPerc}},"memory":{{json .MemUsage}}}'], timeout=20)
    out = {}
    for line in r["out"].splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        ident = d.get("id", "")
        proj = next((c.get("project") for c in allocations if ident and c["id"].startswith(ident)), None)
        if not proj:
            continue
        cpu = float(d.get("cpu", "0%").rstrip("%") or 0)
        mem = _parse_mem(d.get("memory", "0B / 0B").split("/")[0].strip())
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


def _app_url(meta: dict, ports: list[str]) -> str:
    """Nextcloud publishes on 127.0.0.1 only; people reach it through Caddy (round 6, docs/SYNC.md)."""
    if meta.get("template") == "nextcloud":
        from . import cloud
        return cloud.url()
    return _url(ports)


def _url(ports: list[str]) -> str:
    cfg = load()
    if not ports:
        return ""
    return f"http://{cfg.system.hostname}:{ports[0].split(':')[0]}"


def _template_meta(template: str) -> dict:
    cfg = load()
    meta = cfg.templates_dir / template / "template.yaml"
    try:
        return yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def _template_env(template: str) -> dict:
    m = _template_meta(template)
    if not m:
        e = catalog_entry(template)
        m = e or {}
    return {str(k): str(v) for k, v in (m.get("env") or {}).items()}


def _read_env(path: str) -> dict:
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
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
        elif k in existing and not str(existing[k]).startswith("CHANGE-ME"):
            out[k] = existing[k]
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


def _prepare_filebrowser(dest: str) -> dict:
    """Give UID 1500 only its data/config directories, never the app's .env.

    Legacy databases are copied after a clean stop. The original is retained;
    a completed destination always wins on repeat deploys.
    """
    root = Path(dest)
    dbdir, confdir = root / "database", root / "config"
    if dbdir.is_symlink() or confdir.is_symlink():
        return {"ok": False, "err": "File Browser data/config directories must not be symlinks."}
    try:
        dbdir.mkdir(exist_ok=True)
        confdir.mkdir(exist_ok=True)
        legacy, target = root / "filebrowser.db", dbdir / "filebrowser.db"
        if legacy.exists() and not target.exists():
            if legacy.is_symlink() or not (root / "compose.yaml").is_file():
                return {"ok": False, "err": "Legacy File Browser database needs its original Compose configuration before migration."}
            r = run(["docker", "compose", "-p", "filebrowser", "-f", str(root / "compose.yaml"),
                     "--env-file", str(root / ".env"), "stop"], timeout=120)
            if not r["ok"]:
                return {"ok": False, "err": "File Browser could not be stopped; its database was not migrated."}
            pending = []
            # Commit the main database last; its presence marks a complete copy.
            for suffix in ("-wal", "-shm", ""):
                source = root / ("filebrowser.db" + suffix)
                if source.is_symlink():
                    return {"ok": False, "err": "Legacy File Browser database files must not be symlinks."}
                if source.is_file():
                    final = dbdir / source.name
                    temp = dbdir / (source.name + ".migration")
                    shutil.copy2(source, temp)
                    pending.append((temp, final))
            for temp, final in pending:
                os.replace(temp, final)
        for folder in (dbdir, confdir):
            os.chown(folder, 1500, 1500)
            os.chmod(folder, 0o700)
            for item in folder.iterdir():
                if item.is_file() and not item.is_symlink():
                    os.chown(item, 1500, 1500)
                    os.chmod(item, 0o600)
        return {"ok": True}
    except OSError:
        return {"ok": False, "err": "Cannot prepare File Browser's private database/config directories; original data was retained."}


@_serialized
def deploy(template: str, name: str | None = None, env: dict | None = None, start: bool | None = None) -> dict:
    """Deploy a template or a catalogue entry. start=None follows the manifest's
    autostart; False creates the containers (images pulled) and leaves them stopped."""
    cfg = load()
    name = name or template
    if not NAME_RE.match(name):
        return {"ok": False, "err": "name: lowercase letters, digits, dashes; 2-32 chars"}
    if not NAME_RE.fullmatch(template) or name != template:
        return {"ok": False, "err": "Templates currently support one instance under their template name. Custom names would share ports and data; use the template name."}
    src = cfg.templates_dir / template
    entry = None
    if not (src / "compose.yaml").exists():
        entry = catalog_entry(template)
        if not entry:
            return {"ok": False, "err": f"no template or catalogue app called {template}"}
    meta = _template_meta(template) if entry is None else entry
    lim = dict(DEFAULT_LIMITS)
    lim.update({k: v for k, v in (meta.get("limits") or {}).items() if k in lim})
    old = _app_meta(name)
    autostart = bool(old.get("autostart", meta.get("autostart", True))) if start is None else bool(start)
    if not available():
        if not _sample_mode():
            return {"ok": False, "err": DOCKER_DOWN}
        if _sample_app(name):
            return {"ok": False, "err": f"{name} is already installed"}
        ports = [str(p) for p in (meta.get("ports") or [])]
        host = load().system.hostname
        url = f"http://{host}:{ports[0].split(':')[0]}" if ports and ":" in ports[0] else ""
        row = {"name": name, "template": template, "source": "template" if entry is None else "catalog", "status": "running" if autostart else "exited",
               "ports": ports, "cpu": 0.0, "mem": 0, "url": url, "updated": now_iso(), "autostart": autostart,
               "ram_mb": meta.get("ram_mb", 200), "limit_mb": lim.get("mem_mb")}
        _sample_apps().append(row)
        return {"ok": True, "demo": True, "app": row, "out": f"(sample) deployed {template} as {name}" + ("" if autostart else " (left stopped)")}
    dest = os.path.join(cfg.apps.root, name)
    if entry is None:
        doc = yaml.safe_load((src / "compose.yaml").read_text(encoding="utf-8")) or {}
    else:
        doc = compose_from_catalog(entry)
    doc = inject_limits(doc, lim)
    try:
        cap_mb = compose_cap_mb(doc)
    except ValueError as e:
        return {"ok": False, "err": str(e)}
    if autostart:
        allowed = _budget_guard(name, doc)
        if not allowed["ok"]:
            return allowed
    _restart_policy(doc, autostart)
    tp = theme_plan(meta)
    defaults = dict(_template_env(template))
    if template == "nextcloud":
        from . import cloud
        defaults.update(cloud.env_keys())
    defaults.update(tp["env"])
    saved = _read_env(str(APP_SECRETS_DIR / f"{name}.env"))
    for key, value in _read_env(os.path.join(dest, ".env")).items():
        if not str(value).startswith("CHANGE-ME") or key not in saved:
            saved[key] = value
    values, made = fill_secrets(defaults, env, saved)
    # A restored database must never be given a newly invented password.
    data_present = os.path.isdir(dest) and any(p.is_dir() and any(p.iterdir()) for p in Path(dest).iterdir())
    if made and data_present:
        return {"ok": False, "err": "Existing app data found but required credentials are missing. Restore the app .env or its secrets/apps file before redeploying; no passwords were replaced."}
    os.makedirs(dest, exist_ok=True)
    if template == "filebrowser":
        prepared = _prepare_filebrowser(dest)
        if not prepared["ok"]:
            return prepared
    with open(os.path.join(dest, "compose.yaml"), "w", encoding="utf-8") as f:
        f.write(f"# written by arisectl app deploy from {'templates/' + template if entry is None else 'catalog/catalog.yaml (' + template + ')'}; limits from its manifest. Edit the manifest, not this.\n")
        yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)
    if tp["env"] and entry is not None:
        # a catalogue app's main service reads every env key from .env; template compose files name theirs explicitly
        doc["services"][name].setdefault("environment", [])
        for k in tp["env"]:
            if not any(str(e).startswith(k + "=") for e in doc["services"][name]["environment"]):
                doc["services"][name]["environment"].append(f"{k}=${{{k}}}")
        with open(os.path.join(dest, "compose.yaml"), "w", encoding="utf-8") as f:
            f.write(f"# written by arisectl app deploy from catalog/catalog.yaml ({template}); limits and theme from its manifest. Edit the manifest, not this.\n")
            yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)
    for rel, content in tp["files"].items():
        if ".." in rel or rel.startswith("/"):
            continue
        fp = os.path.join(dest, rel)
        if not os.path.exists(fp):          # written once; a person's edits afterwards are kept
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w", encoding="utf-8") as f:
                f.write(content)
    with os.fdopen(os.open(os.path.join(dest, ".env"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(f"APP_NAME={name}\nDATA={dest}/data\nSHARES={cfg.system.data_root}/shares\n")
        for k, v in values.items():
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k):   # mixed case too: Gitea's GITEA__server__ROOT_URL
                f.write(f"{k}={v}\n")
    os.chmod(os.path.join(dest, ".env"), 0o600)
    secret_keys = [k for k, v in defaults.items() if str(v).startswith("CHANGE-ME")]
    if secret_keys:
        # A copy of every generated secret, root-only, so a person can find it.
        sec_dir = str(APP_SECRETS_DIR)
        try:
            os.makedirs(sec_dir, exist_ok=True)
            with os.fdopen(os.open(os.path.join(sec_dir, f"{name}.env"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
                os.fchmod(f.fileno(), 0o600)
                f.write(f"# {name} ({template}): secrets the deploy generated. Same values are in {dest}/.env\n")
                for k in secret_keys:
                    f.write(f"{k}={values[k]}\n")
            os.chmod(os.path.join(sec_dir, f"{name}.env"), 0o600)
        except OSError:
            return {"ok": False, "err": "Cannot save the root-only app credential copy; deployment stopped."}
    os.makedirs(os.path.join(dest, "data"), exist_ok=True)
    for v in (meta.get("volumes") or []):
        host = str(v).split(":")[0]
        if host.startswith(cfg.apps.root):
            os.makedirs(host, exist_ok=True)
    pre = _pre_deploy(template, dest, values)
    if pre and not pre.get("ok", True):
        return pre
    write_json(os.path.join(dest, "arise.json"), {"template": template, "source": "template" if entry is None else "catalog", "autostart": autostart, "cap_mb": cap_mb,
                                                   "ram_mb": int(meta.get("ram_mb") or lim["mem_mb"]), "limits": lim, "deployed": now_iso(), "version": str(meta.get("version") or meta.get("image") or ""),
                                                   "idle_stop_minutes": int(meta.get("idle_stop_minutes") or 0), "kind": meta.get("kind", "service"), "theme_via": tp["via"]})
    base = ["docker", "compose", "-p", name, "-f", os.path.join(dest, "compose.yaml"), "--env-file", os.path.join(dest, ".env")]
    print(f"{name}: pulling images (one Compose pull at a time; {cap_mb} MiB aggregate cap)", flush=True)
    pulled = run_stream(base[:2] + ["--parallel", "1"] + base[2:] + ["pull"], timeout=1800)
    if not pulled["ok"]:
        return pulled
    if autostart:
        r = run(base + ["up", "-d"], timeout=1800)
        if r["ok"] and tp["commands"]:
            # The house look through the app's own command line (Nextcloud's occ), best effort, after it is up.
            import time
            time.sleep(8)
            notes = []
            for c in tp["commands"]:
                rc = run(base + ["exec", "-T", *c], timeout=120)
                notes.append(f"theme: {' '.join(c)[:60]}: {'ok' if rc['ok'] else 'not yet (' + (rc['err'] or rc['out']).strip()[:80] + ')'}")
            r["out"] = (r["out"] or "") + "\n" + "\n".join(notes)
    else:
        r = run(base + ["create", "--pull", "never"], timeout=1800)
        if r["ok"]:
            r["out"] = (r["out"] or "") + f"\n{name}: deployed and left stopped (autostart off). Start it from the Store or: arisectl app start {name}"
    r["secrets_generated"] = made
    r["started"] = autostart
    return r


def install_all(log=print) -> dict:
    """Every template deployed; started only within the memory budget (round 3, 5).
    The installer's 6a step calls this through `arisectl app install-all`."""
    t = templates()
    if t["demo"]:
        return {"ok": True, "demo": True, "out": "(sample) would deploy every template"}
    plan = autostart_plan([x for x in t["templates"] if x["category"] != "broken"], ram_total_mb())
    log(f"app budget: {plan['budget_mb']} MB for apps after {RESERVE_MB} MB kept for the domain and the dashboard; starting {len(plan['start'])} of {len(t['templates'])}")
    results = {"ok": True, "started": [], "stopped": [], "failed": [], "plan": plan}
    for x in sorted(t["templates"], key=lambda x: (x["id"] != "nextcloud", x["id"])):
        if x["category"] == "broken":
            results["failed"].append({"id": x["id"], "err": x["description"]})
            results["ok"] = False
            continue
        start = x["id"] in plan["start"]
        log(f"deploying {x['id']} ({'start' if start else 'leave stopped'})")
        r = deploy(x["id"], start=start)
        if r.get("ok"):
            (results["started"] if start else results["stopped"]).append(x["id"])
            log(f"{'up     ' if start else 'stopped'} {x['id']}")
        else:
            results["failed"].append({"id": x["id"], "err": (r.get("err") or r.get("out") or "")[-200:]})
            results["ok"] = False
            log(f"FAILED  {x['id']}: {(r.get('err') or r.get('out') or '')[-160:]}")
    for s in plan["stopped"]:
        log(f"not started: {s['id']} ({s['ram_mb']} MB): {s['why']}")
    return results


def caps_check() -> dict:
    """For arisectl doctor: do the autostart caps fit in RAM minus the reserve?"""
    total_caps, total_est, count = 0, 0, 0
    for p in Path(load().apps.root).glob("*/compose.yaml"):
        meta = _app_meta(p.parent.name)
        if not meta.get("autostart", True):
            continue
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        total_caps += compose_cap_mb(doc)
        total_est += int(meta.get("ram_mb") or 0)
        count += 1
    ram = ram_total_mb()
    return {"ram_mb": ram, "budget_mb": max(0, ram - RESERVE_MB), "autostart_caps_mb": total_caps, "autostart_est_mb": total_est, "ok": total_caps <= max(0, ram - RESERVE_MB), "count": count}


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


@_serialized
def act(name: str, action: str, confirm: str = "") -> dict:
    cfg = load()
    if not NAME_RE.match(name or ""):
        return {"ok": False, "err": "bad app name"}
    if action not in ("start", "stop", "restart", "remove", "update"):
        return {"ok": False, "err": "action must be start|stop|restart|remove|update"}
    if action == "remove" and confirm != name:
        return {"ok": False, "err": "type the app name to confirm; the data folder is kept"}
    if not available():
        if not _sample_mode():
            return {"ok": False, "err": DOCKER_DOWN}
        a = _sample_app(name)
        if not a:
            return {"ok": False, "err": f"{name} is not installed"}
        if action == "remove":
            _sample_apps().remove(a)
            return {"ok": True, "demo": True, "out": f"(sample) removed the containers of {name}; its data folder is kept"}
        if action in ("start", "restart", "update"):
            a["status"] = "running"
            if action == "update":
                a["updated"] = now_iso()
        else:
            a["status"] = "exited"
            a["cpu"], a["mem"] = 0.0, 0
        return {"ok": True, "demo": True, "status": a["status"], "out": f"(sample) docker compose {action} {name}"}
    dest = os.path.join(cfg.apps.root, name)
    if not os.path.exists(os.path.join(dest, "compose.yaml")):
        return {"ok": False, "err": f"{name} is not installed (no {dest}/compose.yaml)"}
    base = ["docker", "compose", "-p", name, "-f", os.path.join(dest, "compose.yaml"), "--env-file", os.path.join(dest, ".env")]
    if action in ("start", "restart", "update"):
        try:
            doc = yaml.safe_load(Path(dest, "compose.yaml").read_text())
        except (OSError, yaml.YAMLError) as e:
            return {"ok": False, "err": str(e)}
        allowed = _budget_guard(name, doc)
        if not allowed["ok"]:
            return allowed
    if action == "remove":
        r = run(base + ["down"], timeout=300)
        if r["ok"]:
            r["out"] = (r["out"] or "") + f"\nremoved the containers of {name}; its data folder {dest} is kept (delete it by hand if you mean it)"
        return r
    if action == "update":
        r = run_stream(base[:2] + ["--parallel", "1"] + base[2:] + ["pull"], timeout=1800)
        if not r["ok"]:
            return r
        return run(base + ["up", "-d"], timeout=600)
    if action == "start":
        return run(base + ["up", "-d"], timeout=600)
    return run(base + [action], timeout=300)


def logs(name: str, lines: int = 200) -> dict:
    if not NAME_RE.match(name or ""):
        return {"text": "bad app name"}
    if not available():
        if not _sample_mode():
            return {"demo": False, "name": name, "text": DOCKER_DOWN}
        return {"demo": True, "name": name, "text": f"(demo) {name} | server listening on :80\n(demo) {name} | GET / 200"}
    cfg = load()
    dest = os.path.join(cfg.apps.root, name)
    r = run(["docker", "compose", "-p", name, "-f", os.path.join(dest, "compose.yaml"), "--env-file", os.path.join(dest, ".env"), "logs", "--no-color", "--tail", str(min(lines, 2000))], timeout=30)
    return {"demo": False, "name": name, "text": r["out"] or r["err"]}

"""The closet monitor: panel power (round 3, 30) and Screen Sharing (round 3, 17).

The desktop on tty1 is cage (Wayland) running Epiphany as the arise-kiosk user.
Power: wlr-randr on cage's socket turns the one output off at 23:00 and on at
06:00 (two timers). Sharing: wayvnc on that same display, bound to the Docker
bridge gateway so only the Guacamole containers can reach it, with a password
and TLS; a Guacamole connection "Closet monitor" for bradly.dyer alone.

Everything that needs the kiosk says so when it is not running instead of
pretending."""
from __future__ import annotations

import hashlib
import os
import re
import secrets

from .config import load
from .util import run, which

KIOSK_UID = 1501
RUNTIME = f"/run/user/{KIOSK_UID}"
WAYVNC_SECRET = "/etc/arise/secrets/wayvnc"
WAYVNC_CONF = "/etc/arise/wayvnc.conf"
WAYVNC_TLS = "/etc/arise/secrets/wayvnc-tls"
VNC_PORT = 5900


# ----- the Wayland display cage owns --------------------------------------------
def display() -> str | None:
    if not os.path.isdir(RUNTIME):
        return None
    socks = [f for f in os.listdir(RUNTIME) if f.startswith("wayland-") and not f.endswith(".lock")]
    return sorted(socks)[0] if socks else None


def _as_kiosk(cmd: list[str], timeout: int = 15) -> dict:
    d = display()
    if not d:
        return {"ok": False, "err": "the kiosk is not running on this box (no Wayland socket under /run/user/1501)", "out": ""}
    return run(["sudo", "-n", "-u", "arise-kiosk", "env", f"XDG_RUNTIME_DIR={RUNTIME}", f"WAYLAND_DISPLAY={d}", *cmd], timeout=timeout)


def parse_wlr_randr(text: str) -> list[dict]:
    """`wlr-randr` output → [{"name","description","enabled"}]. Pure."""
    outs, cur = [], None
    for line in (text or "").splitlines():
        if line and not line.startswith((" ", "\t")):
            name, _, desc = line.partition(" ")
            cur = {"name": name.strip(), "description": desc.strip().strip('"'), "enabled": None}
            outs.append(cur)
        elif cur is not None:
            m = re.match(r"\s*Enabled:\s*(yes|no)", line)
            if m:
                cur["enabled"] = m.group(1) == "yes"
    return outs


def outputs() -> dict:
    if load().demo:
        from . import demo_state
        return {"demo": True, "outputs": demo_state.get("monitor.outputs", [{"name": "HDMI-A-1", "description": "Dell E2216H", "enabled": True}]), "display": "wayland-0"}
    if not which("wlr-randr"):
        return {"demo": False, "outputs": [], "error": "wlr-randr is not installed (install.sh --kiosk installs it)", "display": display()}
    r = _as_kiosk(["wlr-randr"])
    if not r["ok"]:
        return {"demo": False, "outputs": [], "error": (r["err"] or r["out"]).strip()[:200], "display": display()}
    return {"demo": False, "outputs": parse_wlr_randr(r["out"]), "display": display()}


def power(on: bool) -> dict:
    """Panel on or off. Off means the output is disabled in cage; a key does not
    bring it back by itself - the 06:00 timer or `arisectl monitor on` does."""
    if load().demo:
        for o in outputs()["outputs"]:
            o["enabled"] = bool(on)
        return {"ok": True, "demo": True, "on": bool(on), "out": f"(sample) monitor {'on' if on else 'off'}"}
    o = outputs()
    if o.get("error"):
        return {"ok": False, "err": o["error"]}
    if not o["outputs"]:
        return {"ok": False, "err": "cage reports no output: is a monitor plugged in?"}
    results = []
    for out in o["outputs"]:
        results.append(_as_kiosk(["wlr-randr", "--output", out["name"], "--on" if on else "--off"]))
    okk = all(r["ok"] for r in results)
    return {"ok": okk, "out": "; ".join(f"{o['name']}: {'ok' if r['ok'] else (r['err'] or r['out']).strip()[:120]}" for o, r in zip(o["outputs"], results))}


def status() -> dict:
    cfg = load()
    o = outputs()
    share = share_status()
    sched = {"off": "23:00", "on": "06:00"}
    if cfg.demo:
        return {"demo": True, "kiosk": True, "outputs": o["outputs"], "schedule": sched, "share": share, "timers": {"arise-monitor-off.timer": "enabled", "arise-monitor-on.timer": "enabled"}}
    timers = {}
    if which("systemctl"):
        for t in ("arise-monitor-off.timer", "arise-monitor-on.timer", "arise-wayvnc.service"):
            timers[t] = run(["systemctl", "is-enabled", t], timeout=5)["out"].strip() or "absent"
    return {"demo": False, "kiosk": display() is not None, "display": o.get("display"), "outputs": o.get("outputs", []), "error": o.get("error", ""), "schedule": sched, "share": share, "timers": timers}


# ----- Screen Sharing (wayvnc + Guacamole) --------------------------------------
def guac_password_hash(password: str, salt_hex: str) -> str:
    """Guacamole's JDBC scheme: SHA-256 of the password with the UPPERCASE hex salt
    appended. Pure, pinned by the tests against a hand-checked value."""
    return hashlib.sha256((password + salt_hex.upper()).encode("utf-8")).hexdigest()


def guac_sql(user: str, password: str, conn_name: str, host: str, port: int, vnc_password: str, salt_hex: str | None = None) -> str:
    """The SQL that makes one Guacamole user who may open exactly one VNC connection.
    Idempotent: re-running updates the password and the parameters."""
    if not re.match(r"^[a-z][a-z0-9._-]{1,63}$", user):
        raise ValueError("user")
    salt_hex = salt_hex or secrets.token_hex(32)
    ph = guac_password_hash(password, salt_hex)
    esc = lambda s: str(s).replace("'", "''")
    return f"""
INSERT INTO guacamole_entity (name, type) VALUES ('{esc(user)}', 'USER') ON CONFLICT DO NOTHING;
INSERT INTO guacamole_user (entity_id, password_salt, password_hash, password_date)
  SELECT entity_id, decode('{salt_hex}', 'hex'), decode('{ph}', 'hex'), CURRENT_TIMESTAMP FROM guacamole_entity WHERE name = '{esc(user)}' AND type = 'USER'
  ON CONFLICT (entity_id) DO UPDATE SET password_salt = EXCLUDED.password_salt, password_hash = EXCLUDED.password_hash, password_date = EXCLUDED.password_date;
INSERT INTO guacamole_connection (connection_name, protocol) SELECT '{esc(conn_name)}', 'vnc'
  WHERE NOT EXISTS (SELECT 1 FROM guacamole_connection WHERE connection_name = '{esc(conn_name)}');
DELETE FROM guacamole_connection_parameter WHERE connection_id = (SELECT connection_id FROM guacamole_connection WHERE connection_name = '{esc(conn_name)}');
INSERT INTO guacamole_connection_parameter (connection_id, parameter_name, parameter_value)
  SELECT connection_id, p.n, p.v FROM guacamole_connection, (VALUES ('hostname', '{esc(host)}'), ('port', '{int(port)}'), ('password', '{esc(vnc_password)}'), ('color-depth', '24')) AS p(n, v)
  WHERE connection_name = '{esc(conn_name)}';
INSERT INTO guacamole_connection_permission (entity_id, connection_id, permission)
  SELECT e.entity_id, c.connection_id, 'READ' FROM guacamole_entity e, guacamole_connection c
  WHERE e.name = '{esc(user)}' AND e.type = 'USER' AND c.connection_name = '{esc(conn_name)}'
  ON CONFLICT DO NOTHING;
"""


def wayvnc_conf(address: str, port: int, user: str, password: str) -> str:
    """wayvnc's config file. Auth needs TLS in wayvnc, so the key and cert paths are here too."""
    return (f"address={address}\nport={port}\nenable_auth=true\nusername={user}\npassword={password}\n"
            f"private_key_file={WAYVNC_TLS}/key.pem\ncertificate_file={WAYVNC_TLS}/cert.pem\n")


def guac_gateway() -> str | None:
    """The address this host has on Guacamole's Docker network: the only place
    wayvnc listens, so only guacd can reach it."""
    r = run(["docker", "network", "inspect", "guacamole_default", "--format", "{{(index .IPAM.Config 0).Gateway}}"], timeout=10)
    gw = r["out"].strip()
    return gw if r["ok"] and re.match(r"^\d+\.\d+\.\d+\.\d+$", gw) else None


def share_status() -> dict:
    if load().demo:
        from . import demo_state
        on = demo_state.get("monitor.share", {"on": True})["on"]
        return {"demo": True, "on": on, "address": "172.18.0.1", "port": VNC_PORT, "user": "bradly.dyer", "connection": "Closet monitor", "guacamole": "http://arise-server:8084/guacamole"}
    on = os.path.exists(WAYVNC_CONF)
    addr = ""
    if on:
        try:
            addr = re.search(r"^address=(.*)$", open(WAYVNC_CONF, encoding="utf-8").read(), re.M).group(1)
        except (OSError, AttributeError):
            pass
    svc = run(["systemctl", "is-active", "arise-wayvnc.service"], timeout=5)["out"].strip() if which("systemctl") else ""
    url = ""
    try:
        from . import apps
        g = next((a for a in apps.list_apps()["apps"] if a["name"] == "guacamole"), None)
        url = (g["url"] + "/guacamole") if g and g.get("url") else ""
    except Exception:  # noqa: BLE001
        pass
    return {"demo": False, "on": on, "service": svc, "address": addr, "port": VNC_PORT, "user": load().web.admin_user, "connection": "Closet monitor", "guacamole": url}


def share(on: bool, user: str | None = None) -> dict:
    """Turn Screen Sharing on: a wayvnc password and TLS pair under /etc/arise/secrets,
    the config, the unit, and the Guacamole user + connection. Off: stop wayvnc and
    remove the connection's permission. Root only; the CLI runs this."""
    cfg = load()
    user = user or cfg.web.admin_user
    if cfg.demo:
        from . import demo_state
        demo_state.get("monitor.share", {"on": True})["on"] = bool(on)
        return {"ok": True, "demo": True, "on": bool(on), "out": f"(sample) screen sharing {'on' if on else 'off'} for {user}"}
    if not on:
        run(["systemctl", "disable", "--now", "arise-wayvnc.service"], timeout=30)
        return {"ok": True, "out": "wayvnc stopped. The Guacamole connection stays but has nothing to connect to; `arisectl monitor share on` brings it back."}
    if not which("wayvnc"):
        return {"ok": False, "err": "wayvnc is not installed: install.sh --kiosk installs it (apt install wayvnc)"}
    gw = guac_gateway()
    if not gw:
        return {"ok": False, "err": "Guacamole is not deployed (no guacamole_default Docker network): arisectl app deploy guacamole first"}
    os.makedirs(os.path.dirname(WAYVNC_SECRET), exist_ok=True)
    os.makedirs(WAYVNC_TLS, exist_ok=True)
    if os.path.exists(WAYVNC_SECRET):
        vncpw = open(WAYVNC_SECRET, encoding="utf-8").read().strip()
    else:
        vncpw = secrets.token_urlsafe(18)
        with open(WAYVNC_SECRET, "w", encoding="utf-8") as f:
            f.write(vncpw + "\n")
        os.chmod(WAYVNC_SECRET, 0o600)
    if not os.path.exists(f"{WAYVNC_TLS}/key.pem"):
        r = run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650", "-subj", "/CN=arise-server-monitor", "-keyout", f"{WAYVNC_TLS}/key.pem", "-out", f"{WAYVNC_TLS}/cert.pem"], timeout=60)
        if not r["ok"]:
            return {"ok": False, "err": "openssl could not make the TLS pair: " + (r["err"] or r["out"])[-200:]}
    with open(WAYVNC_CONF, "w", encoding="utf-8") as f:
        f.write(wayvnc_conf(gw, VNC_PORT, user, vncpw))
    os.chmod(WAYVNC_CONF, 0o640)
    run(["chgrp", "arise-kiosk", WAYVNC_CONF, f"{WAYVNC_TLS}/key.pem", f"{WAYVNC_TLS}/cert.pem", WAYVNC_TLS], timeout=10)
    run(["chmod", "0640", f"{WAYVNC_TLS}/key.pem", f"{WAYVNC_TLS}/cert.pem"], timeout=10)
    run(["chmod", "0750", WAYVNC_TLS], timeout=10)
    # The Guacamole side: one user (a local Guacamole account, not the domain one), one connection.
    gpw_path = f"/etc/arise/secrets/guacamole-{user}"
    if os.path.exists(gpw_path):
        gpw = open(gpw_path, encoding="utf-8").read().strip()
        new_pw = False
    else:
        gpw = secrets.token_urlsafe(14)
        with open(gpw_path, "w", encoding="utf-8") as f:
            f.write(gpw + "\n")
        os.chmod(gpw_path, 0o600)
        new_pw = True
    sql = guac_sql(user, gpw, "Closet monitor", gw, VNC_PORT, vncpw)
    dest = os.path.join(cfg.apps.root, "guacamole")
    r = run(["docker", "compose", "-p", "guacamole", "-f", os.path.join(dest, "compose.yaml"), "--env-file", os.path.join(dest, ".env"), "exec", "-T", "db", "psql", "-v", "ON_ERROR_STOP=1", "-U", "guacamole_user", "-d", "guacamole_db"], timeout=60, input_text=sql)
    if not r["ok"]:
        return {"ok": False, "err": "Guacamole's database refused the connection setup: " + (r["err"] or r["out"])[-300:]}
    if which("ufw"):
        run(["ufw", "allow", "from", gw.rsplit(".", 1)[0] + ".0/24", "to", "any", "port", str(VNC_PORT), "proto", "tcp", "comment", "wayvnc (guacd only)"], timeout=15)
    run(["systemctl", "enable", "--now", "arise-wayvnc.service"], timeout=30)
    note = f"Screen Sharing on. Open Guacamole and sign in as {user}" + (f" with the password in {gpw_path} (root only; shown once below)." if new_pw else ".")
    return {"ok": True, "out": note, "guacamole_password": gpw if new_pw else None, "address": gw}

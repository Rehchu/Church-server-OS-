"""SMB shares, read from smb.conf. Adding writes a block to /etc/samba/arise-shares.conf
(which smb.conf includes) and reloads samba, so the main file is never rewritten."""
from __future__ import annotations

import os
import re

from . import demo, demo_state
from .config import load
from .util import dir_size, run, which

SMB_CONF = "/etc/samba/smb.conf"
ARISE_CONF = "/etc/samba/arise-shares.conf"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,31}$")


def available() -> bool:
    return bool(which("testparm")) and os.path.exists(SMB_CONF) and not load().demo


def _parse(text: str) -> dict:
    sections, cur = {}, None
    for raw in text.splitlines():
        line = raw.split(";")[0].split("#")[0].strip()
        if not line:
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            cur = m.group(1).strip()
            sections[cur] = {}
            continue
        if cur and "=" in line:
            k, _, v = line.partition("=")
            sections[cur][k.strip().lower()] = v.strip()
    return sections


def _names(v: str) -> list[str]:
    """'@"Media", @Staff, bradly' -> ['@Media', '@Staff', 'bradly']"""
    out = []
    for tok in re.split(r"[,\s]+", v or ""):
        tok = tok.strip().strip('"')
        if tok:
            out.append(("@" + tok.lstrip("@+&").strip('"')) if tok[0] in "@+&" else tok)
    return out


def can_use(share: dict, user: str, groups: list[str]) -> bool:
    """Does this user reach this share? Empty valid users = everyone in the domain."""
    vu = share.get("valid_users") or []
    if not vu:
        return True
    gs = {g.lower() for g in groups}
    for v in vu:
        if v.startswith("@"):
            if v[1:].lower() in gs or v[1:].lower() == "domain users":
                return True
        elif v.lower() == user.lower():
            return True
    return False


def _sample() -> list[dict]:
    return demo_state.get("shares", demo.SHARES)


def list_shares() -> dict:
    if not available():
        return {"demo": True, "shares": _sample()}
    r = run(["testparm", "-s", "--suppress-prompt"], timeout=20)
    if not r["ok"] and not r["out"]:
        return {"demo": False, "shares": [], "error": ("testparm: " + (r["err"] or "").strip().splitlines()[-1]) if r["err"] else "testparm failed"}
    conf = _parse(r["out"])
    shares = []
    for name, opts in conf.items():
        if name in ("global", "printers", "print$"):
            continue
        path = opts.get("path", "")
        yes = lambda k, d="no": opts.get(k, d).lower() in ("yes", "true", "1")
        shares.append({
            "name": name, "path": path, "comment": opts.get("comment", ""),
            "writable": yes("writable") or yes("writeable") or not yes("read only", "yes"),
            "browseable": yes("browseable", "yes"),
            "used": dir_size(path) if path and os.path.isdir(path) else None,
            "mac": "fruit" in opts.get("vfs objects", ""),
            "valid_users": _names(opts.get("valid users", "")),
            "write_list": _names(opts.get("write list", "")),
        })
    return {"demo": False, "shares": shares}


def share_block(name: str, path: str, comment: str = "", group: str = "Domain Users", mac: bool = True) -> list[str]:
    """Pure: the lines one share adds to arise-shares.conf."""
    block = [f"\n[{name}]", f"  path = {path}", f"  comment = {comment}", f"  valid users = @\"{group}\"",
             "  read only = no", "  browseable = yes", "  create mask = 0664", "  directory mask = 0775"]
    # Every share gets the Trash (recycle): a Mac's delete lands in .Trash/<user>/ for 30 days.
    block += ["  vfs objects = acl_xattr " + ("fruit streams_xattr " if mac else "") + "recycle",
              "  recycle:repository = .Trash/%U", "  recycle:keeptree = yes", "  recycle:versions = yes", "  recycle:touch = yes",
              "  recycle:directory_mode = 0770", "  recycle:exclude = *.tmp,*.temp,~$*,.DS_Store,._*,*.part,*.crdownload", "  recycle:exclude_dir = .Trash,/tmp"]
    if mac:
        block += ["  fruit:metadata = stream", "  fruit:model = MacSamba",
                  "  fruit:posix_rename = yes", "  fruit:veto_appledouble = no", "  fruit:delete_empty_adfiles = yes"]
    return block


def _apply(new_text: str, old_text: str | None, what: str) -> dict:
    """Write arise-shares.conf, prove it with testparm, reload; put the old file back if testparm says no.
    (CLAUDE.md rule 4: a bad smb.conf takes the domain down.)"""
    with open(ARISE_CONF, "w", encoding="utf-8") as f:
        f.write(new_text)
    inc = _ensure_include()
    if inc.get("ok") is False:
        _restore(old_text)
        return inc
    t = run(["testparm", "-s", "--suppress-prompt"], timeout=20)
    if not t["ok"]:
        _restore(old_text)
        last = ((t["err"] or t["out"]).strip().splitlines() or ["testparm failed"])[-1]
        return {"ok": False, "err": f"{what}: testparm refused the change, so it was undone ({last})"}
    r = run(["smbcontrol", "all", "reload-config"], timeout=15)
    if not r["ok"]:
        return {"ok": False, "err": f"{what}: saved and testparm passed, but Samba did not reload ({(r['err'] or r['out']).strip()[:200]}); run: sudo smbcontrol all reload-config"}
    return {"ok": True, "out": what}


def _restore(old_text: str | None):
    try:
        if old_text is None:
            os.remove(ARISE_CONF)
        else:
            with open(ARISE_CONF, "w", encoding="utf-8") as f:
                f.write(old_text)
    except OSError:
        pass


def add_share(name: str, path: str, comment: str = "", group: str = "Domain Users", mac: bool = True) -> dict:
    name = (name or "").strip()
    if not NAME_RE.match(name):
        return {"ok": False, "err": "share name: letters, digits, space, dash, underscore, up to 32"}
    if not path or not path.startswith("/") or ".." in path.split("/"):
        return {"ok": False, "err": "path must be absolute (no ..)"}
    if not (group or "").strip() or any(c in group for c in '"\n'):
        return {"ok": False, "err": "group: one group name"}
    if not available():
        if any(s["name"].lower() == name.lower() for s in _sample()):
            return {"ok": False, "err": f"a share called {name} already exists"}
        row = {"name": name, "path": path, "comment": comment, "writable": True, "browseable": True, "used": 0, "mac": bool(mac),
               "valid_users": [f"@{group}"], "write_list": []}
        _sample().append(row)
        return {"ok": True, "demo": True, "out": f"(sample) added [{name}] at {path}", "share": row}
    if any(s["name"].lower() == name.lower() for s in list_shares()["shares"]):
        return {"ok": False, "err": f"a share called {name} already exists"}
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        return {"ok": False, "err": f"could not make {path}: {e}"}
    try:
        with open(ARISE_CONF, encoding="utf-8") as f:
            old = f.read()
    except FileNotFoundError:
        old = None
    return _apply((old or "") + "\n".join(share_block(name, path, comment, group, mac)) + "\n", old, f"added [{name}]")


def remove_share(name: str, confirm: str) -> dict:
    if confirm != name:
        return {"ok": False, "err": "type the share name to confirm; files on disk are never touched"}
    if not available():
        row = next((s for s in _sample() if s["name"] == name), None)
        if not row:
            return {"ok": False, "err": f"no share called {name}"}
        _sample().remove(row)
        return {"ok": True, "demo": True, "out": f"(sample) removed [{name}]; the files stay on disk"}
    try:
        with open(ARISE_CONF, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return {"ok": False, "err": "that share was not added here; edit smb.conf by hand"}
    new = remove_block(text, name)
    if new == text:
        return {"ok": False, "err": "that share was not added here; edit smb.conf by hand"}
    return _apply(new, text, f"removed [{name}]; the files stay on disk")


def remove_block(text: str, name: str) -> str:
    """Pure: arise-shares.conf without the [name] block."""
    pat = re.compile(rf"(^|\n)\[{re.escape(name)}\]\n(?:[ \t]+[^\n]*(?:\n|$))*")
    new = pat.sub(lambda m: m.group(1), text, count=1)
    return new


def _ensure_include() -> dict:
    """smb.conf includes arise-shares.conf once. smb.conf is copied aside before it is touched."""
    try:
        with open(SMB_CONF, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return {"ok": False, "err": f"{SMB_CONF} is missing"}
    if ARISE_CONF in text:
        return {"ok": True}
    import shutil
    import time as _t
    try:
        shutil.copy2(SMB_CONF, f"{SMB_CONF}.bak-{_t.strftime('%Y%m%d-%H%M%S')}")
        with open(SMB_CONF, "a", encoding="utf-8") as f:
            f.write(f"\ninclude = {ARISE_CONF}\n")
    except OSError as e:
        return {"ok": False, "err": f"could not add the include to {SMB_CONF}: {e}"}
    return {"ok": True}

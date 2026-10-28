"""SMB shares, read from smb.conf. Adding writes a block to /etc/samba/arise-shares.conf
(which smb.conf includes) and reloads samba, so the main file is never rewritten."""
from __future__ import annotations

import os
import re

from . import demo
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


def list_shares() -> dict:
    if not available():
        return {"demo": True, "shares": demo.SHARES}
    r = run(["testparm", "-s", "--suppress-prompt"], timeout=20)
    conf = _parse(r["out"])
    shares = []
    for name, opts in conf.items():
        if name in ("global", "printers", "print$"):
            continue
        path = opts.get("path", "")
        yes = lambda k, d="no": opts.get(k, d).lower() in ("yes", "true", "1")
        shares.append({
            "name": name, "path": path, "comment": opts.get("comment", ""),
            "writable": yes("writable") or yes("read only", "yes") is False or yes("writeable"),
            "browseable": yes("browseable", "yes"),
            "used": dir_size(path) if path and os.path.isdir(path) else None,
            "mac": "fruit" in opts.get("vfs objects", ""),
            "valid_users": _names(opts.get("valid users", "")),
            "write_list": _names(opts.get("write list", "")),
        })
    return {"demo": False, "shares": shares}


def add_share(name: str, path: str, comment: str = "", group: str = "Domain Users", mac: bool = True) -> dict:
    if not NAME_RE.match(name or ""):
        return {"ok": False, "err": "share name: letters, digits, space, dash, underscore, up to 32"}
    if not path or not path.startswith("/"):
        return {"ok": False, "err": "path must be absolute"}
    if not available():
        return {"ok": True, "demo": True, "out": f"(demo) would add [{name}] at {path}"}
    os.makedirs(path, exist_ok=True)
    block = [f"\n[{name}]", f"  path = {path}", f"  comment = {comment}", f"  valid users = @\"{group}\"",
             "  read only = no", "  browseable = yes", "  create mask = 0664", "  directory mask = 0775"]
    # Every share gets the Trash (recycle): a Mac's delete lands in .Trash/<user>/ for 30 days.
    block += ["  vfs objects = acl_xattr " + ("fruit streams_xattr " if mac else "") + "recycle",
              "  recycle:repository = .Trash/%U", "  recycle:keeptree = yes", "  recycle:versions = yes", "  recycle:touch = yes",
              "  recycle:directory_mode = 0770", "  recycle:exclude = *.tmp,*.temp,~$*,.DS_Store,._*,*.part,*.crdownload", "  recycle:exclude_dir = .Trash,/tmp"]
    if mac:
        block += ["  fruit:metadata = stream", "  fruit:model = MacSamba",
                  "  fruit:posix_rename = yes", "  fruit:veto_appledouble = no", "  fruit:delete_empty_adfiles = yes"]
    with open(ARISE_CONF, "a", encoding="utf-8") as f:
        f.write("\n".join(block) + "\n")
    _ensure_include()
    return run(["smbcontrol", "all", "reload-config"], timeout=15)


def remove_share(name: str, confirm: str) -> dict:
    if confirm != name:
        return {"ok": False, "err": "type the share name to confirm; files on disk are never touched"}
    if not available():
        return {"ok": True, "demo": True}
    try:
        text = open(ARISE_CONF, encoding="utf-8").read()
    except FileNotFoundError:
        return {"ok": False, "err": "that share was not added here; edit smb.conf by hand"}
    new = re.sub(rf"\n\[{re.escape(name)}\]\n(?:  .*\n)*", "\n", text)
    if new == text:
        return {"ok": False, "err": "that share was not added here; edit smb.conf by hand"}
    open(ARISE_CONF, "w", encoding="utf-8").write(new)
    return run(["smbcontrol", "all", "reload-config"], timeout=15)


def _ensure_include():
    try:
        text = open(SMB_CONF, encoding="utf-8").read()
    except FileNotFoundError:
        return
    if ARISE_CONF not in text:
        with open(SMB_CONF, "a", encoding="utf-8") as f:
            f.write(f"\ninclude = {ARISE_CONF}\n")

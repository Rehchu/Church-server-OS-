"""Reads /etc/arise/arise.toml (or $ARISE_CONFIG). Missing file = defaults + demo.

Nothing here writes the file. The CLI and the installer own it.
"""
from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

WINDOWS = sys.platform.startswith("win")


def _root(default_linux: str, default_win: str) -> str:
    return default_win if WINDOWS else default_linux


DEFAULTS = {
    "system": {
        "hostname": "arise-server",
        "timezone": "America/Chicago",
        "profile": "windows" if WINDOWS else "server",
        "data_root": _root("/srv/arise", r"C:\Arise\data"),
    },
    "web": {
        "bind": "0.0.0.0",
        "port": 4147,
        "admin_user": "bradly",
        "admin_password_hash": "",
        "session_hours": 12,
        "secret_file": _root("/etc/arise/secrets/web-secret", r"C:\Arise\config\secrets\web-secret"),
    },
    "directory": {
        "enabled": not WINDOWS,
        "realm": "AD.ARISECENLA.CHURCH",
        "netbios": "ARISE",
        "dns_forwarder": "1.1.1.1",
        "homes_path": _root("/srv/arise/homes", r"C:\Arise\data\homes"),
    },
    "automator": {
        "enabled": True,
        "path": _root("/srv/arise/automator/ARISE_YouTube_Updater", r"C:\Arise\automator\ARISE_YouTube_Updater"),
        "python": _root("/opt/arise/venv/bin/python", r"C:\Arise\venv\Scripts\python.exe"),
        "schedule": "02:05",
    },
    "backups": {
        "restic_repo": _root("/mnt/synology/arise-backups/restic", r"Z:\arise-backups\restic"),
        "password_file": _root("/etc/arise/secrets/restic-password", r"C:\Arise\config\secrets\restic-password"),
        "schedule": "03:00",
        "keep_daily": 14,
        "keep_weekly": 8,
        "keep_monthly": 12,
        "jobs_file": _root("/etc/arise/backups.yaml", r"C:\Arise\config\backups.yaml"),
    },
    "nas": {
        "enabled": True,
        "host": "synology.ad.arisecenla.church",
        "mount": _root("/mnt/synology", r"Z:\\"),
        "protocol": "smb",
        "share": "arise",
        "dsm_url": "",
        "dsm_credentials_file": _root("/etc/arise/secrets/dsm.json", r"C:\Arise\config\secrets\dsm.json"),
    },
    "apps": {"docker": not WINDOWS, "root": _root("/srv/arise/apps", r"C:\Arise\data\apps")},
    "github": {
        "mirror": True,
        "mirror_path": _root("/srv/arise/backups/github-mirror", r"C:\Arise\data\backups\github-mirror"),
        "token_file": _root("/etc/arise/secrets/github-token", r"C:\Arise\config\secrets\github-token"),
        "repos": [
            "Rehchu/Church-server-OS-", "Rehchu/arise-youtube-automation", "Rehchu/arisechurch",
            "Rehchu/arisehub", "Rehchu/arise-church-backup", "Rehchu/arise-youtube",
            "Rehchu/projectbackups", "Rehchu/ai-chat-backups",
        ],
    },
    "paths": {
        "state_dir": _root("/var/lib/arise", r"C:\Arise\state"),
        "log_dir": _root("/var/log/arise", r"C:\Arise\logs"),
        "templates": "",   # resolved relative to the repo when empty
    },
}


class Section:
    def __init__(self, d: dict):
        self.__dict__.update(d)

    def get(self, k, default=None):
        return self.__dict__.get(k, default)

    def as_dict(self):
        return dict(self.__dict__)


@dataclass
class Config:
    path: str
    found: bool
    demo: bool
    raw: dict = field(default_factory=dict)

    def __post_init__(self):
        for name, defaults in DEFAULTS.items():
            merged = dict(defaults)
            merged.update(self.raw.get(name, {}) or {})
            setattr(self, name, Section(merged))

    # typed helpers -------------------------------------------------------
    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def web_dir(self) -> Path:
        return self.repo_root / "web"

    @property
    def templates_dir(self) -> Path:
        t = self.paths.get("templates") or ""
        return Path(t) if t else self.repo_root / "templates"

    @property
    def state_dir(self) -> Path:
        return Path(self.paths.state_dir)

    def public(self) -> dict:
        """The non-secret parts, for GET /api/settings."""
        out = {}
        for name in DEFAULTS:
            d = getattr(self, name).as_dict()
            d = {k: v for k, v in d.items() if "password" not in k and "token" not in k and "secret" not in k}
            out[name] = d
        out["_meta"] = {"path": self.path, "found": self.found, "demo": self.demo}
        return out


_cache: Config | None = None


def load(path: str | None = None, force: bool = False) -> Config:
    global _cache
    if _cache is not None and not force and path is None:
        return _cache
    p = path or os.environ.get("ARISE_CONFIG") or DEFAULTS_PATH()
    raw, found = {}, False
    try:
        with open(p, "rb") as f:
            raw = tomllib.load(f)
        found = True
    except FileNotFoundError:
        pass
    demo = os.environ.get("ARISE_DEMO", "") not in ("", "0", "false") or not found
    _cache = Config(path=p, found=found, demo=demo, raw=raw)
    return _cache


def DEFAULTS_PATH() -> str:
    return r"C:\Arise\config\arise.toml" if WINDOWS else "/etc/arise/arise.toml"

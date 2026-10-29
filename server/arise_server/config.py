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
        "session_hours": 8760,           # a year: browsers never sign out until they choose to (round 3, 38); the kiosk still locks at ten minutes
        "member_login": True,            # any directory user may sign in (members see their own files)
        "staff_access": "none",          # "none": staff and members get "your files are on your Mac"; "portal": the member portal (after round 5)
        "admins_group": "Domain Admins", # members of this group get the admin desktop
        "public_url": "",                # e.g. https://arise.arisecenla.com (Wix DNS) - used in share links; empty = the request's host
        "secret_file": _root("/etc/arise/secrets/web-secret", r"C:\Arise\config\secrets\web-secret"),
    },
    "directory": {
        "enabled": not WINDOWS,
        "realm": "AD.ARISECENLA.COM",
        "netbios": "ARISE",
        "dns_forwarder": "1.1.1.1",
        "homes_path": _root("/srv/arise/homes", r"C:\Arise\data\homes"),
    },
    # Mac and phone syncing (round 6, rows 13-19, 39, 40): Nextcloud over the home folders and shares.
    "cloud": {
        "enabled": True,
        "host": "",                     # empty: cloud.<realm in lower case>, the church network and Tailscale only
        "container": "arise-app-nextcloud",
        "www_uid": 33,                  # the official image's www-data; the ACLs give it rwX on homes and shares
        "data_dir": "",                 # empty: /srv/arise/apps/nextcloud/data (Nextcloud's own records; the files are the homes)
        "sync_folders": ["Desktop", "Documents"],   # row 13: what each Mac profile syncs in full
        "conflicts": "newest",          # row 15: the newer copy keeps the name; the older goes to the Trash
        "client_version": "3.14.3",     # the Nextcloud desktop client the Mac helper installs
        "client_team_id": "NKUJUXUJ3B", # Nextcloud GmbH's Apple Developer ID team; the pkg's signature must name it
    },
    # Bradly's Linux account (Oct 28): runs the 02:05 job, sudo without a password. install.sh fills it in.
    "owner": {"user": ""},
    # Round 6, 23: more accounts with the owner's powers (Kristina: "the same as me"): every ariseOS
    # group and sudo without a password. The 02:05 job and Claude stay [owner] user's only.
    "owners": {"users": []},
    "automator": {
        "enabled": True,
        "path": _root("/srv/arise/automator/ARISE_YouTube_Updater", r"C:\Arise\automator\ARISE_YouTube_Updater"),
        "python": _root("/opt/arise/venv/bin/python", r"C:\Arise\venv\Scripts\python.exe"),
        "schedule": "02:05",
    },
    # ---- storage (round 5, rows 12-15, 18) ----
    "storage": {
        "homes_on": "server",          # "server" (/srv/arise/homes) or "synology" (<nas mount>/arise/homes); decided with Friday's specs
        "home_quota_gb": 50,           # per home; 0 = no quota
        "quota_warn_pct": 90,
        "versions_days": 90,           # how far back Finder's Previous Versions reach (restic keeps its own 30/12/24)
        "pastors": ["bryant.sanders", "vanessa.sanders"],
        "pastors_path": "",            # empty: <data_root>/pastors (outside /srv/arise/shares, so no share above it reaches it)
        # Department folders (rows 16-17): all staff write, the department's own account writes its own,
        # people in the department read, admins all. The department's account is the user named like its folder.
        "departments": ["childrens-department", "inedge", "media", "worship", "kids", "alexandria"],
        # Extra logins that count as a department's own (the media booth's shared login, round 1, 32).
        "department_accounts": {"media": ["media-mac"]},
        "church_folder": "church",
        "staff_group": "Staff",
        "shared_path": "",             # empty: <data_root>/shared (one folder per person: what others shared with them)
    },
    "backups": {
        # Where restic writes, in order; the first one that is ready is live (row 15). "synology" is
        # synology_repo (else restic_repo) when the Synology is mounted; "arise-home" is arise_home_repo over Tailscale.
        "targets": ["synology", "arise-home"],
        "synology_repo": "",
        "arise_home_repo": "",         # e.g. sftp:arise-backup@arise-home:/srv/arise/backups/restic-pineville
        "restic_repo": _root("/mnt/synology/arise-backups/restic", r"Z:\arise-backups\restic"),
        "password_file": _root("/etc/arise/secrets/restic-password", r"C:\Arise\config\secrets\restic-password"),
        "schedule": "03:00",
        "keep_daily": 30,
        "keep_weekly": 12,
        "keep_monthly": 24,
        "jobs_file": _root("/etc/arise/backups.yaml", r"C:\Arise\config\backups.yaml"),
    },
    "nas": {
        "enabled": True,
        "host": "",   # empty: synology.<realm>, from [directory] realm (round 5: names come from config)
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
    "links": {"days": 0, "max_days": 365, "max_zip_bytes": 2 * 1024 ** 3},   # days 0 = a link never expires (Bradly, Oct 28)
    "church": {"name": "Arise Church", "city": "Pineville, LA", "tagline": ""},   # services and sunday_checklist: see arise.toml.example
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
        # Round 5: host names follow the realm; homes follow [storage] homes_on unless set by hand.
        if not self.nas.host:
            self.nas.host = "synology." + str(self.directory.realm).lower()
        hp = (self.raw.get("directory") or {}).get("homes_path")
        by_hand = hp and os.path.normpath(str(hp)) != os.path.join(str(self.system.data_root), "homes")
        if str(self.storage.homes_on).lower() == "synology" and not by_hand:
            self.directory.homes_path = os.path.join(self.nas.mount, "arise", "homes")
        if not self.storage.pastors_path:
            self.storage.pastors_path = os.path.join(self.system.data_root, "pastors")
        if not self.storage.shared_path:
            self.storage.shared_path = os.path.join(self.system.data_root, "shared")

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
            d = {k: v for k, v in d.items() if not secret_key(k)}
            out[name] = d
        out["_meta"] = {"path": self.path, "found": self.found, "demo": self.demo}
        return out


def secret_key(k: str) -> bool:
    """Pure: a setting whose value is (or may be) a credential, never sent to a page. A Discord
    or Slack webhook URL and an API key are credentials too, even under an innocent section."""
    k = k.lower()
    return any(w in k for w in ("password", "token", "secret", "webhook", "apikey", "api_key", "private", "credential")) \
        or k.endswith("_key") or k == "key"


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
    except PermissionError:
        raise SystemExit(f"arise: cannot read {p}: this user is not in the arise-conf group (sudo usermod -aG arise-conf $USER), or run as root")
    except FileNotFoundError:
        pass
    demo = os.environ.get("ARISE_DEMO", "") not in ("", "0", "false") or not found
    _cache = Config(path=p, found=found, demo=demo, raw=raw)
    return _cache


def DEFAULTS_PATH() -> str:
    return r"C:\Arise\config\arise.toml" if WINDOWS else "/etc/arise/arise.toml"

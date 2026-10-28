"""Sample data for demo mode.

Demo mode is on whenever /etc/arise/arise.toml is missing, ARISE_DEMO=1, or a
module's tool (samba-tool, restic, docker, systemctl) is not installed. Every
demo response carries "demo": true so the dashboard can say so in the corner.
The numbers are shaped like the real thing - nothing here is a real record of
the church's systems.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

_r = random.Random(4147)


def _ago(hours=0, minutes=0, days=0):
    return (datetime.now() - timedelta(days=days, hours=hours, minutes=minutes)).isoformat(timespec="seconds")


USERS = [
    {"name": "bradly", "display": "Bradly Dyer", "groups": ["Domain Admins", "Media", "Staff"], "enabled": True, "last_logon": _ago(hours=1), "home": r"\\arise-server\homes\bradly"},
    {"name": "media-mac", "display": "Media Booth Mac", "groups": ["Media"], "enabled": True, "last_logon": _ago(days=1), "home": r"\\arise-server\homes\media-mac"},
    {"name": "office", "display": "Church Office", "groups": ["Staff"], "enabled": True, "last_logon": _ago(days=2, hours=3), "home": r"\\arise-server\homes\office"},
    {"name": "kids-checkin", "display": "Kids Check-in", "groups": ["Kids-Check-in"], "enabled": True, "last_logon": _ago(days=6), "home": r"\\arise-server\homes\kids-checkin"},
    {"name": "guest-speaker", "display": "Guest Speaker (loaner)", "groups": ["Volunteers"], "enabled": False, "last_logon": None, "home": r"\\arise-server\homes\guest-speaker"},
    {"name": "childrens.department", "display": "Children's Department", "groups": ["Childrens-Department"], "enabled": True, "last_logon": _ago(days=3), "home": r"\\arise-server\homes\childrens.department"},
    {"name": "inedge", "display": "Inedge", "groups": ["Inedge"], "enabled": True, "last_logon": _ago(days=9), "home": r"\\arise-server\homes\inedge"},
]

GROUPS = [
    {"name": "Domain Admins", "members": ["bradly"], "description": "Server administrators"},
    {"name": "Staff", "members": ["bradly", "office"], "description": "Church office staff"},
    {"name": "Media", "members": ["bradly", "media-mac"], "description": "Livestream, YouTube, projector"},
    {"name": "Leadership", "members": [], "description": "Pastoral leadership"},
    {"name": "Volunteers", "members": ["guest-speaker"], "description": "Volunteer logins"},
    {"name": "Kids-Check-in", "members": ["kids-checkin"], "description": "Children's ministry check-in station"},
    {"name": "Childrens-Department", "members": ["childrens.department"], "description": "Children's Department (department login)"},
    {"name": "Inedge", "members": ["inedge"], "description": "Inedge (department login)"},
    {"name": "Worship", "members": [], "description": "Worship and music"},
]

COMPUTERS = [
    {"name": "MEDIA-MAC", "os": "macOS 15.1", "kind": "mac", "last_seen": _ago(hours=1), "ip": "192.168.1.41"},
    {"name": "OFFICE-IMAC", "os": "macOS 14.6", "kind": "mac", "last_seen": _ago(days=1), "ip": "192.168.1.42"},
    {"name": "LOBBY-PC", "os": "Windows 11 Pro", "kind": "windows", "last_seen": _ago(days=2), "ip": "192.168.1.50"},
    {"name": "SYNOLOGY", "os": "DSM 7.2", "kind": "nas", "last_seen": _ago(minutes=4), "ip": "192.168.1.20"},
]

DIRECTORY_STATUS = {
    "realm": "AD.ARISECENLA.CHURCH", "netbios": "ARISE", "role": "Domain Controller",
    "dc": "arise-server.ad.arisecenla.church", "dns_ok": True, "kerberos_ok": True, "ldap_ok": True,
    "forest_level": "2008_R2", "users": len(USERS), "groups": len(GROUPS), "computers": len(COMPUTERS),
}

SHARES = [
    {"name": "homes", "path": "/srv/arise/homes", "comment": "One folder per user, Mac-friendly", "writable": True, "browseable": False, "used": 48_700_000_000, "mac": True, "valid_users": ["%S"], "write_list": []},
    {"name": "shares", "path": "/srv/arise/shares", "comment": "Everyone in Domain Users", "writable": True, "browseable": True, "used": 212_000_000_000, "mac": True, "valid_users": [], "write_list": []},
    {"name": "media", "path": "/mnt/synology/media", "comment": "On the Synology - service recordings, graphics", "writable": True, "browseable": True, "used": 1_380_000_000_000, "mac": True, "valid_users": ["@Media", "@Staff"], "write_list": ["@Media"]},
    {"name": "staff", "path": "/srv/arise/shares/staff", "comment": "Staff: pastors and paid staff", "writable": True, "browseable": True, "used": 31_000_000_000, "mac": True, "valid_users": ["@Staff", "@Domain Admins"], "write_list": []},
    {"name": "leadership", "path": "/srv/arise/shares/leadership", "comment": "Leadership only", "writable": True, "browseable": True, "used": 4_200_000_000, "mac": True, "valid_users": ["@Leadership", "@Domain Admins"], "write_list": []},
    {"name": "graphics", "path": "/srv/arise/shares/graphics", "comment": "Proclaim backgrounds, loops, lower thirds (synced to the media Mac)", "writable": True, "browseable": True, "used": 58_000_000_000, "mac": True, "valid_users": ["@Media", "@Staff", "@Domain Admins"], "write_list": ["@Media", "@Domain Admins"]},
    {"name": "kids", "path": "/srv/arise/shares/kids", "comment": "Kids ministry", "writable": True, "browseable": True, "used": 2_900_000_000, "mac": True, "valid_users": ["@Kids", "@Childrens-Department", "@Domain Admins"], "write_list": []},
    {"name": "childrens-department", "path": "/srv/arise/shares/childrens-department", "comment": "Children's Department", "writable": True, "browseable": True, "used": 1_100_000_000, "mac": True, "valid_users": ["@Childrens-Department", "@Domain Admins"], "write_list": []},
    {"name": "inedge", "path": "/srv/arise/shares/inedge", "comment": "Inedge", "writable": True, "browseable": True, "used": 640_000_000, "mac": True, "valid_users": ["@Inedge", "@Domain Admins"], "write_list": []},
    {"name": "worship", "path": "/srv/arise/shares/worship", "comment": "Worship and music: charts, setlists, tracks", "writable": True, "browseable": True, "used": 12_000_000_000, "mac": True, "valid_users": ["@Worship", "@Media", "@Domain Admins"], "write_list": []},
    {"name": "recordings", "path": "/mnt/synology/arise/recordings", "comment": "Sunday recordings (on the Synology; not in the restic backup)", "writable": True, "browseable": True, "used": 1_240_000_000_000, "mac": True, "valid_users": ["@Media", "@Domain Admins"], "write_list": []},
    {"name": "sysvol", "path": "/var/lib/samba/sysvol", "comment": "Domain policies (system)", "writable": False, "browseable": False, "used": 2_100_000, "mac": False, "valid_users": ["@Domain Admins"], "write_list": []},
]

SERVICES = [
    {"unit": "arise-web.service", "name": "Arise dashboard", "active": "active", "sub": "running", "since": _ago(days=14, hours=3)},
    {"unit": "samba-ad-dc.service", "name": "Active Directory", "active": "active", "sub": "running", "since": _ago(days=14, hours=3)},
    {"unit": "docker.service", "name": "Docker", "active": "active", "sub": "running", "since": _ago(days=14, hours=3)},
    {"unit": "arise-automator.timer", "name": "YouTube automator (02:05)", "active": "active", "sub": "waiting", "since": _ago(days=14, hours=3)},
    {"unit": "arise-backup.timer", "name": "Backups (03:00)", "active": "active", "sub": "waiting", "since": _ago(days=14, hours=3)},
    {"unit": "arise-mirror.timer", "name": "GitHub mirror (04:00)", "active": "active", "sub": "waiting", "since": _ago(days=14, hours=3)},
    {"unit": "arise-nas-mount.service", "name": "Synology mount", "active": "active", "sub": "exited", "since": _ago(days=14, hours=3)},
    {"unit": "ssh.service", "name": "SSH", "active": "active", "sub": "running", "since": _ago(days=14, hours=3)},
]

BACKUP_JOBS = [
    {"id": "automator", "name": "YouTube automator", "paths": ["/srv/arise/automator"], "tags": ["automator"]},
    {"id": "homes", "name": "Home folders", "paths": ["/srv/arise/homes"], "tags": ["homes"]},
    {"id": "shares", "name": "Shared folders", "paths": ["/srv/arise/shares"], "tags": ["shares"]},
    {"id": "github", "name": "GitHub mirror", "paths": ["/srv/arise/backups/github-mirror"], "tags": ["github"]},
    {"id": "config", "name": "Server config", "paths": ["/etc/arise", "/etc/samba", "/var/lib/samba/private"], "tags": ["config"]},
]


def _history():
    rows = []
    for d in range(10, -1, -1):
        for i, j in enumerate(BACKUP_JOBS):
            started = datetime.now().replace(hour=3, minute=0, second=0, microsecond=0) - timedelta(days=d) + timedelta(minutes=i * 4)
            ok = not (d == 3 and j["id"] == "homes")
            rows.append({
                "job": j["id"], "name": j["name"], "started": started.isoformat(timespec="seconds"),
                "finished": (started + timedelta(minutes=2 + i)).isoformat(timespec="seconds"),
                "ok": ok, "snapshot_id": f"{_r.randrange(16**8):08x}" if ok else None,
                "bytes_added": _r.randrange(2_000_000, 900_000_000) if ok else 0,
                "files_new": _r.randrange(0, 400) if ok else 0,
                "error": None if ok else "Fatal: unable to open repository at /mnt/synology/arise-backups/restic: mount not present (the NAS was rebooting)",
            })
    return rows


BACKUP_HISTORY = _history()
BACKUP_REPO = {"repo": "/mnt/synology/arise-backups/restic", "ok": True, "snapshots": 53, "total_size": 318_000_000_000, "raw_size": 1_950_000_000_000, "last_check": _ago(days=9), "keep": {"daily": 14, "weekly": 8, "monthly": 12}}

AUTOMATOR = {
    "path": "/srv/arise/automator/ARISE_YouTube_Updater",
    "last_run": _ago(hours=datetime.now().hour - 2 if datetime.now().hour >= 2 else 0),
    "last_ok": True, "last_summary": "3 jobs done · 0 failed · 1 skipped · 1,962 of 10,000 units used",
    "next_run": (datetime.now().replace(hour=2, minute=5, second=0, microsecond=0) + timedelta(days=1)).isoformat(timespec="seconds"),
    "quota_today": 1962, "quota_daily": 10000, "quota_reset": "2:00 AM Central",
    "holds": 8, "rules": 3, "worklist_enabled": 4, "worklist_total": 6,
    "token_ok": True, "token_days_left": 5, "token_note": "OAuth app is still in Testing: Google expires the token every 7 days. Publish it (Google Cloud → OAuth consent → Audience → Publish app).",
    "signed_in_as": "Arise Church (@arisechurch4147)",
    "latest_report": """# Arise YouTube — automated run
Sunday 26 October 2026, 02:05 AM Central

3 jobs done · 0 failed · 1 skipped · 1,962 of 10,000 units used

## Preflight
- signed in as **Arise Church**
- quota: 9,999 of 10,000 units left today (resets 2 AM Central)
- 8 videos on hold, 3 standing rules loaded

## Job: star-cleanup (priority 1)
- dry run: 19 descriptions carry `**` from the Grok era
- applied 19 · read back 19 · backed up first to desc_backups/
- cost 1,900 units (50 per write)

## Job: shorts-tags (priority 2)
- **skipped** — disabled in worklist.json until Bradly sets the priority

## Job: chapters-check (priority 3)
- 0 descriptions with a last chapter under 10:00 on a video over an hour
- cost 61 units

## Job: report (priority 9)
- wrote reports/2026-10-26_0205.md
""",
    "reports": [f"2026-10-{26 - i:02d}_0205.md" for i in range(0, 12)],
}

WORKLIST = [
    {"id": "star-cleanup", "priority": 1, "enabled": True, "note": "Remove ** markdown stars from the Grok-era descriptions, 50u each", "cost_estimate": 2000},
    {"id": "shorts-tags", "priority": 2, "enabled": False, "note": "Shorts tags batch 2 (~500 left). Off until Bradly sets the priority vs the ** cleanup", "cost_estimate": 7500},
    {"id": "chapters-check", "priority": 3, "enabled": True, "note": "Flag H:MM chapter lists on videos over an hour", "cost_estimate": 100},
    {"id": "vertical-twins", "priority": 4, "enabled": True, "note": "Label StreamYard vertical copies (Vertical)", "cost_estimate": 300},
    {"id": "playlist-fill", "priority": 5, "enabled": True, "note": "Route new services to the speaker playlists", "cost_estimate": 200},
    {"id": "report", "priority": 9, "enabled": True, "note": "Always last; writes LATEST_REPORT.md", "cost_estimate": 0},
]

HOLDS = {
    "videos": [
        {"id": "8gUVgiIENWk", "reason": "Sep 13 service — Bradly handled it himself"},
        {"id": "bj1epm4xmt0", "reason": "chapters replaced by hand Oct 7"},
        {"id": "MnXmccLS2p8", "reason": "spelling call: GAURD stays"},
        {"id": "GfTvURWWlLg", "reason": "spelling call: DECIEVED stays"},
    ],
    "rules": [
        "Never tidy the pastors' spelling.",
        "Never invent a CCLI number, songwriter, speaker or sermon theme.",
        "Praise (7213077) is always followed by My Worship (7098688).",
    ],
}

QUOTA = {"daily": 10000, "spent": 1962, "entries": [
    {"when": _ago(hours=5), "units": 1, "what": "preflight channel check"},
    {"when": _ago(hours=5), "units": 1900, "what": "star-cleanup: 38 videos.update"},
    {"when": _ago(hours=5), "units": 61, "what": "chapters-check: list reads"},
]}

APPS = [
    {"name": "filebrowser", "template": "filebrowser", "status": "running", "ports": ["8081:80"], "cpu": 0.3, "mem": 38_000_000, "url": "http://arise-server:8081", "updated": _ago(days=3)},
    {"name": "uptime-kuma", "template": "uptime-kuma", "status": "running", "ports": ["8082:3001"], "cpu": 1.1, "mem": 142_000_000, "url": "http://arise-server:8082", "updated": _ago(days=3)},
    {"name": "syncthing", "template": "syncthing", "status": "exited", "ports": ["8384:8384"], "cpu": 0.0, "mem": 0, "url": "http://arise-server:8384", "updated": _ago(days=1)},
]

TEMPLATES = [
    {"id": "filebrowser", "name": "File Browser", "description": "Browse, upload and share the church folders from any browser.", "category": "Files", "ports": ["8081:80"], "icon": "folder"},
    {"id": "uptime-kuma", "name": "Uptime Kuma", "description": "Watches arisecenla.church, the Synology and the stream; texts you when one is down.", "category": "Monitoring", "ports": ["8082:3001"], "icon": "pulse"},
    {"id": "syncthing", "name": "Syncthing", "description": "Keeps a folder on the media Mac and the server identical, both directions.", "category": "Files", "ports": ["8384:8384"], "icon": "sync"},
    {"id": "vaultwarden", "name": "Vaultwarden", "description": "The church password vault, Bitwarden-compatible, self-hosted.", "category": "Security", "ports": ["8083:80"], "icon": "lock"},
]

NAS = {
    "enabled": True, "host": "synology.ad.arisecenla.church", "mount": "/mnt/synology", "protocol": "smb", "mounted": True,
    "total": 16_000_000_000_000, "used": 4_900_000_000_000, "free": 11_100_000_000_000,
    "dsm": {"ok": True, "model": "(set dsm_url in arise.toml to read the model)", "version": "DSM 7.2", "temperature": 41, "volume_status": "healthy", "raid": "SHR (1-drive fault tolerance)", "drives": 4},
    "domain_joined": True,
    "hyper_backup": {"task": "USB off-site", "last": _ago(days=1, hours=2), "ok": True},
}

LOGS = {
    "arise-web.service": "\n".join(f"Oct 2{6 - i // 10} 0{i % 6}:1{i % 10}:0{i % 7} arise-server arise-web[812]: INFO 192.168.1.41 GET /api/overview 200" for i in range(40)),
    "arise-automator.service": AUTOMATOR["latest_report"],
    "samba-ad-dc.service": "Oct 26 02:00:01 arise-server samba[655]:   Kerberos: TGS-REQ bradly@AD.ARISECENLA.CHURCH from ipv4:192.168.1.41 for cifs/arise-server\nOct 26 02:00:01 arise-server samba[655]:   Kerberos: TGS-REQ authtime: 2026-10-26T01:58:11 starttime: unset endtime: 2026-10-26T11:58:11 renew till: 2026-11-02T01:58:11\n",
}

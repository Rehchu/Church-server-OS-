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
    # Round 5: the two pastors (the Pastors folder is theirs alone).
    {"name": "bryant.sanders", "display": "Apostle Bryant Sanders", "groups": ["Domain Admins", "Staff", "Leadership", "Pastors"], "enabled": True, "last_logon": _ago(days=1, hours=4), "home": r"\\arise-server\homes\bryant.sanders"},
    {"name": "vanessa.sanders", "display": "Pastor Vanessa Sanders", "groups": ["Domain Admins", "Staff", "Leadership", "Pastors"], "enabled": True, "last_logon": _ago(days=2), "home": r"\\arise-server\homes\vanessa.sanders"},
    # Round 6, 21-23: the fourth admin at the closet, with Bradly's powers.
    {"name": "kristina.robinson", "display": "Minister Kristina Robinson", "groups": ["Domain Admins", "Staff", "Worship"], "enabled": True, "last_logon": _ago(days=1, hours=7), "home": r"\\arise-server\homes\kristina.robinson"},
]

GROUPS = [
    {"name": "Domain Admins", "members": ["bradly", "bryant.sanders", "vanessa.sanders", "kristina.robinson"], "description": "Server administrators"},
    {"name": "Staff", "members": ["bradly", "office", "bryant.sanders", "vanessa.sanders", "kristina.robinson"], "description": "Church office staff"},
    {"name": "Media", "members": ["bradly", "media-mac"], "description": "Livestream, YouTube, projector"},
    {"name": "Leadership", "members": ["bryant.sanders", "vanessa.sanders"], "description": "Pastoral leadership"},
    {"name": "Volunteers", "members": ["guest-speaker"], "description": "Volunteer logins"},
    {"name": "Kids-Check-in", "members": ["kids-checkin"], "description": "Children's ministry check-in station"},
    {"name": "Childrens-Department", "members": ["childrens.department"], "description": "Children's Department (department login)"},
    {"name": "Inedge", "members": ["inedge"], "description": "Inedge (department login)"},
    {"name": "Worship", "members": ["kristina.robinson"], "description": "Worship and music"},
    {"name": "Pastors", "members": ["bryant.sanders", "vanessa.sanders"], "description": "The Pastors folder: Apostle Bryant and Pastor Vanessa only"},
    {"name": "Alexandria", "members": [], "description": "Arise Church Alexandria (campus)"},
]

COMPUTERS = [
    {"name": "MEDIA-MAC", "os": "macOS 15.1", "kind": "mac", "last_seen": _ago(hours=1), "ip": "192.168.1.41"},
    {"name": "OFFICE-IMAC", "os": "macOS 14.6", "kind": "mac", "last_seen": _ago(days=1), "ip": "192.168.1.42"},
    {"name": "LOBBY-PC", "os": "Windows 11 Pro", "kind": "windows", "last_seen": _ago(days=2), "ip": "192.168.1.50"},
    {"name": "SYNOLOGY", "os": "DSM 7.2", "kind": "nas", "last_seen": _ago(minutes=4), "ip": "192.168.1.20"},
]

DIRECTORY_STATUS = {
    "realm": "AD.ARISECENLA.COM", "netbios": "ARISE", "role": "Domain Controller",
    "dc": "arise-server.ad.arisecenla.com", "dns_ok": True, "kerberos_ok": True, "ldap_ok": True,
    "forest_level": "2008_R2", "users": len(USERS), "groups": len(GROUPS), "computers": len(COMPUTERS),
}

SHARES = [
    {"name": "church", "path": "/srv/arise/shares/church", "comment": "The Church folder: everyone reads and writes", "writable": True, "browseable": True, "used": 3_400_000_000, "mac": True, "valid_users": ["@Domain Users"], "write_list": []},
    {"name": "pastors", "path": "/srv/arise/pastors", "comment": "Pastors only", "writable": True, "browseable": False, "used": 900_000_000, "mac": True, "valid_users": ["bryant.sanders", "vanessa.sanders"], "write_list": []},
    {"name": "shared", "path": "/srv/arise/shared/%U", "comment": "Shared with me", "writable": True, "browseable": True, "used": 0, "mac": True, "valid_users": ["%U"], "write_list": []},
    {"name": "media", "path": "/mnt/synology/media", "comment": "On the Synology - service recordings, graphics", "writable": False, "browseable": True, "used": 1_380_000_000_000, "mac": True, "valid_users": ["@Media", "@Staff", "@Domain Admins", "media", "media-mac"], "write_list": ["@Staff", "@Domain Admins", "media", "media-mac"]},
    {"name": "worship", "path": "/srv/arise/shares/worship", "comment": "Worship and music: charts, setlists, tracks", "writable": False, "browseable": True, "used": 12_000_000_000, "mac": True, "valid_users": ["@Worship", "@Staff", "@Domain Admins", "worship"], "write_list": ["@Staff", "@Domain Admins", "worship"]},
    {"name": "graphics", "path": "/srv/arise/shares/graphics", "comment": "Proclaim backgrounds, loops, lower thirds (synced to the media Mac)", "writable": True, "browseable": True, "used": 58_000_000_000, "mac": True, "valid_users": ["@Media", "@Staff", "@Domain Admins"], "write_list": ["@Media", "@Domain Admins"]},
    {"name": "staff", "path": "/srv/arise/shares/staff", "comment": "Staff: pastors and paid staff", "writable": True, "browseable": True, "used": 31_000_000_000, "mac": True, "valid_users": ["@Staff", "@Domain Admins"], "write_list": []},
    {"name": "leadership", "path": "/srv/arise/shares/leadership", "comment": "Leadership only", "writable": True, "browseable": True, "used": 4_200_000_000, "mac": True, "valid_users": ["@Leadership", "@Domain Admins"], "write_list": []},
    {"name": "kids", "path": "/srv/arise/shares/kids", "comment": "Kids ministry", "writable": False, "browseable": True, "used": 2_900_000_000, "mac": True, "valid_users": ["@Kids", "@Staff", "@Domain Admins", "kids"], "write_list": ["@Staff", "@Domain Admins", "kids"]},
    {"name": "childrens-department", "path": "/srv/arise/shares/childrens-department", "comment": "Children's Department", "writable": False, "browseable": True, "used": 1_100_000_000, "mac": True, "valid_users": ["@Childrens-Department", "@Staff", "@Domain Admins", "childrens.department"], "write_list": ["@Staff", "@Domain Admins", "childrens.department"]},
    {"name": "inedge", "path": "/srv/arise/shares/inedge", "comment": "Inedge", "writable": False, "browseable": True, "used": 640_000_000, "mac": True, "valid_users": ["@Inedge", "@Staff", "@Domain Admins", "inedge"], "write_list": ["@Staff", "@Domain Admins", "inedge"]},
    {"name": "alexandria", "path": "/srv/arise/shares/alexandria", "comment": "Alexandria: staff and the campus write", "writable": False, "browseable": True, "used": 0, "mac": True, "valid_users": ["@Alexandria", "@Staff", "@Domain Admins", "alexandria"], "write_list": ["@Staff", "@Domain Admins", "alexandria"]},
    {"name": "recordings", "path": "/mnt/synology/arise/recordings", "comment": "Sunday recordings (on the Synology; not in the restic backup)", "writable": True, "browseable": True, "used": 1_240_000_000_000, "mac": True, "valid_users": ["@Media", "@Domain Admins"], "write_list": []},
    {"name": "homes", "path": "/srv/arise/homes", "comment": "One folder per user, Mac-friendly", "writable": True, "browseable": False, "used": 48_700_000_000, "mac": True, "valid_users": ["%S"], "write_list": []},
    {"name": "shares", "path": "/srv/arise/shares", "comment": "Everyone in Domain Users", "writable": True, "browseable": True, "used": 212_000_000_000, "mac": True, "valid_users": [], "write_list": []},
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
BACKUP_REPO = {"repo": "/mnt/synology/arise-backups/restic", "ok": True, "snapshots": 53, "total_size": 318_000_000_000, "raw_size": 1_950_000_000_000, "last_check": _ago(days=9), "keep": {"daily": 30, "weekly": 12, "monthly": 24}}

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
    {"name": "netdata", "template": "netdata", "status": "running", "ports": ["19999:19999"], "cpu": 2.6, "mem": 210_000_000, "url": "http://arise-server:19999", "updated": _ago(days=3), "ram_mb": 250, "limit_mb": 512},
    {"name": "uptime-kuma", "template": "uptime-kuma", "status": "running", "ports": ["8082:3001"], "cpu": 1.1, "mem": 142_000_000, "url": "http://arise-server:8082", "updated": _ago(days=3), "ram_mb": 150, "limit_mb": 384},
    {"name": "guacamole", "template": "guacamole", "status": "running", "ports": ["8084:8080"], "cpu": 2.6, "mem": 778_000_000, "url": "http://arise-server:8084", "updated": _ago(days=3), "ram_mb": 900, "limit_mb": 1536},
    {"name": "trilium", "template": "trilium", "status": "running", "ports": ["8090:8080"], "cpu": 0.2, "mem": 160_000_000, "url": "http://arise-server:8090", "updated": _ago(days=3), "ram_mb": 200, "limit_mb": 512},
    {"name": "immich", "template": "immich", "status": "running", "ports": ["2283:2283"], "cpu": 3.4, "mem": 2_100_000_000, "url": "http://arise-server:2283", "updated": _ago(days=2), "ram_mb": 2500, "limit_mb": 4096},
    {"name": "jellyfin", "template": "jellyfin", "status": "running", "ports": ["8096:8096"], "cpu": 0.8, "mem": 480_000_000, "url": "http://arise-server:8096", "updated": _ago(days=3), "ram_mb": 600, "limit_mb": 2048},
    {"name": "vaultwarden", "template": "vaultwarden", "status": "running", "ports": ["8083:80"], "cpu": 0.1, "mem": 60_000_000, "url": "http://arise-server:8083", "updated": _ago(days=3), "ram_mb": 100, "limit_mb": 384},
    {"name": "syncthing", "template": "syncthing", "status": "exited", "ports": ["8384:8384"], "cpu": 0.0, "mem": 0, "url": "http://arise-server:8384", "updated": _ago(days=1), "ram_mb": 150, "limit_mb": 512},
    {"name": "nextcloud", "template": "nextcloud", "status": "exited", "ports": ["8091:80"], "cpu": 0.0, "mem": 0, "url": "http://arise-server:8091", "updated": _ago(days=3), "ram_mb": 1200, "limit_mb": 2048},
    {"name": "ollama", "template": "ollama", "status": "exited", "ports": ["11434:11434"], "cpu": 0.0, "mem": 0, "url": "http://arise-server:11434", "updated": _ago(days=3), "ram_mb": 2500, "limit_mb": 6144},
]

TEMPLATES = [
    {"id": "filebrowser", "name": "File Browser", "description": "Browse, upload and share the church folders from any browser.", "category": "Files", "ports": ["8081:80"], "icon": "folder"},
    {"id": "uptime-kuma", "name": "Uptime Kuma", "description": "Watches arisecenla.church, the Synology and the stream; texts you when one is down.", "category": "Monitoring", "ports": ["8082:3001"], "icon": "pulse"},
    {"id": "syncthing", "name": "Syncthing", "description": "Keeps a folder on the media Mac and the server identical, both directions.", "category": "Files", "ports": ["8384:8384"], "icon": "sync"},
    {"id": "vaultwarden", "name": "Vaultwarden", "description": "The church password vault, Bitwarden-compatible, self-hosted.", "category": "Security", "ports": ["8083:80"], "icon": "lock"},
]

NAS = {
    "enabled": True, "host": "synology.ad.arisecenla.com", "mount": "/mnt/synology", "protocol": "smb", "mounted": True,
    "total": 16_000_000_000_000, "used": 4_900_000_000_000, "free": 11_100_000_000_000,
    "dsm": {"ok": True, "model": "(set dsm_url in arise.toml to read the model)", "version": "DSM 7.2", "temperature": 41, "volume_status": "healthy", "raid": "SHR (1-drive fault tolerance)", "drives": 4},
    "domain_joined": True,
    "hyper_backup": {"task": "USB off-site", "last": _ago(days=1, hours=2), "ok": True},
}

LOGS = {
    "arise-web.service": "\n".join(f"Oct 2{6 - i // 10} 0{i % 6}:1{i % 10}:0{i % 7} arise-server arise-web[812]: INFO 192.168.1.41 GET /api/overview 200" for i in range(40)),
    "arise-automator.service": AUTOMATOR["latest_report"],
    "samba-ad-dc.service": "Oct 26 02:00:01 arise-server samba[655]:   Kerberos: TGS-REQ bradly@AD.ARISECENLA.COM from ipv4:192.168.1.41 for cifs/arise-server\nOct 26 02:00:01 arise-server samba[655]:   Kerberos: TGS-REQ authtime: 2026-10-26T01:58:11 starttime: unset endtime: 2026-10-26T11:58:11 renew till: 2026-11-02T01:58:11\n",
}


# Everything on the switch (sample). MACs are locally administered (02:...), so none is a real device.
DEVICES_META = {"last_scan": "2026-10-28T06:00", "tool": "arp-scan", "subnet": "192.168.1.0/24", "iface": "eno1", "found": 11, "new": 3, "wide": True}
DEVICES = [
    {"mac": "02:a1:00:00:00:01", "ip": "192.168.1.1", "ips": ["192.168.1.1"], "vendor": "Netgear", "guess": "router", "kind": "router", "hostname": "", "name": "Netgear A (the router at the modem)", "note": "hands out the addresses on this wire", "first_seen": "2026-10-26T14:00", "last_seen": "2026-10-28T06:00", "joined": False, "online": True, "kind_final": "router"},
    {"mac": "02:a1:00:00:00:57", "ip": "192.168.1.57", "ips": ["192.168.1.57"], "vendor": "Dell", "guess": "server", "kind": "server", "hostname": "arise-server.ad.arisecenla.com", "name": "arise-server (this box)", "note": "", "first_seen": "2026-10-26T14:00", "last_seen": "2026-10-28T06:00", "joined": True, "online": True, "kind_final": "server"},
    {"mac": "02:a1:00:00:00:11", "ip": "192.168.1.11", "ips": ["192.168.1.11"], "vendor": "Synology", "guess": "nas", "kind": "", "hostname": "synology", "name": "Synology", "note": "", "first_seen": "2026-10-26T14:00", "last_seen": "2026-10-28T06:00", "joined": False, "online": True, "kind_final": "nas"},
    {"mac": "02:a1:00:00:00:02", "ip": "192.168.1.2", "ips": ["192.168.1.2"], "vendor": "Netgear", "guess": "router", "kind": "router", "hostname": "", "name": "Netgear B (office) - its own network behind it", "note": "the office Mac is behind this; it is not visible here", "first_seen": "2026-10-26T14:00", "last_seen": "2026-10-28T06:00", "joined": False, "online": True, "kind_final": "router"},
    {"mac": "02:a1:00:00:00:03", "ip": "192.168.1.3", "ips": ["192.168.1.3"], "vendor": "Google", "guess": "router", "kind": "router", "hostname": "", "name": "Google Mesh - its own network behind it", "note": "the media Mac and the NDI cameras' switch are behind this", "first_seen": "2026-10-26T14:00", "last_seen": "2026-10-28T06:00", "joined": False, "online": True, "kind_final": "router"},
    {"mac": "02:a1:00:00:00:21", "ip": "192.168.1.21", "ips": ["192.168.1.21", "192.168.1.34"], "vendor": "Apple", "guess": "mac", "kind": "", "hostname": "MEDIA-MAC-01.ad.arisecenla.com", "name": "", "note": "", "first_seen": "2026-10-27T09:10", "last_seen": "2026-10-28T06:00", "joined": True, "online": True, "kind_final": "mac"},
    {"mac": "02:a1:00:00:00:40", "ip": "192.168.1.40", "ips": ["192.168.1.40"], "vendor": "HP", "guess": "printer", "kind": "", "hostname": "", "name": "", "note": "", "first_seen": "2026-10-26T14:00", "last_seen": "2026-10-28T06:00", "joined": False, "online": True, "kind_final": "printer"},
    {"mac": "02:a1:00:00:00:64", "ip": "192.168.0.64", "ips": ["192.168.0.64"], "vendor": "Hikvision", "guess": "camera", "kind": "", "hostname": "", "name": "", "note": "", "first_seen": "2026-10-28T06:00", "last_seen": "2026-10-28T06:00", "joined": False, "online": True, "kind_final": "camera", "stray": "192.168.0.0/24"},
    {"mac": "02:a1:00:00:00:65", "ip": "192.168.0.65", "ips": ["192.168.0.65"], "vendor": "Hikvision", "guess": "camera", "kind": "", "hostname": "", "name": "", "note": "", "first_seen": "2026-10-28T06:00", "last_seen": "2026-10-28T06:00", "joined": False, "online": True, "kind_final": "camera", "stray": "192.168.0.0/24"},
    {"mac": "02:a1:00:00:00:88", "ip": "192.168.1.88", "ips": ["192.168.1.88"], "vendor": "", "guess": "unknown", "kind": "", "hostname": "", "name": "", "note": "", "first_seen": "2026-10-28T06:00", "last_seen": "2026-10-28T06:00", "joined": False, "online": True, "kind_final": "unknown"},
    {"mac": "02:a1:00:00:00:60", "ip": "192.168.1.60", "ips": ["192.168.1.60"], "vendor": "Apple", "guess": "mac", "kind": "", "hostname": "", "name": "Loaner MacBook", "note": "", "first_seen": "2026-10-26T14:00", "last_seen": "2026-10-27T17:40", "joined": False, "online": False, "kind_final": "mac"},
]

# Behind the other routers (sample): what Netgear B reports as attached, read from the router.
ROUTERS_BEHIND = [
    {"id": "netgear-b", "name": "Netgear B (office)", "host": "10.0.0.1", "kind": "netgear", "ok": True, "err": "", "devices": [
        {"mac": "02:b2:00:00:00:12", "ip": "10.0.0.12", "hostname": "OFFICE-MAC-01", "name": "", "vendor": "", "kind_final": "wired", "signal": None, "link_rate": 1000, "online": True, "behind": True},
        {"mac": "02:b2:00:00:00:08", "ip": "10.0.0.8", "hostname": "HP-office-printer", "name": "", "vendor": "", "kind_final": "wired", "signal": None, "link_rate": 100, "online": True, "behind": True},
    ]},
    {"id": "google-mesh", "name": "Google Mesh", "host": "", "kind": "google", "ok": False, "err": "Google Mesh has no local device-list API; its clients are in the Google Home app", "devices": []},
]

# ONVIF discovery (sample): two cameras answered, both parked on 192.168.0.x by the installer.
CAMERAS = [
    {"ip": "192.168.0.64", "xaddrs": ["http://192.168.0.64/onvif/device_service"], "name": "FRONT-DOOR", "hardware": "DS-2CD2043G2", "scopes": [], "reachable": False},
    {"ip": "192.168.0.65", "xaddrs": ["http://192.168.0.65/onvif/device_service"], "name": "PARKING", "hardware": "DS-2CD2043G2", "scopes": [], "reachable": False},
]

# Mail (sample): a few contacts and two broadcasts. Not real people.
MAIL_CONTACTS = [
    {"id": "c1", "email": "sample.one@example.com", "first_name": "Sample", "last_name": "One", "created_at": "2026-10-20T14:00:00Z", "unsubscribed": False},
    {"id": "c2", "email": "sample.two@example.com", "first_name": "Sample", "last_name": "Two", "created_at": "2026-10-20T14:00:00Z", "unsubscribed": False},
    {"id": "c3", "email": "sample.three@example.com", "first_name": "", "last_name": "", "created_at": "2026-10-21T09:10:00Z", "unsubscribed": True},
]
MAIL_BROADCASTS = [
    {"id": "bc-1", "name": "This week at Arise", "subject": "This week at Arise", "status": "sent", "created_at": "2026-10-21T15:00:00Z", "sent_at": "2026-10-21T15:05:00Z", "audience_id": "demo-audience"},
    {"id": "bc-2", "name": "Glory Night reminder", "subject": "Glory Night is tonight at 7", "status": "draft", "created_at": "2026-10-27T10:00:00Z", "sent_at": None, "audience_id": "demo-audience"},
]

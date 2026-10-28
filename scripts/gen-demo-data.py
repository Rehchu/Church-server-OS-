#!/usr/bin/env python3
"""Writes web/demo-data.js from the server's own demo-mode responses.

The published preview page and any machine without the API fall back to this
file, so the preview is the real UI over the real sample shapes. Re-run it
whenever server/arise_server/demo.py or a route changes:

    python3 scripts/gen-demo-data.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ["ARISE_DEMO"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from arise_server.main import app  # noqa: E402

GETS = [
    "/overview", "/services", "/directory/status", "/directory/users", "/directory/groups", "/directory/computers",
    "/shares", "/backups/jobs", "/backups/history", "/backups/snapshots", "/backups/repo",
    "/automator", "/automator/worklist", "/automator/holds", "/automator/quota", "/automator/cutover", "/automator/reports",
    "/apps", "/apps/templates", "/nas", "/settings", "/auth/me", "/health",
    "/sites", "/remote", "/sermons", "/files/roots", "/links", "/devices", "/devices/behind", "/devices/cameras", "/church", "/sunday", "/public/signage", "/mail", "/mail/contacts", "/mail/broadcasts", "/bible/translations", "/system/updates", "/notify",
    "/audit?limit=60", "/directory/leaving", "/calendar", "/calendar/subscribe", "/weather", "/help", "/help/PORTAL-GUIDE", "/help/README", "/about/whatsnew", "/me/password/rules",
    "/updates", "/activity", "/automations", "/storage", "/monitor", "/apps/catalog", "/apps/open/trilium", "/apps/open/immich", "/logs/sources",
    "/logs/file/updates.log", "/logs/file/install.log", "/logs/file/backup.log", "/apps/theme/jellyfin", "/apps/theme/homepage", "/apps/theme/nextcloud", "/apps/theme/immich", "/apps/theme/grafana", "/apps/theme/owncast", "/apps/theme/bookstack", "/apps/theme/uptime-kuma", "/apps/theme/onlyoffice",
    "/notifications", "/checklists", "/setup", "/kiosk/scale", "/public/faces", "/desktop",
    "/me/2fa", "/directory/2fa", "/repos", "/automator/cutover", "/security", "/security/scan", "/security/snapshots", "/files/recent", "/files/trash", "/push/key", "/about/week",
    "/bible?ref=John 3:16", "/bible?ref=Psalm 23", "/bible?ref=Romans 8:28", "/bible?ref=Isaiah 40:31", "/bible?ref=Philippians 4:6-7", "/bible?ref=Exodus 19:5-6",
]
c = TestClient(app)
data = {}
for p in GETS:
    r = c.get("/api" + p)
    data["GET " + p] = r.json()
for u in ["arise-web.service", "arise-automator.service", "arise-backup.service", "arise-mirror.service", "samba-ad-dc.service", "docker.service", "arise-nas-mount.service"]:
    data[f"GET /logs/{u}"] = c.get(f"/api/logs/{u}").json()
# The Automator's channel: every sample video, its card and its transcript. The
# preview's mock filters and searches these itself (computedGet in demo-mock.js).
data["GET /automator/channel"] = c.get("/api/automator/channel").json()
data["GET /automator/videos"] = c.get("/api/automator/videos").json()
for v in data["GET /automator/videos"]["videos"]:
    data[f"GET /automator/videos/{v['id']}"] = c.get(f"/api/automator/videos/{v['id']}").json()
    data[f"GET /automator/videos/{v['id']}/transcript"] = c.get(f"/api/automator/videos/{v['id']}/transcript").json()
# The Songs tab: the sample song bank and each song's card (the mock keeps the lyrics you add).
data["GET /songs"] = c.get("/api/songs").json()
for sg in data["GET /songs"]["songs"]:
    data[f"GET /songs/{sg['key']}"] = c.get(f"/api/songs/{sg['key']}").json()
for name in data["GET /automator/reports"]["reports"]:
    data[f"GET /automator/reports/{name}"] = c.get(f"/api/automator/reports/{name}").json()
for a in data["GET /apps"]["apps"]:
    data[f"GET /apps/{a['name']}/logs"] = c.get(f"/api/apps/{a['name']}/logs").json()
from arise_server import files as _files
for path, entries in _files.DEMO_TREE.items():
    data[f"GET /files/list?root=data&path={path}"] = c.get("/api/files/list", params={"root": "data", "path": path}).json()
def _nas(path, entries):
    data[f"GET /files/list?root=nas&path={path}"] = {"demo": True, "root": "nas", "path": path, "entries": [{"name": n, "dir": d, "size": sz, "mtime": mt} for n, d, sz, mt in entries]}
_nas("/", [("arise", True, None, "2026-10-26T03:00"), ("homes", True, None, "2026-10-25T18:12"), ("media", True, None, "2026-10-26T14:02")])
_nas("/arise", [("arise-backups", True, None, "2026-10-28T03:00"), ("media", True, None, "2026-10-26T14:02"), ("mirror", True, None, "2026-10-28T04:00")])
_nas("/arise/arise-backups", [("restic", True, None, "2026-10-28T03:00")])
_nas("/arise/media", [("sermons", True, None, "2026-10-26T14:02"), ("shorts", True, None, "2026-10-25T20:40"), ("thumbnails", True, None, "2026-10-26T14:02"), ("worship", True, None, "2026-10-19T13:10")])
_nas("/arise/media/sermons", [("2026-10-26 Sunday Service.mp4", False, 6_420_000_000, "2026-10-26T14:02"), ("2026-10-20 Glory Night.mp4", False, 5_110_000_000, "2026-10-20T21:30"), ("2026-10-19 Sunday Service.mp4", False, 6_880_000_000, "2026-10-19T14:10")])
_nas("/arise/media/thumbnails", [("2026-10-26_whose_hand.jpg", False, 412_000, "2026-10-26T14:02"), ("2026-10-20_glory_night.jpg", False, 398_000, "2026-10-20T21:30")])
_nas("/homes", [("bradly", True, None, "2026-10-25T18:12")])
_nas("/media", [("backgrounds", True, None, "2026-10-12T09:00"), ("loops", True, None, "2026-09-30T11:20")])
# The preview's stateful mock (web/demo-mock.js) needs a little more than GETs:
# every doc for the Help app, the sample two-step setup (its QR and key are a
# fixed sample, so the preview can check a real Microsoft Authenticator code),
# and the email template with markers the mock fills in.
for d in data["GET /help"].get("docs", []):
    data[f"GET /help/{d['name']}"] = c.get(f"/api/help/{d['name']}").json()
data["POST /me/2fa/setup"] = c.post("/api/me/2fa/setup").json()
data["POST /mail/preview"] = c.post("/api/mail/preview", json={"subject": "@@SUBJECT@@", "body": "@@BODY@@"}).json()
out = ROOT / "web" / "demo-data.js"
out.write_text("/* generated by scripts/gen-demo-data.py - do not edit */\nwindow.ARISE_DEMO_DATA = " + json.dumps(data, ensure_ascii=False, indent=0) + ";\n", encoding="utf-8")
print(f"wrote {out} ({out.stat().st_size:,} bytes, {len(data)} routes)")

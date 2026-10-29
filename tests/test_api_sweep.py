"""The API sweep: every route, called the way the dashboard calls it, on the sample server.

Bradly (Oct 28): "Go through every single feature of the OS because some didn't
work in the Artifact like user creation, Enabling/Disabling, Ect. so make sure
EVERY SINGLE THING WORKS PROPERLY!"

What this pins:
- every route answers (no 500) as the administrator, and as a member it either
  works (the portal routes) or says 403 (everything else);
- every click that changes something shows on the next read (create a user and
  the list has it; disable it and it says disabled; delete it and it is gone);
- a bad body gets a 4xx or {ok: false, err} with words in it, never a quiet yes;
- the public routes need no sign-in on a real server;
- POST /api/demo/reset exists only in demo mode.

A route added later without an entry here is still called (GET, or POST {}) and
must not 500; it is listed as a warning so the sweep can be extended.
"""
import os
import sys
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ["ARISE_DEMO"] = "1"
os.environ["ARISE_CONFIG"] = str(ROOT / "config" / "arise.toml.example")
_STAFF_WAS = None


def setUpModule():
    # The member portal stays a supported setting ([web] staff_access = "portal"); this file
    # sweeps it. The default since round 5, "none", is pinned in tests/test_desktop_r5.py.
    global _STAFF_WAS
    _STAFF_WAS = os.environ.get("ARISE_STAFF_ACCESS")
    os.environ["ARISE_STAFF_ACCESS"] = "portal"


def tearDownModule():
    os.environ.pop("ARISE_STAFF_ACCESS", None) if _STAFF_WAS is None else os.environ.__setitem__("ARISE_STAFF_ACCESS", _STAFF_WAS)

from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arise_server import config, demo_state  # noqa: E402
from arise_server.auth import member_ok  # noqa: E402
from arise_server.main import app  # noqa: E402

# (method, route path) -> (concrete path, json body or None, query params or None)
# Every route the app has today. Bodies are what the dashboard sends.
CALLS = {
    ("POST", "/api/demo/reset"): ("/api/demo/reset", None, None),
    ("POST", "/api/auth/login"): ("/api/auth/login", {"user": "office", "password": "anything"}, None),
    ("POST", "/api/auth/login/code"): ("/api/auth/login/code", {"pending": "x", "code": "123456"}, None),
    # round 5: the first-login password, the reset link, profiles, settings that follow the account
    ("POST", "/api/auth/login/new-password"): ("/api/auth/login/new-password", {"user": "office", "old": "x", "new": "Own-Pass-7777!"}, None),
    ("POST", "/api/auth/forgot"): ("/api/auth/forgot", {"user": "office"}, None),
    ("GET", "/api/auth/reset/check"): ("/api/auth/reset/check", None, {"t": "not-a-token"}),
    ("POST", "/api/auth/reset"): ("/api/auth/reset", {"token": "not-a-token", "new": "Own-Pass-7777!"}, None),
    ("GET", "/api/public/sign-in"): ("/api/public/sign-in", None, None),
    ("GET", "/api/me/profile"): ("/api/me/profile", None, None),
    ("PUT", "/api/me/profile"): ("/api/me/profile", {"mobile": "318-555-0100"}, None),
    ("GET", "/api/me/signins"): ("/api/me/signins", None, None),
    ("GET", "/api/me/prefs"): ("/api/me/prefs", None, None),
    ("PUT", "/api/me/prefs"): ("/api/me/prefs", {"prefs": {"theme": "bone"}}, None),
    ("GET", "/api/people"): ("/api/people", None, None),
    ("GET", "/api/directory/users/{name}/profile"): ("/api/directory/users/office/profile", None, None),
    ("PUT", "/api/directory/users/{name}/profile"): ("/api/directory/users/office/profile", {"title": "Minister"}, None),
    ("POST", "/api/directory/import"): ("/api/directory/import", {"csv": "first,last\nJane,Doe\n", "apply": False}, None),
    ("POST", "/api/auth/reauth"): ("/api/auth/reauth", {"password": "anything"}, None),
    ("POST", "/api/auth/logout"): ("/api/auth/logout", None, None),
    ("GET", "/api/auth/me"): ("/api/auth/me", None, None),
    ("POST", "/api/me/password"): ("/api/me/password", {"old": "a", "new": "longenough1"}, None),
    ("GET", "/api/me/2fa"): ("/api/me/2fa", None, None),
    ("POST", "/api/me/2fa/setup"): ("/api/me/2fa/setup", None, None),
    ("POST", "/api/me/2fa/enable"): ("/api/me/2fa/enable", {"code": "123456"}, None),
    ("POST", "/api/me/2fa/disable"): ("/api/me/2fa/disable", {"password": "x", "code": "123456"}, None),
    ("GET", "/api/directory/2fa"): ("/api/directory/2fa", None, None),
    ("GET", "/api/me/password/rules"): ("/api/me/password/rules", None, None),
    ("GET", "/api/overview"): ("/api/overview", None, None),
    ("GET", "/api/stats/stream"): None,   # a server-sent event stream that never ends: not swept
    ("GET", "/api/stats/history"): ("/api/stats/history", None, None),
    ("GET", "/api/services"): ("/api/services", None, None),
    ("POST", "/api/services/{unit}/{action}"): ("/api/services/arise-mirror.timer/restart", None, None),
    ("GET", "/api/logs/sources"): ("/api/logs/sources", None, None),
    ("GET", "/api/logs/file/{name}"): ("/api/logs/file/install.log", None, None),
    ("GET", "/api/logs/{unit}"): ("/api/logs/arise-web.service", None, None),
    ("GET", "/api/updates"): ("/api/updates", None, None),
    ("POST", "/api/updates/refresh"): ("/api/updates/refresh", None, None),
    ("POST", "/api/updates/check-apps"): ("/api/updates/check-apps", None, None),
    ("POST", "/api/updates/queue"): ("/api/updates/queue", {"packages": ["tzdata"], "apps": [], "reboot": False}, None),
    ("POST", "/api/updates/apply"): ("/api/updates/apply", {"confirm": "install"}, None),
    ("GET", "/api/activity"): ("/api/activity", None, None),
    ("POST", "/api/activity/kill"): ("/api/activity/kill", {"pid": 1, "confirm": "1"}, None),
    ("GET", "/api/automations"): ("/api/automations", None, None),
    ("POST", "/api/automations/{timer}/{action}"): ("/api/automations/arise-mirror.timer/pause", {"confirm": "arise-mirror.timer"}, None),
    ("GET", "/api/storage"): ("/api/storage", None, None),
    ("POST", "/api/storage/scan"): ("/api/storage/scan", None, None),
    ("GET", "/api/monitor"): ("/api/monitor", None, None),
    ("POST", "/api/monitor/power"): ("/api/monitor/power", {"on": False}, None),
    ("GET", "/api/directory/status"): ("/api/directory/status", None, None),
    ("GET", "/api/directory/users"): ("/api/directory/users", None, None),
    ("POST", "/api/directory/users"): ("/api/directory/users", {"name": "sweep.user", "password": "password123", "display": "Sweep User", "groups": []}, None),
    ("POST", "/api/directory/users/{name}/reset-password"): ("/api/directory/users/office/reset-password", {"password": "newpassword1"}, None),
    ("POST", "/api/directory/users/{name}/enable"): ("/api/directory/users/office/enable", None, None),
    ("POST", "/api/directory/users/{name}/disable"): ("/api/directory/users/office/disable", None, None),
    ("DELETE", "/api/directory/users/{name}"): ("/api/directory/users/inedge", {"confirm": "inedge"}, None),
    ("GET", "/api/directory/groups"): ("/api/directory/groups", None, None),
    ("POST", "/api/directory/groups"): ("/api/directory/groups", {"name": "Sweep Group", "description": "x"}, None),
    ("POST", "/api/directory/groups/{group}/members"): ("/api/directory/groups/Worship/members", {"user": "office"}, None),
    ("DELETE", "/api/directory/groups/{group}/members/{user}"): ("/api/directory/groups/Staff/members/office", None, None),
    ("GET", "/api/directory/computers"): ("/api/directory/computers", None, None),
    ("GET", "/api/shares"): ("/api/shares", None, None),
    ("POST", "/api/shares"): ("/api/shares", {"name": "sweep", "path": "/srv/arise/shares/sweep", "comment": "", "group": "Staff", "mac": True}, None),
    ("DELETE", "/api/shares/{name}"): ("/api/shares/kids", {"confirm": "kids"}, None),
    ("GET", "/api/backups/jobs"): ("/api/backups/jobs", None, None),
    ("GET", "/api/backups/history"): ("/api/backups/history", None, None),
    ("GET", "/api/backups/snapshots"): ("/api/backups/snapshots", None, None),
    ("GET", "/api/backups/repo"): ("/api/backups/repo", None, None),
    ("POST", "/api/backups/run/{job}"): ("/api/backups/run/homes", None, None),
    ("POST", "/api/backups/mirror"): ("/api/backups/mirror", None, None),
    ("POST", "/api/backups/check"): ("/api/backups/check", None, None),
    ("GET", "/api/automator"): ("/api/automator", None, None),
    ("GET", "/api/automator/reports"): ("/api/automator/reports", None, None),
    ("GET", "/api/automator/reports/{name}"): ("/api/automator/reports/LATEST_REPORT.md", None, None),
    ("GET", "/api/automator/worklist"): ("/api/automator/worklist", None, None),
    ("GET", "/api/automator/holds"): ("/api/automator/holds", None, None),
    ("GET", "/api/automator/quota"): ("/api/automator/quota", None, None),
    ("POST", "/api/automator/run"): ("/api/automator/run", None, None),
    ("POST", "/api/automator/preview"): ("/api/automator/preview", None, None),
    ("GET", "/api/automator/channel"): ("/api/automator/channel", None, None),
    ("GET", "/api/songs"): ("/api/songs", None, {"q": "room", "has": ""}),
    ("GET", "/api/songs/{key}"): ("/api/songs/7122057", None, None),
    ("PUT", "/api/songs/{key}/lyrics"): ("/api/songs/7122057/lyrics", {"text": "Verse 1\nsample"}, None),
    ("DELETE", "/api/songs/{key}/lyrics"): ("/api/songs/7122057/lyrics", {"confirm": "Make Room"}, None),
    ("POST", "/api/songs/import"): ("/api/songs/import", {"files": [{"name": "a.txt", "text": "Make Room\n\nsample"}]}, None),
    ("GET", "/api/automator/videos"): ("/api/automator/videos", None, {"q": "ship", "kind": "service", "has": "transcript"}),
    ("GET", "/api/automator/videos/{vid}"): ("/api/automator/videos/AnVfOCesXM4", None, None),
    ("GET", "/api/automator/videos/{vid}/transcript"): ("/api/automator/videos/AnVfOCesXM4/transcript", None, None),
    ("GET", "/api/automator/search"): ("/api/automator/search", None, {"q": "garrison", "kind": "all"}),
    ("GET", "/api/automator/archive/doc"): ("/api/automator/archive/doc", None, {"repo": "arise-youtube-automation", "path": "README.md"}),
    ("GET", "/api/automator/archive/file"): ("/api/automator/archive/file", None, {"repo": "arise-youtube-automation", "path": "THUMB_x.jpg"}),
    ("GET", "/api/apps"): ("/api/apps", None, None),
    ("GET", "/api/apps/templates"): ("/api/apps/templates", None, None),
    ("GET", "/api/apps/catalog"): ("/api/apps/catalog", None, None),
    ("GET", "/api/apps/theme/{name}"): ("/api/apps/theme/jellyfin", None, None),
    ("GET", "/api/apps/open/{name}"): ("/api/apps/open/trilium", None, None),
    ("POST", "/api/apps/deploy"): ("/api/apps/deploy", {"template": "kimai", "name": "kimai", "env": {}}, None),
    ("POST", "/api/apps/{name}/autostart"): ("/api/apps/netdata/autostart", {"on": False}, None),
    ("POST", "/api/apps/{name}/{action}"): ("/api/apps/netdata/restart", {"confirm": ""}, None),
    ("GET", "/api/apps/{name}/logs"): ("/api/apps/netdata/logs", None, None),
    ("GET", "/api/nas"): ("/api/nas", None, None),
    ("POST", "/api/nas/mount"): ("/api/nas/mount", None, None),
    ("POST", "/api/nas/unmount"): ("/api/nas/unmount", None, None),
    ("GET", "/api/settings"): ("/api/settings", None, None),
    ("GET", "/api/health"): ("/api/health", None, None),
    ("GET", "/api/sites"): ("/api/sites", None, None),
    ("GET", "/api/remote"): ("/api/remote", None, None),
    ("POST", "/api/remote/wireguard/peers"): ("/api/remote/wireguard/peers", {"name": "sweep-phone"}, None),
    ("GET", "/api/bible"): ("/api/bible", None, {"ref": "John 3:16"}),
    ("GET", "/api/bible/translations"): ("/api/bible/translations", None, None),
    ("GET", "/api/sermons"): ("/api/sermons", None, None),
    ("GET", "/api/files/roots"): ("/api/files/roots", None, None),
    ("GET", "/api/files/list"): ("/api/files/list", None, {"root": "data", "path": "/homes/bradly/Documents"}),
    ("GET", "/api/files/download"): ("/api/files/download", None, {"root": "data", "path": "/homes/bradly/Documents/Sunday setlist 2026-10-26.pdf"}),
    ("GET", "/api/files/view"): ("/api/files/view", None, {"root": "data", "path": "/homes/bradly/Documents/Sunday setlist 2026-10-26.pdf"}),
    ("POST", "/api/files/mkdir"): ("/api/files/mkdir", {"root": "data", "path": "/homes/bradly/Documents", "name": "Sweep folder"}, None),
    ("GET", "/api/search"): ("/api/search", None, {"q": "setlist"}),
    ("GET", "/api/files/all"): ("/api/files/all", None, {"folder": "Documents"}),
    # round 5: storage, sharing and privacy (rows 12-20, 36)
    ("GET", "/api/files/shared"): ("/api/files/shared", None, None),
    ("POST", "/api/files/share"): ("/api/files/share", {"root": "home", "path": "/Documents", "to": ["office"], "perm": "read"}, None),
    ("DELETE", "/api/files/share/{sid}"): ("/api/files/share/nosuchshare", None, None),
    ("GET", "/api/files/share/people"): ("/api/files/share/people", None, None),
    ("GET", "/api/files/quota"): ("/api/files/quota", None, None),
    ("GET", "/api/storage/quotas"): ("/api/storage/quotas", None, None),
    ("GET", "/api/backups/targets"): ("/api/backups/targets", None, None),
    ("POST", "/api/shares/folders"): ("/api/shares/folders", {"dry_run": True}, None),
    ("POST", "/api/files/upload/start"): ("/api/files/upload/start", {"root": "data", "path": "/homes/bradly/Downloads", "name": "sweep.bin", "size": 3, "fingerprint": "sweep|3"}, None),
    ("PUT", "/api/files/upload/chunk"): None,          # needs the token from start: covered by the Finder flow below
    ("GET", "/api/files/upload/status"): ("/api/files/upload/status", None, {"token": "nope"}),
    ("POST", "/api/files/upload/finish"): ("/api/files/upload/finish", {"token": "nope"}, None),
    ("POST", "/api/files/upload"): None,               # multipart: covered by the Finder flow below
    ("GET", "/api/files/info"): ("/api/files/info", None, {"root": "data", "path": "/homes/bradly/Documents"}),
    ("GET", "/api/files/recent"): ("/api/files/recent", None, None),
    ("GET", "/api/files/zip"): ("/api/files/zip", None, {"root": "data", "path": "/homes/bradly/Documents"}),
    ("GET", "/api/files/text"): ("/api/files/text", None, {"root": "data", "path": "/shares/graphics/ARISE_BRAND_KIT.md"}),
    ("PUT", "/api/files/text"): ("/api/files/text", {"root": "data", "path": "/shares/graphics/ARISE_BRAND_KIT.md", "text": "# kit\n"}, None),
    ("POST", "/api/files/text/preview"): ("/api/files/text/preview", {"text": "# hi"}, None),
    ("GET", "/api/files/trash"): ("/api/files/trash", None, None),
    ("POST", "/api/files/trash"): ("/api/files/trash", {"root": "data", "path": "/homes/bradly/Downloads/proclaim-6.4.dmg", "confirm": "proclaim-6.4.dmg"}, None),
    ("POST", "/api/files/trash/restore"): ("/api/files/trash/restore", {"base": "/srv/arise/shares/staff", "user": "bradly", "rel": "Forms/Copy #1 of Visitor card 2025.docx"}, None),
    ("POST", "/api/files/trash/empty"): ("/api/files/trash/empty", {"share": "media", "confirm": "media"}, None),
    ("GET", "/api/files/versions"): ("/api/files/versions", None, {"root": "data", "path": "/homes/bradly/Documents/Sunday setlist 2026-10-26.pdf"}),
    ("POST", "/api/files/versions/restore"): ("/api/files/versions/restore", {"root": "data", "path": "/homes/bradly/Documents/Sunday setlist 2026-10-26.pdf", "snapshot": "abcdef12"}, None),
    ("GET", "/api/links"): ("/api/links", None, None),
    ("POST", "/api/links"): ("/api/links", {"root": "data", "path": "/homes/bradly/Documents/Sunday setlist 2026-10-26.pdf"}, None),
    ("DELETE", "/api/links/{token}"): ("/api/links/demo7x2k9q", None, None),
    ("GET", "/s/{token}"): ("/s/demo7x2k9q", None, None),
    ("GET", "/manifest.webmanifest"): ("/manifest.webmanifest", None, None),
    ("GET", "/sw.js"): ("/sw.js", None, None),
    ("GET", "/api/push/key"): ("/api/push/key", None, None),
    ("POST", "/api/push/subscribe"): ("/api/push/subscribe", {"subscription": {"endpoint": "https://push.example/x", "keys": {"p256dh": "a", "auth": "b"}}, "label": "phone"}, None),
    ("POST", "/api/push/test"): ("/api/push/test", None, None),
    ("GET", "/api/about/week"): ("/api/about/week", None, None),
    ("GET", "/api/church"): ("/api/church", None, None),
    ("GET", "/api/sunday"): ("/api/sunday", None, None),
    ("POST", "/api/sunday/{i}"): ("/api/sunday/1", None, None),
    ("POST", "/api/kiosk/open"): ("/api/kiosk/open", {"url": "https://claude.ai/"}, None),
    ("GET", "/api/public/signage"): ("/api/public/signage", None, None),
    ("GET", "/signage"): ("/signage", None, None),
    ("GET", "/api/calendar"): ("/api/calendar", None, None),
    ("GET", "/api/calendar/subscribe"): ("/api/calendar/subscribe", None, None),
    ("POST", "/api/calendar"): ("/api/calendar", {"title": "Sweep event (sample)", "start": "2026-11-05T18:30", "end": "2026-11-05T19:30", "where": "", "note": ""}, None),
    ("PUT", "/api/calendar/{ev_id}"): ("/api/calendar/demo1", {"title": "Media team meeting (sample, moved)", "start": "2026-11-04T18:30", "end": "2026-11-04T19:30", "where": "", "note": ""}, None),
    ("DELETE", "/api/calendar/{ev_id}"): ("/api/calendar/demo2", None, None),
    ("GET", "/calendar.ics"): ("/calendar.ics", None, None),
    ("GET", "/api/public/calendar.ics"): ("/api/public/calendar.ics", None, None),
    ("GET", "/api/weather"): ("/api/weather", None, None),
    ("GET", "/api/help"): ("/api/help", None, None),
    ("GET", "/api/help/{name}"): ("/api/help/README", None, None),
    ("GET", "/api/about/whatsnew"): ("/api/about/whatsnew", None, None),
    ("GET", "/api/mail"): ("/api/mail", None, None),
    ("GET", "/api/mail/contacts"): ("/api/mail/contacts", None, None),
    ("POST", "/api/mail/import/preview"): ("/api/mail/import/preview", {"csv": "Email,First Name\nnew.one@example.com,New\n"}, None),
    ("POST", "/api/mail/import"): ("/api/mail/import", {"csv": "Email,First Name\nnew.one@example.com,New\n"}, None),
    ("POST", "/api/mail/preview"): ("/api/mail/preview", {"subject": "Hi", "body": "Hello", "name": ""}, None),
    ("POST", "/api/mail/test"): ("/api/mail/test", {"to": "bradly@example.com", "subject": "Hi", "body": "Hello"}, None),
    ("POST", "/api/mail/broadcasts"): ("/api/mail/broadcasts", {"subject": "Hi", "body": "Hello", "name": ""}, None),
    ("POST", "/api/mail/broadcasts/{bc_id}/send"): ("/api/mail/broadcasts/bc-2/send", {"confirm": "send"}, None),
    ("GET", "/api/mail/broadcasts"): ("/api/mail/broadcasts", None, None),
    ("GET", "/api/devices"): ("/api/devices", None, None),
    ("GET", "/api/devices/behind"): ("/api/devices/behind", None, None),
    ("POST", "/api/devices/scan"): ("/api/devices/scan", None, None),
    ("GET", "/api/devices/cameras"): ("/api/devices/cameras", None, None),
    ("POST", "/api/devices/{mac}"): ("/api/devices/02:a1:00:00:00:01", {"name": "Netgear A", "note": "", "kind": "router"}, None),
    ("DELETE", "/api/devices/{mac}"): ("/api/devices/02:a1:00:00:00:57", None, None),
    ("GET", "/api/security"): ("/api/security", None, None),
    ("GET", "/api/security/scan"): ("/api/security/scan", None, None),
    ("POST", "/api/security/scan/run"): ("/api/security/scan/run", None, None),
    ("POST", "/api/security/scan/restore"): ("/api/security/scan/restore", {"name": "invoice.pdf.exe", "confirm": "invoice.pdf.exe"}, None),
    ("GET", "/api/security/snapshots"): ("/api/security/snapshots", None, None),
    ("GET", "/ca.crt"): ("/ca.crt", None, None),
    ("GET", "/api/public/ca.crt"): ("/api/public/ca.crt", None, None),
    ("GET", "/api/system/updates"): ("/api/system/updates", None, None),
    ("POST", "/api/system/update"): ("/api/system/update", None, None),
    ("POST", "/api/system/apt-upgrade"): ("/api/system/apt-upgrade", None, None),
    ("POST", "/api/system/power"): ("/api/system/power", {"action": "reboot", "confirm": "reboot"}, None),
    ("POST", "/api/notify/test"): ("/api/notify/test", None, None),
    ("GET", "/api/notify"): ("/api/notify", None, None),
    # round 5 (R5-C): notifications, the Desktop folder, department checklists, the guided setup, monitor text size, faces
    ("GET", "/api/notifications"): ("/api/notifications", None, None),
    ("POST", "/api/notifications/read"): ("/api/notifications/read", {"ids": None}, None),
    ("POST", "/api/notifications"): ("/api/notifications", {"user": "bradly", "kind": "system", "text": "Sweep note"}, None),
    ("GET", "/api/desktop"): ("/api/desktop", None, None),
    ("PUT", "/api/desktop/positions"): ("/api/desktop/positions", {"positions": {"Start here.md": [40, 40]}}, None),
    ("POST", "/api/files/move"): ("/api/files/move", {"root": "data", "path": "homes/bradly/Desktop/stage-wide.jpg", "to": "homes/bradly"}, None),
    ("GET", "/api/checklists"): ("/api/checklists", None, None),
    ("POST", "/api/checklists/{dept}/tick"): ("/api/checklists/Media/tick", {"i": 0}, None),
    ("PUT", "/api/checklists/{dept}"): ("/api/checklists/Inedge", {"items": ["Room set up"], "leader": "bradly"}, None),
    ("GET", "/api/setup"): ("/api/setup", None, None),
    ("POST", "/api/setup/dismiss"): ("/api/setup/dismiss", None, None),
    ("POST", "/api/setup/reopen"): ("/api/setup/reopen", None, None),
    ("POST", "/api/setup/{step}"): ("/api/setup/shares", {"status": "done"}, None),
    ("GET", "/api/kiosk/scale"): ("/api/kiosk/scale", None, None),
    ("POST", "/api/kiosk/scale"): ("/api/kiosk/scale", {"scale": 1.25}, None),
    ("GET", "/api/public/faces"): ("/api/public/faces", None, None),
    # round 6: Firefox per admin on the monitor; two-step for staff, by an admin
    ("GET", "/api/kiosk/profile"): ("/api/kiosk/profile", None, None),
    ("POST", "/api/kiosk/profile"): ("/api/kiosk/profile", {"action": "neutral"}, None),
    ("POST", "/api/auth/handoff"): ("/api/auth/handoff", {"token": "not-a-token"}, None),
    ("POST", "/api/directory/users/{name}/2fa/setup"): ("/api/directory/users/office/2fa/setup", None, None),
    ("POST", "/api/directory/users/{name}/2fa/enable"): ("/api/directory/users/office/2fa/enable", {"code": "123456"}, None),
    ("POST", "/api/directory/users/{name}/2fa/disable"): ("/api/directory/users/office/2fa/disable", None, None),
    # round 6: the church Macs (the helper's own door speaks plain text with its key: tests/test_macs.py)
    ("GET", "/api/macs"): ("/api/macs", None, None),
    ("POST", "/api/macs/enrol-token"): ("/api/macs/enrol-token", {"name": "OFFICE-MAC-02"}, None),
    ("GET", "/api/macs/{mac_id}"): ("/api/macs/mac-0000000000b2", None, None),
    ("POST", "/api/macs/{mac_id}/local"): ("/api/macs/mac-0000000000b2/local", {"local": "guest", "action": "leave"}, None),
    ("POST", "/api/macs/{mac_id}/task"): ("/api/macs/mac-0000000000b2/task", {"kind": "printers"}, None),
    ("POST", "/api/macs/{mac_id}/retire"): ("/api/macs/mac-0000000000c3/retire", {"confirm": "KIDS-MAC"}, None),
    ("POST", "/api/macs/{mac_id}/cutoff"): ("/api/macs/mac-0000000000c3/cutoff", {"confirm": "KIDS-MAC"}, None),
    ("POST", "/api/macs/{mac_id}/reveal"): ("/api/macs/mac-0000000000a1/reveal", {"kind": "filevault"}, None),
    ("POST", "/api/macs/agent/enrol"): None,
    ("POST", "/api/macs/agent/checkin"): None,
    ("POST", "/api/macs/agent/result"): None,
    ("POST", "/api/macs/agent/secret"): None,
    ("POST", "/api/macs/agent/check"): None,
    ("GET", "/api/macs/agent/config"): None,
    ("GET", "/mac/{name}"): ("/mac/enrol.sh", None, None),

    # round 6: Mac and phone syncing (Nextcloud; tests/test_cloud.py pins the behaviour)
    ("GET", "/api/cloud"): ("/api/cloud", None, None),
    ("GET", "/api/cloud/people"): ("/api/cloud/people", None, None),
    ("GET", "/api/cloud/conflicts"): ("/api/cloud/conflicts", None, {"limit": 20}),
    ("POST", "/api/cloud/app-password"): ("/api/cloud/app-password", {"user": "office", "device": "Sweep iPad"}, None),
    ("POST", "/api/cloud/revoke"): ("/api/cloud/revoke", {"user": "office", "device": "Office iMac"}, None),
    ("POST", "/api/cloud/sweep"): ("/api/cloud/sweep", None, None),
    # the Mac helper's own door: plain text, its Mac key, no session (tests/test_cloud.py)
    ("POST", "/api/cloud/agent/app-password"): None,
    ("GET", "/{path:path}"): ("/", None, None),
}

# Routes a member may call by path, but which check for the administrator inside.
MEMBER_ADMIN_INSIDE = {("POST", "/api/calendar"), ("PUT", "/api/calendar/{ev_id}"), ("DELETE", "/api/calendar/{ev_id}"),
                       ("GET", "/api/files/all"), ("POST", "/api/files/trash/empty"), ("POST", "/api/demo/reset")}
PUBLIC = {"/api/health", "/api/public/signage", "/signage", "/calendar.ics", "/api/public/calendar.ics", "/ca.crt", "/api/public/ca.crt",
          "/manifest.webmanifest", "/sw.js", "/s/{token}", "/{path:path}"}


def app_routes():
    out = []
    for r in app.routes:
        if isinstance(r, APIRoute):
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                out.append((m, r.path))
    return out


def call(c, method, path, body=None, params=None):
    return c.request(method, path, json=body, params=params)


def member_client():
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"user": "office", "password": "anything"})
    assert r.status_code == 200 and r.json().get("role") == "member", r.text
    return c


class Sweep(unittest.TestCase):
    def setUp(self):
        config.load(force=True)
        demo_state.reset()
        self.admin = TestClient(app)
        self.member = member_client()

    def test_every_route_has_a_sweep_entry(self):
        unknown = [r for r in app_routes() if r not in CALLS]
        if unknown:
            warnings.warn(f"routes with no sweep entry yet (still called below): {unknown}")
        stale = [k for k in CALLS if k not in set(app_routes())]
        self.assertEqual(stale, [], "sweep entries for routes that no longer exist")
        self.assertGreaterEqual(len([k for k, v in CALLS.items() if v]), 150)

    def test_no_route_breaks_for_the_administrator(self):
        bad = []
        for (method, route) in app_routes():
            spec = CALLS.get((method, route), "generic")
            if spec is None:
                continue
            if spec == "generic":
                path = route.replace("{", "").replace("}", "")
                spec = (path, {} if method != "GET" else None, None)
            path, body, params = spec
            r = call(self.admin, method, path, body, params)
            if r.status_code >= 500:
                bad.append(f"{method} {path}: {r.status_code} {r.text[:200]}")
                continue
            if path.startswith("/api/") and "calendar.ics" not in path and "ca.crt" not in path:
                try:
                    j = r.json()
                except ValueError:
                    bad.append(f"{method} {path}: not JSON ({r.headers.get('content-type')})")
                    continue
                if isinstance(j, dict) and j.get("ok") is False and not (j.get("err") or j.get("error")):
                    bad.append(f"{method} {path}: ok false with no reason")
        self.assertEqual(bad, [])

    def test_members_get_the_portal_and_nothing_else(self):
        wrong = []
        for (method, route) in app_routes():
            spec = CALLS.get((method, route))
            if not spec or not route.startswith("/api/") or route in PUBLIC or route.startswith("/api/auth/"):
                continue
            path, body, params = spec
            if method != "GET" and (method, route) not in MEMBER_ADMIN_INSIDE and member_ok(route.split("{")[0], "member"):
                continue   # a member's own changes are pinned by the flows below; here: who may knock at all
            r = call(self.member, method, path, body, params)
            allowed = member_ok(route.split("{")[0], "member") and (method, route) not in MEMBER_ADMIN_INSIDE
            if allowed and r.status_code == 403:
                wrong.append(f"member refused a portal route: {method} {path}")
            if not allowed and r.status_code != 403 and not (r.status_code == 200 and r.json().get("ok") is False):
                wrong.append(f"member reached an admin route: {method} {path} -> {r.status_code}")
        self.assertEqual(wrong, [])

    def test_member_cannot_touch_the_directory_at_all(self):
        for method, path, body in (("POST", "/api/directory/users", {"name": "evil.user", "password": "password123"}),
                                   ("POST", "/api/directory/users/office/disable", None),
                                   ("POST", "/api/directory/users/office/enable", None),
                                   ("POST", "/api/directory/users/office/reset-password", {"password": "password123"}),
                                   ("DELETE", "/api/directory/users/office", {"confirm": "office"}),
                                   ("POST", "/api/directory/groups/Domain Admins/members", {"user": "office"})):
            self.assertEqual(call(self.member, method, path, body).status_code, 403, path)
        names = [u["name"] for u in self.admin.get("/api/directory/users").json()["users"]]
        self.assertNotIn("evil.user", names)
        self.assertNotIn("office", [m for g in self.admin.get("/api/directory/groups").json()["groups"] if g["name"] == "Domain Admins" for m in g["members"]])

    def test_bad_bodies_are_refused_with_words(self):
        for method, path, body in (("POST", "/api/directory/users", {"name": "bad name", "password": "password123"}),
                                   ("POST", "/api/directory/users", {"name": "ok.name", "password": "short"}),
                                   ("POST", "/api/directory/users", {"name": "office", "password": "password123"}),
                                   ("POST", "/api/directory/users/nobody.here/disable", None),
                                   ("DELETE", "/api/directory/users/office", {"confirm": "Office"}),
                                   ("POST", "/api/shares", {"name": "x", "path": "relative/path"}),
                                   ("DELETE", "/api/shares/staff", {"confirm": "wrong"}),
                                   ("POST", "/api/apps/nope/start", {"confirm": ""}),
                                   ("POST", "/api/apps/netdata/remove", {"confirm": "wrong"}),
                                   ("POST", "/api/automations/arise-backup.timer/pause", {"confirm": "nope"}),
                                   ("POST", "/api/activity/kill", {"pid": 400, "confirm": "401"}),
                                   ("POST", "/api/mail/broadcasts/bc-2/send", {"confirm": "yes"}),
                                   ("POST", "/api/files/trash", {"root": "data", "path": "/homes/bradly/Downloads/proclaim-6.4.dmg", "confirm": "wrong"}),
                                   ("POST", "/api/system/power", {"action": "reboot", "confirm": "nope"}),
                                   ("POST", "/api/updates/apply", {"confirm": "yes"})):
            r = call(self.admin, method, path, body)
            self.assertTrue(400 <= r.status_code < 500 or (r.json().get("ok") is False and (r.json().get("err") or r.json().get("error"))), f"{method} {path}: {r.text[:200]}")
        r = self.admin.post("/api/directory/users", json={"name": "x"})       # no password at all
        self.assertEqual(r.status_code, 422)

    def test_demo_reset_only_in_demo(self):
        self.admin.post("/api/directory/users", json={"name": "temp.user", "password": "password123"})
        self.assertIn("temp.user", [u["name"] for u in self.admin.get("/api/directory/users").json()["users"]])
        self.assertTrue(self.admin.post("/api/demo/reset").json()["ok"])
        self.assertNotIn("temp.user", [u["name"] for u in self.admin.get("/api/directory/users").json()["users"]])
        self.assertEqual(self.member.post("/api/demo/reset").status_code, 403)
        os.environ["ARISE_DEMO"] = "0"
        try:
            config.load(force=True)
            c = TestClient(app)
            self.assertEqual(c.post("/api/demo/reset").status_code, 401)   # a real server: sign in first, and then 404
            from arise_server import main
            with self.assertRaises(Exception):
                main.api_demo_reset(_={"user": "bradly", "role": "admin"})
        finally:
            os.environ["ARISE_DEMO"] = "1"
            config.load(force=True)

    def test_public_routes_need_no_sign_in_on_a_real_server(self):
        os.environ["ARISE_DEMO"] = "0"
        try:
            config.load(force=True)
            c = TestClient(app)
            for path in ("/api/health", "/api/public/signage", "/signage", "/calendar.ics", "/api/public/calendar.ics", "/manifest.webmanifest", "/sw.js"):
                self.assertNotIn(c.get(path).status_code, (401, 403), path)
            self.assertIn(c.get("/ca.crt").status_code, (200, 404))            # 404 says plainly that Caddy has not run
            self.assertEqual(c.get("/api/directory/users").status_code, 401)   # everything else needs the sign-in
            self.assertEqual(c.post("/api/directory/users", json={"name": "a.b", "password": "password123"}).status_code, 401)
        finally:
            os.environ["ARISE_DEMO"] = "1"
            config.load(force=True)


class Flows(unittest.TestCase):
    """Each click the dashboard makes, then the read that must show it."""

    def setUp(self):
        config.load(force=True)
        demo_state.reset()
        self.c = TestClient(app)

    def users(self):
        return {u["name"]: u for u in self.c.get("/api/directory/users").json()["users"]}

    def test_user_create_disable_enable_password_delete(self):
        c = self.c
        # temporary: False is the plain flow; a temporary first password (the default, round 5) is tests/test_profiles.py's
        r = c.post("/api/directory/users", json={"name": "jane.doe", "password": "password123", "display": "Jane Doe", "groups": ["Staff"], "temporary": False}).json()
        self.assertTrue(r["ok"], r)
        u = self.users()["jane.doe"]
        self.assertTrue(u["enabled"]); self.assertEqual(u["display"], "Jane Doe"); self.assertIn("Staff", u["groups"])
        self.assertIn("jane.doe", next(g for g in c.get("/api/directory/groups").json()["groups"] if g["name"] == "Staff")["members"])
        self.assertEqual(c.get("/api/directory/status").json()["users"], len(self.users()))
        # she can sign in with her password, and not with another
        m = TestClient(app)
        self.assertEqual(m.post("/api/auth/login", json={"user": "jane.doe", "password": "password123"}).json()["role"], "member")
        self.assertEqual(TestClient(app).post("/api/auth/login", json={"user": "jane.doe", "password": "wrongpass1"}).status_code, 401)
        # disable: the list says so, and she cannot sign in
        self.assertTrue(c.post("/api/directory/users/jane.doe/disable").json()["ok"])
        self.assertFalse(self.users()["jane.doe"]["enabled"])
        self.assertEqual(TestClient(app).post("/api/auth/login", json={"user": "jane.doe", "password": "password123"}).status_code, 401)
        # enable again
        self.assertTrue(c.post("/api/directory/users/jane.doe/enable").json()["ok"])
        self.assertTrue(self.users()["jane.doe"]["enabled"])
        # a new password works, the old one does not
        self.assertTrue(c.post("/api/directory/users/jane.doe/reset-password", json={"password": "another-pass", "temporary": False}).json()["ok"])
        self.assertEqual(TestClient(app).post("/api/auth/login", json={"user": "jane.doe", "password": "password123"}).status_code, 401)
        self.assertEqual(TestClient(app).post("/api/auth/login", json={"user": "jane.doe", "password": "another-pass"}).status_code, 200)
        # she changes her own password from the flame menu
        me = TestClient(app); me.post("/api/auth/login", json={"user": "jane.doe", "password": "another-pass"})
        self.assertFalse(me.post("/api/me/password", json={"old": "wrong", "new": "third-pass1"}).json()["ok"])
        self.assertTrue(me.post("/api/me/password", json={"old": "another-pass", "new": "third-pass1"}).json()["ok"])
        # groups: add and remove
        self.assertTrue(c.post("/api/directory/groups/Worship/members", json={"user": "jane.doe"}).json()["ok"])
        self.assertIn("Worship", self.users()["jane.doe"]["groups"])
        self.assertTrue(c.delete("/api/directory/groups/Worship/members/jane.doe").json()["ok"])
        self.assertNotIn("Worship", self.users()["jane.doe"]["groups"])
        self.assertFalse(c.delete("/api/directory/groups/Worship/members/jane.doe").json()["ok"])   # not in it any more: said so
        # delete: the name typed
        self.assertFalse(c.request("DELETE", "/api/directory/users/jane.doe", json={"confirm": "Jane"}).json()["ok"])
        self.assertTrue(c.request("DELETE", "/api/directory/users/jane.doe", json={"confirm": "jane.doe"}).json()["ok"])
        self.assertNotIn("jane.doe", self.users())
        self.assertNotIn("jane.doe", next(g for g in c.get("/api/directory/groups").json()["groups"] if g["name"] == "Staff")["members"])

    def test_groups_and_shares(self):
        c = self.c
        self.assertTrue(c.post("/api/directory/groups", json={"name": "Youth", "description": "Youth ministry"}).json()["ok"])
        self.assertIn("Youth", [g["name"] for g in c.get("/api/directory/groups").json()["groups"]])
        self.assertFalse(c.post("/api/directory/groups", json={"name": "Youth"}).json()["ok"])
        self.assertTrue(c.post("/api/shares", json={"name": "youth", "path": "/srv/arise/shares/youth", "group": "Youth"}).json()["ok"])
        sh = next(s for s in c.get("/api/shares").json()["shares"] if s["name"] == "youth")
        self.assertEqual(sh["valid_users"], ["@Youth"])
        self.assertFalse(c.post("/api/shares", json={"name": "youth", "path": "/srv/arise/shares/youth2"}).json()["ok"])
        self.assertTrue(c.request("DELETE", "/api/shares/youth", json={"confirm": "youth"}).json()["ok"])
        self.assertNotIn("youth", [s["name"] for s in c.get("/api/shares").json()["shares"]])

    def test_finder_folder_upload_edit_trash_putback_versions_link(self):
        c = self.c
        ls = lambda p: [e["name"] for e in c.get("/api/files/list", params={"root": "data", "path": p}).json()["entries"]]
        self.assertTrue(c.post("/api/files/mkdir", json={"root": "data", "path": "/homes/bradly/Documents", "name": "Easter"}).json()["ok"])
        self.assertIn("Easter", ls("/homes/bradly/Documents"))
        self.assertFalse(c.post("/api/files/mkdir", json={"root": "data", "path": "/homes/bradly/Documents", "name": "Easter"}).json()["ok"])
        # a simple upload
        r = c.post("/api/files/upload", data={"root": "data", "path": "/homes/bradly/Documents/Easter"}, files={"file": ("plan.md", b"# Easter\n", "text/markdown")}).json()
        self.assertTrue(r["ok"], r)
        self.assertIn("plan.md", ls("/homes/bradly/Documents/Easter"))
        # the resumable one
        st = c.post("/api/files/upload/start", json={"root": "data", "path": "/homes/bradly/Videos", "name": "clip.mov", "size": 6, "fingerprint": "clip|6"}).json()
        self.assertTrue(st["ok"], st)
        self.assertEqual(c.put("/api/files/upload/chunk", params={"token": st["token"], "offset": 0}, content=b"abcdef").json()["offset"], 6)
        self.assertEqual(c.get("/api/files/upload/status", params={"token": st["token"]}).json()["offset"], 6)
        self.assertTrue(c.post("/api/files/upload/finish", json={"token": st["token"]}).json()["ok"])
        self.assertIn("clip.mov", ls("/homes/bradly/Videos"))
        self.assertIn("clip.mov", [h["name"] for h in c.get("/api/files/recent").json()["hits"]])
        # the editor saves, and the next open shows it
        self.assertTrue(c.put("/api/files/text", json={"root": "data", "path": "/homes/bradly/Documents/Easter/plan.md", "text": "# Easter\n\nSunrise at 6.\n"}).json()["ok"])
        self.assertIn("Sunrise", c.get("/api/files/text", params={"root": "data", "path": "/homes/bradly/Documents/Easter/plan.md"}).json()["text"])
        # Get Info knows it
        self.assertFalse(c.get("/api/files/info", params={"root": "data", "path": "/homes/bradly/Documents/Easter/plan.md"}).json().get("dir"))
        # Trash, then Put Back: the folder and what was in it come back
        self.assertTrue(c.post("/api/files/trash", json={"root": "data", "path": "/homes/bradly/Documents/Easter", "confirm": "Easter"}).json()["ok"])
        self.assertNotIn("Easter", ls("/homes/bradly/Documents"))
        row = next(t for t in c.get("/api/files/trash").json()["items"] if t["name"] == "Easter")
        self.assertTrue(c.post("/api/files/trash/restore", json={"base": row["base"], "user": row["user"], "rel": row["rel"]}).json()["ok"])
        self.assertIn("Easter", ls("/homes/bradly/Documents"))
        self.assertIn("plan.md", ls("/homes/bradly/Documents/Easter"))
        self.assertIn("Sunrise", c.get("/api/files/text", params={"root": "data", "path": "/homes/bradly/Documents/Easter/plan.md"}).json()["text"])
        self.assertNotIn("Easter", [t["name"] for t in c.get("/api/files/trash").json()["items"]])
        # empty one share's Trash (the name typed)
        before = len(c.get("/api/files/trash").json()["items"])
        self.assertTrue(c.post("/api/files/trash/empty", json={"share": "media", "confirm": "media"}).json()["ok"])
        self.assertLess(len(c.get("/api/files/trash").json()["items"]), before)
        # Previous Versions: the restored copy lands beside the original
        doc = "/homes/bradly/Documents/Sunday setlist 2026-10-26.pdf"
        v = c.get("/api/files/versions", params={"root": "data", "path": doc}).json()["versions"]
        r = c.post("/api/files/versions/restore", json={"root": "data", "path": doc, "snapshot": v[0]["snapshot"]}).json()
        self.assertTrue(r["ok"], r)
        self.assertIn(r["restored"], ls("/homes/bradly/Documents"))
        self.assertIn("Sunday setlist 2026-10-26.pdf", ls("/homes/bradly/Documents"))   # the original is untouched
        # a share link to a real file, then revoked
        l = c.post("/api/links", json={"root": "data", "path": doc}).json()
        self.assertTrue(l["ok"]); self.assertIn("/s/", l["url"])
        self.assertIn(l["token"], [x["token"] for x in c.get("/api/links").json()["links"]])
        self.assertFalse(c.post("/api/links", json={"root": "data", "path": "/homes/bradly/nothing.pdf"}).json()["ok"])
        self.assertTrue(c.delete(f"/api/links/{l['token']}").json()["ok"])
        self.assertNotIn(l["token"], [x["token"] for x in c.get("/api/links").json()["links"]])

    def test_claude_flag_and_no_self_disable(self):
        self.assertFalse(member_client().get("/api/auth/me").json()["claude"])    # Claude on the box is Bradly's (round 4, 44)
        me = self.c.get("/api/auth/me").json()["user"]
        for verb in ("disable",):
            r = self.c.post(f"/api/directory/users/{me}/{verb}").json()
            self.assertFalse(r["ok"]); self.assertIn("signed in with", r["err"])

    def test_member_files_stay_in_their_roots(self):
        m = member_client()
        self.assertTrue(m.post("/api/files/mkdir", json={"root": "home", "path": "/", "name": "Mine"}).json()["ok"])
        self.assertIn("Mine", [e["name"] for e in m.get("/api/files/list", params={"root": "home", "path": "/"}).json()["entries"]])
        self.assertFalse(m.post("/api/files/mkdir", json={"root": "data", "path": "/homes/bradly", "name": "x"}).json()["ok"])
        self.assertEqual(m.get("/api/files/list", params={"root": "data", "path": "/"}).json().get("error"), "unknown root")
        self.assertEqual(m.get("/api/files/all", params={"folder": "Documents"}).status_code, 403)

    def test_calendar_sunday_devices(self):
        c = self.c
        r = c.post("/api/calendar", json={"title": "Fall festival (sample)", "start": "2026-11-07T10:00", "end": "2026-11-07T14:00", "where": "Pineville", "note": ""}).json()
        self.assertTrue(r["ok"], r)
        ev = r["event"]["id"]
        items = c.get("/api/calendar", params={"year": 2026, "month": 11}).json()["items"]
        self.assertIn(ev, [i["id"] for i in items])
        self.assertTrue(c.put(f"/api/calendar/{ev}", json={"title": "Fall festival (sample, moved)", "start": "2026-11-08T10:00", "end": "2026-11-08T14:00", "where": "", "note": ""}).json()["ok"])
        self.assertIn("moved", next(i for i in c.get("/api/calendar", params={"year": 2026, "month": 11}).json()["items"] if i["id"] == ev)["title"])
        self.assertIn("Fall festival", c.get("/calendar.ics").text)
        self.assertTrue(c.delete(f"/api/calendar/{ev}").json()["ok"])
        self.assertNotIn(ev, [i["id"] for i in c.get("/api/calendar", params={"year": 2026, "month": 11}).json()["items"]])
        # the Sunday list ticks and unticks
        before = c.get("/api/sunday").json()
        self.assertTrue(c.post("/api/sunday/2").json()["ok"])
        after = c.get("/api/sunday").json()
        self.assertNotEqual(before, after)
        # a device gets a name, then is forgotten
        self.assertTrue(c.post("/api/devices/02:a1:00:00:00:01", json={"name": "Router A", "note": "at the modem", "kind": "router"}).json()["ok"])
        self.assertEqual(next(d for d in c.get("/api/devices").json()["devices"] if d["mac"] == "02:a1:00:00:00:01")["name"], "Router A")
        self.assertTrue(c.delete("/api/devices/02:a1:00:00:00:01").json()["ok"])
        self.assertNotIn("02:a1:00:00:00:01", [d["mac"] for d in c.get("/api/devices").json()["devices"]])
        self.assertFalse(c.delete("/api/devices/02:a1:00:00:00:01").json()["ok"])

    def test_store_timers_updates(self):
        c = self.c
        apps = lambda: {a["name"]: a for a in c.get("/api/apps").json()["apps"]}
        self.assertTrue(c.post("/api/apps/netdata/stop", json={"confirm": ""}).json()["ok"])
        self.assertEqual(apps()["netdata"]["status"], "exited")
        self.assertTrue(c.post("/api/apps/netdata/start", json={"confirm": ""}).json()["ok"])
        self.assertEqual(apps()["netdata"]["status"], "running")
        self.assertTrue(c.post("/api/apps/netdata/autostart", json={"on": False}).json()["ok"])
        self.assertFalse(apps()["netdata"]["autostart"])
        r = c.post("/api/apps/deploy", json={"template": "kimai", "name": "kimai", "env": {}}).json()
        self.assertTrue(r["ok"], r); self.assertIn("kimai", apps())
        self.assertFalse(c.post("/api/apps/deploy", json={"template": "kimai", "name": "kimai", "env": {}}).json()["ok"])
        self.assertTrue(c.post("/api/apps/kimai/remove", json={"confirm": "kimai"}).json()["ok"])
        self.assertNotIn("kimai", apps())
        # timers: pause and resume, by name
        timers = lambda: {t["timer"]: t for t in c.get("/api/automations").json()["timers"]}
        self.assertTrue(c.post("/api/automations/arise-mirror.timer/pause", json={"confirm": "arise-mirror.timer"}).json()["ok"])
        self.assertFalse(timers()["arise-mirror.timer"]["enabled"])
        self.assertTrue(c.post("/api/automations/arise-mirror.timer/resume", json={"confirm": "arise-mirror.timer"}).json()["ok"])
        self.assertTrue(timers()["arise-mirror.timer"]["enabled"])
        # updates: queue, then install empties the queue and records the run
        self.assertTrue(c.post("/api/updates/queue", json={"packages": ["tzdata"], "apps": ["uptime-kuma"], "reboot": False}).json()["ok"])
        self.assertEqual(c.get("/api/updates").json()["queue"]["packages"], ["tzdata"])
        self.assertTrue(c.post("/api/updates/apply", json={"confirm": "install"}).json()["ok"])
        u = c.get("/api/updates").json()
        self.assertEqual(u["queue"]["packages"], []); self.assertIn("installed", u["last_apply"]["summary"])

    def test_automator_preview_always_run_only_with_the_timer_paused(self):
        c = self.c
        self.assertTrue(c.post("/api/automator/preview").json()["ok"])
        self.assertEqual(c.get("/api/automator").json()["manual"]["mode"], "preview")
        r = c.post("/api/automator/run").json()
        self.assertFalse(r["ok"]); self.assertIn("timer", r["err"])          # CLAUDE.md rule 3
        c.post("/api/automations/arise-automator.timer/pause", json={"confirm": "arise-automator.timer"})
        self.assertTrue(c.post("/api/automator/run").json()["ok"])

    def test_backups_mail_security_monitor_nas_services_activity_twofa_peers(self):
        c = self.c
        n = len(c.get("/api/backups/history").json()["rows"])
        self.assertTrue(c.post("/api/backups/run/homes").json()["ok"])
        import time
        for _ in range(30):
            if len(c.get("/api/backups/history").json()["rows"]) > n:
                break
            time.sleep(0.1)
        self.assertGreater(len(c.get("/api/backups/history").json()["rows"]), n)
        self.assertFalse(c.post("/api/backups/run/nope").json()["ok"])
        # mail: import adds, a broadcast is made and sent once
        k = c.get("/api/mail/contacts").json()["count"]
        self.assertTrue(c.post("/api/mail/import", json={"csv": "Email,First Name\nnew.one@example.com,New\nsample.one@example.com,Dup\n"}).json()["ok"])
        self.assertEqual(c.get("/api/mail/contacts").json()["count"], k + 1)
        bc = c.post("/api/mail/broadcasts", json={"subject": "News", "body": "Hello", "name": ""}).json()["id"]
        self.assertTrue(c.post(f"/api/mail/broadcasts/{bc}/send", json={"confirm": "send"}).json()["ok"])
        self.assertEqual(next(b for b in c.get("/api/mail/broadcasts").json()["broadcasts"] if b["id"] == bc)["status"], "sent")
        # security: a quarantined file is put back by name
        q = c.get("/api/security/scan").json()["quarantined"]
        self.assertTrue(q)
        name = q[0]["file"].rsplit("/", 1)[1]
        self.assertTrue(c.post("/api/security/scan/restore", json={"name": name, "confirm": name}).json()["ok"])
        self.assertEqual(c.get("/api/security/scan").json()["quarantined"], [])
        # the closet monitor sleeps and wakes
        c.post("/api/monitor/power", json={"on": False})
        self.assertFalse(c.get("/api/monitor").json()["outputs"][0]["enabled"])
        c.post("/api/monitor/power", json={"on": True})
        self.assertTrue(c.get("/api/monitor").json()["outputs"][0]["enabled"])
        # the Synology
        c.post("/api/nas/unmount"); self.assertFalse(c.get("/api/nas").json()["mounted"])
        c.post("/api/nas/mount"); self.assertTrue(c.get("/api/nas").json()["mounted"])
        # a service stops and starts
        c.post("/api/services/arise-mirror.timer/stop")
        svc = {s["unit"]: s for s in c.get("/api/services").json()["services"]}
        self.assertEqual(svc["arise-mirror.timer"]["active"], "inactive")
        c.post("/api/services/arise-mirror.timer/start")
        self.assertEqual({s["unit"]: s for s in c.get("/api/services").json()["services"]}["arise-mirror.timer"]["active"], "active")
        # Activity Monitor: end a sample process; the protected ones are refused
        procs = c.get("/api/activity").json()["processes"]
        free = next(p for p in procs if not p["protected"])
        self.assertTrue(c.post("/api/activity/kill", json={"pid": free["pid"], "confirm": str(free["pid"])}).json()["ok"])
        self.assertNotIn(free["pid"], [p["pid"] for p in c.get("/api/activity").json()["processes"]])
        samba = next(p for p in procs if p["name"] == "samba")
        self.assertFalse(c.post("/api/activity/kill", json={"pid": samba["pid"], "confirm": str(samba["pid"])}).json()["ok"])
        # two-step: set up, turn on, the directory badge shows it, turn off
        m = member_client()
        self.assertFalse(m.get("/api/me/2fa").json()["on"])
        self.assertTrue(m.post("/api/me/2fa/setup").json()["ok"])
        self.assertTrue(m.post("/api/me/2fa/enable", json={"code": "123456"}).json()["ok"])
        self.assertTrue(m.get("/api/me/2fa").json()["on"])
        self.assertIn("office", c.get("/api/directory/2fa").json()["users"])
        self.assertTrue(m.post("/api/me/2fa/disable", json={"password": "anything", "code": "123456"}).json()["ok"])
        self.assertNotIn("office", c.get("/api/directory/2fa").json()["users"])
        # a WireGuard peer is listed once made, and a second with the same name is refused
        self.assertTrue(c.post("/api/remote/wireguard/peers", json={"name": "bradly-phone"}).json()["ok"])
        self.assertIn("bradly-phone", [p["name"] for p in c.get("/api/remote").json()["wireguard"]["peers"]])
        self.assertFalse(c.post("/api/remote/wireguard/peers", json={"name": "bradly-phone"}).json()["ok"])


if __name__ == "__main__":
    unittest.main()

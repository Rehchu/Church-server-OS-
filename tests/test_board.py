"""Round 8 (Q28, Q29, Q30, Q126): the house board. GET /api/public/board needs no login, so it says
only counts and yes/no: the exact keys are pinned here, and sample data full of people's names,
paths, hostnames and addresses goes in to prove none of them comes out."""
import json
import os
import re
import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("ARISE_DEMO", "1")
os.environ.setdefault("ARISE_CONFIG", str(ROOT / "config" / "arise.toml.example"))

from arise_server import board, servicemode  # noqa: E402

TOP = {"church", "next", "backup", "needs_you", "stream", "verse", "checklists", "demo"}
NEXT = {"name", "site", "at", "in_service"}

# What a leak would look like: people, the box, its paths and addresses, a secret.
PEOPLE = ["bradly", "bradly.dyer", "kristina.robinson", "bryant.sanders", "vanessa.sanders", "Bradly Dyer", "Kristina"]
SECRETS = ["/srv/", "/mnt/", "/etc/", "/var/", "/home/", "arise-server", "AD.ARISECENLA", "192.168.", "100.64.", "@", "restic", "token", "hunter2"]

SERVICE_VIEW = {
    "in_service": True, "demo": False,
    "service": {"name": "Glory Night", "site": "Pineville", "started": "2026-11-02T19:00", "ends_at": "9:00 PM", "by": "bradly.dyer"},
    "stream": {"live": True, "checked": "2026-11-02T19:12", "url": "https://www.youtube.com/channel/x/live", "why": "fetched by bradly"},
    "internet": {"down": 900, "up": 40, "ping": 12, "host": "192.168.1.1"},
    "checklists": [
        {"dept": "media", "done": 3, "total": 5, "left": ["Ask kristina.robinson for the lower thirds", "Recording to /srv/arise/recordings"], "by": "bradly"},
        {"dept": "worship", "done": 4, "total": 4, "left": [], "people": ["vanessa.sanders"]},
    ],
    "run_sheet": {"ok": True, "name": "/srv/arise/data/Glory Night run sheet (bryant.sanders).md", "text": "- 7:00 PM bradly.dyer opens"},
    "next": None,
}
REST_VIEW = {"in_service": False, "demo": False,
             "next": {"name": "Sunday Service", "site": "Pineville", "day": "Sunday", "time": "10:30", "at": "2026-11-08T10:30", "in_minutes": 7000, "in_words": "4 days", "host": "arise-server"}}
BACKUP_ROWS = {"rows": [{"job": "synology", "name": "Arise data to /mnt/synology/arise-backups", "started": "2026-11-03T03:00:04", "finished": "2026-11-03T03:04:41",
                         "ok": False, "error": "restic: wrong password in /etc/arise/secrets/restic (bradly.dyer)", "snapshot_id": "abc", "repo": "/mnt/synology/restic"}],
               "running": [], "demo": False}
ATTENTION = [{"level": "bad", "text": "Backup failed for bradly.dyer at /srv/arise/homes/bradly"},
             {"level": "warn", "text": "kristina.robinson's Mac at 192.168.86.40 has been silent three days"}]


def built(view, live=None):
    board.reset()
    with patch.object(servicemode, "now_view", lambda now=None: json.loads(json.dumps(view))), \
         patch("arise_server.backups.history", lambda limit=200: json.loads(json.dumps(BACKUP_ROWS))), \
         patch.object(servicemode, "live_status", lambda fetch=None: {"live": live, "url": "https://x", "why": "bradly"}), \
         patch.object(board, "load", lambda: SimpleNamespace(demo=False)):
        return board.build(lambda: ATTENTION, now=datetime(2026, 11, 3, 12, 0))


class TheKeysArePinned(unittest.TestCase):
    def test_at_rest(self):
        b = built(REST_VIEW, live=False)
        self.assertEqual(set(b), TOP)
        self.assertEqual(set(b["next"]), NEXT)
        self.assertEqual(set(b["backup"]), {"ok", "when"})
        self.assertEqual(set(b["stream"]), {"live"})
        self.assertEqual(set(b["verse"]), {"text", "ref"})
        self.assertEqual(set(b["church"]), {"name", "city"})
        self.assertEqual(b["checklists"], [])
        self.assertFalse(b["next"]["in_service"])
        self.assertEqual(b["next"]["at"], "2026-11-08T10:30")
        self.assertEqual(b["needs_you"], 2)                      # a count, never the items
        self.assertEqual(b["backup"], {"ok": False, "when": "2026-11-03T03:04"})

    def test_during_a_service(self):
        b = built(SERVICE_VIEW)
        self.assertEqual(set(b), TOP)
        self.assertTrue(b["next"]["in_service"])
        self.assertEqual(b["next"]["name"], "Glory Night")
        self.assertEqual(b["next"]["at"], "2026-11-02T19:00")      # the page counts up from the start
        self.assertIs(b["stream"]["live"], True)
        self.assertEqual(b["checklists"], [{"dept": "media", "done": 3, "total": 5}, {"dept": "worship", "done": 4, "total": 4}])
        for c in b["checklists"]:
            self.assertEqual(set(c), {"dept", "done", "total"})   # department names only (Q28): no items, no people

    def test_stream_is_true_false_or_null(self):
        for live in (True, False, None):
            self.assertIs(built(REST_VIEW, live=live)["stream"]["live"], live)
        self.assertIsNone(built(REST_VIEW, live="yes")["stream"]["live"])


class NothingLeaks(unittest.TestCase):
    def test_no_name_path_address_or_secret(self):
        for view in (REST_VIEW, SERVICE_VIEW):
            text = json.dumps(built(view, live=True))
            for word in PEOPLE + SECRETS:
                self.assertNotIn(word.lower(), text.lower(), f"{word!r} leaked: {text}")
            self.assertIsNone(re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", text))
            self.assertNotIn("in_words", text)                    # clock-independent: the page counts itself

    def test_the_route_needs_no_login_and_keeps_the_keys(self):
        from fastapi.testclient import TestClient
        from arise_server.main import app
        board.reset()
        c = TestClient(app)
        r = c.get("/api/public/board")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(set(j), TOP)
        self.assertIsInstance(j["needs_you"], int)
        text = json.dumps(j)
        # the sample directory's people (the department accounts share their department's name, which may show)
        users = [u["name"] for u in c.get("/api/directory/users").json().get("users", []) if "." in u["name"] and "department" not in u["name"]]
        self.assertTrue(users)
        for word in PEOPLE + ["/srv/", "/mnt/", "/etc/", "arise-server", "@"] + users:
            self.assertNotIn(word, text)
        # during the preview's sample service: the departments' counts, still no names
        c.post("/api/service/demo", json={"on": True})
        board.reset()
        try:
            j = c.get("/api/public/board").json()
        finally:
            c.post("/api/service/demo", json={"on": False})
            board.reset()
        self.assertTrue(j["next"]["in_service"])
        self.assertTrue(j["checklists"])
        for cl in j["checklists"]:
            self.assertEqual(set(cl), {"dept", "done", "total"})
        for word in PEOPLE + ["/srv/", "run sheet", "Cameras on"]:
            self.assertNotIn(word, json.dumps(j))

    def test_the_lobby_page_is_served(self):
        from fastapi.testclient import TestClient
        from arise_server.main import app
        r = TestClient(app).get("/board")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/api/public/board", r.text)


class TheAnswerIsShared(unittest.TestCase):
    def test_cached_for_the_ttl(self):
        board.reset()
        calls = []
        with patch.object(board, "build", lambda attention=None, now=None: calls.append(1) or {"n": len(calls)}):
            a = board.view(); b = board.view()
        board.reset()
        self.assertEqual(len(calls), 1)
        self.assertIs(a, b)


class ThePages(unittest.TestCase):
    """The house board on the closet monitor and the lobby page: nothing clickable, the idle rules kept."""
    def test_app_js(self):
        js = (ROOT / "web" / "app.js").read_text()
        self.assertIn("/public/board", js)
        self.assertIn("if (inService) return;", js)                                 # no screensaver or lock during a service
        self.assertIn("if (idle >= 300 && $('#lock').hidden) saver(true);", js)     # five minutes: the board
        self.assertIn("if (idle >= 600 && $('#lock').hidden) lockScreen(true);", js) # ten: the lock
        self.assertIn("classList.toggle('onair'", js)

    def test_board_html(self):
        html = (ROOT / "web" / "board.html").read_text()
        self.assertIn("/api/public/board", html)
        self.assertIn("60000", html)                     # refreshed every minute (Q126)
        self.assertIn("board.css", html)
        self.assertNotIn("<button", html)                # nothing clickable
        self.assertNotIn("<a ", html)
        css = (ROOT / "web" / "board.css").read_text()
        self.assertIn("body.kiosk", css)                 # the closet HP: no backdrop blur
        self.assertIn("prefers-reduced-motion", css)


if __name__ == "__main__":
    unittest.main()

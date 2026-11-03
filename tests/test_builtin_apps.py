"""v0.9 Leviticus (round 8, 34 and 40): ten Required ariseOS apps, the rest turned on in the Store.

GET /api/apps/builtin says what shows; POST /api/apps/builtin/{id} {on} turns one on or off
(a recent admin, audited). Demo mode keeps the choice in memory with every app on; a real box
starts from [apps] turned_on (empty by default) and the Store's saved choice wins after that.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("ARISE_DEMO", "1")
os.environ.setdefault("ARISE_CONFIG", str(ROOT / "config" / "arise.toml.example"))

from fastapi.testclient import TestClient  # noqa: E402

from arise_server import config, demo_state  # noqa: E402
from arise_server.auth import member_ok  # noqa: E402
from arise_server import main  # noqa: E402

ADMIN = {"user": "bradly", "role": "admin"}
TEN = {"files", "overview", "directory", "backups", "sunday", "calendar", "settings", "apps", "help", "terminal"}


class TheLists(unittest.TestCase):
    def test_the_ten_required_are_bradlys_ten(self):
        self.assertEqual(set(main.BUILTIN_REQUIRED), TEN)                     # Q34: "Those ten"
        self.assertFalse(set(main.BUILTIN_REQUIRED) & set(main.BUILTIN_STORE))

    def test_every_app_in_the_desktop_is_required_or_in_the_store(self):
        """A new app in web/app.js must land in one list, or it would show on a box that never turned it on."""
        js = (ROOT / "web" / "app.js").read_text()
        ids = set(re.findall(r"\{ id: '([a-z]+)', n: '[0-9]*', name: '[^']+', what: '[^']*'(?![^}]*hidden: true)", js))
        self.assertIn("notes", ids)
        missing = ids - set(main.BUILTIN_REQUIRED) - set(main.BUILTIN_STORE)
        self.assertEqual(missing, set(), "add these to BUILTIN_STORE (or BUILTIN_REQUIRED) in main.py")

    def test_a_new_box_turns_nothing_on(self):
        self.assertEqual(config.DEFAULTS["apps"]["turned_on"], [])
        ex = (ROOT / "config" / "arise.toml.example").read_text()
        section = ex.split("\n[apps]\n", 1)[1].split("\n[", 1)[0]
        self.assertRegex(section, r"(?m)^turned_on = \[\]$")


class Demo(unittest.TestCase):
    def setUp(self):
        os.environ["ARISE_DEMO"] = "1"
        config.load(force=True)
        demo_state.reset()
        self.c = TestClient(main.app)

    def tearDown(self):
        demo_state.reset()

    def test_the_sample_shows_every_app_on(self):
        r = self.c.get("/api/apps/builtin").json()
        self.assertEqual(set(r["required"]), TEN)
        self.assertEqual(r["turned_on"], list(main.BUILTIN_STORE))
        self.assertTrue(r["can_change"])
        self.assertTrue(r["demo"])

    def test_turn_one_off_and_on_again(self):
        r = self.c.post("/api/apps/builtin/notes", json={"on": False}).json()   # not taken for /api/apps/{name}/{action}
        self.assertTrue(r["ok"])
        self.assertNotIn("notes", r["turned_on"])
        self.assertNotIn("notes", self.c.get("/api/apps/builtin").json()["turned_on"])
        r = self.c.post("/api/apps/builtin/notes", json={"on": True}).json()
        self.assertIn("notes", r["turned_on"])
        self.assertEqual(r["turned_on"], [a for a in main.BUILTIN_STORE if a in r["turned_on"]])   # always in one order

    def test_required_and_unknown_are_refused(self):
        r = self.c.post("/api/apps/builtin/files", json={"on": False}).json()
        self.assertFalse(r["ok"])
        self.assertIn("Required", r["err"])
        self.assertFalse(self.c.post("/api/apps/builtin/nonsense", json={"on": True}).json()["ok"])
        self.assertEqual(self.c.get("/api/apps/builtin").json()["turned_on"], list(main.BUILTIN_STORE))   # nothing changed

    def test_the_change_is_audited(self):
        from arise_server import audit
        before = len(audit._DEMO)
        self.c.post("/api/apps/builtin/mail", json={"on": False})
        self.assertTrue(any(e["action"] == "apps.builtin.off" and e["target"] == "mail" for e in audit._DEMO[before:]))

    def test_members_may_ask_but_not_change(self):
        self.assertTrue(member_ok("/api/apps/builtin", "member"))
        self.assertFalse(member_ok("/api/apps/templates", "member"))
        r = main.builtin_state({"user": "office", "role": "member"})
        self.assertFalse(r["can_change"])
        route = next(x for x in main.app.routes if getattr(x, "path", "") == "/api/apps/builtin/{app_id}")
        deps = [d.call for d in route.dependant.dependencies]
        self.assertIn(main.require_recent_admin, deps)

    def test_people_with_an_inbox_always_see_it(self):
        self.assertTrue(main.builtin_state({"user": "kristina.robinson", "role": "admin"})["inbox"])   # [inbox] users
        self.assertFalse(main.builtin_state({"user": "someone.else", "role": "admin"})["inbox"])


class RealBox(unittest.TestCase):
    """A real config in a temp folder: [apps] turned_on first, then the Store's saved choice."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="arise-builtin-")
        t = Path(self.tmp)
        self.cfg = t / "arise.toml"
        self.env = {k: os.environ.get(k) for k in ("ARISE_CONFIG", "ARISE_DEMO")}
        os.environ["ARISE_CONFIG"] = str(self.cfg)
        os.environ.pop("ARISE_DEMO", None)

    def write(self, apps_section):
        t = Path(self.tmp)
        self.cfg.write_text(f'[system]\ndata_root = "{t}/data"\n[paths]\nstate_dir = "{t}/state"\nlog_dir = "{t}/state"\n'
                            f'[directory]\nenabled = false\n[apps]\n{apps_section}\n')
        config.load(force=True)

    def tearDown(self):
        for k, v in self.env.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        config.load(force=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_nothing_on_by_default(self):
        self.write("")
        self.assertFalse(config.load().demo)
        self.assertEqual(main.builtin_turned_on(), [])

    def test_the_config_list_is_read_in_store_order_and_unknown_names_dropped(self):
        self.write('turned_on = ["mail", "files", "nope", "automator"]')
        self.assertEqual(main.builtin_turned_on(), ["automator", "mail"])

    def test_the_stores_choice_is_kept_and_wins_and_is_audited(self):
        self.write('turned_on = ["mail"]')
        r = main.api_apps_builtin_set("logs", main.BuiltinOn(on=True), who=ADMIN)
        self.assertEqual(r["turned_on"], ["logs", "mail"])
        saved = json.loads((Path(self.tmp) / "state" / "apps-turned-on.json").read_text())
        self.assertEqual(saved["turned_on"], ["logs", "mail"])
        self.assertEqual(saved["by"], "bradly")
        main.api_apps_builtin_set("mail", main.BuiltinOn(on=False), who=ADMIN)
        self.assertEqual(main.builtin_turned_on(), ["logs"])                  # the config's "mail" no longer counts
        lines = [json.loads(x) for x in (Path(self.tmp) / "state" / "audit.jsonl").read_text().splitlines()]
        self.assertEqual([(e["action"], e["target"]) for e in lines][-2:], [("apps.builtin.on", "logs"), ("apps.builtin.off", "mail")])


if __name__ == "__main__":
    unittest.main()

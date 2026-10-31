"""Round 5's desktop, notifications and first-run answers (docs/ANSWERS.md, round 5,
24 to 35 and 39), and the staff-access change Bradly made after it.

Real temp folders and a real (non-sample) config where it matters; no mocks of the
code under test.
"""
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

SERVICES = [
    {"name": "Sunday Service", "day": "Sunday", "time": "10:30", "site": "Pineville"},
    {"name": "Sunday Service", "day": "Sunday", "time": "10:00", "site": "Alexandria"},
    {"name": "Glory Night", "day": "Monday", "time": "19:00", "site": "Pineville"},
]
T = datetime.fromisoformat


class RealConfig(unittest.TestCase):
    """A real config in a temp folder: state, data and homes all under it."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="arise-r5c-")
        t = Path(cls.tmp)
        (t / "data" / "homes").mkdir(parents=True)
        (t / "arise.toml").write_text(
            f'[system]\ndata_root = "{t}/data"\n[web]\nadmin_user = "bradly"\n[directory]\nenabled = false\nhomes_path = "{t}/data/homes"\n'
            f'[paths]\nstate_dir = "{t}/state"\nlog_dir = "{t}/state"\n[church]\ndepartments = ["Media", "Inedge"]\n')
        cls.env = {k: os.environ.get(k) for k in ("ARISE_CONFIG", "ARISE_DEMO", "ARISE_STAFF_ACCESS")}
        os.environ["ARISE_CONFIG"] = str(t / "arise.toml")
        os.environ.pop("ARISE_DEMO", None)
        os.environ.pop("ARISE_STAFF_ACCESS", None)
        from arise_server import config
        config.load(force=True)

    @classmethod
    def tearDownClass(cls):
        for k, v in cls.env.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        from arise_server import config
        config.load(force=True)
        shutil.rmtree(cls.tmp, ignore_errors=True)


class Cycle(unittest.TestCase):
    """Rows 29-30: a list moves on the night before each service."""

    def setUp(self):
        from arise_server import checklists
        self.c = checklists

    def test_the_round_moves_on_at_8pm_the_night_before(self):
        self.assertEqual(self.c.cycle(T("2026-10-24 19:59"), SERVICES)["key"], "2026-10-19 Glory Night")    # Saturday before 8 PM
        self.assertEqual(self.c.cycle(T("2026-10-24 20:00"), SERVICES)["key"], "2026-10-25 Sunday Service")  # Saturday 8 PM
        self.assertEqual(self.c.cycle(T("2026-10-25 11:30"), SERVICES)["key"], "2026-10-25 Sunday Service")  # during and after the service
        self.assertEqual(self.c.cycle(T("2026-10-25 20:00"), SERVICES)["key"], "2026-10-26 Glory Night")     # Sunday 8 PM, for Monday
        self.assertEqual(self.c.cycle(T("2026-10-28 12:00"), SERVICES)["key"], "2026-10-26 Glory Night")     # mid-week: the last round stays
        only_sunday = self.c.cycle(T("2026-10-25 20:00"), SERVICES, ["Sunday Service"])
        self.assertEqual(only_sunday["key"], "2026-10-25 Sunday Service")                                   # a Sunday-only list waits for Saturday

    def test_nudge_times(self):
        self.assertTrue(self.c.valid_nudge("08:45"))
        for bad in ("8:45", "24:00", "08:60", "", "noon"):
            self.assertFalse(self.c.valid_nudge(bad), bad)


class Checklists(RealConfig):
    def test_admin_edits_and_ticks_a_leader_edits_items_only_and_history_rolls(self):
        from arise_server import checklists as c
        admin, leader, other = {"user": "bradly", "role": "admin"}, {"user": "inedge", "role": "member"}, {"user": "office", "role": "member"}
        sat = T("2026-10-24 21:00")
        r = c.edit("Inedge", admin, items=["Room set up", "Sound check"], leader="inedge", now=sat)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["nudge"], {"Sunday Service": "09:00", "Glory Night": "18:00"})   # the call times (round 7, 90)
        self.assertFalse(c.edit("Inedge", admin, nudge={"Sunday Service": "10:15"}, now=sat)["ok"])   # at or after 10:00: refused
        self.assertFalse(c.edit("Inedge", leader, nudge={"Sunday Service": "08:00"}, now=sat)["ok"])  # the time is the admins'
        self.assertTrue(c.edit("Inedge", leader, items=["Room set up", "Sound check", "Doors"], now=sat)["ok"])   # the leader edits items
        self.assertFalse(c.edit("Inedge", other, items=["x"], now=sat)["ok"])
        self.assertFalse(c.tick("Inedge", 0, other, now=sat)["ok"])                       # not in the department
        self.assertEqual(c.tick("Inedge", 0, admin, now=sat)["done"], 1)
        self.assertFalse(c.edit("Nope", admin, items=["x"])["ok"])                        # departments come from arise.toml
        # The next round: Sunday's ticks go to history.
        r = c.all_lists(admin, T("2026-10-25 20:30"))
        ine = next(x for x in r["lists"] if x["dept"] == "Inedge")
        self.assertEqual(ine["round"]["key"], "2026-10-26 Glory Night")
        self.assertEqual(ine["done"], 0)
        self.assertEqual(ine["history"][0], {"round": "2026-10-25 Sunday Service", "done": 1, "total": 3, "by": ["bradly"]})
        self.assertEqual([x["dept"] for x in c.all_lists(other, sat)["lists"]], [])        # a member sees only their departments

    def test_nudges_come_once_at_their_minute_with_items_left(self):
        from arise_server import checklists as c, notify
        admin = {"user": "bradly", "role": "admin"}
        c.edit("Media", admin, items=["Cameras", "Lower thirds"], leader="kristina.robinson", now=T("2026-10-24 21:00"))
        due = [d for d in c.due_nudges(T("2026-10-25 09:00")) if d["key"].startswith("dept:Media:")]   # call time (round 7, 90)
        self.assertEqual([d["key"] for d in due], ["dept:Media:2026-10-25 Sunday Service"])
        self.assertIn("kristina.robinson", due[0]["to"])
        self.assertEqual(c.due_nudges(T("2026-10-25 09:01")), [])
        r1 = notify.tick(T("2026-10-25 09:00"))
        r2 = notify.tick(T("2026-10-25 09:00"))
        self.assertEqual((r1["sent"] >= 1, r2["sent"]), (True, 0))                          # keyed: never twice
        self.assertIn("Media checklist: 2 of 2 left", notify.feed("kristina.robinson")["items"][0]["text"])


class Notify(RealConfig):
    def test_add_feed_read_and_keys(self):
        from arise_server import notify
        self.assertTrue(notify.add("jane.doe", "shared", "Kristina shared Outpour with you", "/#files", deliver=False)["ok"])
        self.assertFalse(notify.add("jane.doe", "weird", "x")["ok"])
        self.assertTrue(notify.add("jane.doe", "mail", "New mail", key="m1", deliver=False)["ok"])
        self.assertTrue(notify.add("jane.doe", "mail", "New mail", key="m1", deliver=False).get("duplicate"))
        f = notify.feed("jane.doe")
        self.assertEqual((len(f["items"]), f["unread"]), (2, 2))
        self.assertEqual(notify.mark_read("jane.doe")["unread"], 0)
        self.assertEqual(notify.feed("someone.else")["items"], [])

    def test_calendar_reminders_30_minutes_ahead_for_the_people_in_it(self):
        from arise_server import calendar as churchcal, notify
        ev = churchcal.add({"title": "Media team meeting", "start": "2026-10-28T18:30", "where": "the booth", "people": ["kristina.robinson"]}, "bradly")
        self.assertEqual(ev.get("ok", True), True)
        churchcal.add({"title": "Nobody named", "start": "2026-10-28T18:30"}, "bradly")
        self.assertEqual(notify.due_reminders(T("2026-10-28 17:59"), churchcal.events()), [])
        due = notify.due_reminders(T("2026-10-28 18:05"), churchcal.events())
        self.assertEqual([e["title"] for e in due], ["Media team meeting"])
        notify.tick(T("2026-10-28 18:05"))
        notify.tick(T("2026-10-28 18:10"))
        items = [i for i in notify.feed("kristina.robinson")["items"] if i["kind"] == "calendar"]
        self.assertEqual(len(items), 1)
        self.assertIn("Media team meeting at 6:30 PM", items[0]["text"])

    def test_nothing_is_sent_during_a_service(self):
        from arise_server import notify
        self.assertEqual(notify.tick(T("2026-10-25 11:00")), {"held": "during a service"})


class Desktop(RealConfig):
    def test_positions_are_cleaned_and_kept_per_person(self):
        from arise_server import desktop
        self.assertEqual(desktop.clean_positions({"a.md": [10, 20], "b": [-5, 3], "c/d": [1, 1], "e": "x", "f": [1, 2, 3], "g": [20000, 1]}), {"a.md": [10, 20]})
        self.assertTrue(desktop.save_positions("bradly", {"Run sheet.md": [400, 200]})["ok"])
        self.assertEqual(desktop.positions("bradly"), {"Run sheet.md": [400, 200]})
        self.assertEqual(desktop.positions("office"), {})
        self.assertFalse(desktop.save_positions("../x", {})["ok"])
        self.assertEqual(desktop.location({"user": "bradly", "role": "admin"}), {"root": "data", "path": "/homes/bradly/Desktop"})

    def test_a_new_home_gets_a_desktop_and_start_here_an_old_one_is_left_alone(self):
        from arise_server import config, files
        homes = Path(config.load().directory.homes_path)
        files.ensure_home("new.person")
        h = homes / "new.person"
        self.assertTrue((h / "Desktop").is_dir())
        self.assertTrue((h / "Start here.md").read_text().startswith("# Start here"))
        self.assertIn("Bradly", (h / "Start here.md").read_text())
        old = homes / "old.person"
        (old / "Documents").mkdir(parents=True)
        files.ensure_home("old.person")
        self.assertTrue((old / "Desktop").is_dir())
        self.assertFalse((old / "Start here.md").exists())        # a home that existed is never given the note
        (h / "Start here.md").unlink()
        files.ensure_home("new.person")
        self.assertFalse((h / "Start here.md").exists())          # deleted on purpose: not put back

    def test_move_within_one_place_only(self):
        from arise_server import config, desktop
        data = Path(config.load().system.data_root)
        d = data / "homes" / "bradly"
        (d / "Desktop").mkdir(parents=True, exist_ok=True)
        (d / "Documents" / "Sub").mkdir(parents=True, exist_ok=True)
        (d / "Documents" / "setlist.pdf").write_text("x")
        who = {"user": "bradly", "role": "admin"}
        r = desktop.move("data", "/homes/bradly/Documents/setlist.pdf", "/homes/bradly/Desktop", who)
        self.assertTrue(r["ok"], r)
        self.assertTrue((d / "Desktop" / "setlist.pdf").exists())
        (d / "Documents" / "setlist.pdf").write_text("y")
        self.assertFalse(desktop.move("data", "/homes/bradly/Documents/setlist.pdf", "/homes/bradly/Desktop", who)["ok"])   # never over a name
        self.assertFalse(desktop.move("data", "/homes/bradly/Documents", "/homes/bradly/Documents/Sub", who)["ok"])         # never into itself
        self.assertFalse(desktop.move("data", "/../../etc/passwd", "/homes/bradly/Desktop", who)["ok"])
        self.assertFalse(desktop.move("nas", "/x", "/y", who)["ok"])                                                        # no Synology here


class Setup(RealConfig):
    def test_steps_progress_and_dismiss(self):
        from arise_server import setup_wizard as w
        admin = {"user": "bradly", "role": "admin"}
        s = w.state(admin)
        self.assertEqual([x["id"] for x in s["steps"]], ["people", "shares", "synology", "discord", "resend", "tailscale"])
        self.assertTrue(s["show"])
        self.assertFalse(w.state({"user": "office", "role": "member"})["show"])
        self.assertTrue(w.mark("discord", "done", admin)["ok"])
        self.assertFalse(w.mark("nope", "done", admin)["ok"])
        self.assertFalse(w.mark("people", "maybe", admin)["ok"])
        self.assertEqual(next(x for x in w.state(admin)["steps"] if x["id"] == "discord")["status"], "done")
        self.assertFalse(w.dismiss(admin)["show"])
        self.assertTrue(w.dismiss(admin, False)["show"])


class StaffAccess(unittest.TestCase):
    """After round 5: "staff shouldn't have access to the actual server OS"."""

    def test_the_rule(self):
        from arise_server.auth import member_ok
        self.assertTrue(member_ok("/api/files/list", "member", "portal"))
        self.assertFalse(member_ok("/api/files/list", "member", "none"))
        self.assertTrue(member_ok("/api/auth/me", "member", "none"))
        self.assertTrue(member_ok("/api/auth/logout", "member", "none"))
        self.assertTrue(member_ok("/api/anything", "admin", "none"))

    def test_a_member_sign_in_gets_the_mac_page_by_default(self):
        was = {k: os.environ.get(k) for k in ("ARISE_DEMO", "ARISE_STAFF_ACCESS")}
        os.environ["ARISE_DEMO"] = "1"
        os.environ.pop("ARISE_STAFF_ACCESS", None)
        try:
            from fastapi.testclient import TestClient
            from arise_server import config, demo_state
            from arise_server.main import app
            config.load(force=True)
            demo_state.reset()
            m = TestClient(app)
            self.assertEqual(m.post("/api/auth/login", json={"user": "office", "password": "anything"}).json()["role"], "member")
            me = m.get("/api/auth/me").json()
            self.assertEqual(me["staff_access"], "none")
            self.assertEqual(m.get("/api/files/roots").status_code, 403)
            self.assertEqual(m.get("/api/sunday").status_code, 403)
            os.environ["ARISE_STAFF_ACCESS"] = "portal"
            self.assertEqual(m.get("/api/files/roots").status_code, 200)
            a = TestClient(app)   # the admin (sample mode)
            self.assertEqual(a.get("/api/checklists").status_code, 200)
            self.assertIn(m.get("/api/checklists").status_code, (401, 403))   # department lists are the admins' for now
            self.assertTrue(a.post("/api/kiosk/scale", json={"scale": 1.4}).json()["ok"])
            self.assertFalse(a.post("/api/kiosk/scale", json={"scale": 3}).json()["ok"])
            faces = a.get("/api/public/faces").json()["faces"]
            self.assertTrue(faces and all(f["user"] for f in faces))
        finally:
            for k, v in was.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


class Pins(unittest.TestCase):
    """The answers that are a line of config or markup."""

    def test_service_names_row_39(self):
        from arise_server import church
        self.assertEqual({s["name"] for s in church.DEFAULT_SERVICES}, {"Sunday Service", "Glory Night"})
        toml = (ROOT / "config" / "arise.toml.example").read_text()
        self.assertNotRegex(toml, r'name = "(Sunday Morning|Monday Night)')

    def test_monitor_text_size_row_27(self):
        cfg = (ROOT / "config" / "firefox" / "ariseos.cfg").read_text()
        self.assertIn('getenv("ARISE_KIOSK_SCALE")', cfg)
        self.assertIn('pref("layout.css.devPixelsPerPx", s)', cfg)
        launcher = (ROOT / "scripts" / "arise-browser").read_text()
        self.assertIn('ARISE_KIOSK_SCALE="${ARISE_KIOSK_SCALE:-1.25}"', launcher)

    def test_menu_bar_stats_and_glance_view_rows_25_and_34(self):
        css = (ROOT / "web" / "styles.css").read_text()
        self.assertIn("body.member .bar__stat", css)                     # stats are the admins'
        js = (ROOT / "web" / "app.js").read_text()
        saver = js[js.index("function saver(on)"):js.index("function kioskSetup()")]
        for word in ("attention", "backup", "stream", "Needs"):
            self.assertNotIn(word, saver)                                 # the glance view: clock, next service, verse
        self.assertIn("const remembered = '';", js)                       # row 31: nobody preselected

    def test_samba_makes_the_desktop_and_the_note(self):
        smb = (ROOT / "config" / "samba" / "smb.conf.template").read_text()
        self.assertIn('"$h/Desktop"', smb)
        self.assertIn("Start here.md", smb)


if __name__ == "__main__":
    unittest.main()

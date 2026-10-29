"""Round 7: services, the closet desktop and the channel (docs/ANSWERS.md, round 7: 19, 62,
78-81, 85, 87-91, 93, 94, 99, 100, 105-111, 114-116, 121, 144, 145).

Pure functions first; a real temp config where state is written. The directory is the only
thing stood in for (there is no domain here).
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "archive"))

T = datetime.fromisoformat
SERVICES = [
    {"name": "Sunday Service", "day": "Sunday", "time": "10:30", "site": "Pineville"},
    {"name": "Sunday Service", "day": "Sunday", "time": "10:00", "site": "Alexandria"},
    {"name": "Glory Night", "day": "Monday", "time": "19:00", "site": "Pineville"},
]


class RealConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="arise-r7c-")
        t = Path(cls.tmp)
        (t / "data" / "homes").mkdir(parents=True)
        (t / "arise.toml").write_text(
            f'[system]\ndata_root = "{t}/data"\n[web]\nadmin_user = "bradly"\n[directory]\nenabled = false\nhomes_path = "{t}/data/homes"\n'
            f'[paths]\nstate_dir = "{t}/state"\nlog_dir = "{t}/state"\n[church]\ndepartments = ["Media", "Inedge"]\n'
            f'[songs]\ninbox_users = ["worship.leader"]\n[owner]\nuser = "bradly"\n')
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


# ---- 91, 93, 94: what a service holds back ------------------------------------------------
class Holds(RealConfig):
    def test_alexandria_and_calendar_specials_count(self):
        from arise_server import church
        self.assertEqual(church.in_service_now(T("2026-10-25 10:15"), SERVICES)["site"], "Alexandria")   # 93
        self.assertIsNone(church.in_service_now(T("2026-10-25 09:59"), SERVICES))
        easter = [{"title": "Easter Sunrise", "start": "2026-04-05T07:00", "end": "2026-04-05T08:30", "is_service": True}]
        got = church.in_service_now(T("2026-04-05T07:30"), SERVICES, events=easter)                      # 94
        self.assertTrue(got["special"])
        self.assertEqual(got["name"], "Easter Sunrise")
        self.assertIsNone(church.in_service_now(T("2026-04-05T08:31"), SERVICES, events=easter))

    def test_hold_names_the_service_and_what_waits(self):
        from arise_server import church
        h = church.hold("mac", T("2026-10-26 19:30"), services=SERVICES)
        self.assertIn("Glory Night", h["why"])
        self.assertIn("changes to the church Macs", h["why"])
        self.assertIsNone(church.hold("update", T("2026-10-26 22:00"), services=SERVICES))
        for k in ("update", "restart", "mac", "sync", "heavy"):
            self.assertIn(k, church.HOLD_KINDS)

    def test_a_calendar_event_can_count_as_a_service(self):
        from arise_server import calendar
        self.assertTrue(calendar._clean({"title": "The Outpour", "start": "2026-11-06T18:00", "is_service": True})["is_service"])
        self.assertFalse(calendar._clean({"title": "Lunch", "start": "2026-11-06T12:00"})["is_service"])


# ---- 90: call times, 19/88/89: the phone page -----------------------------------------------
class CallTimesAndThePhone(RealConfig):
    def test_call_times_default_and_open_the_list(self):
        from arise_server import checklists as c, church
        self.assertEqual(church.call_time("Sunday Service"), "09:00")
        self.assertEqual(church.call_time("Glory Night"), "18:00")
        self.assertEqual(c.default_nudge("Glory Night"), "18:00")
        rnd = c.cycle(T("2026-10-25 08:00"), church.info()["services"], ["Sunday Service"])
        self.assertEqual(c.opens_at(rnd), T("2026-10-25 09:00"))

    def test_a_member_ticks_after_call_time_only_and_leaders_see_every_list(self):
        from arise_server import checklists as c
        admin, leader, member = {"user": "bradly", "role": "admin"}, {"user": "inedge.lead", "role": "member"}, {"user": "cam.op", "role": "member"}
        c.edit("Media", admin, items=["Cameras", "Lower thirds"], now=T("2026-10-24 21:00"))
        c.edit("Inedge", admin, items=["Room"], leader="inedge.lead", now=T("2026-10-24 21:00"))
        groups = {"cam.op": ["Media"], "inedge.lead": ["Inedge"]}
        with mock.patch("arise_server.directory.user_groups", side_effect=lambda u: groups.get(u, [])):
            early = c.tick("Media", 0, member, now=T("2026-10-25 08:30"))
            self.assertFalse(early["ok"])
            self.assertIn("call time", early["err"])
            self.assertTrue(c.tick("Media", 0, member, now=T("2026-10-25 09:05"))["ok"])
            self.assertTrue(c.tick("Media", 1, admin, now=T("2026-10-25 08:30"))["ok"])             # admins any time
            self.assertEqual([l["dept"] for l in c.phone(member, T("2026-10-25 09:10"))["lists"]], ["Media"])
            lead = c.phone(leader, T("2026-10-25 09:10"))
            self.assertEqual(sorted(l["dept"] for l in lead["lists"]), ["Inedge", "Media"])        # 88: leaders see every list
            self.assertEqual(lead["leads"], ["Inedge"])
            media = next(l for l in lead["lists"] if l["dept"] == "Media")
            self.assertFalse(media["can_tick"])                                                      # but tick only their own

    def test_a_leader_resets_only_their_departments_people(self):
        from arise_server import checklists as c
        c.edit("Inedge", {"user": "bradly", "role": "admin"}, items=["Room"], leader="inedge.lead", now=T("2026-10-24 21:00"))
        leader, other = {"user": "inedge.lead", "role": "member"}, {"user": "cam.op", "role": "member"}
        with mock.patch("arise_server.notify.members_of", side_effect=lambda e: {"@Inedge": {"youth.helper", "inedge.lead", "kristina.robinson"}}.get(e[0], set())), \
                mock.patch("arise_server.directory.list_users", return_value={"users": [{"name": "kristina.robinson", "groups": ["Domain Admins"]}]}), \
                mock.patch("arise_server.directory.set_password", return_value={"ok": True}) as sp:
            self.assertEqual(c.department_people(leader)["people"], ["youth.helper"])               # never an admin, never themself
            r = c.leader_reset(leader, "youth.helper")
            self.assertTrue(r["ok"])
            self.assertEqual(sp.call_args.kwargs.get("temporary"), True)
            self.assertGreaterEqual(len(r["temporary_password"]), 12)
            self.assertFalse(c.leader_reset(leader, "kristina.robinson")["ok"])
            self.assertFalse(c.leader_reset(other, "youth.helper")["ok"])

    def test_staff_reach_the_phone_page_and_nothing_else(self):
        from arise_server.auth import member_ok
        self.assertTrue(member_ok("/api/checklist/mine", "member", "none"))
        self.assertTrue(member_ok("/api/checklist/Media/tick", "member", "none"))
        self.assertFalse(member_ok("/api/checklists", "member", "none"))
        self.assertFalse(member_ok("/api/checklistsx", "member", "none"))
        self.assertTrue((ROOT / "web" / "checklist.html").exists())


# ---- 78, 79, 80, 85, 81/144, 145: reports ----------------------------------------------------
class Reports(unittest.TestCase):
    def test_the_all_green_comes_an_hour_before_each_service(self):
        from arise_server import reports
        due = reports.services_starting(T("2026-10-25 09:00"), services=SERVICES, events=[])
        self.assertEqual([(d["name"], d["site"]) for d in due], [("Sunday Service", "Alexandria")])
        self.assertEqual([d["site"] for d in reports.services_starting(T("2026-10-25 09:30"), services=SERVICES, events=[])], ["Pineville"])
        self.assertEqual([d["name"] for d in reports.services_starting(T("2026-10-26 18:00"), services=SERVICES, events=[])], ["Glory Night"])   # 79
        self.assertEqual(reports.services_starting(T("2026-10-26 18:01"), services=SERVICES, events=[]), [])
        special = [{"title": "The Outpour", "start": "2026-11-06T19:00", "is_service": True}]
        self.assertTrue(reports.services_starting(T("2026-11-06 18:00"), services=[], events=special)[0]["special"])

    def test_green_text_is_green_or_says_what_needs_someone(self):
        from arise_server import reports
        svc = {"name": "Glory Night", "site": "Pineville", "start": "2026-10-26T19:00"}
        self.assertIn("All green", reports.green_text(svc, []))
        t = reports.green_text(svc, [{"level": "bad", "text": "Backup 'homes' failed"}], [{"dept": "Media", "items": [1, 2], "done": 1}])
        self.assertIn("🔴", t)
        self.assertIn("Backup 'homes' failed", t)
        self.assertIn("Media checklist: 1 of 2 done", t)

    def test_partner_progress_and_the_weekly_text(self):
        from arise_server import reports
        self.assertEqual(reports.partner(742, 2913.0), {"subs_left": 258, "subs_pct": 74, "hours_left": 1087.0, "hours_pct": 73})
        t = reports.weekly_text({"week_ending": "2026-10-26", "backups": {"runs": 7, "failed": []}, "storage": [{"mount": "/", "pct": 41}],
                                 "macs": {"count": 3, "offline": [], "failed_tasks": 0}, "signins": {"ok": 9, "failed": 1, "people": 3},
                                 "updates": {"waiting": 2}, "channel": {"ok": False}})
        for want in ("7 runs, all ok", "/ 41%", "3 church Macs", "9 by 3 people", "Updates waiting for a click: 2", "numbers not available yet"):
            self.assertIn(want, t)

    def test_no_channel_file_means_no_number(self):
        from arise_server import reports
        with tempfile.TemporaryDirectory() as d, mock.patch("arise_server.reports.load") as ld:
            ld.return_value.demo = False
            self.assertFalse(reports.channel_numbers(Path(d))["ok"])
            (Path(d) / "channel_stats.json").write_text(json.dumps({"subscriberCount": "812", "watch_hours": 3100}))
            got = reports.channel_numbers(Path(d))
            self.assertEqual((got["subscribers"], got["watch_hours"], got["subs_left"]), (812.0, 3100.0, 188))

    def test_the_pastors_note_is_five_plain_lines(self):
        from arise_server import reports
        t = reports.draft_text({"month": "2026-10", "services": 9, "backups": 31, "backups_failed": 0, "accounts_made": 2, "macs": 3})
        self.assertIn("October 2026", t)
        self.assertEqual(len(t.splitlines()), 6)          # the heading and five lines
        self.assertNotIn("@", t)

    def test_a_failed_run_in_the_reports_own_words(self):
        from arise_server import reports
        rep = ("3 jobs done · 1 failed · 0 skipped\n## Preflight\n- signed in as Arise Church\n## Job: star-cleanup (priority 1)\n"
               "- applied 19 · read back 19\n## Job: shorts-tags (priority 2)\n- failed: quotaExceeded on videos.update\n")
        why = reports.explain_failure(rep)
        self.assertEqual(len(why), 1)
        self.assertTrue(why[0].startswith("shorts-tags: failed: quotaExceeded"))
        self.assertIn("resets at 2:00 AM Central", why[0])
        self.assertEqual(reports.explain_failure("3 jobs done · 0 failed\n## Job: x\n- ok"), [])


# ---- 99/100 the Lyrics inbox, 106 the CCLI report ---------------------------------------------
class Songs(RealConfig):
    def test_quarters(self):
        from arise_server import songs
        self.assertEqual(songs.quarter_of("2026-11-08"), ("2026 Q4", "2026-10-01", "2026-12-31"))
        self.assertEqual(songs.quarter_of(date(2026, 2, 1)), ("2026 Q1", "2026-01-01", "2026-03-31"))

    def test_usage_counts_from_the_set_lists_and_never_guesses_a_number(self):
        from arise_server import songs
        bank = [{"title": "Praise", "ccli": "7213077"}, {"title": "Great Expectation", "ccli": None, "original": True}]
        sls = [{"date": "2026-10-19", "songs": [{"title": "Praise", "ccli": "7213077"}, {"title": "Mystery Song"}]},
               {"date": "2026-10-11", "songs": [{"title": "praise"}, {"title": "Great Expectation"}]},
               {"date": "2026-09-30", "songs": [{"title": "Praise", "ccli": "7213077"}]}]
        r = songs.usage_report("2026-10-01", "2026-12-31", setlists=sls, songs=bank)
        self.assertEqual(r["services"], 2)
        top = r["songs"][0]
        self.assertEqual((top["title"], top["ccli"], top["times"]), ("Praise", "7213077", 2))
        mystery = next(x for x in r["songs"] if x["title"] == "Mystery Song")
        self.assertIsNone(mystery["ccli"])
        self.assertEqual(r["no_number"], ["Mystery Song"])                       # an original is not "missing"
        self.assertIn("Title,CCLI song number", songs.usage_csv(r))

    def test_the_inbox_imports_and_moves_files_aside(self):
        from arise_server import cloud, songs
        d = songs.inbox_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / "One.txt").write_text("Title: Sample Inbox Song\nVerse 1\nA sample line for the test\n")
        (d / "picture.jpg").write_bytes(b"\xff\xd8")
        r = songs.inbox_scan(by="test")
        self.assertEqual(r["files"], 1)
        self.assertTrue((d / "Imported" / "One.txt").exists() or (d / "Not imported" / "One.txt").exists())
        self.assertTrue((d / "picture.jpg").exists())                             # not lyrics: left where it is
        self.assertEqual(songs.inbox_log()["runs"][0]["files"], 1)
        m = next(x for x in cloud.mounts() if x["mount_point"] == "/Lyrics inbox")
        self.assertIn("bradly", m["users"])
        self.assertIn("worship.leader", m["users"])
        self.assertEqual(m["groups"], [])


# ---- 116, 121, 87, 107, 105, 111 -----------------------------------------------------------
class NotesBoard(RealConfig):
    def test_add_pin_put_away_bring_back(self):
        from arise_server import notes_board as nb
        r = nb.add("Mic stands Thursday", "bradly", "amber")
        nid = r["notes"][0]["id"]
        self.assertFalse(nb.add("  ", "bradly")["ok"])
        self.assertTrue(nb.edit(nid, "kristina.robinson", pinned=True)["notes"][0]["pinned"])
        r = nb.put_away(nid, "bradly")
        self.assertEqual((r["notes"], r["away"][0]["id"]), ([], nid))           # put away, never deleted
        self.assertEqual(nb.bring_back(nid, "bradly")["notes"][0]["id"], nid)


class SpeedAndServiceMode(RealConfig):
    def test_speed_maths_and_the_run_is_held_in_a_service(self):
        from arise_server import speedtest
        self.assertEqual(speedtest.mbps(25_000_000, 0.25), 800.0)
        r = speedtest.run(T("2026-10-28 13:00"), tester=lambda: {"down": 812.4, "up": 40.1, "ping": 11.0})
        self.assertTrue(r["ok"])
        sm = speedtest.summary()
        self.assertEqual(sm["last"]["down"], 812.4)
        with mock.patch("arise_server.church.hold", return_value={"why": "Glory Night is on"}):
            self.assertTrue(speedtest.run(T("2026-10-26 19:30"), tester=lambda: {"down": 1, "up": 1, "ping": 1})["held"])

    def test_the_live_page_and_the_run_sheet(self):
        from arise_server import servicemode as sm
        self.assertTrue(sm.is_live_page('var ytInitialData = {"isLiveNow":true}'))
        self.assertFalse(sm.is_live_page('var ytInitialData = {"x":1}'))
        self.assertIsNone(sm.is_live_page(""))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "Sunday run sheet.md").write_text("a")
            (p / "Glory Night run sheet.md").write_text("b")
            (p / "notes.md").write_text("c")
            self.assertEqual(sm.pick_sheet(list(p.iterdir()), "Glory Night", "2026-10-26").name, "Glory Night run sheet.md")
            (p / "2026-10-25 run sheet.txt").write_text("d")
            self.assertEqual(sm.pick_sheet(list(p.iterdir()), "Sunday Service", "2026-10-25").name, "2026-10-25 run sheet.txt")


class KioskAutologin(RealConfig):
    def test_once_per_boot_and_only_soon_after_it(self):
        from arise_server import kiosk_profiles as kp
        self.assertEqual(kp.autologin_user(), "bradly")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(kp, "STATE", Path(d)):
            now = time.time()
            self.assertIsNone(kp.autologin_take(now=now, boot=now - 3600))        # an hour after boot: no
            got = kp.autologin_take(now=now, boot=now - 60)
            self.assertEqual(got[1], "bradly")
            self.assertIsNone(kp.autologin_take(now=now + 5, boot=now - 60))      # once
        from arise_server import auth
        self.assertEqual(auth._serializer().loads(got[0])["r"], "admin")


class TextConsole(unittest.TestCase):
    """Round 7, 108: the kiosk owns tty1 only; tty2 and up keep their login prompt for the admins."""

    def test_only_tty1_is_taken(self):
        units = ROOT / "config" / "systemd"
        for f in units.glob("*.service"):
            t = f.read_text()
            for n in range(2, 7):
                self.assertNotIn(f"getty@tty{n}", t, f"{f.name} must leave tty{n} alone")
        inst = (ROOT / "installer" / "install.sh").read_text()
        self.assertNotIn("mask getty", inst)
        self.assertNotIn("NAutoVTs=0", inst)


class Demo(unittest.TestCase):
    """The sample: held videos stay out of search; two weather places."""
    @classmethod
    def setUpClass(cls):
        cls.was = os.environ.get("ARISE_DEMO")
        os.environ["ARISE_DEMO"] = "1"
        from arise_server import config
        config.load(force=True)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("ARISE_DEMO", None) if cls.was is None else os.environ.__setitem__("ARISE_DEMO", cls.was)
        from arise_server import config
        config.load(force=True)

    def test_held_videos_are_left_out_of_search(self):
        from arise_server import channel
        r = channel.search("sample", kind="all")
        self.assertNotIn("MnXmccLS2p8", [v["id"] for v in r["videos"] + r["titles"]])
        self.assertGreaterEqual(r["held_hidden"], 1)

    def test_weather_for_both_campuses(self):
        from arise_server import weather
        w = weather.all_places()
        self.assertEqual([p["place"] for p in w["places"]], ["Pineville, LA", "Alexandria, LA"])
        self.assertEqual(w["place"], "Pineville, LA")

"""Round 7: accounts, files and privacy (docs/ANSWERS.md, round 7: rows 9-21, 44-47, 60, 66-76, 86, 152).

Pure functions are tested directly; the flows go through the API in sample mode, the way
Directory, Sync and the sign-in call them. The samba-tool lines are checked as argv, never run.
"""
import base64
import os
import re
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from arise_server import accounts, carddav, config, demo_state  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


class Pure(unittest.TestCase):
    def test_a_second_john_smith_gets_a_number(self):
        u = accounts.unique_name
        self.assertEqual(u("john.smith", set()), "john.smith")
        self.assertEqual(u("john.smith", {"john.smith"}), "john.smith2")
        self.assertEqual(u("john.smith", {"John.Smith", "john.smith2"}), "john.smith3")

    def test_the_domain_commands(self):
        self.assertEqual(accounts.display_cmd("bryant.sanders", "Apostle Bryant Sanders"),
                         ["samba-tool", "user", "rename", "bryant.sanders", "--display-name=Apostle Bryant Sanders"])
        cmd = accounts.rename_cmd("jane.doe", "jane.smith", "AD.ARISECENLA.COM")
        self.assertEqual(cmd[:4], ["samba-tool", "user", "rename", "jane.doe"])
        self.assertIn("--samaccountname=jane.smith", cmd)
        self.assertIn("--upn=jane.smith@ad.arisecenla.com", cmd)

    def test_the_welcome_email_never_holds_a_password(self):
        subj, body = accounts.welcome_text("jane.doe", "Minister Jane Doe", ["Staff", "Worship"], "arise-server.ad.arisecenla.com", "cloud.ad.arisecenla.com")
        self.assertIn("jane.doe", body); self.assertIn("Worship", body); self.assertIn("Nextcloud", body)
        self.assertNotRegex(body.lower(), r"password: \S+\d")      # the first password comes from the admin, in person
        self.assertTrue(subj.startswith("Welcome to Arise Church"))

    def test_unused_accounts(self):
        now = datetime(2026, 11, 1)
        users = [{"name": "a.old", "enabled": True, "last_logon": (now - timedelta(days=120)).isoformat()},
                 {"name": "b.recent", "enabled": True, "last_logon": (now - timedelta(days=10)).isoformat()},
                 {"name": "c.never", "enabled": True, "last_logon": None},
                 {"name": "d.off", "enabled": False, "last_logon": None},
                 {"name": "Administrator", "enabled": True, "last_logon": None}]
        created = {"c.never": (now - timedelta(days=91)).isoformat()}
        got = [r["user"] for r in accounts.unused(users, created, {}, now, 90)]
        self.assertEqual(got, ["a.old", "c.never"])
        # named once: not again until they sign in and fall quiet again
        self.assertEqual(accounts.unused(users, created, {"a.old": now.isoformat(), "c.never": now.isoformat()}, now, 90), [])

    def test_new_device(self):
        self.assertFalse(accounts.new_device([], "Safari on a Mac"))                 # the very first sign-in sets the baseline
        self.assertFalse(accounts.new_device(["Safari on a Mac"], "Safari on a Mac"))
        self.assertTrue(accounts.new_device(["Safari on a Mac"], "Chrome on Windows"))

    def test_photo_kinds(self):
        self.assertEqual(accounts.photo_kind(JPEG), "jpeg")
        self.assertEqual(accounts.photo_kind(b"\x89PNG\r\n\x1a\n...."), "png")
        self.assertIsNone(accounts.photo_kind(b"<svg onload=alert(1)>"))

    def test_birthdays_on_the_calendar(self):
        from arise_server import calendar
        rows = [{"user": "a", "name": "Minister A", "birthday": "11-03"}, {"user": "b", "name": "B", "birthday": "02-29"},
                {"user": "c", "name": "C", "birthday": "12-25"}]
        items = calendar.birthday_items(2026, 11, rows)
        self.assertEqual([(i["title"], i["start"][:10]) for i in items], [("Birthday: Minister A", "2026-11-03")])
        self.assertEqual(calendar.birthday_items(2026, 2, rows), [])            # no 29 February in 2026
        self.assertTrue(items[0]["all_day"])

    def test_the_device_list_keeps_a_year(self):
        from arise_server import devices
        now = datetime(2026, 11, 1)
        store = {"_meta": {}, "aa": {"last_seen": (now - timedelta(days=400)).isoformat(timespec="minutes")},
                 "bb": {"last_seen": (now - timedelta(days=100)).isoformat(timespec="minutes")}}
        self.assertEqual(devices.prune(store, now), 1)
        self.assertEqual(sorted(store), ["_meta", "bb"])

    def test_a_leavers_copy_must_arrive_whole(self):
        from arise_server import offboard
        self.assertTrue(offboard.same_tally((3, 100), (3, 100)))
        self.assertFalse(offboard.same_tally((3, 100), (2, 100)))
        self.assertTrue(offboard.archive_dir("/mnt/synology/arise/leavers", "a.b", datetime(2026, 11, 1)).endswith("a.b (2026-11-01)"))


class CardDav(unittest.TestCase):
    def setUp(self):
        os.environ["ARISE_DEMO"] = "1"
        config.load(force=True)
        demo_state.reset()
        carddav._cache.clear()

    def test_vcards_escape_and_fold(self):
        c = carddav.vcard("u1", "Smith, John; Jr", "John", "Smith", "Minister", ["j@example.com"], "318-555-0100", ["Staff directory"])
        self.assertIn("FN:Smith\\, John\\; Jr\r\n", c)
        self.assertIn("TEL;TYPE=CELL:318-555-0100", c)
        self.assertTrue(c.startswith("BEGIN:VCARD\r\nVERSION:3.0\r\n") and c.endswith("END:VCARD\r\n"))
        long = carddav.fold("NOTE:" + "x" * 200)
        self.assertTrue(all(len(line.encode()) <= 75 for line in long.split("\r\n")))

    def test_the_book_holds_the_staff_directory_and_the_contacts_list(self):
        cards = carddav.cards(fresh=True)
        self.assertIn("staff-bradly", cards)
        self.assertFalse([k for k in cards if k.startswith("staff-guest-speaker")])     # a disabled account is left out
        self.assertTrue([k for k in cards if k.startswith("c-")])                     # the Mail app's sample contacts
        self.assertIn("ORG:Arise Church", cards["staff-bradly"])

    def test_discovery_then_cards(self):
        code, xml = carddav.propfind("/carddav/", "office", "0")
        self.assertEqual(code, 207); self.assertIn("/carddav/principals/office/", xml)
        code, xml = carddav.propfind("/carddav/principals/office/", "office", "0")
        self.assertIn("<card:addressbook-home-set><d:href>/carddav/books/office/</d:href>", xml)
        code, xml = carddav.propfind("/carddav/books/office/", "office", "1")
        self.assertIn("/carddav/books/office/church/", xml); self.assertIn("<card:addressbook/>", xml)
        self.assertIn("getctag", xml); self.assertNotIn("<d:write/>", xml)        # read-only
        code, xml = carddav.propfind("/carddav/books/office/church/", "office", "1")
        hrefs = re.findall(r"<d:href>(/carddav/books/office/church/[^<]+\.vcf)</d:href>", xml)
        self.assertGreater(len(hrefs), 3)
        body = "<card:addressbook-multiget xmlns:d='DAV:' xmlns:card='urn:ietf:params:xml:ns:carddav'>" + "".join(f"<d:href>{h}</d:href>" for h in hrefs[:2]) + "</card:addressbook-multiget>"
        code, xml = carddav.report("/carddav/books/office/church/", "office", body)
        self.assertEqual(code, 207); self.assertEqual(xml.count("BEGIN:VCARD"), 2)
        self.assertEqual(carddav.get(hrefs[0], "office")[0], 200)
        self.assertEqual(carddav.propfind("/carddav/books/someone-else/church/", "office", "1")[0], 404)   # only one's own path

    def test_the_routes(self):
        from fastapi.testclient import TestClient
        from arise_server.main import app
        c = TestClient(app)
        self.assertEqual(c.request("PROPFIND", "/carddav/").status_code, 401)                       # the church login first
        auth = {"Authorization": "Basic " + base64.b64encode(b"office:anything").decode()}       # a sample staff account
        r = c.request("PROPFIND", "/carddav/books/office/church/", headers={**auth, "Depth": "1"})
        self.assertEqual(r.status_code, 207, r.text[:200]); self.assertIn("addressbook", r.text)
        self.assertEqual(c.request("PUT", "/carddav/books/office/church/x.vcf", headers=auth, content=b"BEGIN:VCARD").status_code, 403)
        self.assertEqual(c.get("/.well-known/carddav", follow_redirects=False).status_code, 301)
        member = {"Authorization": "Basic " + base64.b64encode(b"media-mac:anything").decode()}
        self.assertEqual(c.request("PROPFIND", "/carddav/", headers=member).status_code, 401 if not carddav.may_read("media-mac") else 207)
        prof = c.get("/contacts.mobileconfig")
        self.assertEqual(prof.status_code, 200); self.assertIn("com.apple.carddav.account", prof.text)
        self.assertNotIn("Password", prof.text)                                                   # it asks on the device
        self.assertTrue(c.get("/api/contacts").json()["url"].endswith("/carddav/"))


class Flows(unittest.TestCase):
    def setUp(self):
        os.environ["ARISE_DEMO"] = "1"
        config.load(force=True)
        demo_state.reset()
        from fastapi.testclient import TestClient
        from arise_server.main import app
        self.c = TestClient(app)

    def discord(self):
        return [x["text"] for x in demo_state.get("r7.discord", list)]

    def test_making_an_account_numbers_a_twin_and_tells_discord(self):
        r = self.c.post("/api/directory/users", json={"name": "office", "password": "password123", "display": "Second Office"}).json()
        self.assertTrue(r["ok"], r); self.assertEqual(r["user"], "office2"); self.assertIn("office was taken", r["renamed"])
        self.assertTrue(any("New account" in t and "office2" in t for t in self.discord()))
        self.assertTrue(self.c.post("/api/directory/users/office2/disable").json()["ok"])
        self.assertTrue(any("switched off" in t and "office2" in t for t in self.discord()))

    def test_rename(self):
        self.c.put("/api/directory/users/office/profile", json={"mobile": "318-555-0100"})
        self.assertFalse(self.c.post("/api/directory/users/office/rename", json={"new": "church.office", "confirm": "wrong"}).json()["ok"])
        self.assertFalse(self.c.post("/api/directory/users/office/rename", json={"new": "bradly", "confirm": "office"}).json()["ok"])   # taken
        r = self.c.post("/api/directory/users/office/rename", json={"new": "church.office", "confirm": "office"}).json()
        self.assertTrue(r["ok"], r); self.assertIn("profile", r["moved"]); self.assertIn("mobile", r["macs"].lower())
        names = [u["name"] for u in self.c.get("/api/directory/users").json()["users"]]
        self.assertIn("church.office", names); self.assertNotIn("office", names)
        p = self.c.get("/api/directory/users/church.office/profile").json()
        self.assertEqual(p["mobile"], "318-555-0100")
        from arise_server import profiles
        self.assertTrue(profiles._read()["church.office"]["mail_aliases"][0].startswith("office@"))   # the old address still delivers
        self.assertEqual(accounts.renames()["office"]["to"], "church.office")                         # for the Mac side

    def test_photo(self):
        bad = self.c.post("/api/directory/users/office/photo", json={"data": base64.b64encode(b"<svg/>").decode()}).json()
        self.assertFalse(bad["ok"])
        big = self.c.post("/api/directory/users/office/photo", json={"data": base64.b64encode(JPEG + b"\x00" * 300_000).decode()}).json()
        self.assertFalse(big["ok"])
        ok = self.c.post("/api/directory/users/office/photo", json={"data": base64.b64encode(JPEG).decode()}).json()
        self.assertTrue(ok["ok"], ok)
        self.assertTrue(accounts.has_photo("office"))

    def test_breakglass_is_bradlys_and_tells_the_pastors(self):
        cfg = config.load()
        cfg.owner.user = "bradly"
        self.addCleanup(setattr, cfg.owner, "user", "")
        from arise_server import files, sharing
        office_admin = {"user": "kristina.robinson", "role": "admin"}
        bradly = {"user": "bradly", "role": "admin"}
        self.assertFalse(sharing.is_pastor(bradly))
        self.assertFalse(accounts.breakglass_open(office_admin, "an emergency, truly", "pastors")["ok"])   # Bradly only (row 69: "You")
        self.assertFalse(accounts.breakglass_open(bradly, "an emergency, truly", "nope")["ok"])            # the name typed
        self.assertFalse(accounts.breakglass_open(bradly, "why?", "pastors")["ok"])                         # a real reason
        r = accounts.breakglass_open(bradly, "Pastor Bryant is in hospital; the funeral notes are needed today", "pastors")
        self.assertTrue(r["ok"], r)
        self.assertEqual(sorted(r["told"]), sorted(cfg.storage.pastors))
        self.assertTrue(sharing.is_pastor(bradly))
        self.assertIn("pastors", [x["id"] for x in files.roots(bradly)])
        self.assertTrue(any("Pastors folder opened" in t for t in self.discord()))
        self.assertFalse(sharing.is_pastor(None))                                   # never the system itself (Claude, the CLI)
        accounts.breakglass_close("bradly", "bradly")
        self.assertFalse(sharing.is_pastor(bradly))
        later = accounts.breakglass_open(bradly, "a second emergency today", "pastors", now=1.0)   # long ago: already over
        self.assertTrue(later["ok"]); self.assertFalse(accounts.breakglass_active("bradly"))

    def test_links_are_admins_only(self):
        from arise_server import links
        self.assertFalse(links.create("home", "/Documents/Bulletin 2026-11-01.docx", {"user": "office", "role": "member"})["ok"])

    def test_cut_off_tells_the_person(self):
        r = self.c.post("/api/cloud/revoke", json={"user": "office", "device": "Office iMac"}).json()
        self.assertTrue(r.get("told"), r)


class Rules(unittest.TestCase):
    def test_claude_never_opens_the_pastors_folder(self):
        src = (ROOT / "scripts" / "arise-owner-setup").read_text()
        self.assertIn('"Read(/srv/arise/pastors/**)"', src)
        self.assertIn('"Bash(*/srv/arise/pastors*)"', src)

    def test_claude_may_read_the_audit_log(self):
        self.assertIn("round 7, 76", (ROOT / "CLAUDE.md").read_text())

    def test_the_audit_log_is_kept_forever(self):
        # Round 7, 67: nothing rotates or trims audit.jsonl.
        for p in (ROOT / "config" / "logrotate").iterdir():
            self.assertNotIn("audit", p.read_text(), p)
        src = (ROOT / "server" / "arise_server" / "audit.py").read_text()
        self.assertNotIn("truncate", src); self.assertNotIn("os.remove", src)


if __name__ == "__main__":
    unittest.main()

"""Accounts and profiles (round 5: 5 to 11, 22, 38), against real files and real processes.

* The profile file, prefs and the reset tokens are written to a temp state folder (real mode).
* "Must change at next login" is the domain's own flag: the samba-tool command lines are
  recorded (no samba-tool here), and a stand-in `kinit` on PATH answers the way MIT kinit does
  for a right-but-expired password, so check_login/change_expired run as real subprocesses.
* The flows (temporary password -> forced change -> sign-in; forgot -> link -> new password;
  the people list) go through the API in sample mode, as the dashboard calls them.
* A leaver's Maildir is exported to an mbox file with Python's own mailbox module.
"""
import mailbox
import os
import shutil
import stat
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from email.message import EmailMessage
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from arise_server import audit, config, demo_state, directory, offboard, profiles  # noqa: E402

FAKE_KINIT = r"""#!/bin/sh
# Answers like MIT kinit: the temporary password is right but expired; then it reads the new one twice.
read -r pw
case "$pw" in
  Temp-Pass-1234!) echo "Password expired.  You must change it now." >&2
    read -r a; read -r b
    if [ "$a" != "$b" ]; then echo "Password mismatch" >&2; exit 1; fi
    if [ "${#a}" -lt 12 ]; then echo "Password change rejected: The password must be at least 12 characters." >&2; exit 1; fi
    exit 0 ;;
  Good-Pass-5678!) exit 0 ;;
  *) echo "kinit: Preauthentication failed while getting initial credentials" >&2; exit 1 ;;
esac
"""


class Rec:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, timeout=60, input_text=None, check=False):
        self.calls.append(list(cmd))
        return {"ok": True, "code": 0, "out": "", "err": "", "cmd": " ".join(cmd)}


@contextmanager
def real_mode(tmp: Path, extra: str = ""):
    conf = tmp / "arise.toml"
    conf.write_text(f'[system]\ndata_root = "{tmp}/data"\n[web]\nadmin_user = "bradly"\n[directory]\nenabled = true\nhomes_path = "{tmp}/homes"\n'
                    f'[paths]\nstate_dir = "{tmp}/state"\nlog_dir = "{tmp}/state"\n' + extra)
    old = {k: os.environ.get(k) for k in ("ARISE_CONFIG", "ARISE_DEMO")}
    os.environ["ARISE_CONFIG"] = str(conf)
    os.environ.pop("ARISE_DEMO", None)
    config.load(force=True)
    try:
        yield
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        config.load(force=True)


class Pure(unittest.TestCase):
    def test_birthdays_keep_month_and_day_only(self):
        n = profiles.normalize_birthday
        self.assertEqual([n("03-14"), n("3/14"), n("March 14"), n("Mar 14, 1985"), n("1985-03-14"), n("02-29")], ["03-14"] * 5 + ["02-29"])
        for bad in ("13-01", "02-30", "April 31", "someday", ""):
            self.assertIsNone(n(bad), bad)

    def test_names_with_titles(self):
        self.assertEqual(profiles.display_name("bryant.sanders", "Bryant Sanders", {"title": "Apostle"}), "Apostle Bryant Sanders")
        self.assertEqual(profiles.display_name("x", "Pastor Vanessa Sanders", {"title": "Pastor"}), "Pastor Vanessa Sanders")   # never twice
        self.assertEqual(profiles.greeting_name("bryant.sanders", "Bryant Sanders", {"title": "Apostle"}), "Apostle Bryant")
        self.assertEqual(profiles.greeting_name("bradly", "Bradly Dyer", {}), "Bradly")
        self.assertEqual(profiles.username_of("Zoë", "O'Neil"), "zoe.oneil")
        self.assertEqual(profiles.username_of("Mary Ann", "Smith"), "mary-ann.smith")

    def test_temporary_passwords_meet_the_domain_rule(self):
        for _ in range(50):
            p = profiles.temp_password()
            self.assertGreaterEqual(len(p), 12)
            kinds = sum(bool(f(p)) for f in (lambda s: any(c.isupper() for c in s), lambda s: any(c.islower() for c in s),
                                              lambda s: any(c.isdigit() for c in s), lambda s: any(not c.isalnum() for c in s)))
            self.assertGreaterEqual(kinds, 3, p)

    def test_kinit_answers(self):
        self.assertEqual(directory.classify_kinit(0, ""), "ok")
        self.assertEqual(directory.classify_kinit(1, "Password expired.  You must change it now."), "expired")
        self.assertEqual(directory.classify_kinit(1, "kinit: Password has expired while getting initial credentials"), "expired")
        self.assertEqual(directory.classify_kinit(1, "kinit: Preauthentication failed"), "bad")

    def test_devices(self):
        self.assertEqual(profiles.device_of("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15"), "Safari on a Mac")
        self.assertEqual(profiles.device_of("Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"), "Firefox on Linux")
        self.assertEqual(profiles.device_of("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari/604.1"), "Safari on an iPhone")


class RealMode(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="arise-profiles-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_profile_and_prefs_are_a_file_in_the_state_folder(self):
        with real_mode(self.tmp):
            me = {"user": "jane.doe", "role": "member"}
            r = profiles.update("jane.doe", {"mobile": "318-555-0100", "birthday": "March 14", "personal_email": "jane@example.com"}, me)
            self.assertTrue(r["ok"], r)
            self.assertFalse(profiles.update("jane.doe", {"title": "Pastor"}, me)["ok"])                 # titles are an admin's
            self.assertFalse(profiles.update("john.smith", {"mobile": "318-555-0101"}, me)["ok"])       # someone else's
            self.assertFalse(profiles.update("jane.doe", {"personal_email": "jane.doe@ad.arisecenla.com"}, me)["ok"])   # the church one
            self.assertTrue(profiles.update("jane.doe", {"title": "Minister", "departments": ["Worship"]}, {"user": "bradly", "role": "admin"})["ok"])
            self.assertTrue(profiles.save_prefs("jane.doe", {"theme": "bone", "dock.hide": "0", "a11y.text": "1"})["ok"])
            self.assertFalse(profiles.save_prefs("jane.doe", {"anything": "x"})["ok"])
            f = self.tmp / "state" / "profiles.json"
            self.assertTrue(f.exists())
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o640)
            d = __import__("json").loads(f.read_text())["jane.doe"]
            self.assertEqual((d["birthday"], d["title"], d["prefs"]["theme"]), ("03-14", "Minister", "bone"))
            self.assertEqual(profiles.birthdays(3)[0]["birthday"], "03-14")

    def test_mail_domain_and_realm_come_from_the_config(self):
        with real_mode(self.tmp, '[mail]\ndomain = "church.example.org"\n'):
            self.assertEqual(profiles.mail_domain(), "church.example.org")
            self.assertEqual(profiles.profile("jane.doe", {"user": "jane.doe", "role": "member"})["mail"], "jane.doe@church.example.org")
        with real_mode(self.tmp):
            self.assertEqual(profiles.mail_domain(), config.load().directory.realm.lower())

    def test_temporary_passwords_are_the_domains_must_change_flag(self):
        rec = Rec()
        with real_mode(self.tmp), mock.patch.object(directory, "run", rec), mock.patch.object(directory, "which", lambda n: f"/usr/bin/{n}"), \
                mock.patch.object(directory, "_mkhome", lambda n: None):
            self.assertTrue(directory.add_user("jane.doe", "Temp-Pass-1234!", "Jane Doe", [], temporary=True)["ok"])
            self.assertTrue(directory.set_password("jane.doe", "Temp-Pass-9999!", temporary=True)["ok"])
            self.assertTrue(directory.set_password("jane.doe", "Own-Pass-5555!", temporary=False)["ok"])
        create = next(c for c in rec.calls if c[:3] == ["samba-tool", "user", "create"])
        self.assertIn("--must-change-at-next-login", create)       # the Mac's login window asks for a new one too
        sets = [c for c in rec.calls if c[:3] == ["samba-tool", "user", "setpassword"]]
        self.assertIn("--must-change-at-next-login", sets[0])
        self.assertNotIn("--must-change-at-next-login", sets[1])
        d = directory.parse_user_show("jane.doe", "pwdLastSet: 0\n")
        self.assertTrue(d["must_change"])

    def test_an_expired_password_is_changed_through_kinit_as_the_person(self):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        k = bin_dir / "kinit"
        k.write_text(FAKE_KINIT)
        k.chmod(0o755)
        path = os.environ["PATH"]
        os.environ["PATH"] = f"{bin_dir}:{path}"
        try:
            with real_mode(self.tmp), mock.patch.object(directory, "which", lambda n: f"/usr/bin/{n}" if n in ("samba-tool", "kinit") else None):
                self.assertEqual(directory.check_login("jane.doe", "Temp-Pass-1234!"), "expired")
                self.assertEqual(directory.check_login("jane.doe", "Good-Pass-5678!"), "ok")
                self.assertEqual(directory.check_login("jane.doe", "wrong"), "bad")
                r = directory.change_expired("jane.doe", "Temp-Pass-1234!", "short-1A!")
                self.assertFalse(r["ok"])
                self.assertIn("12 characters", r["err"])                              # the domain's own words
                self.assertNotIn("short-1A!", r["err"])
                self.assertTrue(directory.change_expired("jane.doe", "Temp-Pass-1234!", "Brand-New-Pass-42!")["ok"])
                self.assertFalse(directory.change_expired("jane.doe", "wrong", "Brand-New-Pass-42!")["ok"])
        finally:
            os.environ["PATH"] = path

    def test_reset_tokens_are_stored_hashed_and_say_nothing_about_accounts(self):
        with real_mode(self.tmp):
            r = profiles.forgot("nobody.here", "http://arise-server", "10.0.0.5")
            self.assertEqual(r["message"], profiles.SAME_ANSWER)
            self.assertNotIn("sample_link", r)
            # a token planted the way forgot() writes it: only its sha256 is on disk
            tok = "t0ken-for-the-test"
            d = {__import__("hashlib").sha256(tok.encode()).hexdigest(): {"user": "jane.doe", "exp": time.time() + 60, "used": False}}
            profiles._save_resets(d)
            raw = (self.tmp / "state" / "password-resets.json").read_text()
            self.assertNotIn(tok, raw)
            self.assertEqual(stat.S_IMODE((self.tmp / "state" / "password-resets.json").stat().st_mode), 0o600)
            self.assertTrue(profiles.check_reset(tok)["ok"])
            self.assertFalse(profiles.check_reset(tok, now=time.time() + 3600)["ok"])     # 30 minutes, then gone
            self.assertFalse(profiles.check_reset("guess")["ok"])

    def test_a_leavers_mail_is_exported_before_anything_else(self):
        with real_mode(self.tmp, f'[mail]\nmaildir_root = "{self.tmp}/mail"\n'):
            maildir = self.tmp / "mail" / profiles.mail_domain() / "jane.doe"   # the domain from the config, never typed
            maildir.parent.mkdir(parents=True)
            md = mailbox.Maildir(str(maildir), create=True)
            for i in range(3):
                m = EmailMessage()
                m["From"], m["To"], m["Subject"] = "a@example.com", f"jane.doe@{profiles.mail_domain()}", f"note {i}"
                m.set_content(f"body {i}")
                md.add(m)
            sub = md.add_folder("Sent")
            m = EmailMessage(); m["Subject"] = "sent one"; m.set_content("x"); sub.add(m)
            dest = offboard.dest_dir(str(self.tmp / "homes"), "john.smith", "jane.doe")
            r = profiles.mailbox_export("jane.doe", dest)
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["exported"], 4)
            box = mailbox.mbox(r["file"])
            self.assertEqual(sorted(x["Subject"] for x in box), ["note 0", "note 1", "note 2", "sent one"])
            self.assertTrue(r["file"].startswith(dest))
            self.assertTrue(maildir.exists())                                         # never deleted here
            none = profiles.mailbox_export("nobody", dest)
            self.assertTrue(none["ok"]); self.assertEqual(none["exported"], 0)


class Flows(unittest.TestCase):
    """Through the API in sample mode, the way the sign-in screen, the reset page and Directory call it."""

    def setUp(self):
        os.environ["ARISE_DEMO"] = "1"
        config.load(force=True)
        demo_state.reset()
        profiles._rate.clear()
        from fastapi.testclient import TestClient
        from arise_server.main import app
        self.TC, self.app = TestClient, app
        self.admin = TestClient(app)

    def test_temporary_password_then_their_own(self):
        a = self.admin
        r = a.post("/api/directory/users", json={"name": "jane.doe", "display": "Jane Doe", "password": "Temp-Pass-1234!", "title": "Minister", "groups": ["Staff"]}).json()
        self.assertTrue(r["ok"]) ; self.assertTrue(r["must_change"])
        row = next(u for u in a.get("/api/directory/users").json()["users"] if u["name"] == "jane.doe")
        self.assertEqual((row["must_change"], row["full_name"]), (True, "Minister Jane Doe"))
        m = self.TC(self.app)
        r = m.post("/api/auth/login", json={"user": "jane.doe", "password": "Temp-Pass-1234!"}).json()
        self.assertTrue(r["need_new_password"])
        self.assertNotIn("arise_session", m.cookies)                                  # not signed in yet
        self.assertFalse(m.post("/api/auth/login/new-password", json={"user": "jane.doe", "old": "Temp-Pass-1234!", "new": "Temp-Pass-1234!"}).json()["ok"])
        self.assertFalse(m.post("/api/auth/login/new-password", json={"user": "jane.doe", "old": "nope", "new": "Own-Pass-7777!"}).json()["ok"])
        r = m.post("/api/auth/login/new-password", json={"user": "jane.doe", "old": "Temp-Pass-1234!", "new": "Own-Pass-7777!"}).json()
        self.assertTrue(r["ok"]); self.assertEqual(r["user"], "jane.doe")
        me = m.get("/api/auth/me").json()
        self.assertEqual((me["user"], me["name"], me["greeting"], me["staff"]), ("jane.doe", "Minister Jane Doe", "Minister Jane", True))
        self.assertEqual(self.TC(self.app).post("/api/auth/login", json={"user": "jane.doe", "password": "Own-Pass-7777!"}).json()["role"], "member")
        sig = m.get("/api/me/signins").json()["signins"]    # newest first; refused tries are listed too
        hows = [s["how"].split(" · ")[0] for s in sig]
        self.assertEqual(hows[:2], ["directory", "temporary password replaced"])
        self.assertIn("temporary password: a new one is needed", hows)
        self.assertIn("Wrong user or password", hows)
        self.assertEqual(sig[0]["ok"], True)
        self.assertFalse(next(s for s in sig if s["how"].startswith("temporary password: a new"))["ok"])
        # an admin's reset is temporary again by default
        a.post("/api/directory/users/jane.doe/reset-password", json={"password": "Temp-Again-1234!"})
        self.assertTrue(self.TC(self.app).post("/api/auth/login", json={"user": "jane.doe", "password": "Temp-Again-1234!"}).json()["need_new_password"])

    def test_forgot_and_the_link(self):
        a = self.admin
        a.post("/api/directory/users", json={"name": "jane.doe", "display": "Jane Doe", "password": "Own-Pass-7777!", "temporary": False})
        anon = self.TC(self.app)
        none = anon.post("/api/auth/forgot", json={"user": "jane.doe"}).json()
        self.assertNotIn("sample_link", none)                       # no personal email on file yet: the same words, no link
        a.put("/api/directory/users/jane.doe/profile", json={"personal_email": "jane@example.com"})
        r = anon.post("/api/auth/forgot", json={"user": "jane.doe"}).json()
        self.assertEqual(r["message"], none["message"])
        tok = r["sample_link"].split("t=")[1]
        self.assertTrue(r["sample_link"].startswith("http://testserver/reset?t="))
        self.assertEqual(anon.get("/api/auth/reset/check", params={"t": tok}).json()["user"], "jane.doe")
        self.assertFalse(anon.post("/api/auth/reset", json={"token": tok, "new": "short"}).json()["ok"])
        self.assertTrue(anon.post("/api/auth/reset", json={"token": tok, "new": "Reset-Pass-3333!"}).json()["ok"])
        self.assertFalse(anon.post("/api/auth/reset", json={"token": tok, "new": "Reset-Pass-4444!"}).json()["ok"])   # single use
        self.assertEqual(self.TC(self.app).post("/api/auth/login", json={"user": "jane.doe", "password": "Reset-Pass-3333!"}).status_code, 200)
        for _ in range(5):
            anon.post("/api/auth/forgot", json={"user": "jane.doe"})
        self.assertNotIn("sample_link", anon.post("/api/auth/forgot", json={"user": "jane.doe"}).json())   # three an hour
        ev = audit.recent(q="auth.forgot", who="jane.doe")["events"]
        self.assertTrue(any(e.get("detail") == "too many requests" for e in ev))
        self.assertEqual(self.TC(self.app).get("/reset").status_code, 200)

    def test_profiles_are_not_for_members(self):
        m = self.TC(self.app)
        self.assertEqual(m.post("/api/auth/login", json={"user": "kids-checkin", "password": "x"}).json()["role"], "member")
        self.assertEqual(m.get("/api/people").status_code, 403)                     # not staff: refused by the server
        a = self.admin
        a.put("/api/directory/users/office/profile", json={"mobile": "318-555-0100"})
        mine = m.get("/api/me/profile").json()
        self.assertEqual(mine["can_edit"], ["personal_email", "mobile", "birthday"])
        s = self.TC(self.app)
        s.post("/api/auth/login", json={"user": "office", "password": "x"})          # Staff group
        ppl = {p["user"]: p for p in s.get("/api/people").json()["people"]}
        self.assertEqual(ppl["office"]["mobile"], "318-555-0100")
        self.assertEqual(m.put("/api/me/prefs", json={"prefs": {"theme": "bone"}}).json()["prefs"]["theme"], "bone")
        self.assertEqual(m.get("/api/me/prefs").json()["prefs"], {"theme": "bone"})

    def test_people_list(self):
        csv = ("first,last,title,departments,personal_email,mobile,birthday,role\n"
               "Kristina,Robinson,Minister,Leadership,b@example.com,,03-02,admin\n"
               "Kristina,Robinson,,,,,,staff\n"
               "Ann,,,,,,,\n"
               "Zoë,O'Neil,Minister,Worship;Nope,,,,staff\n"
               "Sam,Lee,,,,,,boss\n")
        check = self.admin.post("/api/directory/import", json={"csv": csv}).json()
        self.assertFalse(check["apply"])
        self.assertEqual([r["ok"] for r in check["rows"]], [True, False, False, True, False])
        self.assertNotIn("temporary_password", str(check))
        self.assertNotIn("kristina.robinson", [u["name"] for u in self.admin.get("/api/directory/users").json()["users"]])   # nothing made
        made = self.admin.post("/api/directory/import", json={"csv": csv, "apply": True}).json()
        self.assertEqual(made["created"], 2)
        b = made["rows"][0]
        self.assertEqual((b["user"], b["groups"]), ("kristina.robinson", ["Domain Admins", "Leadership"]))
        self.assertIn("no group Nope yet", made["rows"][3]["warnings"][0])
        self.assertTrue(self.TC(self.app).post("/api/auth/login", json={"user": "kristina.robinson", "password": b["temporary_password"]}).json()["need_new_password"])
        self.assertEqual(self.admin.get("/api/directory/users/kristina.robinson/profile").json()["name"], "Minister Kristina Robinson")
        ev = audit.recent(q="directory.import")["events"]
        self.assertTrue(ev and all(b["temporary_password"] not in str(e) for e in ev))   # never in the log

    def test_the_sign_in_page_reads_the_realm_from_the_config(self):
        si = self.TC(self.app).get("/api/public/sign-in").json()
        self.assertEqual(si["realm"], config.load().directory.realm.upper())
        self.assertEqual(si["mail_domain"], profiles.mail_domain())


class Offboard(unittest.TestCase):
    def test_the_sweep_records_the_mail_export(self):
        os.environ["ARISE_DEMO"] = "1"
        config.load(force=True)
        demo_state.reset()
        offboard._DEMO["entries"] = []
        self.assertTrue(offboard.start("office", "bradly", "bradly", days=0)["ok"])
        r = offboard.sweep()
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["results"][0]["mailbox"]["ok"])
        self.assertTrue(offboard._read()[0]["mailbox_exported"])


if __name__ == "__main__":
    unittest.main()

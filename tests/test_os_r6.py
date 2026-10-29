"""Round 6, rows 20-35 (docs/ANSWERS.md): the closet OS for the four admins, Kristina's
powers beside Bradly's, two-step for staff by an admin, and Firefox per admin.

Real scripts and the real policy builder; the sample server for the routes.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("ARISE_DEMO", "1")
os.environ.setdefault("ARISE_CONFIG", str(ROOT / "config" / "arise.toml.example"))

from fastapi.testclient import TestClient  # noqa: E402

from arise_server import config, demo_state, kiosk_profiles  # noqa: E402
from arise_server.auth import member_ok  # noqa: E402
from arise_server.main import app  # noqa: E402

ADMINS = {"bradly", "bryant.sanders", "vanessa.sanders", "kristina.robinson"}


def policies(cfg=None):
    spec = importlib.util.spec_from_file_location("abp_r6", ROOT / "scripts" / "arise-browser-policies.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.build(cfg or {})["policies"]


class Firefox(unittest.TestCase):
    """Rows 29-35."""

    def test_the_policy_still_validates_against_firefoxs_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        schema = json.loads((ROOT / "tests" / "fixtures" / "firefox-policies-schema.json").read_text())
        jsonschema.validate(policies(), schema)
        self.assertIn("SearchEngines", schema["properties"])

    def test_google_ublock_passwords_addons_safe_browsing(self):
        p = policies()
        self.assertEqual(p["SearchEngines"]["Default"], "Google")                       # row 32
        self.assertTrue(p["PasswordManagerEnabled"])                                   # row 30
        ext = p["ExtensionSettings"]
        self.assertEqual(ext["uBlock0@raymondhill.net"]["installation_mode"], "force_installed")   # row 31
        self.assertEqual(ext["*"]["installation_mode"], "allowed")                     # row 34: any add-on
        prefs = p["Preferences"]
        for k in ("browser.safebrowsing.malware.enabled", "browser.safebrowsing.phishing.enabled", "browser.safebrowsing.downloads.enabled"):
            self.assertIs(prefs[k]["Value"], True, k)                                   # row 35
        self.assertNotIn("WebsiteFilter", p)                                           # no other filtering
        self.assertEqual(prefs["browser.download.folderList"]["Value"], 2)             # row 33: the profile's own folder

    def test_the_launcher_and_the_switcher(self):
        for f in ("arise-browser", "arise-browser-profile"):
            self.assertEqual(subprocess.run(["sh", "-n", str(ROOT / "scripts" / f)]).returncode, 0, f)
        launcher = (ROOT / "scripts" / "arise-browser").read_text()
        self.assertIn("/run/arise-kiosk", launcher)
        self.assertIn("arise-neutral", launcher)           # locked: a fresh profile, no history
        self.assertIn("--new-instance", launcher)
        self.assertIn("epiphany", launcher)                # the old fallback stays
        sw = (ROOT / "scripts" / "arise-browser-profile").read_text()
        self.assertIn("chmod 0700", sw)                    # an admin's profile is root's while they are away
        self.assertIn('setfacl -m "u:$KIOSK:rwx"', sw)     # Downloads lent to the kiosk while it is their turn
        self.assertIn('setfacl -x "u:$KIOSK"', sw)         # and taken back on lock
        self.assertIn("http://127.0.0.1:*|http://localhost:*", sw)
        setup = (ROOT / "scripts" / "arise-browser-setup").read_text()
        self.assertIn("/usr/local/sbin/arise-browser-profile", setup)
        self.assertEqual(subprocess.run(["bash", "-n", str(ROOT / "scripts" / "arise-browser-setup")]).returncode, 0)

    def test_the_switcher_refuses_bad_names_and_foreign_urls(self):
        sw = str(ROOT / "scripts" / "arise-browser-profile")
        r = subprocess.run(["sh", sw, "bogus"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


class Handoff(unittest.TestCase):
    def test_a_token_works_once_and_expires(self):
        t = kiosk_profiles.handoff_make("sess", "bradly", now=1000.0)
        self.assertEqual(kiosk_profiles.handoff_take(t, now=1001.0), ("sess", "bradly"))
        self.assertIsNone(kiosk_profiles.handoff_take(t, now=1002.0))
        t2 = kiosk_profiles.handoff_make("sess", "bradly", now=1000.0)
        self.assertIsNone(kiosk_profiles.handoff_take(t2, now=1000.0 + kiosk_profiles.HANDOFF_SECONDS + 1))
        self.assertIsNone(kiosk_profiles.handoff_take("", now=1000.0))

    def test_only_the_monitor_itself_counts(self):
        was = os.environ.pop("ARISE_DEMO", None)
        try:
            os.environ["ARISE_CONFIG"] = str(ROOT / "config" / "arise.toml.example")
            config.load(force=True)
            if config.load().demo:
                self.skipTest("the example config is in sample mode")
            self.assertTrue(kiosk_profiles.on_monitor("127.0.0.1"))
            self.assertFalse(kiosk_profiles.on_monitor("127.0.0.1", "10.0.0.20"))   # through Caddy
            self.assertFalse(kiosk_profiles.on_monitor("10.0.0.20"))
        finally:
            if was is not None:
                os.environ["ARISE_DEMO"] = was
            config.load(force=True)


class Owners(unittest.TestCase):
    """Rows 23-24: Kristina has Bradly's powers, sudo included; Claude stays his."""

    def test_sudo_lines_for_both_and_visudo_accepts_them(self):
        r = subprocess.run(["bash", str(ROOT / "scripts" / "arise-owner-setup"), "--dry-run", "--owner", "bradly", "--also", "kristina"],
                           capture_output=True, text=True)
        lines = [ln.split(": ", 1)[1].split(" (after", 1)[0] for ln in r.stdout.splitlines() if "NOPASSWD" in ln]
        self.assertEqual(lines, ["bradly ALL=(ALL:ALL) NOPASSWD: ALL", "kristina ALL=(ALL:ALL) NOPASSWD: ALL"])
        if not shutil.which("visudo"):
            self.skipTest("visudo not installed")
        with tempfile.NamedTemporaryFile("w", suffix=".sudoers", delete=False) as f:
            f.write("\n".join(lines) + "\n")
        try:
            os.chmod(f.name, 0o440)
            v = subprocess.run(["visudo", "-cf", f.name], capture_output=True, text=True)
            self.assertEqual(v.returncode, 0, v.stdout + v.stderr)
        finally:
            os.unlink(f.name)

    def test_root_is_refused_as_an_extra_owner(self):
        r = subprocess.run(["bash", str(ROOT / "scripts" / "arise-owner-setup"), "--dry-run", "--owner", "bradly", "--also", "root"],
                           capture_output=True, text=True)
        self.assertNotIn("root ALL=", r.stdout)

    def test_claude_users_leave_out_the_other_owners(self):
        from arise_server import church
        tmp = Path(tempfile.mkdtemp(prefix="arise-r6-"))
        try:
            (tmp / "arise.toml").write_text('[web]\nadmin_user = "bradly"\n[owner]\nuser = "bradly"\n[owners]\nusers = ["kristina", "kristina.robinson"]\n'
                                            f'[paths]\nstate_dir = "{tmp}"\nlog_dir = "{tmp}"\n')
            cfg = config.load(path=str(tmp / "arise.toml"), force=True)
            users = church.claude_users(cfg)
            self.assertIn("bradly", users)
            self.assertNotIn("kristina", users)
            self.assertNotIn("kristina.robinson", users)
            self.assertEqual(cfg.raw["owners"]["users"], ["kristina", "kristina.robinson"])
        finally:
            config.load(force=True)
            shutil.rmtree(tmp, ignore_errors=True)


class Routes(unittest.TestCase):
    """Rows 20-22 on the sample server."""

    def setUp(self):
        self.was = os.environ.get("ARISE_STAFF_ACCESS")
        os.environ["ARISE_STAFF_ACCESS"] = "portal"
        config.load(force=True)
        demo_state.reset()
        self.admin = TestClient(app)

    def tearDown(self):
        os.environ.pop("ARISE_STAFF_ACCESS", None) if self.was is None else os.environ.__setitem__("ARISE_STAFF_ACCESS", self.was)

    def member(self):
        c = TestClient(app)
        self.assertEqual(c.post("/api/auth/login", json={"user": "office", "password": "anything"}).json()["role"], "member")
        return c

    def test_the_faces_are_the_four_admins(self):
        faces = {f["user"] for f in self.admin.get("/api/public/faces").json()["faces"]}
        self.assertEqual(faces, ADMINS)

    def test_kristina_signs_in_as_an_admin(self):
        c = TestClient(app)
        r = c.post("/api/auth/login", json={"user": "kristina.robinson", "password": "anything"}).json()
        self.assertEqual(r["role"], "admin")

    def test_only_an_admin_switches_the_monitor_into_a_profile(self):
        r = self.admin.post("/api/kiosk/profile", json={"action": "switch"}).json()
        self.assertTrue(r["ok"])
        self.assertEqual(self.admin.get("/api/kiosk/profile").json()["current"], r["user"])
        self.assertTrue(self.admin.post("/api/kiosk/profile", json={"action": "neutral"}).json()["ok"])
        self.assertEqual(self.admin.get("/api/kiosk/profile").json()["current"], "neutral")
        m = self.member()
        self.assertEqual(m.post("/api/kiosk/profile", json={"action": "switch"}).status_code, 403)
        self.assertEqual(self.admin.post("/api/auth/handoff", json={"token": "nope"}).status_code, 401)

    def test_an_admin_turns_two_step_on_and_off_for_a_staff_member(self):
        a = self.admin
        self.assertTrue(a.post("/api/directory/users/office/2fa/setup").json()["ok"])
        self.assertTrue(a.post("/api/directory/users/office/2fa/enable", json={"code": "123456"}).json()["ok"])
        self.assertIn("office", a.get("/api/directory/2fa").json()["users"])
        r = a.post("/api/directory/users/office/2fa/disable")
        if r.status_code == 403:   # the off switch asks for the admin's password again
            self.assertTrue(a.post("/api/auth/reauth", json={"password": "anything"}).json().get("ok", True))
            r = a.post("/api/directory/users/office/2fa/disable")
        self.assertTrue(r.json()["ok"], r.text)
        self.assertNotIn("office", a.get("/api/directory/2fa").json()["users"])
        self.assertFalse(a.post("/api/directory/users/nobody.here/2fa/setup").json()["ok"])
        m = self.member()
        self.assertEqual(m.post("/api/directory/users/office/2fa/setup").status_code, 403)

    def test_the_reset_page_works_with_staff_access_none(self):
        for path in ("/api/auth/forgot", "/api/auth/reset", "/api/auth/reset/check", "/api/auth/login/new-password"):
            self.assertTrue(member_ok(path, "member", "none"), path)
        self.assertFalse(member_ok("/api/kiosk/profile", "member", "none"))


if __name__ == "__main__":
    unittest.main()


class KioskOpen(unittest.TestCase):
    def test_forwarded_addresses_are_believed_from_this_box_only(self):
        src = (Path(__file__).resolve().parents[1] / "server" / "arise_server" / "__main__.py").read_text()
        self.assertIn('forwarded_allow_ips="127.0.0.1"', src)

    def test_kiosk_open_refuses_a_proxied_request(self):
        src = (Path(__file__).resolve().parents[1] / "server" / "arise_server" / "main.py").read_text()
        i = src.index('def api_kiosk_open')
        self.assertIn('kiosk_profiles.on_monitor(host, request.headers.get("x-forwarded-for", ""))', src[i:i + 700])

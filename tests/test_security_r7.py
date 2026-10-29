"""Round 7 security review: each fix pinned.

Sessions that end when they should, a limit on wrong passwords, the cookie only acting from
this dashboard's own pages (the root Terminal above all), files never served as pages,
links that never re-share what was shared with you, nothing written through a planted link,
escrowed Mac secrets that cannot be overwritten away, two-step codes used once, settings that
never carry a credential, and the display units hardened.
"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("ARISE_DEMO", "1")
os.environ.setdefault("ARISE_CONFIG", str(ROOT / "config" / "arise.toml.example"))

from fastapi.testclient import TestClient  # noqa: E402

from arise_server import auth, config, files, links, macs, twofa  # noqa: E402
from arise_server.main import app  # noqa: E402


class Paths(unittest.TestCase):
    def test_member_prefixes_match_only_at_a_slash(self):
        self.assertTrue(auth.member_ok("/api/me", "member"))
        self.assertTrue(auth.member_ok("/api/me/profile", "member"))
        self.assertFalse(auth.member_ok("/api/media", "member"))           # a later route is never a member's by accident
        self.assertFalse(auth.member_ok("/api/peoplex", "member"))
        self.assertTrue(auth.member_ok("/api/files/list", "member"))
        self.assertFalse(auth.member_ok("/api/me", "member", "none"))       # staff_access none: sign-in routes only
        self.assertTrue(auth.member_ok("/api/auth/me", "member", "none"))


class Origin(unittest.TestCase):
    def test_origin_ok(self):
        self.assertTrue(auth.origin_ok(None, "arise-server.ad.arisecenla.com"))        # not a browser
        self.assertTrue(auth.origin_ok("https://arise-server.ad.arisecenla.com", "arise-server.ad.arisecenla.com"))
        self.assertTrue(auth.origin_ok("http://ARISE-SERVER:4147", "arise-server:4147"))
        self.assertFalse(auth.origin_ok("https://vault.ad.arisecenla.com", "arise-server.ad.arisecenla.com"))   # a sibling site
        self.assertFalse(auth.origin_ok("null", "arise-server"))
        self.assertFalse(auth.origin_ok("https://evil.example", None))

    def test_a_change_from_another_site_with_the_cookie_is_refused(self):
        c = TestClient(app)
        c.cookies.set(auth.COOKIE, "anything")
        r = c.post("/api/files/mkdir", json={"root": "data", "path": "/", "name": "x"}, headers={"Origin": "https://vault.ad.arisecenla.com"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("another site", r.text)
        r = c.post("/api/files/mkdir", json={"root": "data", "path": "/", "name": "x"}, headers={"Origin": "http://testserver"})
        self.assertNotEqual(r.status_code, 403)

    def test_the_terminal_wants_the_dashboards_own_origin(self):
        c = TestClient(app)
        with self.assertRaises(Exception):
            with c.websocket_connect("/api/terminal") as ws:      # no Origin: closed
                ws.receive_text()
        with self.assertRaises(Exception):
            with c.websocket_connect("/api/terminal", headers={"Origin": "https://cloud.ad.arisecenla.com"}) as ws:
                ws.receive_text()
        with c.websocket_connect("/api/terminal", headers={"Origin": "http://testserver"}) as ws:
            self.assertIn("arise-server", ws.receive_text())

    def test_every_answer_carries_the_safety_headers(self):
        r = TestClient(app).get("/api/health")
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(r.headers.get("x-frame-options"), "SAMEORIGIN")


class Sessions(unittest.TestCase):
    def test_a_token_from_before_the_mark_is_dead(self):
        self.assertTrue(auth.session_current({"t": 100}, 0))
        self.assertTrue(auth.session_current({"t": 200}, 150))
        self.assertFalse(auth.session_current({"t": 100}, 150))
        self.assertFalse(auth.session_current({}, 150))                 # a token from before "t" existed

    def test_revoke_writes_the_mark(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d, \
                mock.patch("arise_server.auth.load", return_value=SimpleNamespace(demo=False, state_dir=Path(d))):
            auth.revoke_sessions("Jane.Doe", now=1234.0)
            self.assertEqual(auth.valid_after("jane.doe"), 1234.0)
            self.assertEqual(oct(os.stat(Path(d) / "sessions.json").st_mode & 0o777), "0o600")

    def test_the_role_and_enabled_flag_are_read_back(self):
        auth._live.clear()
        with mock.patch("arise_server.directory.available", return_value=True), \
                mock.patch("arise_server.directory._user_detail", return_value={"enabled": False}), \
                mock.patch("arise_server.directory.is_admin", return_value=True):
            self.assertEqual(auth.live_state("jane.doe", now=1000), (False, True))
        with mock.patch("arise_server.directory.available", return_value=True), \
                mock.patch("arise_server.directory._user_detail", side_effect=AssertionError("cached")):
            self.assertEqual(auth.live_state("jane.doe", now=1050), (False, True))     # two minutes' cache
        with mock.patch("arise_server.directory.available", return_value=True), \
                mock.patch("arise_server.directory._user_detail", return_value={"error": "samba down"}):
            self.assertIsNone(auth.live_state("jane.doe", now=2000))                  # cannot say: the token stands
        auth._live.clear()

    def test_ten_wrong_passwords_wait(self):
        now = 10_000.0
        self.assertFalse(auth.limited([now - 1] * 9, now))
        self.assertTrue(auth.limited([now - 1] * 10, now))
        self.assertFalse(auth.limited([now - 1000] * 30, now))           # older than fifteen minutes
        keys = ["u:test.limit", "ip:203.0.113.9"]
        auth.clear_failures(keys)
        for _ in range(10):
            auth.note_failure(keys, now)
        self.assertTrue(auth.too_many(["u:test.limit"], now))
        auth.clear_failures(keys)
        self.assertFalse(auth.too_many(keys, now))

    def test_password_changes_and_disabling_end_sessions(self):
        src = (ROOT / "server" / "arise_server" / "directory.py").read_text()
        for fn in ("def set_password", "def enable_user", "def delete_user"):
            body = src[src.index(fn):src.index("\ndef ", src.index(fn) + 5)]
            self.assertIn("revoke_sessions(name)", body, fn)


class Files(unittest.TestCase):
    def test_nothing_is_served_as_a_page(self):
        for name in ("a.html", "a.htm", "a.xhtml", "a.xml", "a.js", "a.txt", "a"):
            t, h = files.view_headers(name)
            self.assertTrue(t.startswith("text/plain") or t == "application/octet-stream", (name, t))
            self.assertIn("sandbox", h["Content-Security-Policy"])
            self.assertEqual(h["X-Content-Type-Options"], "nosniff")
        t, h = files.view_headers("logo.svg")
        self.assertEqual(t, "image/svg+xml"); self.assertIn("sandbox", h["Content-Security-Policy"])   # opened alone: no script
        t, h = files.view_headers("plan.pdf")
        self.assertEqual(t, "application/pdf"); self.assertNotIn("Content-Security-Policy", h)        # Chrome's viewer needs it unsandboxed
        self.assertEqual(files.view_headers("p.png")[0], "image/png")

    def test_create_new_never_writes_through_a_link(self):
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "outside.txt")
            link = os.path.join(d, "planted")
            os.symlink(target, link)                                     # dangling: exists() is False
            with self.assertRaises(OSError):
                os.close(files.create_new(link))
            self.assertFalse(os.path.exists(target))
            fd = files.create_new(os.path.join(d, "new.txt")); os.close(fd)
            with self.assertRaises(FileExistsError):
                files.create_new(os.path.join(d, "new.txt"))

    def test_the_editor_and_uploads_use_it(self):
        src = (ROOT / "server" / "arise_server" / "finder.py").read_text()
        wt = src[src.index("def write_text"):src.index("def render_markdown")]
        self.assertIn("files.create_new(tmp", wt)
        self.assertIn("os.path.lexists(tmp)", wt)
        su = (ROOT / "server" / "arise_server" / "files.py").read_text()
        su = su[su.index("def save_upload"):su.index("def make_folder")]
        self.assertIn("create_new(dest)", su)


class Links(unittest.TestCase):
    def test_what_was_shared_with_you_and_the_pastors_folder_get_no_link(self):
        self.assertTrue(links.link_refused("shared:abc123"))
        self.assertTrue(links.link_refused("pastors"))
        self.assertEqual(links.link_refused("home"), "")
        self.assertEqual(links.link_refused("share:media"), "")

    def test_a_folder_zip_leaves_out_what_points_outside_it(self):
        with tempfile.TemporaryDirectory() as d:
            folder = os.path.join(d, "folder"); os.makedirs(os.path.join(folder, "sub"))
            Path(folder, "a.txt").write_text("in")
            Path(folder, "sub", "b.txt").write_text("in too")
            Path(d, "secret.txt").write_text("outside")
            os.symlink(os.path.join(d, "secret.txt"), os.path.join(folder, "link.txt"))
            os.symlink(d, os.path.join(folder, "uplink"))
            names = sorted(arc for _, arc, _ in links.zip_members(folder))
            self.assertEqual(names, ["a.txt", os.path.join("sub", "b.txt")])


class MacSecrets(unittest.TestCase):
    def test_a_replaced_secret_is_kept(self):
        cur = {"filevault": "REAL-KEY", "filevault_at": "2026-10-01T00:00:00"}
        out = macs.keep_previous(cur, {"filevault": "WRONG", "filevault_at": "2026-10-29T00:00:00"})
        self.assertEqual(out["filevault"], "WRONG")
        self.assertEqual(out["filevault_previous"][0]["value"], "REAL-KEY")
        same = macs.keep_previous(out, {"filevault": "WRONG"})
        self.assertEqual(len(same["filevault_previous"]), 1)              # the same value again is not history
        many = cur
        for i in range(9):
            many = macs.keep_previous(many, {"filevault": f"K{i}"})
        self.assertEqual(len(many["filevault_previous"]), 5)


class TwoStep(unittest.TestCase):
    def test_a_code_works_once(self):
        try:
            import pyotp
        except ImportError:
            self.skipTest("pyotp not installed")
        secret = pyotp.random_base32()
        at = time.time()
        code = twofa.code_at(secret, at)
        twofa._last_step.pop("replay.test", None)
        self.assertTrue(twofa.fresh_code("replay.test", secret, code, at))
        self.assertFalse(twofa.fresh_code("replay.test", secret, code, at + 5))     # the same code again
        self.assertTrue(twofa.fresh_code("replay.test", secret, twofa.code_at(secret, at + 30), at + 30))
        self.assertFalse(twofa.fresh_code("replay.test", secret, "000000x", at))
        twofa._last_step.pop("replay.test", None)


class Settings(unittest.TestCase):
    def test_no_credential_reaches_a_page(self):
        for k in ("admin_password_hash", "webhook_url", "discord_webhook", "api_key", "resend_key", "private_pem", "client_secret", "dsm_credentials"):
            self.assertTrue(config.secret_key(k), k)
        for k in ("port", "realm", "homes_path", "public_url", "hostname"):
            self.assertFalse(config.secret_key(k), k)


class Units(unittest.TestCase):
    def test_the_display_units_are_hardened(self):
        for u in ("arise-kiosk.service", "arise-wayvnc.service"):
            s = (ROOT / "config" / "systemd" / u).read_text()
            for k in ("NoNewPrivileges=yes", "RestrictSUIDSGID=yes", "ProtectKernelModules=yes"):
                self.assertIn(k, s, u)
            self.assertNotIn("RestrictNamespaces", s)   # Firefox's sandbox needs namespaces


if __name__ == "__main__":
    unittest.main()

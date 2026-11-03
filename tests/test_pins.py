"""Sign-in PINs (round 7, rows 160 to 162).

The weak-PIN rules, only a hash on disk (0600), the per-account PIN counter beside the
per-device throttle (never a lockout of the password), a PIN never answering the
password-again prompt, and a staff PIN reaching the phone checklist only, on its own phone.
The PINs here are made up for the tests: nobody's real PIN.
"""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("ARISE_DEMO", "1")
os.environ.setdefault("ARISE_CONFIG", str(ROOT / "config" / "arise.toml.example"))

from fastapi.testclient import TestClient  # noqa: E402

from arise_server import auth, config, demo_state, pins  # noqa: E402
from arise_server.main import app  # noqa: E402

GOOD = "583920"     # made up for the tests
GOOD2 = "730418"


class Tmp(unittest.TestCase):
    def setUp(self):
        config.load(force=True)
        demo_state.reset()
        self.tmp = Path(tempfile.mkdtemp())
        self.p = mock.patch.object(pins, "_path", return_value=self.tmp / "pins.json")
        self.p.start()
        self.addCleanup(self.p.stop)


class Rules(unittest.TestCase):
    def test_weak_pins_are_refused(self):
        for bad in ("1111", "5555", "999999", "1212", "121212", "123123", "1234", "4321", "0123", "6789", "98765",
                    "2580", "0852", "1004", "12a4", "123", "123456789", ""):
            self.assertTrue(pins.weak_reason(bad), bad)
        for fine in (GOOD, GOOD2, "8016", "40729"):
            self.assertEqual(pins.weak_reason(fine), "", fine)

    def test_birthday_and_mobile_are_refused(self):
        self.assertTrue(pins.weak_reason("0314", birthday="03-14"))
        self.assertTrue(pins.weak_reason("1403", birthday="03-14"))
        self.assertTrue(pins.weak_reason("0199", mobile="318-555-0199"))
        self.assertEqual(pins.weak_reason("0314"), "")                     # no birthday on file: fine


class Store(Tmp):
    def test_only_a_hash_on_disk_and_0600(self):
        self.assertTrue(pins.set_pin("jane.doe", GOOD, "full")["ok"])
        raw = (self.tmp / "pins.json").read_text()
        self.assertNotIn(GOOD, raw)
        self.assertIn("$2", json.loads(raw)["jane.doe"]["hash"])          # bcrypt
        self.assertEqual(stat.S_IMODE(os.stat(self.tmp / "pins.json").st_mode), 0o600)
        st = pins.status("jane.doe")
        self.assertTrue(st["set"]); self.assertNotIn("hash", json.dumps(st))
        self.assertNotIn("hash", json.dumps(pins.everyone()))
        self.assertTrue(pins.verify("jane.doe", GOOD)["ok"])
        self.assertFalse(pins.verify("jane.doe", GOOD2)["ok"])
        self.assertFalse(pins.set_pin("jane.doe", "1234", "full")["ok"])  # a weak one is refused, the old one stays
        self.assertTrue(pins.verify("jane.doe", GOOD)["ok"])

    def test_ten_wrong_pins_switch_it_off_and_the_password_brings_it_back(self):
        pins.set_pin("jane.doe", GOOD, "full")
        for _ in range(9):
            self.assertFalse(pins.verify("jane.doe", GOOD2)["ok"])
        self.assertTrue(pins.verify("jane.doe", GOOD)["ok"])               # the right one before ten: the count starts again
        with mock.patch.object(pins, "_tell") as told:
            for i in range(10):
                r = pins.verify("jane.doe", GOOD2, device_mark=f"device{i}")   # from ten different devices: one account's count
            self.assertTrue(r.get("off")); told.assert_called_once_with("jane.doe")
        self.assertFalse(pins.verify("jane.doe", GOOD)["ok"])              # off: even the right PIN waits
        pins.full_signin("jane.doe")                                        # a password sign-in
        self.assertTrue(pins.verify("jane.doe", GOOD)["ok"])

    def test_a_password_change_switches_the_pin_off(self):
        pins.set_pin("jane.doe", GOOD, "full")
        auth.revoke_sessions("jane.doe")
        self.assertTrue(pins.status("jane.doe")["off"])
        pins.full_signin("jane.doe")
        self.assertFalse(pins.status("jane.doe")["off"])

    def test_a_staff_pin_works_on_its_own_phone_only(self):
        r = pins.set_pin("media-mac", GOOD, "checklist")
        mark = r["device_mark"]
        self.assertTrue(mark)
        self.assertNotIn(mark, (self.tmp / "pins.json").read_text())       # the mark's hash only
        self.assertTrue(pins.verify("media-mac", GOOD, mark)["ok"])
        self.assertFalse(pins.verify("media-mac", GOOD, "another-phone")["ok"])
        self.assertFalse(pins.verify("media-mac", GOOD)["ok"])

    def test_admins_remove_but_never_see(self):
        pins.set_pin("jane.doe", GOOD, "full")
        self.assertTrue(pins.remove("jane.doe", by="bradly")["removed"])
        self.assertFalse(pins.status("jane.doe")["set"])


class Routes(Tmp):
    def _signed_in(self, user):
        c = TestClient(app)
        r = c.post("/api/auth/login", json={"user": user, "password": "sample"})
        self.assertEqual(r.status_code, 200, r.text)
        return c

    def test_set_with_the_sign_in_then_sign_in_with_the_pin(self):
        c = self._signed_in("bradly")
        r = c.post("/api/auth/pin/set", json={"pin": GOOD})                  # just signed in with the password: no second one
        self.assertTrue(r.json()["ok"], r.text)
        self.assertNotIn(GOOD, r.text)
        self.assertEqual(c.post("/api/auth/pin/set", json={"pin": "1111"}).json()["ok"], False)
        fresh = TestClient(app)
        r = fresh.post("/api/auth/pin", json={"user": "bradly", "pin": GOOD})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["pin"], "full")
        self.assertNotIn(GOOD, r.text)
        st = fresh.get("/api/auth/pin/status").json()
        self.assertTrue(st["this_session_by_pin"]); self.assertTrue(st["password_needed"])
        # a PIN session sets a new PIN only with the password, and the answer never echoes either
        r = fresh.post("/api/auth/pin/set", json={"pin": GOOD2})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(TestClient(app).post("/api/auth/pin", json={"user": "bradly", "pin": GOOD2}).status_code, 401)

    def test_a_pin_token_never_counts_as_the_password_again(self):
        tok, who = auth.pin_token("bradly", "full")
        d = auth._serializer().loads(tok)
        self.assertNotIn("ra", d); self.assertNotIn("fp", d)
        self.assertFalse(auth.recent_auth_ok(d, d["t"]))
        src = (ROOT / "server" / "arise_server" / "main.py").read_text()
        body = src[src.index("def api_reauth"):src.index("\n@app.", src.index("def api_reauth"))]
        self.assertIn("check_password_for", body); self.assertNotIn("pins.", body)   # the password, never a PIN

    def test_the_pin_route_throttles_by_device_never_by_account(self):
        src = (ROOT / "server" / "arise_server" / "main.py").read_text()
        body = src[src.index("def api_auth_pin("):src.index("\n@app.", src.index("def api_auth_pin("))]
        self.assertIn('keys = [f"ip:{_ip(request)}"]', body)
        self.assertNotIn('"u:" +', body)

    def test_a_staff_pin_session_reaches_the_checklist_only(self):
        with mock.patch.dict(os.environ, {"ARISE_STAFF_ACCESS": "portal"}):
            c = self._signed_in("media-mac")
            r = c.post("/api/auth/pin/set", json={"pin": GOOD})
            self.assertTrue(r.json()["ok"], r.text); self.assertEqual(r.json()["scope"], "checklist")
            mark = c.cookies.get(pins.DEVICE_COOKIE)
            self.assertTrue(mark)
            phone = TestClient(app); phone.cookies.set(pins.DEVICE_COOKIE, mark)
            self.assertEqual(phone.post("/api/auth/pin", json={"user": "media-mac", "pin": GOOD}).status_code, 200)
            self.assertEqual(phone.get("/api/checklist/mine").status_code, 200)
            self.assertEqual(phone.get("/api/me/profile").status_code, 403)    # the portal, but not by PIN
            other = TestClient(app)
            self.assertEqual(other.post("/api/auth/pin", json={"user": "media-mac", "pin": GOOD}).status_code, 401)

    def test_the_leaders_reset_wants_the_leaders_password(self):
        c = self._signed_in("bradly")
        r = c.post("/api/checklist/reset", json={"user": "media-mac"})
        self.assertEqual(r.status_code, 401)
        self.assertIn("own password", r.text)

    def test_admins_list_and_remove(self):
        c = self._signed_in("bradly")
        pins.set_pin("media-mac", GOOD, "checklist")
        self.assertIn("media-mac", c.get("/api/directory/pins").json()["pins"])
        self.assertTrue(c.delete("/api/directory/users/media-mac/pin").json()["removed"])
        self.assertNotIn("media-mac", c.get("/api/directory/pins").json()["pins"])


if __name__ == "__main__":
    unittest.main()


class TerminalWantsThePassword(unittest.TestCase):
    def test_a_pin_session_needs_the_password_again_for_the_root_shell(self):
        src = (Path(__file__).resolve().parents[1] / "server" / "arise_server" / "main.py").read_text()
        body = src[src.index("async def api_terminal"):src.index("await ws.accept()", src.index("async def api_terminal"))]
        self.assertIn('who_t.get("pin")', body)
        self.assertIn("recent_auth_ok", body)
        self.assertIn("4409", body)

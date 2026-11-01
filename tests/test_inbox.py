"""A person's own church inbox on the dashboard (Bradly, Nov 1, ANSWERS H11)."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("ARISE_DEMO", "1")
os.environ.setdefault("ARISE_CONFIG", str(ROOT / "config" / "arise.toml.example"))

from arise_server import inbox, mailfwd  # noqa: E402


class Pure(unittest.TestCase):
    def test_address_and_pick(self):
        self.assertEqual(inbox.address_for("Kristina.Robinson", "ArisecenLA.com"), "kristina.robinson@arisecenla.com")
        boxes = [{"id": "a", "email_address": "bradly.dyer@arisecenla.com"}, {"id": "b", "email_address": "Kristina.Robinson@arisecenla.com"}]
        self.assertEqual(inbox.pick(boxes, "kristina.robinson@arisecenla.com")["id"], "b")
        self.assertIsNone(inbox.pick(boxes, "someone@arisecenla.com"))

    def test_ids_cannot_add_path_segments(self):
        p = inbox.path("thread", inbox="ib/../x", thread="t?folders=all")
        self.assertNotIn("/../", p)
        self.assertNotIn("?folders=all", p)
        self.assertTrue(p.startswith("/inboxes/ib%2F..%2Fx/threads/"))

    def test_kristina_is_on_the_list(self):
        self.assertIn("kristina.robinson", inbox.users())
        self.assertTrue(inbox.has_inbox("Kristina.Robinson"))
        self.assertFalse(inbox.has_inbox("someone.else"))


class OnlyYourOwn(unittest.TestCase):
    """The inbox is always worked out from the signed-in account, never from the browser."""

    def test_someone_without_an_inbox_gets_nothing(self):
        with mock.patch.object(inbox, "load") as L:
            L.return_value.demo = False
            L.return_value.raw = {"inbox": {"users": ["kristina.robinson"]}}
            calls = []
            with mock.patch.object(inbox, "_call", side_effect=lambda *a, **k: calls.append(a) or {"ok": True, "data": {"data": []}}):
                r = inbox.overview("someone.else")
            self.assertFalse(r["ok"])
            self.assertEqual(calls, [])                       # Resend is never even asked

    def test_her_inbox_by_her_address_only(self):
        boxes = {"data": [{"id": "ib_bradly", "email_address": "bradly.dyer@arisecenla.com"},
                          {"id": "ib_kr", "email_address": "kristina.robinson@arisecenla.com"}]}
        seen = []

        def call(method, p, body=None):
            seen.append(p)
            if p.startswith("/inboxes?"):
                return {"ok": True, "data": boxes}
            return {"ok": True, "data": {"data": [{"id": "t1", "subject": "hi"}]}}
        with mock.patch.object(inbox, "load") as L, mock.patch.object(inbox, "_call", side_effect=call), \
                mock.patch.object(inbox, "_domain", return_value="arisecenla.com"):
            L.return_value.demo = False
            L.return_value.raw = {"inbox": {"users": ["kristina.robinson"]}}
            r = inbox.overview("kristina.robinson")
        self.assertTrue(r["ok"])
        self.assertTrue(any(p.startswith("/inboxes/ib_kr/threads") for p in seen))
        self.assertFalse(any("ib_bradly" in p for p in seen))

    def test_a_sending_only_key_says_so(self):
        with mock.patch.object(inbox, "load") as L, mock.patch.object(inbox, "_call", return_value={"ok": False, "err": "Resend 401: restricted_api_key"}), \
                mock.patch.object(inbox, "_domain", return_value="arisecenla.com"):
            L.return_value.demo = False
            L.return_value.raw = {"inbox": {"users": ["kristina.robinson"]}}
            r = inbox.overview("kristina.robinson")
        self.assertIn("full access", r["err"])


class Checks(unittest.TestCase):
    def test_send_checks_its_input(self):
        self.assertFalse(inbox.send("kristina.robinson", "not-an-address", "Hi", "x")["ok"])
        self.assertFalse(inbox.send("kristina.robinson", "a@b.org", "two\nlines", "x")["ok"])
        self.assertFalse(inbox.send("kristina.robinson", "a@b.org", "Hi", "  ")["ok"])
        self.assertTrue(inbox.send("kristina.robinson", "a@b.org, c@d.org", "Hi", "hello")["ok"])     # sample mode

    def test_reply_needs_words_and_real_ids(self):
        self.assertFalse(inbox.reply("kristina.robinson", "t-1", "e-1", "")["ok"])
        self.assertFalse(inbox.reply("kristina.robinson", "../x", "e-1", "hi")["ok"])
        self.assertTrue(inbox.reply("kristina.robinson", "t-1", "e-1", "hi")["ok"])

    def test_sample_mail_for_the_preview(self):
        o = inbox.overview("kristina.robinson")
        self.assertTrue(o["demo"])
        self.assertTrue(o["threads"])
        self.assertTrue(inbox.thread("kristina.robinson", o["threads"][0]["id"])["emails"])


class NotForwardedTwice(unittest.TestCase):
    def test_inbox_people_are_skipped_by_forwarding(self):
        als = {"kristina.robinson": {"to": "k@example.com", "enabled": True}, "bryant.sanders": {"to": "b@example.com", "enabled": True}}
        r = mailfwd.route(["kristina.robinson@arisecenla.com", "bryant.sanders@arisecenla.com"], als, "arisecenla.com", ["kristina.robinson"])
        self.assertEqual(r[0]["alias"], "kristina.robinson")
        self.assertNotIn("to", r[0])
        self.assertEqual(r[1], {"alias": "bryant.sanders", "to": "b@example.com"})


class Page(unittest.TestCase):
    def test_email_html_only_in_a_sandboxed_frame(self):
        js = (ROOT / "web" / "app.js").read_text()
        start = js.index("V.inbox = async")
        block = js[start:js.index("V.mail = async", start)]
        self.assertIn('sandbox=""', block)
        self.assertIn("default-src", block)                  # a CSP inside the frame too
        self.assertNotIn("innerHTML", block)
        self.assertNotIn("allow-scripts", block)


if __name__ == "__main__":
    unittest.main()

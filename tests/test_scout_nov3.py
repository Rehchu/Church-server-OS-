"""Scout fixes, Nov 3: I-001 (no silent sample data), I-014 (per-job backup staleness), I-017 (a rebuild that works on a dead box)."""
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("ARISE_CONFIG", str(ROOT / "config" / "arise.toml.example"))

from arise_server import backups, upkeep  # noqa: E402

NOW = datetime(2026, 11, 3, 12, 0)
T = lambda **kw: (NOW - timedelta(**kw)).isoformat(timespec="seconds")


class ServerOutOfReachIsSaid(unittest.TestCase):
    """I-001: a restart or a Tailscale blip never turns the real dashboard into the sample church."""
    def test_api_falls_back_only_in_the_preview(self):
        js = (ROOT / "web" / "app.js").read_text()
        api = js[js.index("async function api("):js.index("function netDown(")]
        for line in api.splitlines():
            if "setDemoOnly()" in line and "demoLookup" in line:
                self.assertIn("window.ARISE_FORCE_DEMO", line, line)
        self.assertIn("netDown()", api)
        self.assertIn("netUp()", api)

    def test_the_bar_and_the_retry(self):
        js = (ROOT / "web" / "app.js").read_text()
        down = js[js.index("function netDown("):js.index("function setDemoOnly(")]
        self.assertIn("Server out of reach", down)
        self.assertIn("/api/health", down)
        self.assertIn("Math.min(NET.wait * 2, 30000)", down)
        self.assertIn(".netbar", (ROOT / "web" / "styles.css").read_text())

    def test_the_checklist_page_does_not_flip_to_sample(self):
        html = (ROOT / "web" / "checklist.html").read_text()
        self.assertNotIn("MOCK = true", html)
        self.assertIn("let MOCK = !!window.ARISE_FORCE_DEMO", html)


class EveryJobIsWatched(unittest.TestCase):
    """I-014: one good job no longer hides the ones a slow night never reached."""
    IDS = ["automator", "songs", "homes", "shares"]

    def test_stale_jobs(self):
        rows = [{"job": "automator", "ok": True, "started": T(hours=9)},
                {"job": "songs", "ok": True, "started": T(hours=9)},
                {"job": "homes", "ok": True, "started": T(hours=33)},
                {"job": "homes", "ok": False, "started": T(hours=9)}]
        self.assertIsNone(backups.missed_night(rows, NOW))      # the night ran ...
        s = backups.stale_jobs(rows, self.IDS, NOW)             # ... but not all of it
        self.assertEqual([x["job"] for x in s], ["homes", "shares"])
        self.assertEqual(s[0]["last_ok"], T(hours=33)[:16])
        self.assertIsNone(s[1]["last_ok"])
        self.assertEqual(backups.stale_jobs([], self.IDS, NOW), [])   # a new box
        self.assertEqual(backups.stale_jobs([{"job": j, "ok": True, "started": T(hours=2)} for j in self.IDS], self.IDS, NOW), [])
        # a skipped row is not a backup
        self.assertEqual(len(backups.stale_jobs([{"job": "songs", "ok": True, "skipped": True, "started": T(hours=2)}], ["songs"], NOW)), 1)

    def test_it_reaches_needs_you(self):
        rows = [{"job": "automator", "ok": True, "started": T(hours=9)}]
        items = upkeep.attention(NOW, hist=rows, macs=[], health_v=[], job_ids=["automator", "homes"])
        st = [i for i in items if i["key"].startswith("backup-stale:")]
        self.assertEqual(len(st), 1)
        self.assertEqual(st[0]["level"], "bad")
        self.assertIn("homes (never)", st[0]["text"])
        self.assertEqual(st[0]["fix"], "sudo arisectl backup run homes")
        # a whole missed night is the one alert, not two
        old = [{"job": "automator", "ok": True, "started": T(hours=40)}]
        items = upkeep.attention(NOW, hist=old, macs=[], health_v=[], job_ids=["automator", "homes"])
        self.assertFalse(any(i["key"].startswith("backup-stale:") for i in items))
        self.assertTrue(any(i["key"].startswith("backup-missed:") for i in items))

    def test_optional_jobs_are_not_expected(self):
        from unittest import mock
        with mock.patch.object(backups, "jobs", return_value={"jobs": [{"id": "homes"}, {"id": "leavers", "optional": True}]}):
            self.assertEqual(backups.nightly_job_ids(), ["homes"])

    def test_the_unit_outlasts_a_long_night(self):
        unit = (ROOT / "config" / "systemd" / "arise-backup.service").read_text()
        self.assertIn("TimeoutStartSec=20h", unit)
        self.assertNotIn("TimeoutStartSec=6h", unit)


class RebuildWorksOnADeadBox(unittest.TestCase):
    """I-017: the cards Kristina follows give the install-disc entry point, not arisectl."""
    def test_closet_card(self):
        html = upkeep.closet_card(False, call=[], facts={"host": "arise-server", "fqdn": "arise-server.ad.arisecenla.com", "ip": "", "repo": "/mnt/synology/arise-backups/restic", "home": ""})
        self.assertNotIn("sudo arisectl reinstall", html)
        self.assertIn("/opt/arise-src/installer/install.sh --restore /mnt/synology/arise-backups/restic", html)

    def test_safe_card(self):
        src = (ROOT / "installer" / "install.sh").read_text()
        self.assertNotIn('rebuild   sudo arisectl reinstall', src)
        self.assertIn("/opt/arise-src/installer/install.sh --restore", src)

    def test_the_entry_point_exists_where_the_card_says(self):
        auto = (ROOT / "installer" / "autoinstall.yaml").read_text()
        self.assertIn("/target/opt/arise-src", auto)
        self.assertIn("--restore", (ROOT / "installer" / "install.sh").read_text())


if __name__ == "__main__":
    unittest.main()


class ForwardsAreRetried(unittest.TestCase):
    """I-020: a failed forward is tried again, never twice to someone who got it; I-086: the From header holds."""
    def _run(self, calls, st):
        from unittest import mock
        from arise_server import mailfwd, mail, inbox
        store = {"st": st}
        posted = []
        with mock.patch.object(mailfwd, "cfg_fwd", return_value={"enabled": True, "domain": "arisecenla.com"}), \
             mock.patch.object(mailfwd, "load", return_value=mock.Mock(demo=False, state_dir=Path("/nonexistent"))), \
             mock.patch.object(mail, "cfg_mail", return_value={"from_email": "it@arisecenla.com"}), \
             mock.patch.object(mailfwd, "read_json", side_effect=lambda *a, **k: store["st"]), \
             mock.patch.object(mailfwd, "write_json", side_effect=lambda p, v: store.update(st=v)), \
             mock.patch.object(mailfwd, "_users_and_emails", return_value=([{"name": "kim.lee", "enabled": True}, {"name": "ann.ray", "enabled": True}], {"kim.lee": "kim@example.com", "ann.ray": "ann@example.com"})), \
             mock.patch.object(mailfwd, "_log"), mock.patch.object(inbox, "users", return_value=[]):
            r = mailfwd.run_once(call=calls, post=lambda *a, **k: posted.append(a) or {"ok": True})
        return r, store["st"], posted

    def test_retry_then_give_up(self):
        msg = {"id": "m1", "to": ["kim.lee@arisecenla.com", "ann.ray@arisecenla.com"], "from": "x@example.org", "subject": "Hi"}
        sent = []
        def calls(method, path, body=None):
            if method == "GET" and path.endswith("/attachments"):
                return {"ok": True, "data": {"data": []}}
            if method == "GET" and "m1" in path:
                return {"ok": True, "data": {"from": "x@example.org", "text": "hello"}}
            if method == "GET":
                return {"ok": True, "data": {"data": [msg]}}
            sent.append(body["to"][0])
            return {"ok": body["to"][0] == "kim@example.com", "err": "500"}
        r, st, _ = self._run(calls, {})
        self.assertEqual(r["forwarded"], 1)
        self.assertNotIn("m1", st["seen"])
        self.assertEqual(st["pending"]["m1"]["done"], ["kim.lee"])
        for _ in range(10):
            r, st, posted = self._run(calls, st)
            if "m1" in st["seen"]:
                break
        self.assertEqual(sent.count("kim@example.com"), 1)        # never twice
        self.assertIn("m1", st["seen"])
        self.assertTrue(posted and "could not be forwarded" in posted[0][1])

    def test_from_header(self):
        from arise_server import mailfwd
        b = mailfwd.forward_body({"from": 'Smith, John "JJ" <jj@example.org>', "text": "x"}, "kim@example.com", "it@arisecenla.com")
        import email.utils
        name, addr = email.utils.parseaddr(b["from"])
        self.assertEqual(addr, "it@arisecenla.com")
        self.assertIn("via Arise Church IT", name)
        self.assertEqual(b["reply_to"], "jj@example.org")
        b = mailfwd.forward_body({"from": '"boss@bank.example" <evil@example.net>', "text": "x"}, "kim@example.com", "it@arisecenla.com")
        self.assertEqual(b["reply_to"], "evil@example.net")   # the address part, not a lookalike in the name


class SmallMediums(unittest.TestCase):
    """I-041, I-071, I-113, I-118, I-119."""
    def test_set_password_signs_out(self):
        src = (ROOT / "cli" / "arisectl").read_text()
        body = src[src.index('if a.sub != "set-password":'):]
        body = body[:body.index("arise-web restarted")]
        self.assertIn("revoke_sessions(cfg.web.admin_user)", body)

    def test_run_all_is_the_nightly_unit(self):
        js = (ROOT / "web" / "app.js").read_text()
        fn = js[js.index("async function runAllBackups()"):]
        fn = fn[:fn.index("\n")]
        self.assertIn("'/backups/run'", fn)
        self.assertNotIn("for (const j of jobs)", fn)
        self.assertNotIn("/backups/run/automator", js)
        src = (ROOT / "server" / "arise_server" / "backups.py").read_text()
        self.assertIn('"start", "--no-block", "arise-backup.service"', src)
        self.assertTrue(backups.run_all()["ok"])   # the sample config is demo mode

    def test_new_folder_belongs_to_its_maker(self):
        src = (ROOT / "server" / "arise_server" / "files.py").read_text()
        fn = src[src.index("def make_folder("):src.index("_search_cache")]
        self.assertIn("os.chown(dest", fn)
        self.assertNotIn("os.makedirs(dest)", fn)

    def test_the_receiver_must_be_a_live_account(self):
        from unittest import mock
        from arise_server import offboard, directory
        with mock.patch.object(directory, "list_users", return_value={"users": [{"name": "kim.lee", "enabled": True}, {"name": "old.one", "enabled": False}], "error": None}):
            self.assertIsNone(offboard.receiver_ok("kim.lee"))
            self.assertIn("no account", offboard.receiver_ok("nobody.here"))
            self.assertIn("switched off", offboard.receiver_ok("old.one"))
            self.assertFalse(offboard.start("ann.ray", "nobody.here", "bradly")["ok"])

    def test_the_leaving_day_is_picked(self):
        js = (ROOT / "web" / "app.js").read_text()
        fn = js[js.index("function leavingModal("):js.index("const secView = V.security")]
        self.assertIn('type="date"', fn)
        self.assertIn("days: d", fn)

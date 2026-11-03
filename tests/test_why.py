"""Leviticus (round 8, Q124): Why? on a Needs-you item. The rules are pure functions, pinned here:
the key each line gets, the one fix (restart, re-run, clear) and only where one is allowed, the
journal read as root only and never a credential, the audit entries, and the route itself.
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("ARISE_DEMO", "1")
os.environ.setdefault("ARISE_CONFIG", str(ROOT / "config" / "arise.toml.example"))

from arise_server import why  # noqa: E402

JOBS = [{"id": "homes", "name": "Home folders"}, {"id": "shares", "name": "Shared folders"}]


class Classify(unittest.TestCase):
    def test_a_stopped_service_gets_a_restart_of_that_unit(self):
        c = why.classify("docker.service is not running.")
        self.assertEqual((c["key"], c["unit"], c["kind"]), ("service:docker.service", "docker.service", "service"))
        self.assertEqual(c["fix"]["kind"], "restart")
        self.assertEqual((c["fix"]["method"], c["fix"]["path"]), ("POST", "/api/services/docker.service/restart"))
        self.assertNotIn("confirm", c["fix"])

    def test_the_domain_and_the_dashboard_ask_for_the_word_first(self):
        self.assertEqual(why.classify("samba-ad-dc.service is not running.")["fix"]["confirm"], "domain")
        self.assertEqual(why.classify("arise-web.service is not running.")["fix"]["confirm"], "dashboard")
        self.assertEqual(why.classify("Directory: LDAP did not answer")["fix"]["confirm"], "domain")

    def test_a_unit_the_services_app_does_not_manage_gets_no_fix(self):
        c = why.classify("caddy.service is not running.")
        self.assertEqual(c["unit"], "caddy.service")
        self.assertIsNone(c["fix"])

    def test_a_failed_backup_reruns_that_job_by_its_id(self):
        c = why.classify("Backup 'Home folders' failed 2026-11-03T03:00: Fatal: unable to open repository", JOBS)
        self.assertEqual(c["key"], "backup:homes")
        self.assertEqual(c["fix"], {"kind": "rerun", "label": "Re-run Home folders", "method": "POST", "path": "/api/backups/run/homes", "body": None})
        self.assertIsNone(why.classify("Backup 'Gone job' failed 2026-11-03", JOBS)["fix"])   # no id, no guess

    def test_a_missed_night_and_a_stale_job(self):
        self.assertEqual(why.classify("No backup ran last night. Backups shows why. (sudo arisectl backup run)")["fix"]["path"], "/api/backups/run")
        c = why.classify("Last night's backup didn't reach 2 jobs: shares (last good 2026-11-01 03:16), homes (never). Backups shows why.", JOBS)
        self.assertEqual(c["fix"]["path"], "/api/backups/run/shares")

    def test_the_automator_and_its_sign_in_never_get_a_fix(self):
        for t in ("Last automator run had failures: 2 failed", "token.json missing.",
                  "The server's YouTube sign-in expired on Sunday; renew it from the Media Mac"):
            c = why.classify(t)
            self.assertEqual(c["kind"], "automator", t)
            self.assertIsNone(c["fix"], t)
            self.assertEqual(c["unit"], "arise-automator.service")

    def test_the_synology_restarts_its_mount(self):
        c = why.classify("Synology not mounted at /mnt/synology. Backups will fail until it is: `arisectl nas mount`.")
        self.assertEqual(c["fix"]["path"], "/api/services/arise-nas-mount.service/restart")

    def test_mac_lines_open_macs_and_change_nothing(self):
        for t, key in (("The Mac helper is in watch mode: 4 task(s) on 3 Mac(s) would run.", "macs-watch"),
                       ("KIDS-MAC's disk is 91% full.", "mac-disk:KIDS-MAC"),
                       ("KIDS-MAC: the helper has no Full Disk Access, so no profile can be removed from it.", "mac-fda:KIDS-MAC"),
                       ("OFFICE-MAC hasn't checked in for 4 days", "mac-silent:OFFICE-MAC")):
            c = why.classify(t)
            self.assertEqual((c["key"], c["open"], c["fix"]), (key, "macs", None), t)

    def test_every_line_has_a_sentence_and_a_stable_key(self):
        lines = ["/srv/arise is 91% full: 40 GB left.", "Replace the disk /dev/sda (WD): reallocated sectors",
                 "The CPU is at 84°C (the warning is 80°C)", "STAGING: this box is not at the church yet.",
                 "No admin password set.", "Something nobody has explained yet"]
        for t in lines:
            c = why.classify(t)
            self.assertTrue(c["sentence"], t)
            self.assertEqual(c["key"], why.classify(t)["key"])
        self.assertTrue(why.classify(lines[-1])["key"].startswith("item:"))


class Journal(unittest.TestCase):
    def test_root_only(self):
        calls = []
        log, note = why.journal_tail("docker.service", run=lambda *a, **k: calls.append(a) or {"out": "x"}, root=False)
        self.assertEqual((log, calls), ([], []))
        self.assertIn("root", note)

    def test_reads_twenty_lines_of_that_unit_and_hides_credentials(self):
        seen = {}

        def run(cmd, timeout=60):
            seen["cmd"] = cmd
            return {"ok": True, "out": "-- Boot abc --\n" + "\n".join(f"line {i}" for i in range(30)) + "\nmount: password=hunter2 user=x\nAuthorization: Bearer abcdefghijklmnop\n"}
        log, note = why.journal_tail("arise-nas-mount.service", run=run, root=True)
        self.assertEqual(seen["cmd"][:5], ["journalctl", "-u", "arise-nas-mount.service", "-n", "20"])
        self.assertEqual(len(log), 20)
        self.assertFalse(any("hunter2" in x or "abcdefghijklmnop" in x for x in log))
        self.assertIn("password=•••", log[-2])
        self.assertFalse(any(x.startswith("-- ") for x in log))

    def test_never_a_unit_outside_the_readable_list(self):
        calls = []
        log, note = why.journal_tail("../../etc/shadow", run=lambda *a, **k: calls.append(a) or {"out": "x"}, root=True)
        self.assertEqual((log, calls), ([], []))

    def test_no_unit_no_journal(self):
        self.assertEqual(why.journal_tail(None)[0], [])


class Explain(unittest.TestCase):
    ITEMS = [{"level": "bad", "text": "docker.service is not running."}, {"level": "warn", "text": "KIDS-MAC's disk is 91% full."}]

    def test_no_key_lists_the_items_with_keys(self):
        r = why.explain("", self.ITEMS)
        self.assertEqual([x["key"] for x in r["items"]], ["service:docker.service", "mac-disk:KIDS-MAC"])
        self.assertEqual([x["has_fix"] for x in r["items"]], [True, False])

    def test_by_key_or_by_text(self):
        search = lambda limit, q: {"events": [{"t": "2026-11-03T06:00:00", "who": "bradly", "action": "services.restart", "target": q, "ok": True, "ip": "10.0.0.2", "detail": "x"}]}
        for k in ("service:docker.service", "docker.service is not running."):
            r = why.explain(k, self.ITEMS, run=lambda cmd, timeout=60: {"out": "a\nb"}, root=True, search=search)
            self.assertTrue(r["ok"])
            self.assertEqual(set(r) >= {"sentence", "unit", "log", "audit", "fix"}, True)
            self.assertEqual(r["log"], ["a", "b"])
            self.assertEqual(r["audit"], [{"t": "2026-11-03T06:00:00", "who": "bradly", "action": "services.restart", "target": "docker.service", "ok": True}])
            self.assertEqual(r["fix"]["path"], "/api/services/docker.service/restart")

    def test_an_item_that_cleared_itself(self):
        r = why.explain("service:ssh.service", self.ITEMS)
        self.assertFalse(r["ok"])
        self.assertTrue(r["err"])


class Route(unittest.TestCase):
    def test_sample_mode(self):
        from fastapi.testclient import TestClient
        from arise_server import config
        from arise_server.main import app
        config.load(force=True)
        c = TestClient(app)
        r = c.get("/api/why").json()
        self.assertTrue(r["ok"])
        self.assertTrue(all(x["key"] for x in r["items"]))
        if r["items"]:
            one = c.get("/api/why", params={"key": r["items"][0]["key"]}).json()
            self.assertTrue(one["ok"])
            self.assertTrue(one["sentence"])
            self.assertTrue(one["log"])          # the preview shows a believable sample journal
        self.assertFalse(c.get("/api/why", params={"key": "nothing:here"}).json()["ok"])


if __name__ == "__main__":
    unittest.main()

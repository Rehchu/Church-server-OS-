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

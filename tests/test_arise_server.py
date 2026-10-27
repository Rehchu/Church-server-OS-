"""Pure-function tests. Run: python3 -m unittest discover tests  (from the repo root).

Nothing here touches samba, docker or restic; the rules that decide what gets
written are what is pinned.
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ["ARISE_DEMO"] = "1"
os.environ["ARISE_CONFIG"] = str(ROOT / "config" / "arise.toml.example")

from arise_server import apps, automator, backups, config, directory, shares, util  # noqa: E402


class Config(unittest.TestCase):
    def test_example_config_loads_with_fixed_names(self):
        cfg = config.load(force=True)
        self.assertTrue(cfg.found)
        self.assertEqual(cfg.web.port, 4147)
        self.assertEqual(cfg.directory.realm, "AD.ARISECENLA.CHURCH")
        self.assertEqual(cfg.directory.netbios, "ARISE")
        self.assertEqual(cfg.system.hostname, "arise-server")
        self.assertEqual(cfg.automator.schedule, "02:05")

    def test_public_view_hides_secrets(self):
        pub = config.load(force=True).public()
        flat = " ".join(f"{k}" for sec in pub.values() for k in (sec if isinstance(sec, dict) else {}))
        self.assertNotIn("password", flat)
        self.assertNotIn("token", flat)

    def test_missing_config_means_demo(self):
        cfg = config.load(path="/nowhere/arise.toml", force=True)
        self.assertFalse(cfg.found)
        self.assertTrue(cfg.demo)
        config.load(force=True)


class Directory(unittest.TestCase):
    def test_delete_needs_exact_confirmation(self):
        self.assertFalse(directory.delete_user("office", "")["ok"])
        self.assertFalse(directory.delete_user("office", "Office")["ok"])
        self.assertTrue(directory.delete_user("office", "office")["ok"])

    def test_user_names_are_validated(self):
        self.assertFalse(directory.add_user("bad name", "password123")["ok"])
        self.assertFalse(directory.add_user("1abc", "password123")["ok"])
        self.assertFalse(directory.add_user("ok", "short")["ok"])
        self.assertTrue(directory.add_user("media-mac", "password123")["ok"])


class Shares(unittest.TestCase):
    def test_smb_conf_parser(self):
        conf = shares._parse("[global]\n  workgroup = ARISE\n; comment\n[homes]\n  path = /srv/arise/homes/%U\n  read only = no\n  vfs objects = fruit streams_xattr\n")
        self.assertEqual(conf["global"]["workgroup"], "ARISE")
        self.assertEqual(conf["homes"]["path"], "/srv/arise/homes/%U")
        self.assertIn("fruit", conf["homes"]["vfs objects"])

    def test_remove_needs_confirmation_and_keeps_files(self):
        self.assertFalse(shares.remove_share("graphics", "")["ok"])
        self.assertIn("never touched", shares.remove_share("graphics", "nope")["err"])

    def test_add_requires_absolute_path(self):
        self.assertFalse(shares.add_share("x", "relative/path")["ok"])
        self.assertFalse(shares.add_share("bad/name", "/srv/x")["ok"])


class Backups(unittest.TestCase):
    def test_example_jobs_file_has_the_contract_jobs(self):
        cfg = config.load(force=True)
        import yaml
        with open(ROOT / "config" / "backups.yaml.example") as f:
            jobs = yaml.safe_load(f)["jobs"]
        ids = {j["id"] for j in jobs}
        for needed in ("automator", "homes", "shares", "github", "config"):
            self.assertIn(needed, ids)
        for j in jobs:
            self.assertTrue(j["paths"], j["id"])
            self.assertTrue(all(p.startswith("/") for p in j["paths"]), j["id"])
        self.assertEqual(cfg.backups.keep_daily, 14)

    def test_unknown_job_is_refused(self):
        self.assertFalse(backups.run_job("nope")["ok"])

    def test_history_is_newest_first(self):
        rows = backups.history(limit=50)["rows"]
        self.assertTrue(all(rows[i]["started"] >= rows[i + 1]["started"] for i in range(len(rows) - 1)))


class Automator(unittest.TestCase):
    def test_next_run_is_in_the_future_at_the_schedule(self):
        nxt = automator._next_run("02:05")
        self.assertTrue(nxt.endswith("02:05:00"))
        from datetime import datetime
        self.assertGreater(datetime.fromisoformat(nxt), datetime.now())

    def test_bad_schedule_falls_back_to_0205(self):
        self.assertTrue(automator._next_run("garbage").endswith("02:05:00"))

    def test_report_names_are_validated(self):
        self.assertIn("error", automator.report("../etc/passwd"))
        self.assertIn("error", automator.report("x.txt"))

    def test_mode_is_validated(self):
        self.assertFalse(automator.start("delete-everything")["ok"])


class Apps(unittest.TestCase):
    def test_templates_in_repo_are_well_formed(self):
        t = apps.templates()
        self.assertFalse(t["demo"], "templates/ should be read from the repo")
        ids = {x["id"] for x in t["templates"]}
        for needed in ("filebrowser", "uptime-kuma", "syncthing", "vaultwarden"):
            self.assertIn(needed, ids)
        for x in t["templates"]:
            self.assertTrue(x["name"] and x["description"], x["id"])
            self.assertTrue(all(":" in p for p in x["ports"]), x["id"])

    def test_names_and_actions_validated(self):
        self.assertFalse(apps.act("Bad Name", "start")["ok"])
        self.assertFalse(apps.act("ok-name", "explode")["ok"])
        self.assertFalse(apps.act("ok-name", "remove", "")["ok"])

    def test_mem_parse(self):
        self.assertEqual(apps._parse_mem("38.5MiB"), int(38.5 * 1024 ** 2))
        self.assertEqual(apps._parse_mem("1.2GiB"), int(1.2 * 1024 ** 3))
        self.assertEqual(apps._parse_mem("nonsense"), 0)


class Util(unittest.TestCase):
    def test_human_bytes(self):
        self.assertEqual(util.human_bytes(0), "0 B")
        self.assertEqual(util.human_bytes(1536), "1.5 KB")
        self.assertEqual(util.human_bytes(2 * 1024 ** 4), "2.0 TB")
        self.assertEqual(util.human_bytes(None), "—")

    def test_run_handles_missing_binary(self):
        r = util.run(["definitely-not-a-command-xyz"])
        self.assertFalse(r["ok"])
        self.assertEqual(r["code"], 127)


class Units(unittest.TestCase):
    def test_timers_match_the_contract(self):
        t = (ROOT / "config" / "systemd" / "arise-automator.timer").read_text()
        self.assertIn("02:05:00 America/Chicago", t)
        self.assertIn("Persistent=true", t)
        b = (ROOT / "config" / "systemd" / "arise-backup.timer").read_text()
        self.assertIn("03:00:00 America/Chicago", b)
        w = (ROOT / "config" / "systemd" / "arise-web.service").read_text()
        self.assertIn("-m arise_server", w)


if __name__ == "__main__":
    unittest.main()

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
        self.assertEqual(cfg.backups.keep_daily, 30)  # Bradly: more history (docs/ANSWERS.md 47)

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


class V02(unittest.TestCase):
    def test_sites_come_from_example_config(self):
        from arise_server import sites
        ids = [s["id"] for s in sites.sites()]
        self.assertEqual(ids, ["pineville", "alexandria", "hub"])

    def test_sites_place_computers_by_subnet(self):
        from arise_server import sites
        r = sites.status([{"name": "A", "ip": "192.168.2.20"}, {"name": "B", "ip": "192.168.1.5"}, {"name": "C", "ip": "10.9.9.9"}])
        by = {s["id"]: s["computers"] for s in r["sites"]}
        self.assertEqual(by["alexandria"], ["A"])
        self.assertEqual(by["pineville"], ["B"])

    def test_bible_rejects_garbage_and_answers_sample(self):
        from arise_server import bible
        self.assertFalse(bible.lookup("drop table")["ok"])
        r = bible.lookup("John 3:16")
        self.assertTrue(r["ok"])
        self.assertEqual(r["verses"][0]["verse"], 16)

    def test_files_never_escape_the_root(self):
        from arise_server import files
        self.assertIsNone(files._resolve("/srv/arise", "../../etc/passwd"))
        self.assertEqual(files._resolve("/srv/arise", "homes/x"), "/srv/arise/homes/x")
        self.assertIn("error", files.listing("nope", "/"))

    def test_wireguard_peer_name_validated(self):
        from arise_server import remote
        self.assertFalse(remote.add_wireguard_peer("bad name!")["ok"])
        self.assertTrue(remote.add_wireguard_peer("hub-laptop")["ok"])

    def test_power_needs_typed_confirmation(self):
        from arise_server import system
        self.assertFalse(system.power("reboot", "")["ok"])
        self.assertFalse(system.power("explode", "explode")["ok"])
        self.assertTrue(system.power("reboot", "reboot")["ok"])

    def test_sermon_kind_from_title_and_duration(self):
        from arise_server import sermons
        self.assertEqual(sermons._kind("GLORY NIGHT | Oct 20", "1:30:00"), "Glory Night")
        self.assertEqual(sermons._kind("Declare it", "0:48"), "Short")
        self.assertEqual(sermons._kind("THE GOD KIND OF FAITH", "1:55:18"), "Sunday Service")


class V04(unittest.TestCase):
    """Per-user logins, scoped files, share links."""

    def test_member_paths_are_the_portal_only(self):
        from arise_server import auth
        for p in ("/api/files/list", "/api/search", "/api/links", "/api/sermons", "/api/bible", "/api/sites", "/api/me/password", "/api/auth/me"):
            self.assertTrue(auth.member_ok(p, "member"), p)
        for p in ("/api/overview", "/api/directory/users", "/api/services", "/api/terminal", "/api/settings", "/api/system/power", "/api/backups/run/x"):
            self.assertFalse(auth.member_ok(p, "member"), p)
            self.assertTrue(auth.member_ok(p, "admin"), p)

    def test_share_valid_users_parse_and_match(self):
        self.assertEqual(shares._names('@"Media", @Staff, bradly'), ["@Media", "@Staff", "bradly"])
        self.assertTrue(shares.can_use({"valid_users": ["@Media"]}, "office", ["Media", "Staff"]))
        self.assertFalse(shares.can_use({"valid_users": ["@Media"]}, "office", ["Staff"]))
        self.assertTrue(shares.can_use({"valid_users": []}, "anyone", []))
        self.assertTrue(shares.can_use({"valid_users": ["office"]}, "Office", []))

    def test_admin_and_member_roots(self):
        from arise_server import files
        admin = [r["id"] for r in files.roots({"user": "bradly", "role": "admin"})]
        self.assertEqual(admin[0], "data")
        member = files.roots({"user": "office", "role": "member"})
        ids = [r["id"] for r in member]
        self.assertEqual(ids[0], "home")
        self.assertIn("share:media", ids)
        self.assertNotIn("data", ids)
        self.assertNotIn("share:sysvol", ids)
        media = next(r for r in member if r["id"] == "share:media")
        self.assertFalse(media["writable"])  # write list is Media only; office is Staff

    def test_member_cannot_reach_another_root(self):
        from arise_server import files
        who = {"user": "office", "role": "member"}
        self.assertEqual(files.listing("data", "/", who).get("error"), "unknown root")
        self.assertEqual(files.make_folder("share:media", "/", "x", who)["ok"], False)

    def test_share_links_create_list_revoke(self):
        from arise_server import links
        me = {"user": "office", "role": "member"}; other = {"user": "media-mac", "role": "member"}; admin = {"user": "bradly", "role": "admin"}
        r = links.create("home", "/Documents/x.pdf", me, days=99)
        self.assertTrue(r["ok"]); tok = r["token"]
        self.assertEqual(r["link"]["user"], "office")
        self.assertLess(r["link"]["expires"], links._iso(31 * 86400))  # clamped to max_days
        self.assertFalse(links.create("data", "/", me)["ok"])  # not a member root
        self.assertIn(tok, [l["token"] for l in links.mine(me)["links"]])
        self.assertNotIn(tok, [l["token"] for l in links.mine(other)["links"]])
        self.assertIn(tok, [l["token"] for l in links.mine(admin)["links"]])
        self.assertFalse(links.revoke(tok, other)["ok"])
        self.assertTrue(links.revoke(tok, me)["ok"])
        self.assertIsNone(links.resolve(tok))

    def test_directory_sample_auth_and_roles(self):
        self.assertTrue(directory.authenticate("office", "anything"))
        self.assertFalse(directory.authenticate("guest-speaker", "anything"))  # disabled
        self.assertFalse(directory.authenticate("office", ""))
        self.assertTrue(directory.is_admin("bradly"))
        self.assertFalse(directory.is_admin("office"))


class Devices(unittest.TestCase):
    def test_arp_scan_and_neigh_parse(self):
        from arise_server import devices
        rows = devices.parse_arp_scan("192.168.1.5\t00:11:22:33:44:55\tApple, Inc.\nStarting arp-scan\n192.168.1.6\tAA:BB:CC:DD:EE:FF\n")
        self.assertEqual([r["ip"] for r in rows], ["192.168.1.5", "192.168.1.6"])
        self.assertEqual(rows[1]["mac"], "aa:bb:cc:dd:ee:ff")
        n = devices.parse_neigh("192.168.1.9 dev eno1 lladdr 00:11:22:33:44:66 REACHABLE\n192.168.1.10 dev eno1  FAILED\n")
        self.assertEqual(len(n), 1)

    def test_classify_guesses_kind(self):
        from arise_server import devices
        self.assertEqual(devices.classify("Synology Incorporated"), ("Synology", "nas"))
        self.assertEqual(devices.classify("NETGEAR"), ("Netgear", "router"))
        self.assertEqual(devices.classify("", "ds920.local")[1], "nas")
        self.assertEqual(devices.classify("Something Else")[1], "unknown")

    def test_sample_devices_and_label_rules(self):
        from arise_server import devices
        r = devices.list_devices()
        self.assertTrue(r["demo"]); self.assertGreaterEqual(len(r["devices"]), 5)
        self.assertTrue(all(d["mac"].startswith("02:") for d in r["devices"]))  # sample MACs are never real ones
        self.assertEqual(devices.label("02:a1:00:00:00:01", kind="toaster").get("ok"), True)  # demo: nothing written

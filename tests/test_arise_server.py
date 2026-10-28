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

    def test_router_attached_devices_normalize_and_sample(self):
        from arise_server import routers
        d = routers.normalize({"name": "OFFICE-MAC-01", "ip": "10.0.0.12", "mac": "02:B2:00:00:00:12", "type": "wired", "signal": None, "link_rate": 1000})
        self.assertEqual(d["mac"], "02:b2:00:00:00:12"); self.assertEqual(d["kind_final"], "wired"); self.assertTrue(d["behind"])
        self.assertEqual(routers.attached({"kind": "google"})["ok"], False)
        b = routers.behind(); self.assertTrue(b["demo"]); self.assertTrue(any(not x["ok"] for x in b["routers"]))  # the Mesh says so honestly

    def test_onvif_parse_and_sample_cameras(self):
        from arise_server import devices
        x = '<d:ProbeMatch><d:Scopes>onvif://www.onvif.org/name/FRONT%20DOOR onvif://www.onvif.org/hardware/DS-2CD2043</d:Scopes><d:XAddrs>http://192.168.0.64/onvif/device_service http://[fe80::1]/onvif</d:XAddrs></d:ProbeMatch>'
        c = devices.parse_onvif(x, "192.168.0.64")
        self.assertEqual(c["name"], "FRONT DOOR"); self.assertEqual(c["hardware"], "DS-2CD2043"); self.assertEqual(c["xaddrs"][0], "http://192.168.0.64/onvif/device_service")
        r = devices.find_cameras(); self.assertTrue(r["demo"]); self.assertTrue(all(not c["reachable"] for c in r["cameras"]))
        self.assertTrue(devices.scan(wide=True)["wide"])
        self.assertTrue(any(d.get("stray") for d in devices.list_devices()["devices"]))
        self.assertIn("192.168.0.0/24", devices.WIDE_RANGES)


class AppSecrets(unittest.TestCase):
    def test_change_me_becomes_a_secret_and_is_kept_on_redeploy(self):
        env, made = apps.fill_secrets({"POSTGRES_PASSWORD": "CHANGE-ME-x", "TZ": "America/Chicago"})
        self.assertEqual(made, ["POSTGRES_PASSWORD"]); self.assertGreater(len(env["POSTGRES_PASSWORD"]), 20); self.assertEqual(env["TZ"], "America/Chicago")
        again, made2 = apps.fill_secrets({"POSTGRES_PASSWORD": "CHANGE-ME-x"}, existing=env)
        self.assertEqual(again["POSTGRES_PASSWORD"], env["POSTGRES_PASSWORD"]); self.assertEqual(made2, [])
        given, made3 = apps.fill_secrets({"POSTGRES_PASSWORD": "CHANGE-ME-x"}, given={"POSTGRES_PASSWORD": "mine"})
        self.assertEqual(given["POSTGRES_PASSWORD"], "mine"); self.assertEqual(made3, [])

    def test_every_template_secret_is_marked_change_me(self):
        for t in apps.templates()["templates"]:
            env = apps._template_env(t["id"])
            for k, v in env.items():
                if any(w in k for w in ("PASS", "TOKEN", "SECRET")) and "HASH" not in k:
                    self.assertTrue(v.startswith("CHANGE-ME"), f"{t['id']}.{k} should be CHANGE-ME so the deploy generates it")


class Church(unittest.TestCase):
    def test_next_service_and_week_rollover(self):
        from arise_server import church
        from datetime import datetime
        svcs = [{"name": "Sunday Service", "day": "Sunday", "time": "10:30", "site": "Pineville"}, {"name": "Glory Night", "day": "Monday", "time": "19:00", "site": "Pineville"}]
        n = church.next_service(datetime(2026, 10, 28, 15, 0), svcs)   # a Wednesday
        self.assertEqual((n["name"], n["day"]), ("Sunday Service", "Sunday")); self.assertEqual(n["at"], "2026-11-01T10:30")
        n = church.next_service(datetime(2026, 11, 1, 10, 31), svcs)   # a minute after Sunday's start
        self.assertEqual(n["name"], "Glory Night")
        n = church.next_service(datetime(2026, 11, 2, 19, 1), svcs)    # after Glory Night: next Sunday
        self.assertEqual(n["at"], "2026-11-08T10:30")

    def test_verse_of_day_is_a_real_reference_with_text(self):
        from arise_server import church
        v = church.verse_of_day()
        self.assertIn(v["ref"], church.VERSES); self.assertTrue(v["text"]); self.assertNotIn("(Preview)", v["text"])

    def test_sunday_checklist_toggles_and_keys_by_sunday(self):
        from arise_server import church
        from datetime import datetime
        self.assertEqual(church._sunday_key(datetime(2026, 10, 28)), "2026-11-01")
        self.assertEqual(church._sunday_key(datetime(2026, 11, 1)), "2026-11-01")
        r = church.toggle(3, "media"); self.assertTrue(r["ok"]); self.assertTrue(r["items"][3]["done"]); self.assertEqual(r["items"][3]["by"], "media")
        r = church.toggle(3, "media"); self.assertFalse(r["items"][3]["done"])
        self.assertFalse(church.toggle(99, "x")["ok"])

    def test_kiosk_opens_only_listed_https_sites(self):
        from arise_server import church
        self.assertTrue(church.allowed_url("https://claude.ai/new")); self.assertTrue(church.allowed_url("https://chatgpt.com/"))
        self.assertFalse(church.allowed_url("http://claude.ai/")); self.assertFalse(church.allowed_url("https://example.com/"))
        self.assertTrue(church.open_on_kiosk("https://grok.com/")["ok"])

    def test_transcript_search_sample(self):
        from arise_server import files
        self.assertEqual(files.search_transcripts("ab"), [])
        self.assertTrue(files.search_transcripts("faith")[0]["id"])


class Mail(unittest.TestCase):
    def test_wix_csv_parses_dedupes_and_validates(self):
        from arise_server import mail
        r = mail.parse_contacts("\ufeffFirst Name,Last Name,Email,Phone\nJane,Doe,Jane@Example.com,555\nBad,,notanemail,\nJane,Again,jane@example.com,\n,,who@example.com,\n")
        self.assertEqual([c["email"] for c in r["contacts"]], ["jane@example.com", "who@example.com"]); self.assertEqual(r["skipped"], 2)
        self.assertEqual(r["contacts"][0]["first_name"], "Jane")
        self.assertIn("err", mail.parse_contacts("name,phone\nx,1\n"))
        full = mail.parse_contacts("Name;Email\nJohn Smith;john@x.org\n")
        self.assertEqual((full["contacts"][0]["first_name"], full["contacts"][0]["last_name"]), ("John", "Smith"))

    def test_template_has_unsubscribe_and_first_name_and_escapes(self):
        from arise_server import mail
        h = mail.render("Hi", "Hello <b>world</b> **bold** [site](https://arisecenla.church)\n\n## Head\n- one\n- two")
        self.assertIn("{{{RESEND_UNSUBSCRIBE_URL}}}", h); self.assertIn("{{{FIRST_NAME|there}}}", h)
        self.assertIn("&lt;b&gt;world&lt;/b&gt;", h); self.assertIn("<strong>bold</strong>", h); self.assertIn('href="https://arisecenla.church"', h); self.assertIn("<li", h)

    def test_sending_to_everyone_needs_the_word(self):
        from arise_server import mail
        self.assertFalse(mail.send_broadcast("x", "yes")["ok"]); self.assertTrue(mail.send_broadcast("x", "send")["ok"])
        self.assertFalse(mail.send_test("nope", "s", "b")["ok"])


class Feel(unittest.TestCase):
    def test_push_subscription_shape_and_recipients(self):
        from arise_server import push
        self.assertTrue(push.valid_subscription({"endpoint": "https://p/x", "keys": {"p256dh": "a", "auth": "b"}}))
        self.assertFalse(push.valid_subscription({"endpoint": "http://p/x", "keys": {"p256dh": "a", "auth": "b"}}))
        self.assertFalse(push.valid_subscription({"endpoint": "https://p/x"}))
        self.assertEqual(push.who_gets()[0], config.load(force=True).web.admin_user)   # answer 10: Bradly only
        self.assertFalse(push.subscribe("bradly", {"endpoint": "nope"})["ok"])
        self.assertEqual(push.send("a", "b", tag="t", throttle_s=3600)["ok"], True)
        self.assertEqual(push.send("a", "b", tag="t", throttle_s=3600).get("skipped"), "throttled")

    def test_manifest_and_icons_exist(self):
        import json as _j
        m = _j.loads((ROOT / "web" / "manifest.webmanifest").read_text())
        self.assertEqual(m["name"], "ariseOS"); self.assertEqual(m["display"], "standalone")
        for ic in m["icons"]:
            self.assertTrue((ROOT / "web" / ic["src"].replace("/assets/", "")).exists(), ic["src"])
        self.assertTrue((ROOT / "web" / "sw.js").exists())


class Finder(unittest.TestCase):
    """v0.8: Trash, Previous Versions, Get Info, Recents, the text editor, Open on my Mac."""

    def test_trash_names_follow_samba_recycle_and_put_back_never_overwrites(self):
        from arise_server import finder
        taken = {"x.pdf", "Copy #1 of x.pdf"}
        self.assertEqual(finder.versioned_name("x.pdf", lambda n: n in taken), "Copy #2 of x.pdf")
        self.assertEqual(finder.versioned_name("y.pdf", lambda n: n in taken), "y.pdf")
        self.assertEqual(finder.put_back_name("Copy #2 of x.pdf", lambda n: False), "x.pdf")
        self.assertEqual(finder.put_back_name("x.pdf", lambda n: n == "x.pdf"), "x (put back).pdf")
        self.assertEqual(finder.put_back_name("x.pdf", lambda n: n in ("x.pdf", "x (put back).pdf")), "x (put back 2).pdf")
        self.assertEqual(finder.trash_rel("/srv/arise/shares/media", "/srv/arise/shares/media/loops/a.mov"), "loops/a.mov")

    def test_trash_base_is_the_enclosing_share_then_home_then_root(self):
        from arise_server import finder
        self.assertEqual(finder.trash_base("/srv/arise/shares/staff/Forms/a.pdf"), "/srv/arise/shares/staff")
        self.assertEqual(finder.trash_base("/srv/arise/shares/other/a.pdf"), "/srv/arise/shares")  # no narrower share: the shares share
        self.assertEqual(finder.trash_base("/srv/arise/homes/office/Documents/b.docx"), "/srv/arise/homes/office")
        self.assertEqual(finder.trash_base("/srv/arise/automator/x.json"), "/srv/arise")
        self.assertIsNone(finder.trash_base("/etc/passwd"))

    def test_sweep_age_is_thirty_days(self):
        from datetime import datetime
        from arise_server import finder
        now = datetime(2026, 10, 28, 4, 30)
        self.assertTrue(finder.expired("2026-09-27T10:00:00", now))
        self.assertFalse(finder.expired("2026-09-29T10:00:00", now))
        self.assertFalse(finder.expired(None, now)); self.assertFalse(finder.expired("garbage", now))

    def test_trash_put_needs_the_name_typed_and_members_stay_in_their_roots(self):
        from arise_server import finder
        office = {"user": "office", "role": "member"}
        self.assertFalse(finder.trash_put("home", "/Documents/x.docx", office, confirm="wrong")["ok"])
        self.assertTrue(finder.trash_put("home", "/Documents/x.docx", office, confirm="x.docx")["ok"])
        self.assertFalse(finder.trash_put("share:media", "/loops/a.mov", office, confirm="a.mov")["ok"])  # read-only for office
        self.assertFalse(finder.trash_restore("/srv/arise/shares/staff", "bradly", "Forms/x", office)["ok"])  # not their file
        self.assertFalse(finder.trash_empty("staff", "staff", office)["ok"])  # not an admin
        self.assertFalse(finder.trash_empty("staff", "nope", {"user": "bradly", "role": "admin"})["ok"])  # not typed
        mine = finder.trash_list(office)["items"]
        self.assertTrue(all(t["user"] == "office" for t in mine))
        self.assertGreater(len(finder.trash_list({"user": "bradly", "role": "admin"})["items"]), len(mine))

    def test_previous_versions_parse_and_restored_name(self):
        from arise_server import backups
        out = '''[{"matches":[{"path":"/srv/arise/shares/staff/a.pdf","size":10,"mtime":"2026-10-20T10:00:00Z","type":"file"}],"hits":1,"snapshot":"abcdef1234"},
                  {"matches":[{"path":"/srv/arise/shares/staff/a.pdf","size":12,"mtime":"2026-10-25T10:00:00Z","type":"file"}],"hits":1,"snapshot":"0123456789"}]'''
        rows = backups.parse_find(out, {"abcdef12": "2026-10-21T03:00:00", "01234567": "2026-10-26T03:00:00"})
        self.assertEqual([r["snapshot"] for r in rows], ["01234567", "abcdef12"])  # newest first
        self.assertEqual(rows[0]["size"], 12)
        self.assertEqual(backups.restored_name("setlist.pdf", "2026-10-27", lambda n: False), "setlist (restored 2026-10-27).pdf")
        self.assertEqual(backups.restored_name("setlist.pdf", "2026-10-27", lambda n: n == "setlist (restored 2026-10-27).pdf"), "setlist (restored 2026-10-27 2).pdf")
        self.assertEqual(backups.job_for("/srv/arise/shares/staff/a.pdf")["id"], "shares")
        self.assertIsNone(backups.job_for("/mnt/synology/arise/recordings/x.mp4"))
        self.assertFalse(backups.versions_of("/mnt/synology/arise/recordings/x.mp4")["backed_up"])
        self.assertTrue(backups.versions_of("/srv/arise/homes/office/Documents/b.docx")["versions"])

    def test_text_editor_allowlist_and_markdown_never_passes_html(self):
        from arise_server import finder
        self.assertTrue(finder.is_text("notes.MD")); self.assertTrue(finder.is_text("a.yaml"))
        self.assertFalse(finder.is_text("movie.mp4")); self.assertFalse(finder.is_text("sheet.xlsx"))
        who = {"user": "bradly", "role": "admin"}
        self.assertFalse(finder.read_text("data", "/shares/media/Sunday 2026-10-26 program.mp4", who)["ok"])
        self.assertTrue(finder.read_text("data", "/shares/graphics/ARISE_BRAND_KIT.md", who)["ok"])
        office = {"user": "office", "role": "member"}
        self.assertFalse(finder.write_text("share:media", "/x.md", "hi", office)["ok"])  # read-only share
        self.assertTrue(finder.write_text("home", "/x.md", "hi", office)["ok"])
        html = finder.render_markdown("# T <script>alert(1)</script>\n\n[go](javascript:alert(1))\n\n> q")
        self.assertNotIn("<script>", html); self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("javascript:", html); self.assertIn("<blockquote>", html)

    def test_smb_address_and_who_can_open_it(self):
        from arise_server import finder
        office = {"user": "office", "role": "member"}; admin = {"user": "bradly", "role": "admin"}
        self.assertEqual(finder.smb_path("home", "/Documents", office), "smb://arise-server.ad.arisecenla.church/office/Documents")
        self.assertEqual(finder.smb_path("share:staff", "/Forms", office), "smb://arise-server.ad.arisecenla.church/staff/Forms")
        self.assertEqual(finder.smb_path("data", "/homes/bradly/Desktop", admin), "smb://arise-server.ad.arisecenla.church/bradly/Desktop")
        self.assertEqual(finder.smb_path("data", "/shares/media/loops", admin), "smb://arise-server.ad.arisecenla.church/shares/media/loops")
        self.assertIsNone(finder.smb_path("data", "/automator", admin))
        info = finder.info("data", "/shares/staff/Phone list.xlsx", admin)
        self.assertEqual(info["access"]["share"], "staff")
        self.assertIn("Staff", info["access"]["who"])
        self.assertEqual(finder.info("home", "/Documents/x.docx", office)["access"]["who"], ["office"])

    def test_recents_are_scoped_like_the_roots(self):
        from arise_server import finder
        hits = finder.recent({"user": "office", "role": "member"})["hits"]
        self.assertTrue(hits)
        self.assertTrue(all(h["root"] in ("home", "share:media", "share:staff", "share:graphics") for h in hits), {h["root"] for h in hits})
        self.assertTrue(all(h["root"] == "data" for h in finder.recent({"user": "bradly", "role": "admin"})["hits"]))

    def test_shares_template_and_new_shares_carry_the_recycle_trash(self):
        tpl = (ROOT / "config" / "samba" / "smb.conf.template").read_text()
        for name in ("homes", "shares", "staff", "media", "graphics", "worship"):
            block = tpl.split(f"[{name}]")[1].split("\n[")[0]
            self.assertIn("recycle:repository = .Trash/%U", block, name)
            self.assertIn("fruit", block.split("vfs objects =")[1].split("\n")[0], name)
        self.assertNotIn("recycle:repository", tpl.split("[recordings]")[1].split("\n[")[0])
        self.assertIn("**/.Trash", (ROOT / "config" / "backups.yaml.example").read_text().split("id: shares")[1].split("id:")[0])
        self.assertTrue((ROOT / "config" / "systemd" / "arise-trash.timer").exists())

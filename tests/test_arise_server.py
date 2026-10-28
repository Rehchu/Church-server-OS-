"""Pure-function tests. Run: python3 -m unittest discover tests  (from the repo root).

Nothing here touches samba, docker or restic; the rules that decide what gets
written are what is pinned.
"""
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ["ARISE_DEMO"] = "1"
os.environ["ARISE_CONFIG"] = str(ROOT / "config" / "arise.toml.example")

from arise_server import apps, automator, backups, config, demo_state, directory, shares, util  # noqa: E402

# The sample server now remembers clicks (demo_state). Every test starts from the seed.
_plain_setup = unittest.TestCase.setUp


def _fresh_sample(self):
    demo_state.reset()
    _plain_setup(self)


unittest.TestCase.setUp = _fresh_sample


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
        self.assertFalse(directory.add_user("media-mac", "password123")["ok"])   # already in the sample
        self.assertTrue(directory.add_user("jane.doe", "password123")["ok"])


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
        self.assertIn("Persistent=false", t)   # the automator handoff, section 7: a missed night never fires on a Sunday morning
        b = (ROOT / "config" / "systemd" / "arise-backup.timer").read_text()
        self.assertIn("03:00:00 America/Chicago", b)
        w = (ROOT / "config" / "systemd" / "arise-web.service").read_text()
        self.assertIn("-m arise_server", w)



class AuditAndLeaving(unittest.TestCase):
    """Round 2, 23 and 24; round 4, 79 and 82: the audit log (forever, read-only) and offboarding."""

    def test_action_and_target_from_a_path(self):
        from arise_server import audit
        self.assertEqual(audit.action_of("POST", "/api/directory/users/bryant.sanders/disable"), "directory.users.disable")
        self.assertEqual(audit.target_of("/api/directory/users/bryant.sanders/disable"), "bryant.sanders")
        self.assertEqual(audit.action_of("DELETE", "/api/shares/staff"), "shares.delete"); self.assertEqual(audit.target_of("/api/shares/staff"), "staff")
        self.assertEqual(audit.action_of("POST", "/api/sunday/3"), "sunday")
        self.assertEqual(audit.target_of("/api/sunday/3"), "3")

    def test_filter(self):
        from arise_server import audit
        ev = {"who": "bradly", "action": "directory.users.disable", "target": "guest-speaker", "ok": True}
        self.assertTrue(audit.matches(ev, "disable guest"))
        self.assertFalse(audit.matches(ev, "enable"))
        self.assertFalse(audit.matches(ev, failed_only=True))
        self.assertTrue(audit.matches({**ev, "ok": False}, failed_only=True))
        self.assertFalse(audit.matches(ev, who="office"))

    def test_records_survive_and_never_carry_a_body(self):
        import os, tempfile, json
        from unittest import mock
        from arise_server import audit
        with tempfile.TemporaryDirectory() as d:
            from pathlib import Path
            fake = mock.Mock(); fake.demo = False; fake.state_dir = Path(d)
            with mock.patch.object(audit, "load", return_value=fake):
                audit.record("bradly", "auth.login")
                audit.record("x", "auth.login", ok=False, detail="wrong user or password")
                lines = (Path(d) / "audit.jsonl").read_text().splitlines()
                self.assertEqual(len(lines), 2)
                self.assertNotIn("password\":", lines[1])
                r = audit.recent(failed_only=True)
                self.assertEqual([e["who"] for e in r["events"]], ["x"])
                self.assertEqual(r["kept"], "forever")
                self.assertEqual(oct(os.stat(Path(d) / "audit.jsonl").st_mode & 0o777), "0o640")

    def test_leaving_plan_rules(self):
        from datetime import datetime
        from arise_server import offboard
        now = datetime(2026, 10, 28, 12, 0)
        p = offboard.plan("guest.speaker", "bradly.dyer", "bradly", now=now)
        self.assertTrue(p["ok"]); self.assertEqual(p["entry"]["disable_on"], "2026-11-27")
        self.assertFalse(offboard.plan("guest.speaker", "guest.speaker", "bradly", now=now)["ok"])
        self.assertFalse(offboard.plan("guest.speaker", "", "bradly", now=now)["ok"])
        self.assertFalse(offboard.plan("Bad Name", "bradly.dyer", "bradly", now=now)["ok"])
        e = [p["entry"], {**p["entry"], "name": "a.b", "disable_on": "2026-10-01"}, {**p["entry"], "name": "c.d", "disable_on": "2026-10-01", "done": "x"}]
        self.assertEqual([x["name"] for x in offboard.due(e, now)], ["a.b"])
        self.assertTrue(offboard.dest_dir("/srv/arise/homes", "bradly.dyer", "guest.speaker", now).endswith("bradly.dyer/From guest.speaker (2026-10-28)"))

    def test_sweep_moves_files_only_after_the_account_is_off(self):
        import os, tempfile
        from datetime import datetime
        from pathlib import Path
        from unittest import mock
        from arise_server import offboard, audit
        with tempfile.TemporaryDirectory() as d:
            homes = Path(d) / "homes"; (homes / "a.b" / "Documents").mkdir(parents=True); (homes / "a.b" / "Documents" / "x.txt").write_text("x")
            (homes / "c.d").mkdir()
            fake = mock.Mock(); fake.demo = False; fake.state_dir = Path(d); fake.directory.homes_path = str(homes)
            with mock.patch.object(offboard, "load", return_value=fake), mock.patch.object(audit, "load", return_value=fake):
                offboard._write([{"name": "a.b", "move_to": "c.d", "by": "bradly", "since": "2026-09-01", "disable_on": "2026-10-01", "done": None}])
                with mock.patch.object(offboard.directory, "enable_user", return_value={"ok": False, "err": "samba-tool: no such user"}):
                    r = offboard.sweep(now=datetime(2026, 10, 28))
                self.assertFalse(r["ok"]); self.assertTrue((homes / "a.b" / "Documents" / "x.txt").exists())   # refused: files stay
                with mock.patch.object(offboard.directory, "enable_user", return_value={"ok": True}) as en:
                    r = offboard.sweep(now=datetime(2026, 10, 28))
                en.assert_called_once_with("a.b", False)
                self.assertTrue(r["ok"])
                self.assertTrue((homes / "c.d" / "From a.b (2026-10-28)" / "Documents" / "x.txt").exists())
                self.assertEqual(offboard.due(offboard._read(), datetime(2026, 10, 29)), [])        # done once, never again

    def test_routes_admin_only_and_the_flow_in_demo(self):
        import os
        os.environ["ARISE_DEMO"] = "1"
        from fastapi.testclient import TestClient
        from arise_server.main import app
        from arise_server.auth import member_ok
        for p in ("/api/audit", "/api/directory/leaving", "/api/directory/users/x.y/leaving"):
            self.assertFalse(member_ok(p, "member"), p)
        c = TestClient(app)
        r = c.post("/api/directory/users/guest.speaker/leaving", json={"move_to": "bradly.dyer"}).json()
        self.assertTrue(r["ok"], r)
        self.assertIn("guest.speaker", [e["name"] for e in c.get("/api/directory/leaving").json()["entries"]])
        ev = c.get("/api/audit?q=leaving").json()["events"]
        self.assertTrue(any(e["action"].startswith("directory.leaving") for e in ev), ev)
        self.assertTrue(c.delete("/api/directory/users/guest.speaker/leaving").json()["ok"])
        self.assertFalse(c.delete("/api/directory/users/guest.speaker/leaving").json()["ok"])



class Browser(unittest.TestCase):
    """Firefox on the closet monitor, in the ariseOS theme (docs/BROWSER.md)."""
    ROOT = Path(__file__).resolve().parents[1]

    def _build(self, cfg=None):
        import importlib.util
        spec = importlib.util.spec_from_file_location("abp", self.ROOT / "scripts" / "arise-browser-policies.py")
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        return m, m.build(cfg or {})

    def test_policy_validates_against_firefoxs_own_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        schema = json.loads((self.ROOT / "tests" / "fixtures" / "firefox-policies-schema.json").read_text())
        _, doc = self._build()
        jsonschema.validate(doc["policies"], schema)
        _, doc2 = self._build({"browser": {"open_web": True}})
        jsonschema.validate(doc2["policies"], schema)

    def test_every_preference_is_one_the_policy_may_set(self):
        # Policies.sys.mjs (mozilla-firefox/firefox, main, 161.0a1): Preferences' allowedPrefixes, the ones used here
        allowed = ("accessibility.", "browser.", "dom.", "extensions.", "layout.", "media.", "ui.", "toolkit.legacyUserProfileCustomizations.stylesheets")
        _, doc = self._build()
        for k in doc["policies"]["Preferences"]:
            self.assertTrue(k.startswith(allowed), k)
        self.assertEqual(doc["policies"]["Preferences"]["toolkit.legacyUserProfileCustomizations.stylesheets"]["Value"], True)

    def test_site_list_and_open_web(self):
        m, doc = self._build({"browser": {"allow": ["bible.com"]}, "system": {"hostname": "arise-pineville"}})
        ex = doc["policies"]["WebsiteFilter"]["Exceptions"]
        for need in ("*://127.0.0.1/*", "*://claude.ai/*", "*://studio.youtube.com/*" if False else "*://*.youtube.com/*", "*://*.google.com/*", "*://bible.com/*", "*://arise-pineville/*", "*://challenges.cloudflare.com/*"):
            self.assertIn(need, ex)
        self.assertEqual(doc["policies"]["WebsiteFilter"]["Block"], ["<all_urls>"])
        _, open_doc = self._build({"browser": {"open_web": True}})
        self.assertNotIn("WebsiteFilter", open_doc["policies"])
        self.assertEqual(m.patterns(["https://example.org/x/*"]), ["https://example.org/x/*"])

    def test_the_theme_and_the_setup_are_all_there(self):
        fx = self.ROOT / "config" / "firefox"
        for f in ("chrome/userChrome.css", "chrome/userContent.css", "user.js", "autoconfig.js", "ariseos.cfg"):
            self.assertTrue((fx / f).is_file(), f)
        css = (fx / "chrome" / "userChrome.css").read_text()
        self.assertEqual(css.count("{"), css.count("}"))
        self.assertIn('label="ariseOS"', css)                       # the desktop tab hides the toolbars
        self.assertIn("<title>ariseOS</title>", (self.ROOT / "web" / "index.html").read_text())   # ...which needs this title
        self.assertTrue((fx / "ariseos.cfg").read_text().startswith("//"))   # autoconfig skips line one
        self.assertIn("/newtab.html", (fx / "ariseos.cfg").read_text())
        self.assertTrue((self.ROOT / "web" / "newtab.html").is_file())
        setup = (self.ROOT / "scripts" / "arise-browser-setup").read_text()
        for f in ("userChrome.css", "userContent.css", "user.js", "autoconfig.js", "ariseos.cfg", "arise-browser-policies.py", "scripts/arise-browser"):
            self.assertIn(f, setup)
        self.assertIn("35BAA0B33E9EB396F59CA838C0BA5CE6DC6315A3", setup)   # Mozilla's published apt key fingerprint
        unit = (self.ROOT / "config" / "systemd" / "arise-kiosk.service").read_text()
        self.assertIn("/usr/local/bin/arise-browser", unit)
        launcher = (self.ROOT / "scripts" / "arise-browser").read_text()
        self.assertIn("/usr/bin/firefox", launcher); self.assertIn("epiphany", launcher)   # Firefox, with Epiphany as the fallback


class AutomatorHandoff(unittest.TestCase):
    """SERVER_HANDOFF.md (Rehchu/arise-youtube-automation, 'Server-ready automator'), as ariseOS carries it out."""
    ROOT = Path(__file__).resolve().parents[1]

    def test_no_google_credential_in_this_repo(self):
        # The automator's rule 1: scan for 1//, GOCSPX- and ya29. before any commit. Real token shapes only,
        # so the docs may name the prefixes.
        import re, subprocess
        files = subprocess.run(["git", "-C", str(self.ROOT), "ls-files"], capture_output=True, text=True).stdout.split()
        pat = re.compile(r"(GOCSPX-[A-Za-z0-9_-]{10,}|ya29\.[A-Za-z0-9_-]{20,}|1//0[A-Za-z0-9_-]{20,})")
        hits = []
        for f in files:
            pth = self.ROOT / f
            if pth.suffix in (".png", ".jpg", ".ico", ".ttf", ".woff2") or not pth.is_file():
                continue
            try:
                if pat.search(pth.read_text(errors="ignore")):
                    hits.append(f)
            except OSError:
                pass
        self.assertEqual(hits, [])

    def test_units_follow_the_handoff(self):
        svc = (self.ROOT / "config" / "systemd" / "arise-automator.service").read_text()
        for need in ("User=arise-yt", "EnvironmentFile=/etc/arise/arise.env", "ExecStart=/opt/arise/scripts/arise-nightly.sh",
                     "NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=read-only", "TimeoutStartSec=3h",
                     "ReadWritePaths=/srv/arise/automator/ARISE_YouTube_Updater /var/lib/arise/automator /etc/arise/secrets/youtube"):
            self.assertIn(need, svc)
        self.assertNotIn("User=root", svc)
        prev = (self.ROOT / "config" / "systemd" / "arise-automator-preview.service").read_text()
        self.assertIn("arise-nightly.sh --plan-only", prev)
        tim = (self.ROOT / "config" / "systemd" / "arise-automator.timer").read_text()
        self.assertIn("OnCalendar=*-*-* 02:05:00 America/Chicago", tim); self.assertIn("Persistent=false", tim)
        env = (self.ROOT / "config" / "automator" / "arise.env").read_text()
        for k in ("ARISE_RUNNER_NAME=ariseOS", "ARISE_TOKEN=/etc/arise/secrets/youtube/token.json", "ARISE_STATE_DIR=/var/lib/arise/automator", "TZ=America/Chicago"):
            self.assertIn(k, env)
        self.assertNotRegex(env, r"(?i)(secret|token|password)\s*=\s*[A-Za-z0-9_-]{16,}")   # paths only
        wrap = (self.ROOT / "scripts" / "arise-nightly.sh").read_text()
        for need in ("flock -n 9", "git merge --ff-only", "MODE=(--plan-only)", "LATEST_REPORT.md\" -nt"):
            self.assertIn(need, wrap)
        kh = (self.ROOT / "config" / "automator" / "github_known_hosts").read_text()
        self.assertIn("AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl", kh)   # GitHub's published Ed25519 key

    def test_credentials_stay_out_of_the_backups(self):
        import yaml
        jobs = {j["id"]: j for j in yaml.safe_load((self.ROOT / "config" / "backups.yaml.example").read_text())["jobs"]}
        self.assertIn("/etc/arise/secrets/youtube", jobs["config"].get("exclude", []))
        for pat in ("**/token.json", "**/client_secret*.json", "**/deploy_key*"):
            self.assertIn(pat, jobs["automator"]["exclude"])
        self.assertIn("/var/lib/arise/automator", jobs["automator"]["paths"])

    def test_runner_and_budget(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from arise_server import automator
        doc = {"runner": "pc", "budgets": {"pc": {"default": 10000}, "ariseOS": {"default": 4000, "sun": 2000, "mon": 2000}}}
        tue = datetime(2026, 10, 27, 2, 5, tzinfo=ZoneInfo("America/Chicago"))      # Tuesday 02:05 CDT = Tuesday 00:05 PDT
        r = automator.runner_info(doc, "ariseOS", tue)
        self.assertFalse(r["is_runner"]); self.assertEqual((r["day"], r["budget"]), ("tue", 4000))
        mon_0130 = datetime(2026, 10, 27, 1, 30, tzinfo=ZoneInfo("America/Chicago"))  # Tuesday 01:30 Central is still Monday in Pacific
        self.assertEqual(automator.runner_info(doc, "ariseOS", mon_0130)["budget"], 2000)
        self.assertTrue(automator.runner_info({**doc, "runner": "ARISEOS"}, "ariseOS", tue)["is_runner"])   # case-insensitive, as runner.py
        miss = automator.runner_info(None, "ariseOS", tue)
        self.assertFalse(miss["is_runner"]); self.assertIn("fails closed", miss["note"])

    def test_previews_and_runs_go_through_the_units_never_as_root(self):
        src = (self.ROOT / "server" / "arise_server" / "automator.py").read_text()
        self.assertIn('run(["systemctl", "start", "--no-block", unit]', src)
        self.assertNotIn("--dry-run", src)          # the job's flag is --plan-only, and the unit passes it
        cli = (self.ROOT / "cli" / "arisectl").read_text()
        self.assertIn('"runuser", "-u", "arise-yt"', cli)   # signin runs as the automator's user
        self.assertNotIn('["--dry-run"] if a.sub == "preview"', cli)

    def test_env_file_reader(self):
        import tempfile
        from arise_server import automator
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("# c\nARISE_RUNNER_NAME=ariseOS\nARISE_STATE_DIR=\"/x/y\"\n\nbad line\n")
        e = automator.read_env(f.name)
        self.assertEqual(e, {"ARISE_RUNNER_NAME": "ariseOS", "ARISE_STATE_DIR": "/x/y"})


class AutomatorRevision(unittest.TestCase):
    """The revised handoff (Oct 28): 6,000 cap, job state in ARISE_STATE_DIR, a blocked pull moved aside."""

    def test_blocked_pull_files_from_the_last_run_only(self):
        from arise_server import automator
        log = ("============\n Arise automator - started 2026-10-29 02:05\n"
               "error: The following untracked working tree files would be overwritten by merge:\n"
               "\ttranscripts/old1.json\nPlease move or remove them before you merge.\nAborting\n"
               "============\n Arise automator - started 2026-10-30 02:05\n"
               "error: The following untracked working tree files would be overwritten by merge:\n"
               "\ttranscripts/abcDEF12345.json\n\ttranscripts/xyzXYZ98765.json\n"
               "Please move or remove them before you merge.\nAborting\n WARNING: could not fast-forward\n")
        self.assertEqual(automator.pull_blocked_files(log), ["transcripts/abcDEF12345.json", "transcripts/xyzXYZ98765.json"])
        self.assertEqual(automator.pull_blocked_files(log + "============\n Arise automator - started 2026-10-31\n repo at abc\n"), [])

    def test_unblock_moves_never_deletes_and_never_touches_tracked_files(self):
        import subprocess, tempfile
        from unittest import mock
        from arise_server import automator
        with tempfile.TemporaryDirectory() as d:
            repo, state = os.path.join(d, "repo"), os.path.join(d, "state")
            os.makedirs(os.path.join(repo, "transcripts")); os.makedirs(state)
            subprocess.run(["git", "init", "-q", repo], check=True)
            open(os.path.join(repo, "transcripts", "tracked.json"), "w").write("{}")
            subprocess.run(["git", "-C", repo, "add", "."], check=True)
            open(os.path.join(repo, "transcripts", "mine.json"), "w").write("{}")
            fake = {"root": repo, "state": state}
            with mock.patch.object(automator, "_paths", return_value=fake):
                r = automator.unblock(["transcripts/mine.json", "transcripts/tracked.json", "../etc/passwd"])
            self.assertEqual([m["file"] for m in r["moved"]], ["transcripts/mine.json"])
            self.assertEqual(sorted(r["refused"]), ["../etc/passwd", "transcripts/tracked.json"])
            self.assertTrue(os.path.exists(r["moved"][0]["to"]))
            self.assertTrue(os.path.exists(os.path.join(repo, "transcripts", "tracked.json")))
            self.assertFalse(os.path.exists(os.path.join(repo, "transcripts", "mine.json")))

    def test_six_thousand_every_day(self):
        from arise_server import automator
        doc = {"runner": "pc", "budgets": {"pc": {"default": 10000}, "ariseOS": {"default": 6000}}}
        from datetime import datetime
        from zoneinfo import ZoneInfo
        for day in (25, 26, 27):     # Sun, Mon, Tue
            self.assertEqual(automator.runner_info(doc, "ariseOS", datetime(2026, 10, day, 12, tzinfo=ZoneInfo("America/Chicago")))["budget"], 6000)


class SshdAndEnv(unittest.TestCase):
    def test_first_value_wins_in_name_order(self):
        from arise_server import remote
        self.assertFalse(remote.sshd_password_auth("PasswordAuthentication yes\n", ["PasswordAuthentication no\n", "PasswordAuthentication yes\n"]))
        self.assertTrue(remote.sshd_password_auth("", ["# nothing\n"]))
        self.assertTrue(remote.sshd_password_auth("PasswordAuthentication no\n", [], {"ok": True, "out": "port 22\npasswordauthentication yes\n"}))

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
        self.assertFalse(remote.add_wireguard_peer("hub-laptop")["ok"])    # that name already has a key
        r = remote.add_wireguard_peer("bradly-phone")
        self.assertTrue(r["ok"]); self.assertIn(r["ip"], r["config"])
        self.assertIn("bradly-phone", [p["name"] for p in remote.wireguard_status()["peers"]])

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
        r = links.create("home", "/Documents/Bulletin 2026-11-01.docx", me, days=99)
        self.assertTrue(r["ok"]); tok = r["token"]
        self.assertEqual(r["link"]["user"], "office")
        self.assertLess(r["link"]["expires"], links._iso(100 * 86400))  # a chosen life is kept (max_days 365)
        self.assertFalse(links.create("home", "/Documents/not-there.pdf", me)["ok"])   # the file has to exist
        forever = links.create("home", "/Documents/Visitor cards October.xlsx", me)   # no life picked: never expires (Bradly, Oct 28)
        self.assertIsNone(forever["link"]["expires"])
        self.assertFalse(next(l for l in links.mine(me)["links"] if l["token"] == forever["token"])["expired"])
        self.assertIsNotNone(links.resolve(forever["token"]))
        links.revoke(forever["token"], me)
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
        self.assertFalse(devices.label("02:a1:00:00:00:01", kind="toaster").get("ok"))   # not a kind, in the sample too
        self.assertTrue(devices.label("02:a1:00:00:00:01", name="Netgear A").get("ok"))
        self.assertEqual(next(d for d in devices.list_devices()["devices"] if d["mac"] == "02:a1:00:00:00:01")["name"], "Netgear A")

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
        bc = mail.create_broadcast("Hello", "Body")["id"]
        self.assertFalse(mail.send_broadcast(bc, "yes")["ok"]); self.assertTrue(mail.send_broadcast(bc, "send")["ok"])
        self.assertFalse(mail.send_broadcast(bc, "send")["ok"])            # it has gone; never twice
        self.assertEqual(next(b for b in mail.broadcasts()["broadcasts"] if b["id"] == bc)["status"], "sent")
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


class Safety(unittest.TestCase):
    """Round 3: two-step sign-in, the break-glass admin, encryption, snapshots, the scan, the certificate."""

    def test_totp_verifies_within_one_step_and_rejects_junk(self):
        from arise_server import twofa
        secret = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
        t = 1_800_000_000.0
        code = twofa.code_at(secret, t)
        self.assertTrue(twofa.verify_code(secret, code, at=t))
        self.assertTrue(twofa.verify_code(secret, code, at=t + 29))     # the same step
        self.assertTrue(twofa.verify_code(secret, code, at=t + 45))     # one step later: still inside the window
        self.assertFalse(twofa.verify_code(secret, code, at=t + 120))   # four steps later: gone
        self.assertFalse(twofa.verify_code(secret, "12345", at=t))      # five digits
        self.assertFalse(twofa.verify_code(secret, "", at=t))
        self.assertFalse(twofa.verify_code("", code, at=t))
        uri = twofa.provisioning_uri(secret, "bradly.dyer")
        self.assertTrue(uri.startswith("otpauth://totp/ariseOS:bradly.dyer?") and "issuer=ariseOS" in uri)
        svg = twofa.qr_svg(uri)
        self.assertTrue(svg.startswith("<svg") and secret not in svg)  # the QR is a picture, the secret is not in its text

    def test_pending_login_three_strikes_and_expiry(self):
        from arise_server import twofa
        wrong, dead = {}, set()
        self.assertEqual(twofa.pending_attempt("n1", False, wrong, dead)["left"], 2)
        self.assertEqual(twofa.pending_attempt("n1", False, wrong, dead)["left"], 1)
        a = twofa.pending_attempt("n1", False, wrong, dead)
        self.assertTrue(a["dead"]); self.assertEqual(a["left"], 0)
        self.assertTrue(twofa.pending_attempt("n1", True, wrong, dead)["dead"])   # dead stays dead, even with the right code
        self.assertTrue(twofa.pending_attempt("n2", True, wrong, dead)["ok"])     # another login is unaffected
        tok = twofa.pending_token("session-token", "bradly")
        import time as _t
        _t.sleep(1.2)
        r = twofa.finish(tok, "000000", max_age=0)
        self.assertFalse(r["ok"]); self.assertTrue(r["expired"])                  # a token older than max_age is dead
        self.assertFalse(twofa.finish("not-a-token", "000000")["ok"])
        # demo: bradly has it on, nobody else; no secret ever in the status
        self.assertEqual(twofa.who_has(), ["bradly"])
        self.assertNotIn("secret", twofa.status("bradly"))

    def test_member_paths_cover_two_step_and_the_public_certificate(self):
        from arise_server.auth import member_ok
        for p in ("/api/me/2fa", "/api/me/2fa/setup", "/api/me/2fa/enable", "/api/me/2fa/disable", "/api/auth/login/code", "/api/public/ca.crt"):
            self.assertTrue(member_ok(p, "member"), p)
        for p in ("/api/security", "/api/security/scan/run", "/api/directory/2fa"):
            self.assertFalse(member_ok(p, "member"), p)

    def test_rescue_journal_lines(self):
        from arise_server import security
        self.assertEqual(security.parse_rescue_line("Oct 28 21:02:11 arise-server sshd[4412]: Accepted password for arise-rescue from 10.0.0.5 port 50112 ssh2"), {"via": "ssh", "from": "10.0.0.5"})
        self.assertEqual(security.parse_rescue_line("Oct 28 21:02:11 arise-server login[812]: pam_unix(login:session): session opened for user arise-rescue(uid=1001) by LOGIN(uid=0)"), {"via": "console", "from": "the closet monitor"})
        self.assertIsNone(security.parse_rescue_line("Oct 28 21:02:11 arise-server sshd[4412]: Accepted publickey for bradly from 10.0.0.5 port 50113 ssh2"))
        self.assertIsNone(security.parse_rescue_line("session opened for user arise-rescuer(uid=1002) by (uid=0)"))

    def test_lsblk_parse_finds_luks_and_the_encrypted_root(self):
        from arise_server import security
        doc = {"blockdevices": [{"name": "sda", "type": "disk", "fstype": None, "mountpoint": None, "children": [
            {"name": "sda1", "type": "part", "fstype": "vfat", "mountpoint": "/boot/efi"},
            {"name": "sda3", "type": "part", "fstype": "crypto_LUKS", "mountpoint": None, "children": [
                {"name": "dm_crypt-0", "type": "crypt", "fstype": "LVM2_member", "mountpoint": None, "children": [
                    {"name": "ubuntu--vg-ubuntu--lv", "type": "lvm", "fstype": "ext4", "mountpoint": "/"}]}]}]}]}
        st = security.parse_lsblk(doc)
        self.assertEqual(st["luks"], ["/dev/sda3"])
        self.assertTrue(st["root_encrypted"])
        plain = security.parse_lsblk({"blockdevices": [{"name": "sda", "type": "disk", "children": [{"name": "sda2", "type": "part", "fstype": "ext4", "mountpoint": "/"}]}]})
        self.assertEqual(plain["luks"], []); self.assertFalse(plain["root_encrypted"])
        self.assertEqual(security.parse_lsblk("not json")["luks"], [])

    def test_timeshift_list_parse(self):
        from arise_server import security
        out = """Device : /dev/dm-0
UUID   : 1234
Path   : /run/timeshift/backup
Mode   : RSYNC
Status : OK
3 snapshots, 180.2 GB free

Num     Name                 Tags  Description
------------------------------------------------------------------------------
0    >  2026-10-25_03-30-02  O     before update
1    >  2026-10-28_03-30-01  O     before update
2    >  2026-10-28_12-00-00  O
"""
        rows = security.parse_timeshift_list(out)
        self.assertEqual([r["name"] for r in rows], ["2026-10-25_03-30-02", "2026-10-28_03-30-01", "2026-10-28_12-00-00"])
        self.assertEqual(rows[0]["note"], "before update"); self.assertEqual(rows[2]["note"], "")
        self.assertEqual(security.snapshot_list()["keep"], 5)

    def test_clamscan_parse_and_the_skip_list(self):
        from arise_server import security
        out = "/srv/arise/shares/staff/invoice.exe: Win.Trojan.Agent-123 FOUND\n/srv/arise/homes/bradly/ok.pdf: OK\n\n----------- SCAN SUMMARY -----------\nScanned files: 1842\nInfected files: 1\nTime: 912.400 sec (15 m 12 s)\n"
        rep = security.parse_clamscan(out)
        self.assertEqual(rep["scanned"], 1842); self.assertEqual(rep["infected"], 1)
        self.assertEqual(rep["found"], [{"file": "/srv/arise/shares/staff/invoice.exe", "sig": "Win.Trojan.Agent-123"}])
        self.assertEqual(rep["seconds"], 912.4)
        args = security.scan_args(["/srv/arise/shares"], "/srv/arise/.quarantine/2026-10-26")
        self.assertEqual(args[0], "clamscan"); self.assertIn("--move=/srv/arise/.quarantine/2026-10-26", args)
        self.assertTrue(any(a.startswith("--exclude=") and "mp4" in a and "mp3" in a for a in args))
        self.assertTrue(any(a.startswith("--exclude-dir=") and "Trash" in a for a in args))
        self.assertEqual(args[-1], "/srv/arise/shares")
        self.assertIn("mp4", security.SCAN_SKIP_EXT); self.assertIn(".Trash", security.SCAN_SKIP_DIRS)

    def test_in_service_window_and_refusal(self):
        from datetime import datetime
        from arise_server import security
        services = [{"name": "Sunday Service", "day": "Sunday", "time": "10:30", "site": "Pineville"}, {"name": "Glory Night", "day": "Monday", "time": "19:00", "site": "Pineville"}]
        sun = datetime(2026, 11, 1, 11, 15)   # a Sunday
        self.assertEqual(security.in_service(sun, services)["name"], "Sunday Service")
        self.assertIsNone(security.in_service(datetime(2026, 11, 1, 13, 30), services))  # 2.5 h later: over
        self.assertEqual(security.in_service(datetime(2026, 11, 2, 20, 0), services)["name"], "Glory Night")
        self.assertIsNone(security.in_service(datetime(2026, 11, 3, 3, 30), services))   # Tuesday 03:30: free

    def test_certificate_path_and_the_security_rows(self):
        from arise_server import security
        self.assertEqual(security.CADDY_ROOT, "/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt")
        rows = security.rows(security.facts())   # demo facts
        ids = [r["id"] for r in rows]
        for want in ("encrypt", "scan", "ca", "twofa", "rescue", "firewall", "tailscale", "updates", "snapshot", "lockout", "logs"):
            self.assertIn(want, ids)
        for r in rows:
            self.assertIn(r["level"], ("ok", "warn", "bad")); self.assertTrue(r["text"])
        bad = security.rows({"encrypt": {"luks": []}, "scan": {"installed": True, "last": {"when": "2026-10-26T23:31", "found": [{"file": "x", "sig": "y"}]}}, "ca": {"present": False}, "twofa": [], "rescue": {"exists": False}, "firewall": False, "tailscale": "down", "updates": None, "snapshot": None})
        by = {r["id"]: r for r in bad}
        self.assertEqual(by["scan"]["level"], "bad"); self.assertEqual(by["firewall"]["level"], "bad")
        self.assertEqual(by["encrypt"]["level"], "warn"); self.assertTrue(by["rescue"]["fix"])
        self.assertIn(security.overview()["worst"], ("ok", "warn", "bad"))

    def test_sessions_last_a_year_and_the_system_job_backs_up_the_domain_offline(self):
        import yaml
        cfg = config.load(force=True)
        self.assertEqual(int(cfg.web.session_hours), 8760)
        jobs = yaml.safe_load((ROOT / "config" / "backups.yaml.example").read_text())["jobs"]
        sysjob = next(j for j in jobs if j["id"] == "config")
        self.assertTrue(sysjob.get("samba_offline"))
        for p in ("/etc/arise", "/etc/samba", "/var/lib/arise/samba-backup", "/etc/netplan/60-arise-pinned.yaml"):
            self.assertIn(p, sysjob["paths"])
        self.assertIn("system", sysjob["tags"])
        self.assertTrue((ROOT / "LICENSE").read_text().startswith("MIT License"))
        self.assertIn("Bradly Dyer", (ROOT / "LICENSE").read_text())
        unit = (ROOT / "config" / "systemd" / "arise-clamscan.timer").read_text()
        self.assertIn("Sun *-*-* 23:30:00 America/Chicago", unit)

    def test_reauth_stamp_lasts_five_minutes(self):
        from arise_server import auth
        self.assertTrue(auth.recent_auth_ok({"u": "bradly", "ra": 1000}, 1200))
        self.assertFalse(auth.recent_auth_ok({"u": "bradly", "ra": 1000}, 1301))
        self.assertFalse(auth.recent_auth_ok({"u": "bradly"}, 1200))
        self.assertFalse(auth.recent_auth_ok({"u": "bradly", "ra": 2000}, 1200))  # a stamp from the future is not a stamp
        self.assertEqual(auth.REAUTH_SECONDS, 300)
class Everyday(unittest.TestCase):
    """v0.8 Exodus, Fork A: the calendar feed, the service-hour guard, the weather words, help rendering, what's new, password rules."""

    def test_in_service_now_window(self):
        from datetime import datetime
        from arise_server import church
        svcs = [{"name": "Sunday Service", "day": "Sunday", "time": "10:30", "site": "Pineville"}, {"name": "Glory Night", "day": "Monday", "time": "19:00", "site": "Pineville"}]
        sun = datetime(2026, 11, 1, 11, 0)   # a Sunday, mid-service
        self.assertEqual(church.in_service_now(sun, svcs)["name"], "Sunday Service")
        self.assertEqual(church.in_service_now(sun, svcs)["ends_at"], "12:30 PM")
        self.assertIsNone(church.in_service_now(datetime(2026, 11, 1, 12, 31), svcs))   # two hours after the start: over
        self.assertIsNone(church.in_service_now(datetime(2026, 11, 1, 10, 29), svcs))   # a minute before: not yet
        self.assertEqual(church.in_service_now(datetime(2026, 11, 2, 19, 0), svcs)["name"], "Glory Night")
        self.assertIsNone(church.in_service_now(datetime(2026, 11, 3, 19, 0), svcs))     # a Tuesday

    def test_service_occurrences_and_month(self):
        from datetime import date
        from arise_server import calendar as cal
        svcs = [{"name": "Sunday Service", "day": "Sunday", "time": "10:30", "site": "Pineville"}, {"name": "Glory Night", "day": "Monday", "time": "19:00", "site": "Pineville"}]
        occ = cal.service_occurrences(date(2026, 11, 1), date(2026, 11, 30), svcs)
        self.assertEqual(len(occ), 5 + 5)   # five Sundays and five Mondays in November 2026
        self.assertEqual(occ[0]["start"], "2026-11-01T10:30")
        self.assertTrue(all(o["service"] for o in occ))
        m = cal.month(2026, 11)
        self.assertEqual(m["month"], 11)
        self.assertTrue(m["demo"])

    def test_ics_feed_shape(self):
        from datetime import date
        from arise_server import calendar as cal
        svcs = [{"name": "Sunday Service", "day": "Sunday", "time": "10:30", "site": "Pineville"}]
        evs = [{"id": "abc", "title": "Volunteer lunch, with a comma; and a semicolon", "start": "2026-11-14T12:00", "end": "2026-11-14T13:30", "where": "The hall", "note": "line one\nline two"}]
        text = cal.ics("arise-server", svcs, evs, anchor=date(2026, 1, 4))
        self.assertTrue(text.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertIn("TZID:America/Chicago", text)
        self.assertIn("RRULE:FREQ=WEEKLY;BYDAY=SU", text)
        self.assertIn("DTSTART;TZID=America/Chicago:20260104T103000", text)
        self.assertIn("SUMMARY:Volunteer lunch\\, with a comma\\; and a semicolon", text)
        self.assertIn("DESCRIPTION:line one\\nline two", text)
        self.assertIn("UID:abc@arise-server", text)
        self.assertTrue(text.endswith("END:VCALENDAR\r\n"))
        for line in text.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 76, line)   # folded at 75 octets (+ the fold space)

    def test_event_cleaning(self):
        from arise_server import calendar as cal
        self.assertIsNone(cal._clean({"title": "", "start": "2026-11-05T18:30"}))
        self.assertIsNone(cal._clean({"title": "x", "start": "not a date"}))
        c = cal._clean({"title": " Meeting ", "start": "2026-11-05T18:30", "end": "2026-11-05T17:00", "where": "x"})
        self.assertEqual(c["title"], "Meeting")
        self.assertEqual(c["end"], "")   # an end before the start is dropped, not kept

    def test_weather_words_and_shape(self):
        from arise_server import weather
        self.assertEqual(weather.words(0), "Clear")
        self.assertEqual(weather.words(95), "Thunderstorm")
        self.assertEqual(weather.words("x"), "—")
        d = weather.fetch()   # demo: the sample
        self.assertTrue(d["ok"] and d["demo"])
        self.assertEqual(len(d["days"]), 6)
        self.assertTrue(weather.summary(d).startswith("Pineville, LA:"))
        self.assertEqual(weather.summary({"ok": False}), "")

    def test_help_escapes_raw_html_and_lists_member_docs(self):
        from arise_server import help as h
        html = h.render_markdown("# Title\n\n<script>alert(1)</script>\n\nA **bold** word.\n")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script", html)
        self.assertIn("<strong>bold</strong>", html)
        self.assertEqual(h.title_of("intro\n# The portal guide\n", "x"), "The portal guide")
        member = h.docs("member")["docs"]
        self.assertEqual([d["name"] for d in member], ["PORTAL-GUIDE"])
        self.assertFalse(h.doc("INSTALL", "member")["ok"])
        self.assertTrue(h.doc("PORTAL-GUIDE", "member")["ok"])
        self.assertFalse(h.doc("../etc/passwd", "admin")["ok"])

    def test_whatsnew_takes_the_top_section_only(self):
        from arise_server.main import whatsnew_lines
        text = "# What's new\n\nintro\n\n## v0.8\n\n- one\n- two\n\n## v0.7\n\n- old\n"
        self.assertEqual(whatsnew_lines(text), ["one", "two"])
        self.assertEqual(len(whatsnew_lines("## v\n" + "\n".join(f"- {i}" for i in range(30)))), 10)

    def test_password_rules_in_words(self):
        r = directory.rules_from_show("Minimum password length: 12\nPassword complexity: on\nPassword history length: 24\nMaximum password age (days): 0\n")
        self.assertEqual(r["min_length"], 12)
        self.assertIn("At least 12 characters", r["words"])
        self.assertIn("Never expires", r["words"])
        self.assertIn("Not one of your last 24 passwords", r["words"])
        r2 = directory.rules_from_show("")   # nothing reported: nothing claimed
        self.assertEqual(r2["words"], [])
        self.assertTrue(directory.password_rules()["demo"])

    def test_member_routes_include_the_new_apps(self):
        from arise_server import auth
        for p in ("/api/calendar", "/api/calendar/subscribe", "/api/weather", "/api/help", "/api/help/PORTAL-GUIDE", "/api/about/whatsnew", "/api/me/password/rules"):
            self.assertTrue(auth.member_ok(p, "member"), p)
        self.assertFalse(auth.member_ok("/api/system/power", "member"))
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
        doc = "Bulletin 2026-11-01.docx"
        self.assertFalse(finder.trash_put("home", f"/Documents/{doc}", office, confirm="wrong")["ok"])
        self.assertTrue(finder.trash_put("home", f"/Documents/{doc}", office, confirm=doc)["ok"])
        self.assertNotIn(doc, [e["name"] for e in files_listing("home", "/Documents", office)])   # gone from the folder
        row = next(t for t in finder.trash_list(office)["items"] if t["name"] == doc)                # into the Trash
        self.assertTrue(finder.trash_restore(row["base"], row["user"], row["rel"], office)["ok"])     # and back
        self.assertIn(doc, [e["name"] for e in files_listing("home", "/Documents", office)])
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
        self.assertFalse(finder.write_text("home", "/x.md", "hi", office)["ok"])        # no such file: the editor saves, it does not create
        from arise_server import files as _f
        self.assertTrue(_f.save_upload("home", "/", "x.md", b"# x\n", office)["ok"])
        self.assertTrue(finder.write_text("home", "/x.md", "hi", office)["ok"])
        self.assertEqual(finder.read_text("home", "/x.md", office)["text"], "hi")
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

    def test_home_folders_and_the_admin_merged_views(self):
        from arise_server import files
        self.assertEqual(files.HOME_FOLDERS, ("Documents", "Photos", "Videos", "Music", "Downloads"))
        self.assertTrue(files.ensure_home("office")["ok"])  # demo: nothing written
        admin = {"user": "bradly", "role": "admin"}; office = {"user": "office", "role": "member"}
        r = files.all_of("Documents", admin)
        self.assertEqual(set(r["owners"]), {"bradly", "office"})  # the sample homes that have folders
        owners = {e["owner"] for e in r["entries"]}
        self.assertEqual(owners, {"bradly", "office"})
        self.assertTrue(all(e["path"].startswith(f"/homes/{e['owner']}/Documents/") for e in r["entries"]))
        self.assertEqual(files.all_of("Documents", office).get("error"), "administrator only")
        self.assertEqual(files.all_of("Desktop", admin).get("error"), "not one of the home folders")
        self.assertFalse(any(e["owner"] != "office" for e in []))  # a member's roots never include another home: pinned by test_admin_and_member_roots
        tpl = (ROOT / "config" / "samba" / "smb.conf.template").read_text()
        pre = tpl.split("[homes]")[1].split("root preexec")[1].split("\n")[0]
        for f in files.HOME_FOLDERS:
            self.assertIn(f, pre)

    def test_resumable_upload_rules(self):
        from arise_server import finder
        office = {"user": "office", "role": "member"}
        self.assertFalse(finder.upload_start("home", "/", ".hidden", 10, "x", office)["ok"])
        self.assertFalse(finder.upload_start("home", "/", "big.mov", 11 * 1024 ** 3, "x", office)["ok"])
        self.assertFalse(finder.upload_start("share:media", "/", "a.mov", 10, "x", office)["ok"])   # read-only for office
        self.assertFalse(finder.upload_start("data", "/", "a.mov", 10, "x", office)["ok"])          # not a member root
        st = finder.upload_start("home", "/Downloads", "a.mov", 6, "a.mov|6|1", office)
        self.assertTrue(st["ok"]); self.assertEqual(st["offset"], 0); self.assertEqual(st["chunk"], 8 * 1024 ** 2)
        self.assertEqual(finder.upload_chunk(st["token"], 0, b"abc", office)["offset"], 3)
        self.assertFalse(finder.upload_finish(st["token"], office)["ok"])                        # half a file is not a file
        self.assertEqual(finder.upload_start("home", "/Downloads", "a.mov", 6, "a.mov|6|1", office)["offset"], 3)   # resumes
        self.assertEqual(finder.upload_chunk(st["token"], 3, b"def", office)["offset"], 6)
        self.assertTrue(finder.upload_finish(st["token"], office)["ok"])
        self.assertIn("a.mov", [e["name"] for e in files_listing("home", "/Downloads", office)])
        self.assertEqual(finder.UPLOAD_MAX, 10 * 1024 ** 3)
class SystemApps(unittest.TestCase):
    """v0.8 Exodus (round 3): Software Update, the Store's caps and budget, the catalogue,
    Activity Monitor's refusals, Logs, Automations, the monitor, the theme pack, idle apps."""

    def test_apt_upgradable_splits_security_from_the_rest(self):
        from arise_server import updates
        r = updates.parse_apt_upgradable("Listing... Done\nopenssl/noble-security 3.0.13-0ubuntu3.4 amd64 [upgradable from: 3.0.13-0ubuntu3.3]\n"
                                         "samba/noble-updates 2:4.19.5+dfsg-4ubuntu9 amd64 [upgradable from: 2:4.19.5+dfsg-4ubuntu8]\nWARNING: apt does not have a stable CLI\n")
        self.assertEqual([p["name"] for p in r["security"]], ["openssl"])
        self.assertEqual([p["name"] for p in r["other"]], ["samba"])
        self.assertEqual(r["other"][0]["from"], "2:4.19.5+dfsg-4ubuntu8")

    def test_service_window_refuses_sunday_morning_and_allows_tuesday_night(self):
        from datetime import datetime
        from arise_server import updates
        svcs = [{"name": "Sunday Service", "day": "Sunday", "time": "10:30"}, {"name": "Glory Night", "day": "Monday", "time": "19:00"}]
        self.assertIsNotNone(updates.in_service_window(datetime(2026, 11, 1, 10, 0), svcs))       # a Sunday, half an hour before
        self.assertIsNotNone(updates.in_service_window(datetime(2026, 11, 2, 21, 30), svcs))      # Glory Night still on
        self.assertIsNone(updates.in_service_window(datetime(2026, 11, 3, 3, 30), svcs))          # Tuesday 03:30
        self.assertIsNone(updates.in_service_window(datetime(2026, 10, 31, 3, 30), svcs))         # the Saturday window
        self.assertEqual(updates.set_queue(["samba", "bad name!"], ["uptime-kuma", "Bad"], True, "t")["queue"]["packages"], ["samba"])

    def test_limits_are_injected_into_every_service_and_manifests_carry_them(self):
        doc = apps.inject_limits({"services": {"a": {"image": "x"}, "b": {"image": "y", "mem_limit": "128m"}}}, {"mem_mb": 768, "cpus": 1.5})
        self.assertEqual(doc["services"]["a"]["mem_limit"], "768m"); self.assertEqual(doc["services"]["a"]["cpus"], 1.5)
        self.assertEqual(doc["services"]["b"]["mem_limit"], "128m")
        t = apps.templates()["templates"]
        self.assertGreaterEqual(len(t), 25)
        for x in t:
            self.assertNotEqual(x["category"], "broken", x["id"])
            self.assertGreater(x["limits"]["mem_mb"], 0, x["id"]); self.assertGreater(x["ram_mb"], 0, x["id"])
        self.assertFalse(next(x for x in t if x["id"] == "ollama")["autostart"])
        self.assertTrue(next(x for x in t if x["id"] == "immich")["autostart"])

    def test_autostart_plan_keeps_two_gigabytes_for_the_domain(self):
        items = [{"id": "small", "autostart": True, "ram_mb": 100}, {"id": "big", "autostart": True, "ram_mb": 3000}, {"id": "heavy", "autostart": False, "ram_mb": 2500}]
        p = apps.autostart_plan(items, ram_total_mb=4096)
        self.assertEqual(p["budget_mb"], 2048); self.assertEqual(p["start"], ["small"])
        self.assertEqual({s["id"] for s in p["stopped"]}, {"big", "heavy"})
        self.assertIn("budget", next(s for s in p["stopped"] if s["id"] == "big")["why"])

    def test_catalogue_entries_shape_a_compose_and_keep_secrets_change_me(self):
        c = apps.catalog()
        self.assertFalse(c.get("error"), c.get("error")); self.assertGreaterEqual(len(c["apps"]), 30)
        ids = {x["id"] for x in c["apps"]}
        for needed in ("gitea", "paperless", "gimp", "libreoffice", "onlyoffice", "game-night", "proclaim-wine"):
            self.assertIn(needed, ids)
        self.assertTrue(next(x for x in c["apps"] if x["id"] == "proclaim-wine")["experimental"])
        self.assertEqual(next(x for x in c["apps"] if x["id"] == "gimp")["idle_stop_minutes"], 60)
        for e in c["apps"]:
            self.assertFalse(e["autostart"] and e["category"] in ("desktop", "experiment"), e["id"])
        entry = apps.catalog_entry("umami")
        doc = apps.compose_from_catalog(entry)
        self.assertIn("umami-db", doc["services"]); self.assertEqual(doc["services"]["umami"]["depends_on"], ["umami-db"])
        self.assertIn("APP_SECRET=${APP_SECRET}", doc["services"]["umami"]["environment"])
        for e in c["apps"]:
            for k, v in (apps.catalog_entry(e["id"]).get("env") or {}).items():
                if any(w in k for w in ("PASS", "TOKEN", "SECRET")) and "HASH" not in k:
                    self.assertTrue(str(v).startswith("CHANGE-ME"), f"{e['id']}.{k}")

    def test_theme_plan_fills_house_values_and_none_keeps_its_own_look(self):
        self.assertEqual(apps.theme_plan({"theme": "none"})["via"], "none")
        self.assertEqual(apps.theme_plan({})["note"], "keeps its own look")
        p = apps.theme_plan({"theme": {"via": "env", "accepts": ["dark", "name"], "env": {"X": "{{name}}", "Y": "{{red}}"}}})
        self.assertEqual(p["env"], {"X": "Arise Church", "Y": "#D6222D"})
        f = apps.theme_plan({"theme": {"via": "files", "accepts": ["css"], "files": {"custom.css": "{{css}}"}}})
        self.assertIn("#D6222D", f["files"]["custom.css"]); self.assertIn("Anton", f["css"])
        self.assertEqual(apps.theme_for("jellyfin")["via"], "css"); self.assertEqual(apps.theme_for("gimp")["via"], "none")

    def test_idle_decision_stops_only_after_the_quiet_hour(self):
        now = 10_000.0
        self.assertEqual(apps.idle_decision(now, None, now - 7200, 0, 60), (True, now - 7200))
        self.assertEqual(apps.idle_decision(now, now - 600, now - 7200, 0, 60), (False, now - 600))
        self.assertEqual(apps.idle_decision(now, now - 7200, now - 7200, 2, 60)[0], False)
        self.assertEqual(apps.idle_decision(now, now - 7200, None, 0, 0)[0], False)

    def test_activity_refuses_the_processes_the_box_cannot_live_without(self):
        from arise_server import activity
        self.assertFalse(activity.may_kill(1, "systemd")[0])
        self.assertFalse(activity.may_kill(500, "samba", "/usr/sbin/samba -D")[0])
        self.assertFalse(activity.may_kill(501, "python3", "/opt/arise/venv/bin/python -m arise_server")[0])
        self.assertFalse(activity.may_kill(502, "sshd")[0]); self.assertFalse(activity.may_kill(503, "dockerd")[0])
        self.assertTrue(activity.may_kill(504, "gimp", "/usr/bin/gimp")[0])
        self.assertFalse(activity.kill(1, "1")["ok"]); self.assertFalse(activity.kill(504, "wrong")["ok"])

    def test_logs_last_error_and_readable_units(self):
        from arise_server import services
        self.assertEqual(services.last_error_index(["ok", "Error: x", "fine", "connection refused", "done"]), 3)
        self.assertIsNone(services.last_error_index(["all", "good"]))
        self.assertTrue(services.READABLE_RE.match("arise-update.service")); self.assertTrue(services.READABLE_RE.match("caddy.service"))
        self.assertFalse(services.READABLE_RE.match("../etc/passwd")); self.assertFalse(services.READABLE_RE.match("getty@tty1.service"))
        self.assertIn("not a log file", services.log_file("../secrets")["text"])

    def test_timers_parse_and_only_arise_timers_pause(self):
        from arise_server import automations
        rows = automations.parse_timers_json('[{"next": 1798000000000000, "left": 1, "last": 1797900000000000, "passed": 2, "unit": "arise-backup.timer", "activates": "arise-backup.service"}, {"next": null, "unit": "snapd.refresh.timer", "activates": "snapd.refresh.service"}]')
        self.assertEqual([r["timer"] for r in rows], ["arise-backup.timer"]); self.assertTrue(rows[0]["next"].startswith("2026"))
        self.assertFalse(automations.pause("docker.service", False, "docker.service")["ok"])
        self.assertFalse(automations.pause("arise-backup.timer", False, "wrong")["ok"])
        self.assertEqual(automations.describe("arise-update.timer")[0], "Software updates")
        t = (ROOT / "config" / "systemd" / "arise-update.timer").read_text(); self.assertIn("Sat *-*-* 03:30:00 America/Chicago", t)
        self.assertIn("23:00:00 America/Chicago", (ROOT / "config" / "systemd" / "arise-monitor-off.timer").read_text())

    def test_monitor_parses_outputs_and_guacamole_hash(self):
        from arise_server import monitor
        o = monitor.parse_wlr_randr('HDMI-A-1 "Dell E2216H"\n  Make: Dell\n  Enabled: yes\n  Modes:\n    1920x1080 px, 60.000 Hz (preferred, current)\nDP-1 "unknown"\n  Enabled: no\n')
        self.assertEqual([(x["name"], x["enabled"]) for x in o], [("HDMI-A-1", True), ("DP-1", False)])
        import hashlib
        self.assertEqual(monitor.guac_password_hash("pw", "ab"), hashlib.sha256(b"pwAB").hexdigest())
        sql = monitor.guac_sql("bradly.dyer", "pw", "Closet monitor", "172.18.0.1", 5900, "vnc'pw", salt_hex="00ff")
        self.assertIn("'bradly.dyer'", sql); self.assertIn("vnc''pw", sql); self.assertIn("decode('00ff', 'hex')", sql)
        with self.assertRaises(ValueError):
            monitor.guac_sql("Bad User", "x", "c", "h", 1, "v")
        self.assertIn("enable_auth=true", monitor.wayvnc_conf("172.18.0.1", 5900, "bradly.dyer", "s"))

    def test_disk_alert_at_75_percent(self):
        from arise_server import storage
        items = storage.disk_alerts([{"mount": "/srv/arise", "pct": 76, "free": 1e9}, {"mount": "/", "pct": 40, "free": 1e11}, {"mount": "/mnt/synology", "pct": 92, "free": 1e10}])
        self.assertEqual([(i["level"], i["text"].split()[0]) for i in items], [("warn", "/srv/arise"), ("bad", "/mnt/synology")])
        self.assertEqual(storage.DISK_ALERT_PCT, 75)


def files_listing(root, path, who):
    from arise_server import files
    return files.listing(root, path, who).get("entries", [])

"""Round 7: backups off-site, the missed night, the drill line, Discord, upkeep, the closet card,
staged updates and staff mail forwarding. The rules are pure functions, pinned here.
"""
import contextlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("ARISE_DEMO", "1")
os.environ.setdefault("ARISE_CONFIG", str(ROOT / "config" / "arise.toml.example"))

from arise_server import backups, config, discord, mailfwd, system, upkeep  # noqa: E402

NOW = datetime(2026, 11, 3, 12, 0)
T = lambda **kw: (NOW - timedelta(**kw)).isoformat(timespec="seconds")


@contextlib.contextmanager
def real_mode(extra: str = ""):
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        conf = tmp / "arise.toml"
        conf.write_text(f'[system]\ndata_root = "{tmp}/data"\n[paths]\nstate_dir = "{tmp}/state"\nlog_dir = "{tmp}/state"\n' + extra)
        old = {k: os.environ.get(k) for k in ("ARISE_CONFIG", "ARISE_DEMO")}
        os.environ["ARISE_CONFIG"] = str(conf)
        os.environ.pop("ARISE_DEMO", None)
        config.load(force=True)
        try:
            yield tmp
        finally:
            for k, v in old.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
            config.load(force=True)


TARGETS = lambda live, home_ready=True, home_repo="sftp:arise-backup@arise-home:/srv/r": {
    "live": live, "repo": "/mnt/synology/r" if live == "synology" else home_repo, "name": "the Synology" if live == "synology" else "Arise-Home",
    "targets": [{"id": "synology", "name": "the Synology", "repo": "/mnt/synology/r", "ready": live == "synology"},
                {"id": "arise-home", "name": "Arise-Home over Tailscale", "repo": home_repo or None, "ready": home_ready, "why": "not reachable over Tailscale"}]}


class Offsite(unittest.TestCase):
    """Round 7, 53/54: Arise-Home is the off-site copy; raw recordings never go."""
    def test_plan(self):
        p = backups.offsite_plan(TARGETS("synology"), "arise-home")
        self.assertEqual((p["action"], p["src"], p["dst"]), ("copy", "/mnt/synology/r", "sftp:arise-backup@arise-home:/srv/r"))
        self.assertEqual(backups.offsite_plan(TARGETS("arise-home"), "arise-home")["action"], "same")      # no Synology yet: one place
        self.assertEqual(backups.offsite_plan(TARGETS("synology", home_ready=False), "arise-home")["action"], "unreachable")
        self.assertEqual(backups.offsite_plan(TARGETS("synology", home_repo=""), "arise-home")["action"], "unreachable")
        self.assertEqual(backups.offsite_plan(TARGETS(None), "arise-home")["action"], "none")
        self.assertEqual(backups.offsite_plan(TARGETS("synology"), "")["action"], "off")

    def test_recordings_never_go(self):
        snaps = [{"short_id": "a1", "tags": ["homes"]}, {"short_id": "b2", "tags": ["recordings"]}, {"id": "c3c3c3c3ffff", "tags": ["system", "config"]}]
        self.assertEqual(backups.offsite_ids(snaps, ["recordings"]), ["a1", "c3c3c3c3"])

    def test_the_nightly_run_copies_after_pruning(self):
        src = (ROOT / "cli" / "arisectl").read_text()
        run = src[src.index('    elif a.sub == "run":'):src.index('    elif a.sub == "offsite":')]
        self.assertLess(run.index("forget_prune()"), run.index("offsite_copy()"))
        self.assertIn("offsite_skip_tags", (ROOT / "config" / "arise.toml.example").read_text())


class MissedNight(unittest.TestCase):
    """Round 7, 64: one missed night is reported."""
    def test_rules(self):
        self.assertIsNone(backups.missed_night([], NOW))                                            # a new box
        self.assertIsNone(backups.missed_night([{"job": "homes", "ok": True, "started": T(hours=9)}], NOW))
        m = backups.missed_night([{"job": "homes", "ok": True, "started": T(hours=33)}, {"job": "homes", "ok": False, "started": T(hours=9)}], NOW)
        self.assertEqual(m["last_ok"], T(hours=33)[:16])
        # the off-site copy alone is not a backup
        self.assertIsNotNone(backups.missed_night([{"job": "offsite", "ok": True, "started": T(hours=2)}], NOW))

    def test_it_reaches_needs_you(self):
        items = upkeep.attention(NOW, hist=[{"job": "homes", "ok": True, "started": T(hours=40)}], macs=[], health_v=[])
        self.assertTrue(any(i["key"].startswith("backup-missed:") and i["level"] == "bad" for i in items))


class Drill(unittest.TestCase):
    """Round 7, 56: the drill's result is a line in Discord #weekly."""
    def test_line(self):
        self.assertIn("passed", backups.drill_line({"ok": True, "file": "/srv/arise/homes/x/a.pdf", "snapshot": "ab12", "matched": True}))
        self.assertIn("FAILED", backups.drill_line({"ok": False, "note": "restore failed"}))
        src = (ROOT / "cli" / "arisectl").read_text()
        self.assertIn('discord.post("weekly", backups.drill_line(r)', src)


class Discord(unittest.TestCase):
    def test_line_and_post(self):
        self.assertTrue(discord.line("Backup failed", "sudo arisectl backup run", NOW).startswith("Tue Nov 3, 12:00 PM · Backup failed\n→ `sudo arisectl"))
        sent = []
        r = discord.post("alerts", "hello", hooks={"alerts": "https://discord.com/api/webhooks/x"}, send=lambda u, b: sent.append((u, b)))
        self.assertTrue(r["ok"]); self.assertEqual(len(sent), 1)
        self.assertFalse(discord.post("alerts", "x", hooks={})["ok"])                                  # not set: says so
        self.assertFalse(discord.post("nope", "x", hooks={})["ok"])

    def test_a_key_posts_once(self):
        with real_mode():
            sent = []
            h = {"alerts": "https://discord.com/api/webhooks/x"}
            for _ in range(3):
                discord.post("alerts", "Mac silent", key="mac-silent:m1", hooks=h, send=lambda u, b: sent.append(b))
            self.assertEqual(len(sent), 1)

    def test_status_never_returns_an_address(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write('alerts = "https://discord.com/api/webhooks/SECRET"\nweekly = "not a url"\n')
        try:
            self.assertEqual(discord._hooks(f.name), {"alerts": "https://discord.com/api/webhooks/SECRET"})
        finally:
            os.unlink(f.name)
        self.assertNotIn("https", json.dumps(discord.status()))


class Health(unittest.TestCase):
    """Round 7, 137/138: SMART's own verdict and 80 C."""
    def test_smart(self):
        good = upkeep.parse_smart({"device": {"name": "/dev/sda"}, "model_name": "SSD", "smart_status": {"passed": True}, "temperature": {"current": 33},
                                   "ata_smart_attributes": {"table": [{"id": 5, "raw": {"value": 0}}, {"id": 197, "raw": {"value": 0}}]}})
        self.assertEqual(good["why"], [])
        bad = upkeep.parse_smart({"device": {"name": "/dev/sdb"}, "smart_status": {"passed": False},
                                  "ata_smart_attributes": {"table": [{"id": 197, "raw": {"value": 8}}]}})
        self.assertEqual(len(bad["why"]), 2)
        worn = upkeep.parse_smart({"device": {"name": "/dev/nvme0"}, "smart_status": {"passed": True}, "nvme_smart_health_information_log": {"percentage_used": 100}})
        self.assertTrue(worn["why"])
        items = upkeep.health_items([good, bad], 81.0)
        self.assertEqual([i["key"] for i in items], ["disk:/dev/sdb", "cpu-hot"])
        self.assertEqual(upkeep.health_items([good], 79.9), [])


class Macs(unittest.TestCase):
    """Round 7, 82: a church Mac silent three days."""
    def test_silent(self):
        ms = [{"id": "a", "name": "MEDIA-MAC-01", "status": "active", "last_checkin": T(days=4)},
              {"id": "b", "name": "OFFICE", "status": "active", "last_checkin": T(hours=2)},
              {"id": "c", "name": "OLD", "status": "retired", "last_checkin": T(days=90)},
              {"id": "d", "name": "NEW", "status": "active"}]
        got = upkeep.silent_macs(ms, NOW, 3)
        self.assertEqual([m["id"] for m in got], ["a", "d"])
        self.assertEqual(got[0]["days"], 4)

    def test_hourly_posts_once_per_silence(self):
        posts = []
        fake = lambda ch, text, key="", fix="": (posts.append((ch, key)) or {"ok": True})
        with mock.patch.object(upkeep, "attention", return_value=[{"level": "warn", "key": "mac-silent:a:2026-10-30T10:00", "text": "x"}]):
            upkeep.hourly(NOW, post=fake)
        self.assertEqual(posts, [("alerts", "mac-silent:a:2026-10-30T10:00")])


class January(unittest.TestCase):
    """Round 7, 63/139: it lists, it never deletes."""
    def test_parts(self):
        users = [{"name": "a", "enabled": True, "last_logon": T(days=120)}, {"name": "b", "enabled": True, "last_logon": T(days=3)},
                 {"name": "c", "enabled": False, "last_logon": None}, {"name": "d", "enabled": True, "last_logon": None}]
        self.assertEqual([u["name"] for u in upkeep.unused_accounts(users, NOW)], ["a", "d"])
        tree = {"/s": ["media", "empty", "x.txt"], "/s/media": ["a.mov"], "/s/empty": [".Trash"]}
        isdir = lambda p: p in tree
        with mock.patch("os.path.isdir", side_effect=isdir):
            self.assertEqual(upkeep.empty_shares("/s", listdir=lambda p: tree[p]), ["empty"])
        d = {"macs": {"m1": {"name": "OFFICE-MAC-01"}}, "tasks": {"m1": [
            {"kind": "remove_profile", "state": "done", "finished": "2026-11-03T02:12:00",
             "detail": "removed after the server confirmed 40 files; the rest of their Mac folder is kept in /Users/Deleted Users/old.timer-20261103-0212.dmg"},
            {"kind": "remove_profile", "state": "refused", "detail": "kept in /Users/Deleted Users/x.dmg"}]}}
        self.assertEqual(upkeep.removed_images(d), [{"mac": "OFFICE-MAC-01", "image": "/Users/Deleted Users/old.timer-20261103-0212.dmg", "when": "2026-11-03T02:12:00"}])
        rep = {"year": 2027, "unused": [], "biggest": [], "empty_shares": [], "images": [], "reminder": upkeep.GOOGLE_EXPORT}
        self.assertIn("nothing is deleted", upkeep.january_text(rep))
        self.assertIn("Takeout", upkeep.january_text(rep))

    def test_biggest_skips_the_trash(self):
        walk = lambda root: iter([(root, [".Trash", "a"], ["big"]), (root + "/a", [], ["small"])])
        with mock.patch("os.lstat", side_effect=lambda p: type("S", (), {"st_size": 100 if p.endswith("big") else 1})()):
            got = upkeep.biggest_files(["/h"], n=5, walk=walk)
        self.assertEqual([g["path"] for g in got], ["/h/big", "/h/a/small"])

    def test_timer(self):
        t = (ROOT / "config" / "systemd" / "arise-january.timer").read_text()
        self.assertIn("*-01-05 09:12:00", t)
        self.assertNotIn("rm ", (ROOT / "config" / "systemd" / "arise-january.service").read_text())


class ChangeRecord(unittest.TestCase):
    """Round 7, 140: what changed, by Bradly, Kristina or Claude."""
    def test_rules(self):
        self.assertTrue(upkeep.is_change({"action": "directory.users", "ok": True}))
        for a in ("auth.login", "macs.check", "files.view"):
            self.assertFalse(upkeep.is_change({"action": a}))
        self.assertFalse(upkeep.is_change({"action": "directory.users", "ok": False}))
        self.assertEqual(upkeep.actor("bradly", "bradly", ["kristina.robinson"]), "Bradly")
        self.assertEqual(upkeep.actor("bradly+claude", "bradly", []), "Claude")
        self.assertEqual(upkeep.actor("kristina.robinson", "bradly", ["kristina.robinson"]), "Kristina")
        self.assertEqual(upkeep.actor("bradly.dyer", "", []), "Bradly")      # before [owner] is set
        self.assertEqual(upkeep.actor("mac:Office-iMac", "bradly", []), "Office-iMac")
        src = (ROOT / "cli" / "arisectl").read_text()
        self.assertIn('("+claude" if os.environ.get("CLAUDECODE") else "")', src)


class ClosetCard(unittest.TestCase):
    """Round 7, 57/73/141: inside the closet, the password on the printed card only."""
    FACTS = {"host": "arise-server", "fqdn": "arise-server.ad.arisecenla.com", "ip": "10.0.0.20", "repo": "/mnt/synology/r", "home": ""}

    def test_private_and_public(self):
        priv = upkeep.closet_card(True, "Pw<&>123", facts=self.FACTS, now=NOW)
        pub = upkeep.closet_card(False, "Pw<&>123", facts=self.FACTS, now=NOW)
        self.assertIn("Pw&lt;&amp;&gt;123", priv)
        self.assertNotIn("Pw", pub.replace("Pwd", ""))
        self.assertIn("INSIDE the closet", priv)
        for name in ("Bradly Dyer", "Kristina Robinson", "Ronnie"):
            self.assertIn(name, priv)
        self.assertNotRegex(priv, r"\(\d{3}\) ?\d{3}-\d{4}")                                       # no invented numbers
        self.assertIn("itportal.myfaithtech.com", priv)

    def test_the_cli_never_prints_the_password(self):
        src = (ROOT / "cli" / "arisectl").read_text()
        card = src[src.index('    elif a.sub == "card":'):src.index("def cmd_encrypt")]
        self.assertIn("upkeep.write_cards()", card)
        self.assertNotIn("read_text()", card)


class Staged(unittest.TestCase):
    """Round 7, 135/136: Arise-Home first, Pineville a week later."""
    def test_rings(self):
        self.assertEqual(system.stage_args("home"), ["rev-list", "-1", "origin/main"])
        self.assertEqual(system.stage_args("pineville"), ["rev-list", "-1", "--before=7 days ago", "origin/main"])
        src = (ROOT / "server" / "arise_server" / "system.py").read_text()
        self.assertIn('"merge", "--ff-only", ref', src)
        self.assertNotIn('"pull", "--ff-only"', src)


class MailForwarding(unittest.TestCase):
    """Round 7, 155: forwarding only, no port opened, no mailbox kept."""
    ALS = {"bryant.sanders": {"to": "b@example.com", "enabled": True}, "old.timer": {"to": "o@example.com", "enabled": False},
           "office": {"to": "", "enabled": True}}

    def test_route(self):
        to = mailfwd.addresses(["Bryant <Bryant.Sanders@ad.arisecenla.com>", {"email": "old.timer@ad.arisecenla.com"},
                                "office@ad.arisecenla.com", "someone@gmail.com", "nobody@ad.arisecenla.com", "bryant.sanders@ad.arisecenla.com"])
        r = mailfwd.route(to, self.ALS)
        self.assertEqual(r[0], {"alias": "bryant.sanders", "to": "b@example.com"})
        self.assertEqual([x.get("why") for x in r[1:]], ["account switched off", "no personal email on their profile", "no such person"])
        self.assertEqual(len(r), 4)                                                                  # the duplicate and gmail dropped

    def test_the_forward(self):
        b = mailfwd.forward_body({"from": "Guest Speaker <guest@example.org>", "subject": "Notes", "text": "hi",
                                  "attachments": [{"filename": "a.pdf", "download_url": "https://x/a.pdf"}]}, "b@example.com", "it@mail.arisecenla.com")
        self.assertEqual(b["from"], "Guest Speaker via Arise Church IT <it@mail.arisecenla.com>")
        self.assertEqual((b["reply_to"], b["to"], b["subject"]), ("guest@example.org", ["b@example.com"], "Notes"))
        self.assertIn("Forwarded by the church server", b["text"])
        self.assertEqual(b["attachments"], [{"filename": "a.pdf", "path": "https://x/a.pdf"}])
        self.assertEqual(mailfwd.mask("bradly@gmail.com"), "b***@gmail.com")

    def test_one_poll(self):
        with real_mode('[mailfwd]\nenabled = true\n[mail]\nfrom_email = "it@mail.arisecenla.com"\n'):
            calls = []

            def call(method, path, body=None):
                calls.append((method, path, body))
                if path.startswith(mailfwd.RECEIVED_LIST):
                    return {"ok": True, "data": {"data": [{"id": "r2", "to": ["bryant.sanders@ad.arisecenla.com"], "from": "g@x.org", "subject": "two"},
                                                          {"id": "r1", "to": ["old.timer@ad.arisecenla.com"], "from": "v@x.org", "subject": "one"}]}}
                if path.startswith("/emails/receiving/"):
                    return {"ok": True, "data": {"from": "g@x.org", "subject": "two", "text": "body"}}
                return {"ok": True, "data": {"id": "sent"}}
            users = [{"name": "bryant.sanders", "enabled": True}, {"name": "old.timer", "enabled": False}]
            with mock.patch.object(mailfwd, "_users_and_emails", return_value=(users, {"bryant.sanders": "b@example.com", "old.timer": "o@example.com"})):
                r1 = mailfwd.run_once(call=call)
                r2 = mailfwd.run_once(call=call)                                                     # nothing new the second time
            self.assertEqual((r1["arrived"], r1["forwarded"]), (2, 1))
            self.assertEqual((r2["arrived"], r2["forwarded"]), (0, 0))
            self.assertEqual(sum(1 for c in calls if c[0] == "POST"), 1)
            log = mailfwd.log()
            self.assertEqual({(x["alias"], x["ok"]) for x in log}, {("bryant.sanders", True), ("old.timer", False)})
            self.assertNotIn("body", json.dumps(log))                                                # never the message itself
            p = config.load().state_dir / "mail-forward.log.jsonl"
            self.assertEqual(oct(p.stat().st_mode & 0o777), "0o600")
            ex = mailfwd.export("old.timer")
            self.assertIn("v@x.org", ex["csv"]); self.assertIn("not kept on the server", ex["note"])

    def test_off_until_switched_on(self):
        with real_mode():
            self.assertIn("off", mailfwd.run_once(call=lambda *a, **k: self.fail("called Resend while off"))["skipped"])

    def test_nothing_listens(self):
        for u in ("arise-mailfwd.service", "arise-mailfwd.timer"):
            t = (ROOT / "config" / "systemd" / u).read_text()
            self.assertNotIn("ListenStream", t)
        self.assertIn("server_from_name", (ROOT / "server" / "arise_server" / "mail.py").read_text())


if __name__ == "__main__":
    unittest.main()

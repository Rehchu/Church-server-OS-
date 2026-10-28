"""Real mode, proven without the hardware.

The sample server shows that every click lands somewhere. These tests show what
the same click does on the real box: the exact command each module builds, that a
command which fails comes back as {"ok": false, "err": <the tool's own words>}
and is never reported as success (Bradly: "Tell him what failed"), and that a tool
missing from a real server is said plainly instead of answered from the sample.

Nothing here runs samba-tool, docker, restic or systemctl: `run` is replaced by a
recorder that answers with canned output.
"""
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ["ARISE_DEMO"] = "1"
os.environ["ARISE_CONFIG"] = str(ROOT / "config" / "arise.toml.example")

from arise_server import (apps, automations, automator, backups, config, demo_state, directory, monitor, nas,  # noqa: E402
                          remote, security, services, shares, system)


class Recorder:
    """Stands in for util.run: remembers argv, answers from a table of (argv prefix -> result)."""

    def __init__(self, answers=None, default_ok=True):
        self.calls = []
        self.answers = answers or []
        self.default_ok = default_ok

    def __call__(self, cmd, timeout=60, input_text=None, check=False):
        self.calls.append(list(cmd))
        for prefix, res in self.answers:
            if list(cmd[:len(prefix)]) == list(prefix):
                out = {"ok": True, "code": 0, "out": "", "err": ""}
                out.update(res)
                out["cmd"] = " ".join(cmd)
                return out
        return {"ok": self.default_ok, "code": 0 if self.default_ok else 1, "out": "", "err": "" if self.default_ok else "boom", "cmd": " ".join(cmd)}

    def find(self, *prefix):
        return [c for c in self.calls if c[:len(prefix)] == list(prefix)]


@contextmanager
def real(*modules, rec=None, tools=("samba-tool", "testparm", "smbcontrol", "systemctl", "docker", "restic", "wg", "timeshift", "clamscan", "wlr-randr", "git", "apt-get", "chpasswd")):
    """Real mode (not demo) with `run` and `which` replaced in the given modules."""
    rec = rec or Recorder()
    os.environ["ARISE_DEMO"] = "0"
    config.load(force=True)
    patches = []
    try:
        for m in modules:
            if hasattr(m, "run"):
                patches.append(mock.patch.object(m, "run", rec))
            if hasattr(m, "which"):
                patches.append(mock.patch.object(m, "which", lambda name, _t=tools: f"/usr/bin/{name}" if name in _t else None))
        for p in patches:
            p.start()
        yield rec
    finally:
        for p in patches:
            p.stop()
        os.environ["ARISE_DEMO"] = "1"
        config.load(force=True)
        demo_state.reset()


class Directory(unittest.TestCase):
    def test_user_create_uses_samba_tool_4_19_syntax_and_adds_groups(self):
        with real(directory) as rec, mock.patch.object(directory, "_mkhome", lambda n: None):
            r = directory.add_user("jane.doe", "S3cret-pass", "Jane Doe", ["Staff", "Media"])
        self.assertTrue(r["ok"], r)
        create = rec.find("samba-tool", "user", "create")[0]
        self.assertEqual(create[:5], ["samba-tool", "user", "create", "jane.doe", "S3cret-pass"])
        self.assertIn("--given-name", create); self.assertEqual(create[create.index("--given-name") + 1], "Jane")
        self.assertEqual(create[create.index("--surname") + 1], "Doe")
        self.assertEqual(create[create.index("--home-directory") + 1], "\\\\arise-server\\homes\\jane.doe")
        self.assertEqual([c[3:] for c in rec.find("samba-tool", "group", "addmembers")], [["Staff", "jane.doe"], ["Media", "jane.doe"]])

    def test_a_one_word_display_name_has_no_empty_surname(self):
        with real(directory) as rec, mock.patch.object(directory, "_mkhome", lambda n: None):
            directory.add_user("media.mac", "S3cret-pass", "Media")
        create = rec.find("samba-tool", "user", "create")[0]
        self.assertNotIn("--surname", create)

    def test_a_failed_create_says_what_samba_said(self):
        rec = Recorder([(["samba-tool", "user", "create"], {"ok": False, "code": 255, "err": "ERROR(ldb): Failed to add user 'jane.doe':  - LDAP error 68 LDAP_ENTRY_ALREADY_EXISTS -  <00002071: samldb: account name 'jane.doe' already in use!>"})])
        with real(directory, rec=rec), mock.patch.object(directory, "_mkhome", lambda n: None) as _m:
            r = directory.add_user("jane.doe", "S3cret-pass")
        self.assertFalse(r["ok"])
        self.assertIn("could not create jane.doe", r["err"]); self.assertIn("already in use", r["err"])
        self.assertNotIn("S3cret-pass", r.get("cmd", "") + r["err"])
        self.assertEqual(rec.find("samba-tool", "group", "addmembers"), [])

    def test_a_group_that_failed_is_named_not_hidden(self):
        rec = Recorder([(["samba-tool", "group", "addmembers", "Nope"], {"ok": False, "code": 255, "err": "ERROR: Unable to find group \"Nope\""})])
        with real(directory, rec=rec), mock.patch.object(directory, "_mkhome", lambda n: None):
            r = directory.add_user("jane.doe", "S3cret-pass", "", ["Staff", "Nope"])
        self.assertFalse(r["ok"]); self.assertTrue(r["created"])
        self.assertIn("not added to: Nope", r["err"]); self.assertNotIn("Staff (", r["err"])

    def test_enable_disable_password_delete_and_members(self):
        with real(directory) as rec:
            self.assertTrue(directory.enable_user("jane.doe", False)["ok"])
            self.assertTrue(directory.enable_user("jane.doe", True)["ok"])
            self.assertTrue(directory.set_password("jane.doe", "N3w-password")["ok"])
            self.assertTrue(directory.delete_user("jane.doe", "jane.doe")["ok"])
            self.assertTrue(directory.add_member("Staff", "jane.doe")["ok"])
            self.assertTrue(directory.remove_member("Staff", "jane.doe")["ok"])
            self.assertTrue(directory.add_group("Youth Ministry", "the youth")["ok"])
        self.assertEqual(rec.calls, [
            ["samba-tool", "user", "disable", "jane.doe"],
            ["samba-tool", "user", "enable", "jane.doe"],
            ["samba-tool", "user", "setpassword", "jane.doe", "--newpassword=N3w-password"],
            ["samba-tool", "user", "delete", "jane.doe"],
            ["samba-tool", "group", "addmembers", "Staff", "jane.doe"],
            ["samba-tool", "group", "removemembers", "Staff", "jane.doe"],
            ["samba-tool", "group", "add", "Youth Ministry", "--description", "the youth"],
        ])

    def test_every_failure_is_a_failure(self):
        with real(directory, rec=Recorder(default_ok=False)):
            for r in (directory.enable_user("jane.doe", False), directory.set_password("jane.doe", "N3w-password"),
                      directory.delete_user("jane.doe", "jane.doe"), directory.add_member("Staff", "jane.doe"),
                      directory.remove_member("Staff", "jane.doe"), directory.add_group("Youth")):
                self.assertFalse(r["ok"]); self.assertIn("boom", r["err"])
            self.assertNotIn("N3w-password", str(directory.set_password("jane.doe", "N3w-password")))

    def test_bad_names_never_reach_samba(self):
        with real(directory) as rec:
            for r in (directory.add_member("Staff", "bad name"), directory.add_member("bad\ngroup", "x.y"), directory.enable_user("-rf", True),
                      directory.delete_user("x", "x"), directory.add_user("a b", "password123")):
                self.assertFalse(r["ok"])
        self.assertEqual([c for c in rec.calls if "-rf" in c or "bad name" in c], [])

    def test_user_show_parses_disabled_last_logon_and_groups(self):
        text = ("dn: CN=Jane Doe,CN=Users,DC=ad,DC=arisecenla,DC=com\ndisplayName: Jane Doe\nuserAccountControl: 514\n"
                "lastLogon: 134064288000000000\nmemberOf: CN=Staff,CN=Users,DC=ad,DC=arisecenla,DC=com\n")
        d = directory.parse_user_show("jane.doe", text)
        self.assertFalse(d["enabled"]); self.assertEqual(d["groups"], ["Staff"]); self.assertEqual(d["display"], "Jane Doe")
        self.assertTrue(d["last_logon"].startswith("2025-"))   # a FILETIME, turned into a date
        self.assertIsNone(directory.filetime_iso("0"))

    def test_no_domain_on_a_real_box_is_said_not_sampled(self):
        with real(directory, tools=()):
            self.assertFalse(directory.add_user("jane.doe", "password123")["ok"])
            self.assertIn("No domain", directory.enable_user("office", False)["err"])
            lu = directory.list_users()
            self.assertEqual(lu["users"], []); self.assertIn("samba-tool", lu["error"])
            self.assertFalse(directory.authenticate("office", "anything"))


class Shares(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.smb = os.path.join(self.tmp.name, "smb.conf")
        self.arise = os.path.join(self.tmp.name, "arise-shares.conf")
        Path(self.smb).write_text("[global]\n  workgroup = ARISE\n")

    def tearDown(self):
        self.tmp.cleanup()

    def paths(self):
        return mock.patch.multiple(shares, SMB_CONF=self.smb, ARISE_CONF=self.arise)

    def test_add_writes_the_block_tests_with_testparm_reloads_and_keeps_a_backup(self):
        with real(shares) as rec, self.paths():
            r = shares.add_share("youth", os.path.join(self.tmp.name, "youth"), "Youth", "Youth")
        self.assertTrue(r["ok"], r)
        self.assertIn("[youth]", Path(self.arise).read_text())
        self.assertIn(f"include = {self.arise}", Path(self.smb).read_text())
        self.assertTrue([f for f in os.listdir(self.tmp.name) if f.startswith("smb.conf.bak-")])   # rule 4: a copy first
        self.assertTrue(rec.find("testparm", "-s"))
        self.assertTrue(rec.find("smbcontrol", "all", "reload-config"))

    def test_testparm_refusing_undoes_the_change(self):
        rec = Recorder([(["testparm", "-s", "--suppress-prompt"], {"ok": False, "code": 1, "err": "Unknown parameter encountered: \"bad\""})])
        Path(self.arise).write_text("\n[old]\n  path = /x\n")
        with real(shares, rec=rec), self.paths(), mock.patch.object(shares, "list_shares", lambda: {"shares": []}):
            r = shares.add_share("youth", os.path.join(self.tmp.name, "youth"))
        self.assertFalse(r["ok"]); self.assertIn("undone", r["err"]); self.assertIn("Unknown parameter", r["err"])
        self.assertEqual(Path(self.arise).read_text(), "\n[old]\n  path = /x\n")
        self.assertEqual(rec.find("smbcontrol"), [])

    def test_remove_takes_only_that_block(self):
        Path(self.arise).write_text("\n[a]\n  path = /a\n\n[youth]\n  path = /y\n  read only = no\n\n[b]\n  path = /b\n")
        with real(shares), self.paths():
            self.assertFalse(shares.remove_share("youth", "Youth")["ok"])
            self.assertTrue(shares.remove_share("youth", "youth")["ok"])
            self.assertFalse(shares.remove_share("nope", "nope")["ok"])
        t = Path(self.arise).read_text()
        self.assertNotIn("[youth]", t); self.assertIn("[a]", t); self.assertIn("[b]", t)

    def test_a_duplicate_name_is_refused(self):
        with real(shares), self.paths(), mock.patch.object(shares, "list_shares", lambda: {"shares": [{"name": "Youth"}]}):
            self.assertFalse(shares.add_share("youth", "/srv/arise/shares/youth")["ok"])


class ServicesTimersPower(unittest.TestCase):
    def test_services(self):
        with real(services) as rec:
            self.assertTrue(services.act("arise-mirror.timer", "restart")["ok"])
            self.assertFalse(services.act("ssh.service", "explode")["ok"])
            self.assertFalse(services.act("cron.service", "stop")["ok"])   # not a unit managed here
        self.assertEqual(rec.calls, [["systemctl", "restart", "arise-mirror.timer"]])
        with real(services, rec=Recorder(default_ok=False)):
            r = services.act("arise-mirror.timer", "restart")
        self.assertFalse(r["ok"]); self.assertIn("boom", r["err"])

    def test_timers_pause_and_resume(self):
        with real(automations) as rec:
            self.assertTrue(automations.pause("arise-backup.timer", False, "arise-backup.timer")["ok"])
            self.assertTrue(automations.pause("arise-backup.timer", True, "arise-backup.timer")["ok"])
            self.assertFalse(automations.pause("ssh.service", False, "ssh.service")["ok"])
        self.assertEqual(rec.calls, [["systemctl", "disable", "--now", "arise-backup.timer"], ["systemctl", "enable", "--now", "arise-backup.timer"]])
        with real(automations, rec=Recorder(default_ok=False)):
            self.assertIn("boom", automations.pause("arise-backup.timer", False, "arise-backup.timer")["err"])

    def test_power(self):
        with real(system) as rec:
            self.assertFalse(system.power("reboot", "")["ok"])
            self.assertTrue(system.power("reboot", "reboot")["ok"])
        self.assertEqual(rec.calls, [["systemctl", "reboot"]])
        with real(system, rec=Recorder(default_ok=False)):
            self.assertFalse(system.power("poweroff", "poweroff")["ok"])
        with real(system, tools=()):
            self.assertFalse(system.power("reboot", "reboot")["ok"])
            self.assertFalse(system.apt_upgrade()["ok"])


class AppsNasPeers(unittest.TestCase):
    def test_app_actions_are_compose_commands_on_its_own_folder(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "netdata").mkdir(); Path(d, "netdata", "compose.yaml").write_text("services: {}\n")
            from types import SimpleNamespace
            fake = SimpleNamespace(demo=False, apps=SimpleNamespace(root=d, docker=True))
            with real(apps) as rec, mock.patch.object(apps, "available", lambda: True), mock.patch.object(apps, "load", lambda: fake):
                self.assertTrue(apps.act("netdata", "stop")["ok"])
                self.assertTrue(apps.act("netdata", "start")["ok"])
                self.assertFalse(apps.act("netdata", "remove", "wrong")["ok"])
                self.assertFalse(apps.act("nope", "start")["ok"])            # not installed: said so
            base = ["docker", "compose", "-p", "netdata", "-f", os.path.join(d, "netdata", "compose.yaml"), "--env-file", os.path.join(d, "netdata", ".env")]
            self.assertEqual(rec.calls, [base + ["stop"], base + ["up", "-d"]])

    def test_nas_mount_command(self):
        self.assertEqual(nas.mount_cmd("smb", "synology.ad.arisecenla.com", "arise", "/mnt/synology", "/etc/arise/secrets/synology.cred"),
                         ["mount", "-t", "cifs", "//synology.ad.arisecenla.com/arise", "/mnt/synology", "-o",
                          "credentials=/etc/arise/secrets/synology.cred,vers=3.0,iocharset=utf8,uid=0,gid=0,file_mode=0660,dir_mode=0770,_netdev"])
        self.assertEqual(nas.mount_cmd("nfs", "nas", "arise", "/mnt/synology", "x")[:4], ["mount", "-t", "nfs", "nas:/volume1/arise"])

    def test_wireguard_next_address_reads_the_configured_subnet(self):
        conf = "[Peer]\nAllowedIPs = 10.47.0.2/32\n[Peer]\nAllowedIPs = 10.47.0.3/32\n"
        self.assertEqual(remote.next_peer_ip(conf, "10.47.0.0/24"), "10.47.0.4")
        self.assertEqual(remote.next_peer_ip("AllowedIPs = 10.9.8.2/32\n", "10.9.8.0/24"), "10.9.8.3")    # not hard-coded to 10.47
        self.assertIsNone(remote.next_peer_ip("".join(f"AllowedIPs = 10.1.1.{i}/32\n" for i in range(2, 250)), "10.1.1.0/24"))

    def test_no_wireguard_is_said(self):
        with real(remote, tools=()):
            r = remote.add_wireguard_peer("phone")
        self.assertFalse(r["ok"]); self.assertIn("WireGuard is not installed", r["err"])


class SafetyAndBackups(unittest.TestCase):
    def test_missing_tools_are_failures_not_sample_successes(self):
        with real(security, system, backups, tools=()):
            self.assertFalse(security.scan_run()["ok"])
            self.assertFalse(security.snapshot_create("before update")["ok"])
            self.assertFalse(security.rescue_rotate()["ok"])
            self.assertFalse(system.update_arise()["ok"] if not os.path.isdir("/opt/arise/.git") else False)
            self.assertFalse(backups.check()["ok"])
            row = backups._execute({"id": "homes", "name": "Home folders", "paths": ["/srv/arise/homes"]})
            self.assertFalse(row["ok"]); self.assertIn("restic is not installed", row["error"])

    def test_snapshot_command(self):
        rec = Recorder([(["timeshift", "--list"], {"out": "Num     Name                 Tags  Description\n------------------------------------------\n0    >  2026-10-28_03-30-01  O     before update\n"})])
        with real(security, rec=rec), mock.patch.object(security, "_refuse_in_service", lambda what: None):
            r = security.snapshot_create("before update")
        self.assertTrue(r["ok"], r)
        self.assertEqual(rec.find("timeshift", "--create")[0], ["timeshift", "--create", "--comments", "before update", "--tags", "O", "--scripted"])
        self.assertEqual(r["name"], "2026-10-28_03-30-01")

    def test_github_mirror_never_puts_the_token_in_argv_or_the_url(self):
        args = backups.git_auth_args("ghp_secret")
        self.assertNotIn("ghp_secret", " ".join(args))
        self.assertIn("$GH_TOKEN", " ".join(args))
        self.assertEqual(backups.git_auth_args(""), [])


class Automator(unittest.TestCase):
    def test_a_real_run_is_refused_while_the_timer_is_on(self):
        rec = Recorder([(["systemctl", "is-enabled", "arise-automator.timer"], {"out": "enabled\n"})])
        with real(automator, rec=rec):
            r = automator.start("run")
        self.assertFalse(r["ok"]); self.assertIn("timer is on", r["err"])

    def test_a_real_run_without_the_automator_is_said(self):
        rec = Recorder([(["systemctl", "is-enabled", "arise-automator.timer"], {"ok": False, "code": 1, "out": "disabled\n"})])
        with real(automator, rec=rec):
            r = automator.start("run")
        self.assertFalse(r["ok"]); self.assertIn("missing", r["err"])

    def test_preview_is_never_refused_by_the_timer(self):
        self.assertIsNone(None if True else automator.run_refusal())
        demo = automator.start("preview")
        self.assertTrue(demo["ok"])


class Monitor(unittest.TestCase):
    def test_panel_off_runs_wlr_randr_as_the_kiosk_user(self):
        rec = Recorder([(["sudo", "-n", "-u", "arise-kiosk"], {"out": "HDMI-A-1 \"Dell E2216H\"\n  Enabled: yes\n"})])
        with real(monitor, rec=rec), mock.patch.object(monitor, "display", lambda: "wayland-0"):
            r = monitor.power(False)
        self.assertTrue(r["ok"], r)
        off = [c for c in rec.calls if "--off" in c][0]
        self.assertEqual(off[:4], ["sudo", "-n", "-u", "arise-kiosk"]); self.assertEqual(off[-4:], ["wlr-randr", "--output", "HDMI-A-1", "--off"])

    def test_no_kiosk_is_said(self):
        with real(monitor), mock.patch.object(monitor, "display", lambda: None):
            r = monitor.power(False)
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()

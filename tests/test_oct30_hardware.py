"""Oct 30: the server is an HP EliteDesk 800 G1 SFF (TPM 1.2, so no clevis) and the NAS a two-bay DS216.
docs/ANSWERS.md rows H1 to H6."""
import os
import re
import sys
import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("ARISE_DEMO", "1")
os.environ.setdefault("ARISE_CONFIG", str(ROOT / "config" / "arise.toml.example"))

from arise_server import config, maintenance, security, system, updates  # noqa: E402


def public_key(key=None):
    key = key or ed25519.Ed25519PrivateKey.from_private_bytes(b"\x01" * 32).public_key()
    return key.public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()


class TpmVersion(unittest.TestCase):
    def _sysfs(self, major):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        d = temp.name
        os.makedirs(os.path.join(d, "tpm0"))
        with open(os.path.join(d, "tpm0", "tpm_version_major"), "w") as f:
            f.write(f"{major}\n")
        return d

    def test_a_1_2_chip_is_not_enough_for_clevis(self):
        self.assertEqual(security.tpm_version(self._sysfs(1)), 1)

    def test_a_2_0_chip(self):
        self.assertEqual(security.tpm_version(self._sysfs(2)), 2)

    def test_installer_reads_the_version_not_just_dev_tpm0(self):
        s = (ROOT / "installer" / "install.sh").read_text()
        self.assertIn("/sys/class/tpm/tpm0/tpm_version_major", s)
        self.assertNotIn('[ ! -e /dev/tpmrm0 ] && [ ! -e /dev/tpm0 ]', s)


class UnlockKeys(unittest.TestCase):
    def test_each_key_may_only_answer_the_passphrase_prompt(self):
        ed = public_key()
        rsa_key = public_key(rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key())
        keys = security.unlock_keys(f"# mine\n{ed} bradly@pc\n\n{rsa_key} old\n")
        self.assertEqual(len(keys), 2)
        for k in keys:
            self.assertTrue(k.startswith('no-port-forwarding,no-agent-forwarding,no-X11-forwarding,command="/usr/bin/cryptroot-unlock" '))
        self.assertTrue(keys[0].endswith(ed))
        self.assertTrue(keys[1].endswith(rsa_key))

    def test_restricted_malformed_and_unsupported_keys_are_rejected(self):
        valid = public_key()
        for line in (f'from="10.0.0.0/8" {valid}', f'command="echo hi" {valid}',
                     "not a key", "ssh-ed25519 AAAA", "ssh-rsa " + valid.split()[1],
                     valid.replace("ssh-ed25519", "sk-ssh-ed25519@openssh.com"), valid + "\x00"):
            with self.subTest(line=line[:35]), self.assertRaises(ValueError):
                security.unlock_keys(line)
        weak = public_key(rsa.generate_private_key(public_exponent=65537, key_size=1024).public_key())
        with self.assertRaisesRegex(ValueError, "2048"):
            security.unlock_keys(weak)

    def test_no_keys_no_lines(self):
        self.assertEqual(security.unlock_keys("# nothing\n\n"), [])

    def test_the_early_ssh_is_not_the_real_sshd_port(self):
        self.assertEqual(security.UNLOCK_PORT, 2222)
        self.assertEqual(security.DROPBEAR_DIR, "/etc/dropbear/initramfs")


class NoSurpriseRestart(unittest.TestCase):
    def test_never_restarts_when_the_disk_waits_for_its_passphrase(self):
        go, why = updates.reboot_ok(needs_passphrase=True, in_service=False, force_service=True)
        self.assertFalse(go)
        self.assertIn("passphrase", why)

    def test_never_during_a_service(self):
        self.assertFalse(updates.reboot_ok(False, True)[0])
        self.assertTrue(updates.reboot_ok(False, True, force_service=True)[0])

    def test_otherwise_it_may(self):
        self.assertEqual(updates.reboot_ok(False, False), (True, ""))


class CoreApps(unittest.TestCase):
    def test_the_installer_installs_the_core_five(self):
        s = (ROOT / "installer" / "install.sh").read_text()
        m = re.search(r'^DEFAULT_APPS="([^"]*)"', s, re.M)
        self.assertEqual(m.group(1).split(), ["nextcloud", "vaultwarden", "uptime-kuma", "netdata", "filebrowser"])
        for name in m.group(1).split():
            self.assertTrue((ROOT / "templates" / name / "template.yaml").exists(), name)

    def test_all_is_still_one_flag_away(self):
        s = (ROOT / "installer" / "install.sh").read_text()
        self.assertIn('if [ "$APPS" = "all" ]; then', s)


class DiskScreen(unittest.TestCase):
    def test_the_install_grows_the_system_volume(self):
        s = (ROOT / "installer" / "install.sh").read_text()
        self.assertIn('lvextend -r -l +100%FREE "$ROOT_SRC"', s)

    def test_answers_record_the_hardware(self):
        a = (ROOT / "docs" / "ANSWERS.md").read_text()
        for row in ("| H1 |", "| H2 |", "| H3 |", "| H4 |", "| H5 |", "| H6 |"):
            self.assertIn(row, a)


class HardwareLayer(unittest.TestCase):
    def setUp(self):
        self.s = (ROOT / "installer" / "install.sh").read_text()

    def test_microcode_for_the_cpu(self):
        self.assertIn("intel-microcode", self.s)
        self.assertIn("amd64-microcode", self.s)

    def test_trim_reaches_the_ssd_through_luks(self):
        prog = re.search(r"awk -v dev=\"\$device\" -v uuid=\"\$uuid\" '(.*?)' \"\$crypttab\"", self.s, re.S).group(1)
        import subprocess
        src = "dm_crypt-0 UUID=abc none luks\n# dm_crypt-1 UUID=x none luks\nother UUID=y none luks,discard\nsw /dev/x /dev/urandom swap\nexternal UUID=other none luks\n"
        out = subprocess.run(["awk", "-v", "dev=/dev/sda3", "-v", "uuid=abc", prog], input=src, capture_output=True, text=True, check=True).stdout
        self.assertEqual(out.splitlines(), ["dm_crypt-0 UUID=abc none luks,discard", "# dm_crypt-1 UUID=x none luks",
                                            "other UUID=y none luks,discard", "sw /dev/x /dev/urandom swap", "external UUID=other none luks"])

    def test_the_fallback_boot_file(self):
        self.assertIn('cp -- "$source/shimx64.efi" "$stage/BOOTX64.EFI"', self.s)
        self.assertIn('mountpoint -q "$esp"', self.s)


class BootEncryption(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = config.Config(path=str(self.root / "arise.toml"), found=True, demo=False,
                                 raw={"paths": {"state_dir": str(self.root / "state"), "log_dir": str(self.root)}})
        for mod in (security, updates, system, maintenance):
            self.enterContext(patch.object(mod, "load", return_value=self.cfg))
        self.enterContext(patch.object(security, "which", side_effect=lambda name: "/usr/bin/" + name))
        self.dropbear = self.root / "dropbear"
        self.dropbear.mkdir()
        self.boot = self.root / "boot"
        self.boot.mkdir()
        self.initrd = self.boot / "initrd.img-test"
        self.initrd.write_bytes(b"test initramfs; no actual boot changes")
        for name in ("DROPBEAR_HOOK", "CRYPTROOT_HOOK"):
            file = self.root / name
            file.touch()
            self.enterContext(patch.object(security, name, str(file)))
        self.enterContext(patch.object(security, "DROPBEAR_DIR", str(self.dropbear)))
        self.enterContext(patch.object(security, "UNLOCK_NETWORK", str(self.root / "network")))
        self.enterContext(patch.object(security, "UNLOCK_BOOT", str(self.boot)))
        self.keys = self.root / "owner.pub"
        self.keys.write_text(public_key() + " owner\n")
        (self.dropbear / "dropbear_ed25519_host_key").write_bytes(b"test host key")

    @staticmethod
    def block_tree(extra=True):
        root = {"name": "sda3", "fstype": "crypto_LUKS", "children": [
            {"name": "rootcrypt", "type": "crypt", "mountpoint": "/"}]}
        return json.dumps({"blockdevices": [*([{"name": "sdb1", "fstype": "crypto_LUKS"}] if extra else []), root]})

    def test_partial_binding_does_not_allow_unattended_restart(self):
        def run(cmd, **kwargs):
            out = self.block_tree() if cmd[0] == "lsblk" else ('1: tpm2 {"pcr_ids":"7"}' if cmd[-1] == "/dev/sdb1" else "")
            return {"ok": True, "out": out}
        with patch.object(security, "run", side_effect=run), patch.object(security, "tpm_version", return_value=2):
            status = security.encrypt_status()
        self.assertEqual(status["root_luks"], ["/dev/sda3"])
        self.assertEqual(status["tpm_bound_devices"], ["/dev/sdb1"])
        self.assertFalse(status["tpm_bound"])
        self.assertTrue(status["needs_passphrase"])

    def test_unknown_or_failed_storage_probe_blocks_restart(self):
        for result in ({"ok": False, "out": ""}, {"ok": True, "out": "not json"},
                       {"ok": True, "out": "{}"}, {"ok": True, "out": "[]"}):
            with self.subTest(result=result), patch.object(security, "run", return_value=result):
                self.assertTrue(updates._needs_passphrase())
        with patch.object(security, "encrypt_status", return_value={}):
            self.assertTrue(updates._needs_passphrase())

    def test_tpm_binding_targets_root_ancestor_not_first_data_disk(self):
        status = {"known": True, "luks": ["/dev/sdb1", "/dev/sda3"], "root_luks": ["/dev/sda3"],
                  "tpm": True, "tpm_bound": False, "tpm_bound_devices": []}
        with patch.object(security, "encrypt_status", return_value=status), patch.object(security, "run", return_value={"ok": True}) as run:
            self.assertTrue(security.encrypt_tpm("test passphrase")["ok"])
        self.assertEqual(run.call_args_list[0].args[0][4], "/dev/sda3")
        self.assertNotIn("test passphrase", run.call_args_list[0].args[0])

    def _setup(self, *, fail_update=False, missing_unlock=False):
        def run(cmd, **kwargs):
            if cmd[0] == "lsinitramfs":
                files = ["usr/sbin/dropbear", "root-AbCdEf1234/.ssh/authorized_keys",
                         "etc/dropbear/dropbear_ed25519_host_key"]
                if not missing_unlock:
                    files.append("usr/bin/cryptroot-unlock")
                return {"ok": True, "out": "\n".join(files), "err": ""}
            return {"ok": not fail_update, "out": "", "err": "failed" if fail_update else ""}
        self.enterContext(patch.object(security, "encrypt_status", return_value={"known": True, "root_encrypted": True}))
        return self.enterContext(patch.object(security, "run", side_effect=run))

    def test_setup_requires_explicit_network_and_rejects_shell_text(self):
        self.assertEqual(security.unlock_network("enp0s25:dhcp"), ":::::enp0s25:dhcp")
        self.assertEqual(security.unlock_network("192.168.1.20::192.168.1.1:255.255.255.0::eth0:none"),
                         "192.168.1.20::192.168.1.1:255.255.255.0::eth0:none")
        for invalid in ("", "dhcp; touch /tmp/unsafe", '$(id)', "192.168.1.20::bad:255.255.255.0::eth0:none"):
            with self.subTest(network=invalid):
                self.assertFalse(security.encrypt_ssh(network=invalid, authorized_keys=str(self.keys))["ok"])
        self.assertFalse((self.dropbear / "authorized_keys").exists())

    def test_setup_checks_all_boot_images_before_reporting_configured(self):
        run = self._setup()
        self.assertTrue(security.encrypt_ssh(network="dhcp", authorized_keys=str(self.keys))["ok"])
        self.assertIn(["update-initramfs", "-u", "-k", "all"], [c.args[0] for c in run.call_args_list])
        self.assertTrue(security.ssh_unlock_ready())
        self.assertIn("command=", (self.dropbear / "authorized_keys").read_text())
        self.assertIn("-s -j -k", (self.dropbear / "dropbear.conf").read_text())
        self.assertEqual((self.dropbear / "authorized_keys").stat().st_mode & 0o777, 0o600)
        self.initrd.write_bytes(b"new image invalidates prior validation")
        self.assertFalse(security.ssh_unlock_ready())

    def test_failed_initramfs_or_missing_unlock_never_reports_ready(self):
        for fail, missing in ((True, False), (False, True)):
            with self.subTest(failed=fail, missing=missing):
                self._setup(fail_update=fail, missing_unlock=missing)
                self.assertFalse(security.encrypt_ssh(network="dhcp", authorized_keys=str(self.keys))["ok"])
                self.assertFalse(security.ssh_unlock_ready())

    def test_dropbear_binary_alone_does_not_satisfy_package_check(self):
        Path(security.DROPBEAR_HOOK).unlink()
        run = self._setup()
        self.assertFalse(security.encrypt_ssh(network="dhcp", authorized_keys=str(self.keys))["ok"])
        self.assertEqual(run.call_args_list[0].args[0], ["apt-get", "install", "-y", "-q", "dropbear-initramfs", "cryptsetup-initramfs"])

    def test_manual_reboot_reports_required_unlock(self):
        with patch.object(security, "encrypt_status", return_value={"known": True, "needs_passphrase": True}), \
                patch.object(system, "which", return_value="systemctl"), patch.object(system, "run", return_value={"ok": True}) as run:
            result = system.power("reboot", "reboot")
        self.assertTrue(result["ok"])
        self.assertIn("passphrase", result["out"])
        self.assertEqual(run.call_args.args[0], ["systemctl", "reboot"])

    def test_apply_keeps_passphrase_reboot_queued_without_power_command(self):
        queue = {"packages": [], "apps": [], "reboot": True}
        with patch.object(updates, "queue", return_value=queue), patch.object(updates, "_in_service", return_value=None), \
                patch.object(updates, "_needs_passphrase", return_value=True), patch.object(updates.os.path, "exists", return_value=True), \
                patch.object(updates, "run") as run:
            result = updates.apply(no_snapshot=True, log=lambda _: None)
        self.assertTrue(result["ok"])
        self.assertIn("restart waiting", result["summary"])
        self.assertTrue(queue["reboot"])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class UnitsCanImportTheServer(unittest.TestCase):
    """Nov 2 (scout I-003): a unit that runs `python -c "from arise_server..."` must run from
    /opt/arise/server or carry PYTHONPATH, or it dies with ModuleNotFoundError and the backup's
    app restart, the boot recovery and the monthly verify never run."""

    def test_every_python_unit_finds_the_package(self):
        for p in sorted((ROOT / "config" / "systemd").glob("*.service")):
            s = p.read_text()
            if "arise_server" not in s or "/venv/bin/python" not in s:
                continue
            ok = "WorkingDirectory=/opt/arise/server" in s or "PYTHONPATH=/opt/arise/server" in s
            self.assertTrue(ok, f"{p.name}: python -c/-m arise_server without WorkingDirectory=/opt/arise/server or PYTHONPATH")


class TrashBelongsToThePerson(unittest.TestCase):
    """Nov 2 (scout I-031): folders the dashboard makes under .Trash/<user> become that person's,
    0770, so Samba's recycle bin can keep writing there instead of purging their deletes."""

    def test_own_trash_dirs_chowns_the_chain(self):
        from arise_server import finder
        calls = []
        with tempfile.TemporaryDirectory() as base:
            dest = os.path.join(base, ".Trash", "kristina.robinson", "Documents", "old")
            os.makedirs(dest)
            fake_pw = type("pw", (), {"pw_uid": 4242, "pw_gid": 4242})()
            with patch.object(finder.pwd, "getpwnam", return_value=fake_pw), \
                    patch.object(finder.os, "chown", side_effect=lambda p, u, g: calls.append(("chown", p, u))), \
                    patch.object(finder.os, "chmod", side_effect=lambda p, m: calls.append(("chmod", p, m))):
                finder.own_trash_dirs(base, "kristina.robinson", dest)
        chowned = sorted(c[1] for c in calls if c[0] == "chown")
        self.assertEqual(len(chowned), 3)                       # .Trash/<user>, Documents, old; never .Trash itself
        self.assertTrue(all(p.endswith(("kristina.robinson", "Documents", "old")) for p in chowned))
        self.assertTrue(all(c[2] == 4242 for c in calls if c[0] == "chown"))
        self.assertTrue(all(c[2] == 0o770 for c in calls if c[0] == "chmod"))

    def test_unknown_user_changes_nothing(self):
        from arise_server import finder
        with tempfile.TemporaryDirectory() as base, patch.object(finder.pwd, "getpwnam", side_effect=KeyError), \
                patch.object(finder.os, "chown") as ch:
            os.makedirs(os.path.join(base, ".Trash", "nobody"))
            finder.own_trash_dirs(base, "nobody", os.path.join(base, ".Trash", "nobody"))
            ch.assert_not_called()


class FailedBackupTellsBradly(unittest.TestCase):
    """Nov 2 (scout I-015): a failed job posts to Discord #alerts and the phone the same night,
    once per job per night; a skipped optional source does not."""

    def test_tell_failure_posts_once_with_a_night_key(self):
        from arise_server import backups, discord, push
        with patch.object(discord, "post", return_value={"ok": True}) as dp, patch.object(push, "send", return_value={"ok": True}) as ps:
            backups._tell_failure({"id": "homes", "name": "Home folders"}, {"error": "restic: repository locked\nFatal: lock", "finished": "2026-11-02T03:05:00"})
        dp.assert_called_once()
        self.assertEqual(dp.call_args.args[0], "alerts")
        self.assertIn("Home folders", dp.call_args.args[1]); self.assertIn("Fatal: lock", dp.call_args.args[1])
        self.assertEqual(dp.call_args.kwargs["key"], "backup-failed:homes:2026-11-02")
        ps.assert_called_once(); self.assertEqual(ps.call_args.kwargs["tag"], "backup-failed:homes:2026-11-02")

    def test_a_discord_outage_never_breaks_the_backup(self):
        from arise_server import backups, discord, push
        with patch.object(discord, "post", side_effect=RuntimeError("down")), patch.object(push, "send", side_effect=RuntimeError("down")):
            backups._tell_failure({"id": "x"}, {"error": "e"})   # no raise


class SplashShowsThePassphrasePrompt(unittest.TestCase):
    """Nov 2 (scout I-004): with no TPM 2.0 the disk asks its passphrase at every boot; the
    splash must draw the prompt or the box looks hung."""

    def test_the_three_callbacks_are_registered(self):
        s = (ROOT / "config" / "plymouth" / "ariseos" / "ariseos.script").read_text()
        for fn in ("SetDisplayPasswordFunction", "SetDisplayQuestionFunction", "SetDisplayNormalFunction"):
            self.assertIn(f"Plymouth.{fn}(", s)
        self.assertIn("Type the disk passphrase", s)


class NamesTheAppsNeed(unittest.TestCase):
    """Nov 2 (scout I-011): vault and remote are CNAMEs like cloud; no DNS record is left to type."""

    def test_installer_adds_vault_and_remote(self):
        s = (ROOT / "installer" / "install.sh").read_text()
        self.assertIn("for _name in cloud vault remote; do", s)
        self.assertNotIn("DNS records still needed", s)


class KioskReachesDownloads(unittest.TestCase):
    """Nov 2 (scout I-027): the home is 0700, so the kiosk needs traverse on it, granted and removed with the Downloads ACL."""

    def test_traverse_acl_set_and_removed(self):
        s = (ROOT / "scripts" / "arise-browser-profile").read_text()
        self.assertIn('setfacl -m "u:$KIOSK:x" "$(dirname "$dl")"', s)
        self.assertIn('setfacl -x "u:$KIOSK" "$(dirname "$dl")"', s)


class ForwardsCarryAttachments(unittest.TestCase):
    """Nov 2 (scout I-021): attachments ride along as URL attachments, up to Resend's 25 MB; the rest are named."""

    def test_forward_body_attaches_by_url_and_names_the_oversize(self):
        from arise_server import mailfwd
        big = 30 * 1024 * 1024
        b = mailfwd.forward_body({"from": "a@x.org", "subject": "s", "text": "hi",
                                  "attachments": [{"filename": "notes.pdf", "size": 1000, "download_url": "https://r/1"},
                                                  {"filename": "video.mov", "size": big, "download_url": "https://r/2"}]},
                                 "k@example.com", "it@arisecenla.com")
        self.assertEqual(b["attachments"], [{"filename": "notes.pdf", "path": "https://r/1"}])
        self.assertIn("video.mov (30 MB)", b["text"])

    def test_run_once_fetches_the_attachment_list(self):
        from arise_server import mailfwd
        self.assertEqual(mailfwd.RECEIVED_ATTACHMENTS, "/emails/receiving/{id}/attachments")
        self.assertIn("RECEIVED_ATTACHMENTS.format(id=it[\"id\"])", (ROOT / "server" / "arise_server" / "mailfwd.py").read_text())

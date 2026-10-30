"""Oct 30: the real hardware is an OptiPlex 3010 (no TPM 2.0, 8 GB at most) and a two-bay DS216.
docs/ANSWERS.md rows H1 to H5."""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("ARISE_DEMO", "1")
os.environ.setdefault("ARISE_CONFIG", str(ROOT / "config" / "arise.toml.example"))

from arise_server import security, updates  # noqa: E402


class TpmVersion(unittest.TestCase):
    def _sysfs(self, major):
        d = tempfile.mkdtemp()
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
        keys = security.unlock_keys("# mine\nssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA bradly@pc\n\nnot a key\n"
                                    'from="10.0.0.0/8" ssh-rsa AAAAB3NzaC1yc2E= old\n')
        self.assertEqual(len(keys), 2)
        for k in keys:
            self.assertTrue(k.startswith('no-port-forwarding,no-agent-forwarding,no-X11-forwarding,command="/usr/bin/cryptroot-unlock" '))
        self.assertTrue(keys[0].endswith("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA bradly@pc"))
        self.assertTrue(keys[1].endswith("ssh-rsa AAAAB3NzaC1yc2E= old"))

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
        for row in ("| H1 |", "| H2 |", "| H3 |", "| H4 |", "| H5 |"):
            self.assertIn(row, a)


if __name__ == "__main__":
    unittest.main()

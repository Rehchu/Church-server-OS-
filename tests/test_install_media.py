"""The install media: the autoinstall config, the media builder, the first-boot wizard.

installer/autoinstall.yaml is checked against subiquity's own published schema,
vendored at installer/schema/subiquity-autoinstall-schema.json from
canonical/subiquity commit SCHEMA_COMMIT below (autoinstall-schema.json at the
repo root). Re-fetch it from that path when Ubuntu moves on.

Pinned here: no git clone and no password in the install, the wizard never puts
a password on a command line, the builder and the wizard parse, and (when
xorriso is installed) the add-on disc really is a CIDATA disc with the code on it.
"""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = ROOT / "installer" / "autoinstall.yaml"
SCHEMA_PATH = ROOT / "installer" / "schema" / "subiquity-autoinstall-schema.json"
SCHEMA_COMMIT = "5aad030a6727ebf173093ef2af4132e8dd074b4c"
BUILDER = ROOT / "scripts" / "make-install-media.sh"
WIZARD = ROOT / "scripts" / "arise-firstboot"
UNIT = ROOT / "config" / "systemd" / "arise-firstboot.service"

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None
try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None


def load_config() -> dict:
    return yaml.safe_load(YAML_PATH.read_text())["autoinstall"]


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class AutoinstallConfig(unittest.TestCase):
    def test_starts_as_cloud_config(self):
        self.assertTrue(YAML_PATH.read_text().startswith("#cloud-config\n"))

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_validates_against_subiquity_schema(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        jsonschema.validate(load_config(), schema)

    def test_only_identity_and_the_disk_are_asked(self):
        c = load_config()
        # the disk screen: encryption is ticked there (no TPM 2.0 on the OptiPlex 3010, Oct 30)
        self.assertEqual(c["interactive-sections"], ["identity", "storage"])
        # identity given here would need a password hash in the file
        self.assertNotIn("identity", c)
        self.assertNotIn("user-data", c)

    def test_the_settings_asked_for(self):
        c = load_config()
        self.assertEqual(c["locale"], "en_US.UTF-8")
        self.assertEqual(c["keyboard"]["layout"], "us")
        self.assertEqual(c["timezone"], "America/Chicago")
        self.assertEqual(c["storage"]["layout"]["name"], "lvm")
        self.assertEqual(c["storage"]["layout"]["match"], {"size": "largest"})
        self.assertTrue(c["ssh"]["install-server"])
        self.assertEqual(c["updates"], "security")
        for pkg in ("git", "python3", "python3-venv", "curl", "ca-certificates"):
            self.assertIn(pkg, c["packages"])

    def test_late_commands_carry_no_clone_and_no_password(self):
        text = "\n".join(load_config()["late-commands"])
        self.assertNotIn("git clone", text)
        self.assertNotIn("REPLACE_WITH_HASH", text)
        self.assertNotRegex(text, r"(?i)--admin-pass|password|passwd|\$6\$")
        self.assertNotRegex(YAML_PATH.read_text(), r"\$6\$|REPLACE_WITH_HASH")

    def test_late_commands_use_the_media_and_check_it(self):
        text = "\n".join(load_config()["late-commands"])
        self.assertIn("/cdrom/arise", text)
        self.assertIn("CIDATA", text)
        self.assertIn("sha256sum -c SHA256SUMS", text)
        self.assertIn("/target/opt/arise-src", text)
        self.assertRegex(text, r"install\.sh --no-start --skip-domain --skip-docker")
        self.assertIn("systemctl enable arise-firstboot.service", text)


class Builder(unittest.TestCase):
    def test_parses(self):
        subprocess.run(["bash", "-n", str(BUILDER)], check=True)

    def test_full_keeps_ubuntus_boot_records(self):
        s = BUILDER.read_text()
        self.assertIn("-boot_image any replay", s)
        self.assertIn("-volid ARISEOS_2404", s)
        self.assertIn("/autoinstall.yaml", s)
        self.assertIn("SHA256SUMS", s)       # the Ubuntu ISO is checked before use
        self.assertIn("set timeout=-1", s)   # the erasing entry never boots by itself
        self.assertIn("Install by hand", s)

    def test_grub_edit_on_ubuntus_real_menu(self):
        # tests/fixtures/ubuntu-24.04.5-live-server-grub.cfg is /boot/grub/grub.cfg from
        # ubuntu-24.04.5-live-server-amd64.iso (read from releases.ubuntu.com, Oct 29 2026)
        code = [b for b in re.findall(r"<<'PY'\n(.*?)\nPY\n", BUILDER.read_text(), re.S)
                if "menuentry" in b][0]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "grub.cfg"
            subprocess.run(["python3", "-c", code,
                            str(ROOT / "tests" / "fixtures" / "ubuntu-24.04.5-live-server-grub.cfg"),
                            str(out)], check=True)
            g = out.read_text()
        entries = [a or b for a, b in re.findall(r'''(?m)^menuentry\s+(?:"([^"]*)"|'([^']*)')''', g)]
        self.assertEqual(entries[0], "Install ariseOS (ERASES the disk you confirm)")
        self.assertEqual(entries[1], "Install by hand (the plain Ubuntu installer)")
        first, second = re.findall(r"(?ms)^menuentry.*?^\}", g)[:2]
        self.assertRegex(first, r"(?m)^\tlinux\t/casper/vmlinuz\s+autoinstall ---$")
        self.assertNotIn("autoinstall", second)
        self.assertEqual(g.count("autoinstall"), 1)
        self.assertIn("set timeout=-1", g)
        self.assertNotIn("set timeout=30", g)
        self.assertIn("Ubuntu Server with the HWE kernel", g)   # the rest stays as Ubuntu made it

    def test_media_carries_the_committed_tree(self):
        s = BUILDER.read_text()
        self.assertIn("git -C \"$ROOT\" archive", s)
        code = "\n".join(l for l in s.splitlines() if not l.lstrip().startswith("#"))
        self.assertNotIn("git clone", code)

    @unittest.skipUnless(shutil.which("xorriso") and shutil.which("zip") and shutil.which("git")
                         and (ROOT / ".git").exists(), "xorriso, zip or a git checkout missing")
    def test_builds_a_cidata_disc(self):
        with tempfile.TemporaryDirectory() as out:
            r = subprocess.run(["bash", str(BUILDER), "--out", out], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            iso = Path(out) / "ariseos-addon.iso"
            pvd = iso.read_bytes()[16 * 2048:17 * 2048]       # the primary volume descriptor
            self.assertEqual(pvd[1:6], b"CD001")
            self.assertEqual(pvd[40:72].decode().strip(), "CIDATA")
            ls = subprocess.run(["xorriso", "-indev", str(iso), "-find", "/", "-type", "f"],
                                capture_output=True, text=True).stdout
            for f in ("/user-data", "/meta-data", "/autoinstall.yaml",
                      "/arise/ariseos-src.tar.gz", "/arise/SHA256SUMS", "/arise/VERSION"):
                self.assertIn(f"'{f}'", ls)
            z = subprocess.run(["unzip", "-l", str(Path(out) / "ariseos-addon.zip")],
                               capture_output=True, text=True).stdout if shutil.which("unzip") else ""
            if z:
                self.assertIn("autoinstall.yaml", z)
                self.assertIn("arise/ariseos-src.tar.gz", z)


class Wizard(unittest.TestCase):
    def test_parses(self):
        subprocess.run(["bash", "-n", str(WIZARD)], check=True)

    def test_password_never_on_a_command_line(self):
        s = WIZARD.read_text()
        self.assertIn("--admin-pass-file", s)
        self.assertNotRegex(s, r'--admin-pass[ =]"?\$')
        self.assertIn("chmod 600", s)
        self.assertIn("shred -u", s)
        # the domain password is read without echo
        self.assertIn("--passwordbox", s)
        self.assertIn("read -r -s", s)
        # the log is fed by install.sh's output, never by the password variables
        for line in s.splitlines():
            if "$LOG" in line or "firstboot.log" in line:
                self.assertNotRegex(line, r"\$\{?P[12]\b")

    def test_runs_install_with_the_answers(self):
        s = WIZARD.read_text()
        for flag in ("--owner", "--staging", "--kiosk", "--with-tailscale", "--no-tailscale"):
            self.assertIn(flag, s)
        self.assertIn("ARISE_FIRSTBOOT=1", s)
        self.assertIn("arisectl admin set-password", s)
        self.assertIn("arisectl doctor", s)
        self.assertIn("systemctl disable arise-firstboot.service", s)
        self.assertIn("systemctl reboot", s)

    def test_unit_runs_once_on_tty1(self):
        u = UNIT.read_text()
        self.assertIn("TTYPath=/dev/tty1", u)
        self.assertIn("ConditionPathExists=!/var/lib/arise/firstboot.done", u)
        self.assertIn("Before=getty@tty1.service arise-kiosk.service", u)
        self.assertIn("--from-boot", u)
        self.assertIn("firstboot.done", WIZARD.read_text())

    def test_setup_verb_and_password_file_flag(self):
        self.assertRegex((ROOT / "cli" / "arisectl").read_text(), r'add_parser\("setup"\)')
        inst = (ROOT / "installer" / "install.sh").read_text()
        self.assertIn("--admin-pass-file)", inst)
        self.assertIn("ARISE_FIRSTBOOT", inst)
        subprocess.run(["bash", "-n", str(ROOT / "installer" / "install.sh")], check=True)


class Docs(unittest.TestCase):
    def test_no_stale_manual_steps(self):
        for p in (ROOT / "installer" / "MAKE-USB.md", ROOT / "docs" / "VIRTUALBOX.md"):
            t = p.read_text()
            self.assertNotIn("REPLACE_WITH_HASH", t, p.name)
            self.assertIn("make-install-media.sh", t, p.name)
        self.assertIn("make-install-media.sh", (ROOT / "INSTALL.md").read_text())


if __name__ == "__main__":
    unittest.main()

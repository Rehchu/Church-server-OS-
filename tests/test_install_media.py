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

    def test_disk_and_identity_are_always_confirmed_on_screen(self):
        c = load_config()
        self.assertEqual(c["interactive-sections"], ["storage", "identity"])
        # identity given here would need a password hash in the file
        self.assertNotIn("identity", c)
        self.assertNotIn("user-data", c)

    def test_the_settings_asked_for(self):
        c = load_config()
        self.assertEqual(c["locale"], "en_US.UTF-8")
        self.assertEqual(c["keyboard"]["layout"], "us")
        self.assertEqual(c["timezone"], "America/Chicago")
        self.assertEqual(c["storage"]["layout"]["name"], "lvm")
        self.assertNotIn("match", c["storage"]["layout"])
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
        self.assertNotIn("install.sh", text)  # firstboot owns service/network setup after location choice
        self.assertIn("set -eu", text)
        self.assertNotIn("exit 0", text)  # payload failures must stop the install
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
        self.assertEqual(entries[0], "Install ariseOS (choose disk and encryption on screen)")
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
            r = subprocess.run(["bash", str(BUILDER), "--working-tree", "--out", out], capture_output=True, text=True)
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
            self.assertNotIn("/arise/secrets", ls)                  # the plain disc never carries a key

    @unittest.skipUnless(shutil.which("xorriso") and shutil.which("zip") and shutil.which("git")
                         and (ROOT / ".git").exists(), "xorriso, zip or a git checkout missing")
    def test_a_private_disc_carries_only_the_named_keys(self):
        """Oct 31, H9: the Resend key rides on a private disc, never in git or the shared one."""
        with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as sec:
            Path(sec, "resend-api-key").write_text("re_" + "x" * 30 + "\n")
            Path(sec, "something-else").write_text("not allowed\n")
            r = subprocess.run(["bash", str(BUILDER), "--working-tree", "--out", out, "--secrets", sec], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertNotIn("re_xxx", r.stdout + r.stderr)          # never printed
            iso = Path(out) / "ariseos-addon-private.iso"
            ls = subprocess.run(["xorriso", "-indev", str(iso), "-find", "/", "-type", "f"],
                                capture_output=True, text=True).stdout
            self.assertIn("'/arise/secrets/resend-api-key'", ls)
            self.assertNotIn("something-else", ls)
        y = YAML_PATH.read_text()
        self.assertIn('install -m 0600 -o root -g root "$f" "/target/etc/arise/secrets/$(basename "$f")"', y)


class PublishedDisc(unittest.TestCase):
    """install-media/ is in the public repo (Bradly, Nov 1): the plain disc only, never a key."""

    def test_no_private_disc_and_no_secrets(self):
        d = ROOT / "install-media"
        if not d.exists():
            self.skipTest("no install-media folder")
        names = [p.name for p in d.iterdir()]
        self.assertFalse([n for n in names if "private" in n], names)
        self.assertIn("*-private.iso", (ROOT / ".gitignore").read_text())
        iso = d / "ariseos-addon.iso"
        if iso.exists() and shutil.which("xorriso"):
            ls = subprocess.run(["xorriso", "-indev", str(iso), "-find", "/", "-type", "f"],
                                capture_output=True, text=True).stdout
            self.assertIn("'/arise/ariseos-src.tar.gz'", ls)
            self.assertNotIn("/arise/secrets/", ls)                  # no key file on the published disc
        self.assertNotRegex(iso.read_bytes().decode("latin-1") if iso.exists() else "", r"re_[A-Za-z0-9_]{20,}")

    def test_working_tree_export_includes_edits_and_excludes_untracked(self):
        import tarfile
        code = re.search(r"<<'PYEXPORT'\n(.*?)\nPYEXPORT", BUILDER.read_text(), re.S).group(1)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"; root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "file.txt").write_text("before")
            subprocess.run(["git", "-C", str(root), "add", "file.txt"], check=True)
            (root / "file.txt").write_text("reviewed edit")
            (root / "untracked-secret.txt").write_text("must not be shipped")
            out = Path(d) / "payload.tar.gz"
            subprocess.run(["python3", "-c", code, str(root), str(out)], check=True)
            with tarfile.open(out) as archive:
                self.assertEqual(archive.getnames(), ["file.txt"])
                self.assertEqual(archive.extractfile("file.txt").read(), b"reviewed edit")
            (root / ".env").write_text("credential")
            subprocess.run(["git", "-C", str(root), "add", ".env"], check=True)
            result = subprocess.run(["python3", "-c", code, str(root), str(out)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing sensitive", result.stderr)
            self.assertNotIn("credential", result.stderr)

    def test_media_integrity_manifest_preserves_original_and_covers_changed_files(self):
        import hashlib
        code = re.search(r"<<'PYMD5'\n(.*?)\nPYMD5", BUILDER.read_text(), re.S).group(1)
        with tempfile.TemporaryDirectory() as d:
            stage = Path(d)
            (stage / "arise").mkdir()
            unchanged = hashlib.md5(b"original package", usedforsecurity=False).hexdigest()
            (stage / "md5sum.orig.txt").write_text(
                unchanged + "  ./pool/unchanged.deb\n" + "0" * 32 + "  ./boot/grub/grub.cfg\n"
                + "1" * 32 + "  ./md5sum.txt\n" + "2" * 32 + "  ./arise/old-payload\n")
            payloads = {"grub.cfg": b"new menu", "autoinstall.yaml": b"guided storage", "arise/ariseos-src.tar.gz": b"new source", "arise/VERSION": b"reviewed snapshot", "arise/SHA256SUMS": b"source checksum"}
            for name, content in payloads.items():
                (stage / name).write_bytes(content)
            subprocess.run(["python3", "-c", code, str(stage)], check=True)
            lines = (stage / "md5sum.txt").read_text().splitlines()
            entries = dict(line.split("  ", 1)[::-1] for line in lines)
            self.assertEqual(entries["./pool/unchanged.deb"], unchanged)
            self.assertNotIn("./md5sum.txt", entries)
            self.assertNotIn("./arise/old-payload", entries)
            self.assertEqual(len(entries), 1 + len(payloads))
            for name, content in payloads.items():
                iso_name = "./boot/grub/grub.cfg" if name == "grub.cfg" else "./" + name
                self.assertEqual(entries[iso_name], hashlib.md5(content, usedforsecurity=False).hexdigest())
            # Deterministic merge: reprocessing the same inputs gives the same manifest.
            before = (stage / "md5sum.txt").read_bytes()
            subprocess.run(["python3", "-c", code, str(stage)], check=True)
            self.assertEqual((stage / "md5sum.txt").read_bytes(), before)
            (stage / "md5sum.orig.txt").write_text("malformed manifest\n")
            result = subprocess.run(["python3", "-c", code, str(stage)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_supplied_base_iso_requires_checksum(self):
        text = BUILDER.read_text()
        self.assertIn('--ubuntu-iso requires --ubuntu-sha256', text)
        self.assertIn('Supplied Ubuntu ISO does not match', text)


class Wizard(unittest.TestCase):
    def test_parses(self):
        subprocess.run(["bash", "-n", str(WIZARD)], check=True)

    def test_password_never_on_a_command_line(self):
        s = WIZARD.read_text()
        self.assertIn("--admin-pass-file", s)
        self.assertNotRegex(s, r'--admin-pass[ =]"?\$')
        self.assertIn("chmod 600", s)
        self.assertNotIn("install -d -m 0700 /etc/arise/secrets", s)
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

    def test_completion_is_gated_by_password_and_readiness(self):
        src = WIZARD.read_text()
        done = src.index('touch "$DONE"')
        self.assertLess(src.index('if [ "$PW_SET" != 1 ]'), done)
        self.assertLess(src.index('if [ "$READY" != 1 ]'), done)
        self.assertIn('ARISE_WIZARD_SESSION=1 bash "$0" --from-boot', src)
        self.assertNotIn('Press Enter for a login prompt', src)
        self.assertIn('core) FLAGS+=(--no-apps)', src)

    def test_wizard_defaults_to_core_five_and_keeps_directory_only_test(self):
        src = WIZARD.read_text()
        menu = next(line for line in src.splitlines() if line.startswith('APP_SET='))
        self.assertLess(menu.index(' essentials "'), menu.index(' core "'))
        self.assertIn('essentials) FLAGS+=(--apps "nextcloud vaultwarden uptime-kuma netdata filebrowser")', src)
        self.assertIn('core) FLAGS+=(--no-apps)', src)
        self.assertIn('[ "$FROM_BOOT" = 1 ] && FLAGS+=(--grow-root)', src)
        self.assertIn('needs its disk passphrase at every restart', src)


class Docs(unittest.TestCase):
    def test_no_stale_manual_steps(self):
        for p in (ROOT / "installer" / "MAKE-USB.md", ROOT / "docs" / "VIRTUALBOX.md"):
            t = p.read_text()
            self.assertNotIn("REPLACE_WITH_HASH", t, p.name)
            self.assertIn("make-install-media.sh", t, p.name)
        self.assertIn("make-install-media.sh", (ROOT / "INSTALL.md").read_text())


if __name__ == "__main__":
    unittest.main()

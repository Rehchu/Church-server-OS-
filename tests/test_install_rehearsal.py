"""What the install rehearsal (a fresh Ubuntu 24.04 in a chroot, Oct 29) found, pinned so it stays fixed."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Rehearsal(unittest.TestCase):
    def test_the_cli_switches_to_the_venv(self):
        # A venv's python is a symlink to the system one: comparing resolved interpreter paths never
        # switched, and arisectl ran without the venv's modules (bcrypt, fastapi, psutil).
        for name in ("arisectl", "arisetui"):
            src = (ROOT / "cli" / name).read_text()
            self.assertIn('Path(sys.prefix).resolve() != (HOME / "venv").resolve()', src, name)
            self.assertNotIn("Path(sys.executable).resolve() != VENV_PY.resolve()", src, name)

    def test_secrets_stay_traversable(self):
        # 0711, never 0700: the owner reaches secrets/youtube/ and arise-kb secrets/archive/.
        src = (ROOT / "installer" / "install.sh").read_text()
        self.assertFalse(re.search(r'chmod 0?700 "\$CONF_DIR/secrets"', src))
        self.assertIn('chmod 0711 "$CONF_DIR/secrets"', src)

    def test_no_network_manager(self):
        # cockpit-networkmanager brings NetworkManager, a second owner for the network netplan runs.
        src = (ROOT / "installer" / "install.sh").read_text()
        install_lines = [ln for ln in src.splitlines() if "apt-get install" in ln and not ln.lstrip().startswith("#")]
        self.assertFalse([ln for ln in install_lines if "cockpit-networkmanager" in ln or "network-manager" in ln])

    def test_firefox_never_from_ubuntus_snap_stub(self):
        src = (ROOT / "scripts" / "arise-browser-setup").read_text()
        i = src.index("Mozilla's repository is not set up")
        self.assertLess(i, src.index("apt-get install -y -q firefox"))

    def test_service_account_ids_are_unique(self):
        ids = {}
        for f, pat in (("scripts/arise-repos-setup", r"useradd -u (\d+)"), ("scripts/arise-archive-setup", r"UID_WANTED=(\d+)"),
                       ("installer/install.sh", r"useradd -u (\d+)")):
            for m in re.finditer(pat, (ROOT / f).read_text()):
                ids.setdefault(m.group(1), set()).add(f)
        self.assertEqual({k: v for k, v in ids.items() if len(v) > 1}, {})
        owner = (ROOT / "scripts" / "arise-owner-setup").read_text()
        self.assertIn("arise-repos:1502", owner)
        self.assertIn("useradd -u 1502 -g arise-repos", (ROOT / "scripts" / "arise-repos-setup").read_text())


class DockerDown(unittest.TestCase):
    """A real box (not the preview) with Docker not running: no sample app is ever shown or "deployed"."""
    def test_no_sample_apps_on_a_real_box(self):
        import os
        import sys
        import tempfile
        from unittest import mock
        sys.path.insert(0, str(ROOT / "server"))
        from arise_server import apps, config
        with tempfile.TemporaryDirectory() as t:
            conf = Path(t) / "arise.toml"
            conf.write_text(f'[system]\ndata_root = "{t}/data"\n[paths]\nstate_dir = "{t}/state"\nlog_dir = "{t}/state"\n[apps]\nroot = "{t}/apps"\n')
            old = {k: os.environ.get(k) for k in ("ARISE_CONFIG", "ARISE_DEMO")}
            os.environ["ARISE_CONFIG"] = str(conf)
            os.environ.pop("ARISE_DEMO", None)
            config.load(force=True)
            try:
                with mock.patch.object(apps, "available", return_value=False):
                    listing = apps.list_apps()
                    self.assertEqual(listing["apps"], [])
                    self.assertFalse(listing["demo"])
                    self.assertFalse(listing["docker"])
                    for r in (apps.deploy("bookstack"), apps.act("bookstack", "start")):
                        self.assertFalse(r["ok"])
                        self.assertIn("Docker is not running", r["err"])
                    self.assertIn("Docker is not running", apps.logs("bookstack")["text"])
            finally:
                for k, v in old.items():
                    os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                config.load(force=True)


if __name__ == "__main__":
    unittest.main()

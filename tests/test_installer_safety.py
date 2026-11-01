"""Behavioral checks for installer decision helpers without changing the host."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / 'installer' / 'install.sh'


def shell_function(name):
    source = INSTALLER.read_text()
    return re.search(r'(?ms)^' + re.escape(name) + r'\(\) \{\n.*?^\}', source).group(0)


class InstallerSafety(unittest.TestCase):
    def run_helper(self, name, args, stubs='', extra_env=None):
        script = 'set -euo pipefail\nnote() { :; }\nwarn() { :; }\n' + stubs + '\n' + shell_function(name)
        return subprocess.run(['bash', '-c', script + '\n' + name + ' "$@"', 'test', *args],
                              env={**os.environ, 'DRY_RUN': '0', **(extra_env or {})},
                              capture_output=True, text=True)

    def test_app_selection_is_exact_and_empty_means_none(self):
        for selection, app, wanted in [('', 'nextcloud', False), ('all', 'nextcloud', True),
                                      ('vaultwarden filebrowser', 'nextcloud', False),
                                      ('nextcloud vaultwarden', 'nextcloud', True),
                                      ('nextcloud-copy', 'nextcloud', False)]:
            result = subprocess.run(['bash', '-c', shell_function('wants_app') + '\nwants_app "$1"',
                                     'test', app], env={**os.environ, 'APPS_REQUESTED': selection})
            self.assertEqual(result.returncode == 0, wanted, (selection, app))

    def test_no_start_suppresses_direct_service_starts_and_removes_now(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / 'calls'
            stub = Path(d) / 'systemctl'
            stub.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALL_LOG"\n')
            stub.chmod(0o755)
            script = shell_function('systemctl') + '''
systemctl enable --now docker
systemctl start samba-ad-dc
systemctl restart arise-web
systemctl reload caddy
systemctl is-active samba-ad-dc
'''
            subprocess.run(['bash', '-c', script], check=True, env={**os.environ, 'NO_START':'1',
                           'PATH': d + ':' + os.environ['PATH'], 'CALL_LOG':str(log)})
            self.assertEqual(log.read_text().splitlines(), ['enable docker', 'is-active samba-ad-dc'])
            log.unlink()
            subprocess.run(['bash', '-c', script], check=True, env={**os.environ, 'NO_START':'0',
                           'PATH': d + ':' + os.environ['PATH'], 'CALL_LOG':str(log)})
            self.assertIn('start samba-ad-dc', log.read_text().splitlines())

    def test_package_start_policy_restores_existing_and_preserves_failed_move(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'policy-rc.d'
            saved = Path(d) / 'saved'; saved.mkdir()
            target.write_text('temporary deny')
            (saved / 'original').symlink_to('../original-policy')
            (Path(d) / 'original-policy').write_text('admin policy')
            code = shell_function('cleanup_install').replace('/usr/sbin/policy-rc.d', str(target))
            subprocess.run(['bash', '-c', code + '\ncleanup_install'], check=True,
                           env={**os.environ, 'POLICY_DIR':str(saved), 'POLICY_WRITTEN':'1'})
            self.assertTrue(target.is_symlink())
            self.assertEqual(os.readlink(target), '../original-policy')
            target.unlink(); target.write_text('untouched admin policy'); saved.mkdir()
            subprocess.run(['bash', '-c', code + '\ncleanup_install'], check=True,
                           env={**os.environ, 'POLICY_DIR':str(saved), 'POLICY_WRITTEN':'0'})
            self.assertEqual(target.read_text(), 'untouched admin policy')

    def test_default_address_and_recovery_are_fail_closed(self):
        text = INSTALLER.read_text()
        self.assertRegex(text, r'(?m)^PIN_IP=0$')
        self.assertNotIn('addresses: [127.0.0.1]', text)
        self.assertIn('die "No Samba offline backup', text)
        self.assertIn('die "Samba domain restore failed', text)
        self.assertIn('NO_START=1; APPS=""; APPS_REQUESTED=""', text)
        self.assertNotRegex(text, r'arisectl rescue card >>')

    def test_backup_job_migration_is_additive_and_repeatable(self):
        import yaml
        code = re.search(r"<<'PYJOBS'\n(.*?)\nPYJOBS", INSTALLER.read_text(), re.S).group(1)
        with tempfile.TemporaryDirectory() as d:
            current, defaults = Path(d) / 'custom.yaml', Path(d) / 'defaults.yaml'
            current.write_text('jobs:\n  - id: custom\n    paths: [/custom]\n  - id: state\n    paths: [/my-state]\n')
            defaults.write_text('jobs:\n  - id: state\n    paths: [/default-state]\n  - id: leavers\n    paths: [/leavers]\n')
            for _ in range(2):
                subprocess.run([os.sys.executable, '-c', code, str(current), str(defaults)], check=True, capture_output=True)
            jobs = yaml.safe_load(current.read_text())['jobs']
            self.assertEqual([j['id'] for j in jobs], ['custom', 'state', 'leavers'])
            self.assertEqual(jobs[1]['paths'], ['/my-state'])
            self.assertTrue(current.with_name('custom.yaml.before-state-jobs').exists())

    def test_root_luks_selection_rejects_ambiguous_or_unencrypted_root(self):
        for devices, expected in [('/dev/mapper/root ext4\n/dev/sda3 crypto_LUKS\n/dev/sda\n', '/dev/sda3'),
                                  ('/dev/mapper/root ext4\n/dev/sda3 crypto_LUKS\n/dev/sdb3 crypto_LUKS\n', None),
                                  ('/dev/sda2 ext4\n/dev/sda\n', None)]:
            result = self.run_helper('root_luks_device', ['/dev/mapper/root'],
                                     'lsblk() { printf "%s" "$DEVICES"; }', {'DEVICES': devices})
            self.assertEqual(result.returncode == 0, expected is not None)
            if expected:
                self.assertEqual(result.stdout.strip(), expected)

    def test_tpm_binding_requires_confirmed_version_two(self):
        with tempfile.TemporaryDirectory() as d:
            version_file = Path(d) / 'tpm_version_major'
            for detected, expected in [('1\n', '1'), ('2\n', '2'), ('unexpected\n', '0')]:
                version_file.write_text(detected)
                result = self.run_helper('tpm_version_major', [str(version_file)])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)
        source = INSTALLER.read_text()
        self.assertIn('elif [ "$TPM_MAJOR" != 2 ]; then', source)
        self.assertNotIn('[ ! -e /dev/tpmrm0 ] && [ ! -e /dev/tpm0 ]', source)

    def test_root_growth_only_uses_free_extents_on_single_linear_ext4_lv(self):
        stubs = '''
findmnt() { echo "$ROOT_FS"; }
lvs() { if [[ "$*" == *vg_name* ]]; then echo ubuntu-vg; else echo "$SEGMENT"; fi; }
vgs() { if [[ "$*" == *lv_count* ]]; then echo "$LV_COUNT"; else echo "$FREE_EXTENTS"; fi; }
run() { printf '%s\\n' "$*" >> "$CALL_LOG"; }
'''
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / 'calls'
            for fs, segment, count, free, grows in [('ext4', 'linear', '1', '12', True),
                                                    ('ext4', 'linear', '2', '12', False),
                                                    ('ext4', 'thin', '1', '12', False),
                                                    ('ext4', 'linear', '1', '0', False),
                                                    ('xfs', 'linear', '1', '12', False)]:
                log.unlink(missing_ok=True)
                result = self.run_helper('grow_root_volume', ['/dev/mapper/ubuntu-root'], stubs,
                                         {'ROOT_FS': fs, 'SEGMENT': segment, 'LV_COUNT': count,
                                          'FREE_EXTENTS': free, 'CALL_LOG': str(log)})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(log.exists(), grows, (fs, segment, count, free))
                if grows:
                    self.assertEqual(log.read_text().strip(), 'lvextend -r -l +100%FREE /dev/mapper/ubuntu-root')

    def test_trim_changes_only_root_preserves_mode_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as d:
            crypttab = Path(d) / 'crypttab'
            log = Path(d) / 'calls'
            original = ('root UUID=root-id none luks\n# comment stays\n'
                        'backup UUID=backup-id none luks\n'
                        'swap /dev/sda4 /dev/urandom swap\n')
            crypttab.write_text(original); crypttab.chmod(0o600)
            stubs = 'blkid() { echo root-id; }\nupdate-initramfs() { printf "%s\\n" "$*" >> "$CALL_LOG"; }'
            for _ in range(2):
                result = self.run_helper('enable_root_trim', [str(crypttab), '/dev/sda3'], stubs,
                                         {'CALL_LOG': str(log)})
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(crypttab.read_text(), original.replace('root-id none luks', 'root-id none luks,discard'))
            self.assertEqual(crypttab.stat().st_mode & 0o777, 0o600)
            self.assertEqual(log.read_text().splitlines(), ['-u -k all'])
            backups = list(Path(d).glob('crypttab.arise-backup.*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), original)
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)

    def test_trim_initramfs_failure_restores_original_and_fails(self):
        with tempfile.TemporaryDirectory() as d:
            crypttab = Path(d) / 'crypttab'
            original = 'root UUID=root-id none luks\n'
            crypttab.write_text(original)
            stubs = '''
blkid() { echo root-id; }
update-initramfs() {
  printf '%s\\n' "$*" >> "$CALL_LOG"
  if [ ! -e "$FAIL_MARKER" ]; then touch "$FAIL_MARKER"; return 1; fi
}
'''
            log = Path(d) / 'calls'
            result = self.run_helper('enable_root_trim', [str(crypttab), '/dev/sda3'], stubs,
                                     {'CALL_LOG': str(log), 'FAIL_MARKER': str(Path(d) / 'failed')})
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(crypttab.read_text(), original)
            self.assertEqual(log.read_text().splitlines(), ['-u -k all', '-u -k all'])

    def test_trim_dry_run_never_creates_files(self):
        with tempfile.TemporaryDirectory() as d:
            crypttab = Path(d) / 'crypttab'; crypttab.write_text('root UUID=root-id none luks\n')
            result = self.run_helper('enable_root_trim', [str(crypttab), '/dev/sda3'],
                                     'blkid() { echo root-id; }\nupdate-initramfs() { return 99; }', {'DRY_RUN': '1'})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(Path(d).iterdir()), [crypttab])
            self.assertEqual(crypttab.read_text(), 'root UUID=root-id none luks\n')

    def test_efi_fallback_publishes_complete_set_and_preserves_existing(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / 'EFI' / 'ubuntu'; source.mkdir(parents=True)
            for name in ['shimx64.efi', 'grubx64.efi', 'mmx64.efi', 'grub.cfg']:
                (source / name).write_text(name)
            stubs = 'mountpoint() { return 0; }\nfindmnt() { echo vfat; }'
            result = self.run_helper('install_efi_fallback', [d], stubs)
            self.assertEqual(result.returncode, 0, result.stderr)
            target = Path(d) / 'EFI' / 'BOOT'
            self.assertEqual(sorted(p.name for p in target.iterdir()), ['BOOTX64.EFI', 'grub.cfg', 'grubx64.efi', 'mmx64.efi'])
            self.assertEqual((target / 'BOOTX64.EFI').read_text(), 'shimx64.efi')
            (target / 'BOOTX64.EFI').write_text('existing fallback')
            self.assertEqual(self.run_helper('install_efi_fallback', [d], stubs).returncode, 0)
            self.assertEqual((target / 'BOOTX64.EFI').read_text(), 'existing fallback')

    def test_efi_fallback_copy_failure_leaves_no_success_marker_and_can_retry(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / 'EFI' / 'ubuntu'; source.mkdir(parents=True)
            for name in ['shimx64.efi', 'grubx64.efi', 'mmx64.efi', 'grub.cfg']:
                (source / name).write_text(name)
            stubs = '''
mountpoint() { return 0; }
findmnt() { echo vfat; }
cp() { if [[ "$*" == *mmx64* ]]; then return 1; fi; command cp "$@"; }
'''
            result = self.run_helper('install_efi_fallback', [d], stubs)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((Path(d) / 'EFI' / 'BOOT').exists())
            self.assertEqual(list((Path(d) / 'EFI').iterdir()), [source])
            retry = self.run_helper('install_efi_fallback', [d], 'mountpoint() { return 0; }\nfindmnt() { echo vfat; }')
            self.assertEqual(retry.returncode, 0, retry.stderr)

    def test_efi_fallback_requires_mounted_fat_and_preserves_other_bootloader(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / 'EFI' / 'ubuntu'; source.mkdir(parents=True)
            for name in ['shimx64.efi', 'grubx64.efi', 'mmx64.efi', 'grub.cfg']:
                (source / name).write_text(name)
            for stubs in ['mountpoint() { return 1; }',
                          'mountpoint() { return 0; }\nfindmnt() { echo ext4; }']:
                self.assertEqual(self.run_helper('install_efi_fallback', [d], stubs).returncode, 0)
                self.assertFalse((Path(d) / 'EFI' / 'BOOT').exists())
            target = Path(d) / 'EFI' / 'BOOT'; target.mkdir()
            (target / 'grubx64.efi').write_text('other OS')
            self.assertEqual(self.run_helper('install_efi_fallback', [d], 'mountpoint() { return 0; }\nfindmnt() { echo vfat; }').returncode, 0)
            self.assertFalse((target / 'BOOTX64.EFI').exists())
            self.assertEqual((target / 'grubx64.efi').read_text(), 'other OS')


if __name__ == '__main__':
    unittest.main()

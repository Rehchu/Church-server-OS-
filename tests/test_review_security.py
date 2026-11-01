"""Regression checks for login challenges and archive authorization."""
import copy
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
os.environ.setdefault('ARISE_DEMO', '1')
from arise_server import auth, twofa, config, archive_safe, sharing, finder, links


class LoginChallenge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = copy.deepcopy(config.load(force=True))
        self.cfg.web.secret_file = str(Path(self.tmp.name) / 'session-key')
        self.cfg.demo = False
        self.patch = mock.patch.object(auth, 'load', return_value=self.cfg)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.patch2 = mock.patch.object(twofa, 'load', return_value=self.cfg)
        self.patch2.start()
        self.addCleanup(self.patch2.stop)
        twofa._pending.clear()

    def test_challenge_contains_no_session_and_is_single_use(self):
        completed = auth._serializer().dumps({'u': 'review', 'r': 'admin'})
        challenge = twofa.pending_token(completed, 'review')
        payload = twofa._serializer().loads(challenge)
        self.assertEqual(set(payload), {'n'})
        self.assertNotIn(completed, str(payload))
        with mock.patch.object(twofa, '_read', return_value={'on': True, 'secret': 'test'}), mock.patch.object(twofa, 'fresh_code', return_value=True):
            result = twofa.finish(challenge, '123456')
            self.assertEqual(result['token'], completed)
            self.assertFalse(twofa.finish(challenge, '123456')['ok'])

    def test_failed_codes_destroy_the_server_challenge(self):
        challenge = twofa.pending_token('fixture-session', 'review')
        with mock.patch.object(twofa, '_read', return_value={'on': True}), mock.patch.object(twofa, 'fresh_code', return_value=False):
            for remaining in (2, 1, 0):
                result = twofa.finish(challenge, '000000')
                self.assertFalse(result['ok'])
                self.assertEqual(result['left'], remaining)
        with mock.patch.object(twofa, 'fresh_code', return_value=True):
            self.assertFalse(twofa.finish(challenge, '123456')['ok'])

    def test_restart_and_expiry_invalidate_challenges(self):
        challenge = twofa.pending_token('fixture-session', 'review')
        for rec in twofa._pending.values():
            rec['expires'] = 0
        self.assertFalse(twofa.finish(challenge, '123456')['ok'])
        challenge = twofa.pending_token('fixture-session', 'review')
        twofa._pending.clear()
        self.assertFalse(twofa.finish(challenge, '123456')['ok'])

    def test_nonroot_demo_key_is_stable_but_real_server_fails_closed(self):
        self.cfg.web.secret_file = str(Path(self.tmp.name) / 'unwritable-key')
        with mock.patch.dict(os.environ, {'ARISE_WEB_SECRET': ''}), mock.patch.object(Path, 'read_text', side_effect=PermissionError), mock.patch('arise_server.auth.os.open', side_effect=PermissionError):
            self.cfg.demo = True
            self.assertEqual(auth._secret(self.cfg), auth._secret(self.cfg))
            self.cfg.demo = False
            with self.assertRaises(RuntimeError):
                auth._secret(self.cfg)

    def test_privileged_mutations_require_recent_admin_password(self):
        from arise_server.main import app
        for path in ['/api/directory/users', '/api/directory/users/{name}/reset-password', '/api/directory/groups/{group}/members', '/api/apps/deploy']:
            routes = [r for r in app.routes if getattr(r, 'path', None) == path and 'POST' in getattr(r, 'methods', set())]
            self.assertTrue(routes, path)
            for route in routes:
                self.assertIn(auth.require_recent_admin, [dep.call for dep in route.dependant.dependencies], path)


class ArchivePermissions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        (self.base / 'pastors').mkdir()
        (self.base / 'pastors' / 'private.txt').write_text('fixture private data')
        (self.base / 'public.txt').write_text('fixture public data')
        (self.base / 'alias').symlink_to(self.base / 'pastors', target_is_directory=True)
        (self.base / 'file-alias').symlink_to(self.base / 'pastors' / 'private.txt')
        self.who = {'user': 'review-admin', 'role': 'admin'}
        self.cfg = copy.deepcopy(config.load(force=True))
        self.cfg.demo = False
        self.cfg.storage.pastors_path = str(self.base / 'pastors')
        self.cfg.links.max_zip_bytes = 1024 * 1024
        for module in (sharing, finder, links):
            p = mock.patch.object(module, 'load', return_value=self.cfg)
            p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(sharing, 'is_pastor', return_value=False)
        p.start(); self.addCleanup(p.stop)

    def test_recursive_public_and_finder_archives_exclude_private_descendants(self):
        self.assertEqual([p[1] for p in links.zip_members(str(self.base), self.who)], ['public.txt'])
        with mock.patch.object(finder, '_abs', return_value=({}, str(self.base))):
            result = finder.zip_path('data', '/', self.who)
        self.assertTrue(result['ok'])
        self.addCleanup(__import__('shutil').rmtree, str(Path(result['zip']).parent))
        with zipfile.ZipFile(result['zip']) as z:
            self.assertEqual(z.namelist(), ['Server/public.txt'])
            self.assertEqual(z.read('Server/public.txt'), b'fixture public data')

    def test_public_archive_never_includes_pastors_even_for_pastor(self):
        with mock.patch.object(sharing, 'is_pastor', return_value=True):
            self.assertEqual([p[1] for p in links.zip_members(str(self.base), self.who)], ['public.txt'])

    def test_symlink_replacement_between_listing_and_read_is_refused(self):
        (self.base / 'normal').mkdir()
        (self.base / 'normal' / 'data.txt').write_text('normal')
        (self.base / 'normal' / 'data.txt').unlink()
        (self.base / 'normal').rmdir()
        (self.base / 'normal').symlink_to(self.base / 'pastors', target_is_directory=True)
        with zipfile.ZipFile(io.BytesIO(), 'w') as z, self.assertRaises((OSError, ValueError)):
            archive_safe.write_member(z, str(self.base), 'normal/private.txt', 'data.txt', self.who)

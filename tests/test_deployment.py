import hashlib
import io
import json
import shutil
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_release import build
from deploy_receiver import Deployer
from site_rules import allowed_path, REQUIRED_FILES

REVISION = 'a' * 40


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / 'source'
        self.source.mkdir()
        for name in REQUIRED_FILES:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('current site: ' + name)
        self.live = self.base / 'www' / 'promoznachki.ru'
        self.live.parent.mkdir()
        shutil.copytree(self.source, self.live)
        self.original = (self.live / 'index.html').read_bytes()
        self.deployer = Deployer(self.base / 'deploy', self.live, php=shutil.which('true'), health=lambda *_: None)
        self.archive = self.base / 'release.tar.gz'
        build(self.source, self.archive, REVISION, '1-1')

    def deploy(self, revision=REVISION, run_id='1-1'):
        with self.archive.open('rb') as archive:
            self.deployer.deploy(archive, revision, run_id)

    def rewrite_archive(self, change):
        with tarfile.open(self.archive, 'r:gz') as source:
            members = [(member, source.extractfile(member).read()) for member in source]
        with tarfile.open(self.archive, 'w:gz') as output:
            for member, data in members:
                member, data = change(member, data)
                member.size = len(data)
                output.addfile(member, io.BytesIO(data))

    def test_success_keeps_original_and_removes_private_manifest(self):
        self.deploy()
        self.assertTrue(self.live.is_symlink())
        state = json.loads((self.deployer.root / 'state.json').read_text())
        self.assertEqual((self.deployer.releases / state['previous'] / 'index.html').read_bytes(), self.original)
        self.assertFalse((self.live / '.deploy-manifest.json').exists())
        self.assertEqual((self.live / 'deploy-version.json').stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.live.resolve().stat().st_mode & 0o777, 0o755)

    @patch('deploy_receiver.time.sleep')
    def test_failed_health_restores_original(self, _sleep):
        self.deployer.health = lambda *_: (_ for _ in ()).throw(RuntimeError('HTTP check failed'))
        with self.assertRaises(RuntimeError):
            self.deploy()
        self.assertEqual((self.live / 'index.html').read_bytes(), self.original)
        self.assertEqual(json.loads((self.deployer.root / 'state.json').read_text())['current'], self.live.resolve().name)

    def test_manual_rollback_and_stale_guard(self):
        self.deploy()
        release = self.live.resolve().name
        with self.assertRaises(ValueError):
            self.deployer.rollback('b' * 40 + '-2-1')
        self.deployer.rollback(release)
        self.assertEqual((self.live / 'index.html').read_bytes(), self.original)
        self.assertFalse((self.live / 'deploy-version.json').exists())

    def test_invalid_identity_never_changes_production(self):
        with self.assertRaises(ValueError):
            self.deploy('b' * 40)
        self.assertFalse(self.live.is_symlink())

    def test_checksum_failure_never_changes_production(self):
        self.rewrite_archive(lambda member, data: (member, b'corrupted' if member.name == 'index.html' else data))
        with self.assertRaises(ValueError):
            self.deploy()
        self.assertFalse(self.live.is_symlink())

    def test_path_traversal_is_rejected(self):
        def change(member, data):
            if member.name == 'index.html':
                member.name = '../escaped.html'
            return member, data
        self.rewrite_archive(change)
        with self.assertRaises(ValueError):
            self.deploy()
        self.assertFalse((self.deployer.releases / 'escaped.html').exists())
        self.assertFalse(self.live.is_symlink())

    def test_archive_symlinks_are_rejected(self):
        def change(member, data):
            if member.name == 'index.html':
                member.type = tarfile.SYMTYPE
                member.linkname = '/etc/passwd'
            return member, data
        self.rewrite_archive(change)
        with self.assertRaises(ValueError):
            self.deploy()

    def test_second_release_and_rollback(self):
        self.deploy()
        first = self.live.resolve()
        (self.source / 'index.html').write_text('updated website')
        build(self.source, self.archive, 'b' * 40, '2-1')
        self.deploy('b' * 40, '2-1')
        second = self.live.resolve()
        self.assertNotEqual(first, second)
        self.deployer.rollback(second.name)
        self.assertEqual(self.live.resolve(), first)

    @patch('deploy_receiver.time.sleep')
    def test_failed_second_deploy_preserves_previous_rollback(self, _sleep):
        self.deploy()
        state = json.loads((self.deployer.root / 'state.json').read_text())
        first = self.live.resolve()
        build(self.source, self.archive, 'b' * 40, '2-1')
        self.deployer.health = lambda *_: (_ for _ in ()).throw(RuntimeError('unhealthy'))
        with self.assertRaises(RuntimeError):
            self.deploy('b' * 40, '2-1')
        self.assertEqual(first, self.live.resolve())
        self.assertEqual(state, json.loads((self.deployer.root / 'state.json').read_text()))

    def test_archive_is_reproducible_and_excludes_credentials(self):
        before = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        (self.source / '.env').write_text('SECRET=do-not-ship')
        (self.source / '.git').mkdir()
        (self.source / '.git/config').write_text('private git config')
        build(self.source, self.archive, REVISION, '1-1')
        self.assertEqual(before, hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.assertFalse(allowed_path('assets/evil.php'))
        self.assertFalse(allowed_path('assets/../send-request.php'))
        self.assertFalse(allowed_path('/index.html'))


if __name__ == '__main__':
    unittest.main()

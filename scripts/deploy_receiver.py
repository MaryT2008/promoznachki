#!/usr/bin/env python3
"""Installed outside the document root; used as the deploy key's forced command."""
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from site_rules import allowed_path, REQUIRED_FILES

MAX_ARCHIVE = 64 * 1024 * 1024
MAX_CONTENT = 128 * 1024 * 1024
RELEASE_ID = re.compile(r'[0-9a-f]{40}-\d+-\d+\Z')


class Deployer:
    def __init__(self, root, document_root, url='https://promoznachki.ru', php='/opt/php/8.3/bin/php', health=None):
        self.root = Path(root)
        self.document_root = Path(document_root)
        self.releases = self.root / 'releases'
        self.url = url
        self.php = php
        self.health = health or self.check_health
        self.root.mkdir(parents=True, exist_ok=True)
        self.releases.mkdir(exist_ok=True)

    def log(self, event, **fields):
        entry = dict(fields, event=event, timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
        with (self.root / 'deployments.jsonl').open('a') as stream:
            stream.write(json.dumps(entry, sort_keys=True) + '\n')
        print(json.dumps(entry, sort_keys=True), flush=True)

    def current(self):
        if not self.document_root.is_symlink():
            return None
        target = self.document_root.resolve(strict=True)
        if target.parent != self.releases.resolve():
            raise ValueError('Document root points outside this deployment')
        return target

    def switch(self, target):
        if target.parent.resolve() != self.releases.resolve() or not target.is_dir():
            raise ValueError('Invalid release target')
        temporary = self.document_root.with_name('.promoznachki-switch-' + str(os.getpid()))
        try:
            temporary.symlink_to(target)
            os.replace(str(temporary), str(self.document_root))
        finally:
            if temporary.is_symlink():
                temporary.unlink()

    def save_state(self, current, previous):
        state = {'current': current.name, 'previous': previous.name if previous else None}
        temporary = self.root / 'state.json.tmp'
        temporary.write_text(json.dumps(state, sort_keys=True) + '\n')
        os.replace(str(temporary), str(self.root / 'state.json'))

    def unpack(self, source, stage, revision, run_id):
        size = 0
        with tempfile.TemporaryFile() as incoming:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_ARCHIVE:
                    raise ValueError('Archive exceeds 64 MiB')
                incoming.write(chunk)
            incoming.seek(0)
            with tarfile.open(fileobj=incoming, mode='r:gz') as archive:
                names = set()
                total = 0
                for member in archive:
                    name = member.name
                    if not member.isfile() or name in names or len(names) >= 2000:
                        raise ValueError('Only unique regular files are permitted')
                    if name != '.deploy-manifest.json' and not allowed_path(name):
                        raise ValueError('Forbidden archive path: ' + name)
                    total += member.size
                    if member.size > 32 * 1024 * 1024 or total > MAX_CONTENT:
                        raise ValueError('Uncompressed release is too large')
                    names.add(name)
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as original, target.open('wb') as output:
                        shutil.copyfileobj(original, output)
                    target.chmod(0o644)
        manifest_path = stage / '.deploy-manifest.json'
        manifest = json.loads(manifest_path.read_text())
        if manifest['revision'] != revision or manifest['run_id'] != run_id:
            raise ValueError('Release identity mismatch')
        files = manifest['files']
        if set(files) != names - {'.deploy-manifest.json'} or not REQUIRED_FILES <= files.keys():
            raise ValueError('Manifest does not match the complete release')
        for name, expected in files.items():
            data = (stage / name).read_bytes()
            if len(data) != expected['size'] or hashlib.sha256(data).hexdigest() != expected['sha256']:
                raise ValueError('Checksum mismatch: ' + name)
        version = json.loads((stage / 'deploy-version.json').read_text())
        if version != {'revision': revision, 'run_id': run_id}:
            raise ValueError('Public version marker mismatch')
        subprocess.run([self.php, '-l', str(stage / 'send-request.php')], check=True, timeout=30)
        manifest_path.unlink()
        return manifest

    def check_health(self, revision=None, run_id=None):
        def request(path, expected):
            url = self.url + path + ('&' if '?' in path else '?') + 'deploy-check=' + str(time.time_ns() if hasattr(time, 'time_ns') else time.time())
            try:
                with urllib.request.urlopen(url, timeout=20) as response:
                    status, body = response.status, response.read()
            except urllib.error.HTTPError as error:
                status, body = error.code, error.read()
            if status != expected:
                raise RuntimeError('{} returned {}, expected {}'.format(path, status, expected))
            return body
        if revision:
            version = json.loads(request('/deploy-version.json', 200))
            if version != {'revision': revision, 'run_id': run_id}:
                raise RuntimeError('Wrong release is being served')
        request('/', 200)
        request('/kontakty.html', 200)
        request('/sitemap.xml', 200)
        response = json.loads(request('/send-request.php', 405))
        if response.get('success') is not False:
            raise RuntimeError('Form handler is not responding correctly')
        request('/deployment-nonexistent-page', 404)

    def retry_health(self, revision=None, run_id=None):
        for attempt in range(4):
            try:
                self.health(revision, run_id)
                return
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2)

    def deploy(self, source, revision, run_id):
        release_id = revision + '-' + run_id
        if not RELEASE_ID.fullmatch(release_id):
            raise ValueError('Invalid release ID')
        release = self.releases / release_id
        if release.exists():
            raise ValueError('Release ID already exists; rerun with a new attempt')
        stage = Path(tempfile.mkdtemp(prefix='.incoming-', dir=str(self.releases)))
        previous = None
        switched = False
        old_state = json.loads((self.root / 'state.json').read_text()) if (self.root / 'state.json').exists() else {}
        try:
            manifest = self.unpack(source, stage, revision, run_id)
            stage.chmod(0o755)
            os.rename(str(stage), str(release))
            previous = self.current()
            if previous is None:
                if not self.document_root.is_dir():
                    raise ValueError('Existing production directory is missing')
                # Keep the original tree intact as the permanent initial backup.
                previous = self.releases / ('baseline-' + time.strftime('%Y%m%d%H%M%S'))
                os.rename(str(self.document_root), str(previous))
                try:
                    self.switch(release)
                except BaseException:
                    os.rename(str(previous), str(self.document_root))
                    raise
            else:
                self.switch(release)
            switched = True
            self.retry_health(revision, run_id)
            self.save_state(release, previous)
            (self.root / (release_id + '.json')).write_text(json.dumps(manifest, sort_keys=True))
            self.log('deployed', current=release_id, previous=previous.name, revision=revision)
        except BaseException:
            if switched and previous:
                self.switch(previous)
                older = self.releases / old_state['previous'] if old_state.get('previous') else None
                self.save_state(previous, older)
                self.log('automatic_rollback', failed=release_id, restored=previous.name)
            raise
        finally:
            if stage.exists():
                shutil.rmtree(str(stage))
        # Keep ten recent releases, both rollback targets, and the initial backup.
        protected = {release, previous}
        candidates = sorted((p for p in self.releases.iterdir() if RELEASE_ID.fullmatch(p.name) and p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
        for obsolete in candidates[10:]:
            if obsolete not in protected:
                try:
                    shutil.rmtree(str(obsolete))
                except OSError as error:
                    self.log('retention_warning', release=obsolete.name, error=str(error))

    def rollback(self, expected):
        if not RELEASE_ID.fullmatch(expected):
            raise ValueError('Invalid expected release ID')
        current = self.current()
        if current is None or current.name != expected:
            raise ValueError('Current release changed; refusing stale rollback')
        state = json.loads((self.root / 'state.json').read_text())
        if state.get('current') != expected or not state.get('previous'):
            raise ValueError('No matching previous release')
        previous = self.releases / state['previous']
        self.switch(previous)
        try:
            version_file = previous / 'deploy-version.json'
            version = json.loads(version_file.read_text()) if version_file.exists() else {}
            self.retry_health(version.get('revision'), version.get('run_id'))
        except BaseException:
            self.switch(current)
            raise
        self.save_state(previous, current)
        self.log('manual_rollback', current=previous.name, previous=current.name)


def main():
    os.umask(0o022)
    def interrupted(number, _frame):
        raise InterruptedError('Interrupted by signal ' + str(number))
    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGALRM):
        signal.signal(number, interrupted)
    signal.alarm(600)
    root = Path(__file__).resolve().parent
    deployer = Deployer(root, Path.home() / 'www/promoznachki.ru')
    command = os.environ.get('SSH_ORIGINAL_COMMAND', '').split()
    with (root / 'deploy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if len(command) == 3 and command[0] == 'deploy':
            deployer.deploy(sys.stdin.buffer, command[1], command[2])
        elif len(command) == 2 and command[0] == 'rollback':
            deployer.rollback(command[1])
        elif command == ['status']:
            current = deployer.current()
            print((root / 'state.json').read_text() if (root / 'state.json').exists() else json.dumps({'current': current.name if current else 'original-directory'}))
        else:
            raise ValueError('Only deploy, rollback and status commands are allowed')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Deployment failed: ' + str(error), file=sys.stderr)
        sys.exit(1)

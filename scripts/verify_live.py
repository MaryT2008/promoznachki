#!/usr/bin/env python3
"""Verify public bytes after deployment without submitting a real enquiry."""
import argparse
import concurrent.futures
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote


def fetch(base, path, expected=200, method='GET', headers=None, data=None):
    url = base.rstrip('/') + '/' + path + ('&' if '?' in path else '?') + 'ci-check=' + str(time.time_ns())
    request = urllib.request.Request(url, method=method, headers=headers or {}, data=data)
    for attempt in range(3):
        try:
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    status, body = response.status, response.read()
            except urllib.error.HTTPError as error:
                status, body = error.code, error.read()
                if status in (429, 502, 503, 504) and status != expected:
                    raise ConnectionError('Temporary HTTP ' + str(status))
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    if status != expected:
        raise AssertionError('{}: HTTP {}, expected {}'.format(path, status, expected))
    return body


def verify(base, directory):
    paths = sorted(p for p in directory.rglob('*') if p.is_file() and p.name != '.deploy-manifest.json')

    def check(path):
        name = path.relative_to(directory).as_posix()
        if name in ('.htaccess', '.user.ini', 'send-request.php'):
            return
        url_path = '' if name == 'index.html' else quote(name)
        actual = fetch(base, url_path)
        if hashlib.sha256(actual).digest() != hashlib.sha256(path.read_bytes()).digest():
            raise AssertionError('Public bytes differ: ' + name)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(check, paths))
    assert json.loads(fetch(base, 'send-request.php', 405))['success'] is False
    assert json.loads(fetch(base, 'send-request.php', 403, 'POST', data=b''))['success'] is False
    assert json.loads(fetch(base, 'send-request.php', 200, 'POST', headers={'Origin': 'https://promoznachki.ru', 'Content-Type': 'application/x-www-form-urlencoded'}, data=b'_honey=ci-check'))['success'] is True
    fetch(base, '.user.ini', 403)
    fetch(base, 'ci-unexpected.php', 403)
    fetch(base, 'ci-missing-page', 404)
    print('All public release files match; form, access restrictions and 404 respond correctly. No mail sent.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='https://promoznachki.ru')
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    verify(args.base, args.directory)

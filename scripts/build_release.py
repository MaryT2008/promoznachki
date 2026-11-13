#!/usr/bin/env python3
"""Create an allowlisted, reproducible archive; never upload the checkout itself."""
import argparse
import gzip
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path
from site_rules import allowed_path, REQUIRED_FILES


def build(root, output, revision, run_id):
    if not re.fullmatch(r'[0-9a-f]{40}', revision) or not re.fullmatch(r'\d+-\d+', run_id):
        raise ValueError('Invalid revision or run ID')
    contents = {}
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if allowed_path(name):
            if path.is_symlink():
                raise ValueError('Symlink in public files: ' + name)
            if path.is_file():
                contents[name] = path.read_bytes()
    if not REQUIRED_FILES <= contents.keys():
        raise ValueError('Required site files are missing')
    contents['deploy-version.json'] = (json.dumps({'revision': revision, 'run_id': run_id}, sort_keys=True) + '\n').encode()
    manifest = {'revision': revision, 'run_id': run_id, 'files': {
        name: {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
        for name, data in contents.items()
    }}
    contents['.deploy-manifest.json'] = json.dumps(manifest, sort_keys=True).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as archive:
            for name, data in sorted(contents.items()):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(data))
    print('Built {} public files: {}'.format(len(contents) - 1, output))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, default=Path('dist/site.tar.gz'))
    args = parser.parse_args()
    build(Path(__file__).resolve().parents[1], args.output, args.revision, args.run_id)

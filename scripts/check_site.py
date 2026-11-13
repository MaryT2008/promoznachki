#!/usr/bin/env python3
"""Offline checks for the public site, links and structured data."""
import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from site_rules import allowed_path, REQUIRED_FILES

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://promoznachki.ru/'


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h1 = 0
        self.title = 0
        self.canonicals = []
        self.links = []
        self.scripts = []
        self.script = None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        self.h1 += tag == 'h1'
        self.title += tag == 'title'
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonicals.append(attrs.get('href'))
        for key in ('src', 'href', 'poster'):
            if attrs.get(key):
                self.links.append(attrs[key])
        if tag == 'script' and not attrs.get('src'):
            self.script = [attrs.get('type', ''), '']

    def handle_data(self, data):
        if self.script is not None:
            self.script[1] += data

    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            self.scripts.append(self.script)
            self.script = None


def main():
    files = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and allowed_path(p.relative_to(ROOT).as_posix())}
    assert REQUIRED_FILES <= files, 'Required website files are missing'
    for name in sorted(files):
        assert not (ROOT / name).is_symlink(), 'Public symlinks are forbidden: ' + name
    errors = []
    pages = sorted(ROOT.glob('*.html'))
    with tempfile.TemporaryDirectory() as temporary:
        for path in pages:
            text = path.read_text(encoding='utf-8')
            page = Page()
            page.feed(text)
            if page.h1 != 1 or page.title != 1:
                errors.append(path.name + ': expected exactly one h1 and title')
            if path.name != '404.html':
                canonical = BASE + ('' if path.name == 'index.html' else path.name)
                if page.canonicals != [canonical]:
                    errors.append(path.name + ': incorrect canonical')
            for link in page.links:
                url = urlsplit(urljoin(BASE + path.name, link))
                if url.scheme not in ('http', 'https') or url.hostname != 'promoznachki.ru':
                    continue
                target = unquote(url.path).lstrip('/') or 'index.html'
                if target not in files:
                    errors.append(path.name + ': missing local target ' + target)
            for number, (kind, code) in enumerate(page.scripts):
                if kind == 'application/ld+json':
                    json.loads(code)
                elif kind in ('', 'text/javascript', 'application/javascript', 'module'):
                    script = Path(temporary) / '{}-{}.{}'.format(path.stem, number, 'mjs' if kind == 'module' else 'js')
                    script.write_text(code, encoding='utf-8')
                    subprocess.run(['node', '--check', str(script)], check=True, capture_output=True)
    for path in (ROOT / 'js').glob('*.js'):
        subprocess.run(['node', '--check', str(path)], check=True, capture_output=True)
    sitemap = ET.parse(str(ROOT / 'sitemap.xml'))
    locations = [element.text for element in sitemap.iter() if element.tag.endswith('}loc')]
    assert locations and len(locations) == len(set(locations)), 'Sitemap is empty or contains duplicate URLs'
    for location in locations:
        assert location.startswith(BASE), 'Unexpected sitemap origin'
        assert (urlsplit(location).path.lstrip('/') or 'index.html') in files, 'Missing sitemap page: ' + location
    index = (ROOT / 'index.html').read_text()
    assert 'action="/send-request.php"' in index, 'Production form must use the PHP handler'
    assert 'formsubmit.co' not in index, 'Obsolete external form handler'
    if errors:
        raise SystemExit('\n'.join(sorted(set(errors))))
    print('Validated {} HTML pages, {} sitemap URLs, local links, JSON-LD and JavaScript'.format(len(pages), len(locations)))


if __name__ == '__main__':
    main()

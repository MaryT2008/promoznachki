"""Only public website files belong in a release."""
import re
from pathlib import PurePosixPath

ROOT_FILES = {
    '.htaccess', '.user.ini', 'send-request.php', 'robots.txt', 'sitemap.xml',
    'favicon.ico', 'favicon-32.png', 'favicon-192.png', 'apple-touch-icon.png',
    'deploy-version.json',
}
REQUIRED_FILES = {
    'index.html', 'kontakty.html', '404.html', '.htaccess', '.user.ini',
    'send-request.php', 'robots.txt', 'sitemap.xml', 'css/style.css', 'js/basket.js',
}
DIRECTORY_SUFFIXES = {
    'assets': {'.png', '.jpg', '.jpeg', '.webp', '.avif', '.svg', '.gif', '.ico', '.woff', '.woff2', '.ttf'},
    'css': {'.css'}, 'js': {'.js'},
    'downloads': {'.pdf', '.cdr', '.ai', '.eps', '.zip'},
}


def allowed_path(name):
    path = PurePosixPath(name)
    if name != path.as_posix() or path.is_absolute() or '..' in path.parts or '\\' in name:
        return False
    if len(path.parts) == 1:
        return name in ROOT_FILES or re.fullmatch(r'[a-z0-9-]+\.html', name) is not None
    return (
        path.parts[0] in DIRECTORY_SUFFIXES
        and all(not part.startswith('.') for part in path.parts)
        and path.suffix.lower() in DIRECTORY_SUFFIXES[path.parts[0]]
        and re.fullmatch(r'[A-Za-z0-9_./-]+', name) is not None
    )

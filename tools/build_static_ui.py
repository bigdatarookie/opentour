#!/usr/bin/env python3
"""Export only public UI assets with a trusted, explicit API target; never deploys."""
import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.campaign_preview import FixtureCampaign
from backend.server import UI_FILES, STATIC
from backend.web_config import deployment_url, ui_policy


def build(output, api_base_url, base_path='/opentour'):
    api = deployment_url(api_base_url)
    base = base_path.rstrip('/')
    if base and not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)+', base):
        raise ValueError('invalid_static_base_path')
    # No overwrite/cleanup of an existing directory; no private source copied.
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for route, (filename, content_type) in UI_FILES.items():
        raw = (STATIC / filename).read_bytes()
        if filename == 'index.html':
            raw = raw.replace(b'name="opentour-base" content=""', ('name="opentour-base" content="'+base+'"').encode())
            raw = raw.replace(b'name="opentour-api-base" content=""', ('name="opentour-api-base" content="'+html.escape(api, quote=True)+'"').encode())
            policy = '<meta http-equiv="Content-Security-Policy" content="'+html.escape(ui_policy(api), quote=True)+'">'
            raw = raw.replace(b'<head>', ('<head>'+policy+'<meta name="referrer" content="no-referrer">').encode())
        if base and content_type.startswith(('text/html', 'text/css')):
            raw = raw.replace(b'"/ui/', ('"'+base+'/ui/').encode()).replace(b"'/ui/", ("'"+base+'/ui/').encode())
        relative = 'index.html' if route == '/' else route.lstrip('/')
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (output / 'ui' / 'campaign-email.css').write_bytes(FixtureCampaign().stylesheet())
    (output / '.nojekyll').touch()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory outside source; never overwrites')
    parser.add_argument('--api-base-url', required=True, help='Trusted protected HTTPS API base, optional prefix; no /api suffix, credentials, query or fragment. Literal loopback HTTP for synthetic validation only')
    parser.add_argument('--base-path', default='/opentour', help='Static project prefix; /opentour for agreed GitHub Pages route')
    args = parser.parse_args()
    build(args.output, args.api_base_url, args.base_path)
    print('Public static assets prepared; no deployment or access grant created.')


if __name__ == '__main__':
    main()

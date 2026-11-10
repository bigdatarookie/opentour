#!/usr/bin/env python3
"""Loopback Atlas preview with synthetic sources and a temporary application DB.

No CRM, native daemon, owner sources or external delivery is accessed. Access
keys are written only to a new private file. Ctrl-C cleans up the temporary DB.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from backend.board_store import BoardStore
from backend.core import Auth, Service
from backend.server import make_server
from test_board_conversations import ADMIN, USER
from ui_browser_probe import SyntheticCRM, synthetic_native


def prepare(directory):
    store = BoardStore(Path(directory) / 'database' / 'board.sqlite3')
    task = store.create(ADMIN, {'requestId': 'atlas-preview-0001', 'title': 'Synthetic draft review',
        'description': 'Preview context only. No real recipient or campaign.', 'section': 'clients',
        'clientRef': {'entity': 'Contact', 'externalId': 'p2'}, 'requestText': 'Please review the synthetic draft.'})
    keys = {role: secrets.token_urlsafe(32) for role in ('administrator', 'user')}
    grants = [{'subject': ADMIN.subject if role == 'administrator' else USER.subject, 'role': role,
        'projects': ['opentour'], 'tokenSha256': hashlib.sha256(token.encode()).hexdigest(),
        'board': {'read': True, 'respond': True, 'create': role == 'administrator', 'tasks': [task['id']]}}
        for role, token in keys.items()]
    crm, native = SyntheticCRM(), synthetic_native()
    return store, task, keys, grants, crm, native


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18085)
    parser.add_argument('--access-file', required=True, type=Path, help='New private key file outside the repository')
    args = parser.parse_args()
    access_path = args.access_file.expanduser().absolute()
    if access_path.is_relative_to(ROOT):
        parser.error('access-file must be outside the repository')
    with tempfile.TemporaryDirectory(prefix='opentour-atlas-preview-') as private:
        store, _, keys, grants, crm, native = prepare(private)
        server = make_server(Service(crm, native), Auth(grants=grants), args.port,
            data_mode='synthetic', board_store=store)
        created_access = False
        try:
            with os.fdopen(os.open(access_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
                created_access = True
                json.dump(keys, output)
            print(json.dumps({'mode': 'SYNTHETIC ONLY', 'url': 'http://127.0.0.1:' + str(server.server_port),
                'access_file': str(access_path), 'crm_access': False, 'native_delivery': False}), flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        finally:
            server.server_close()
            if created_access and access_path.exists():
                access_path.unlink()


if __name__ == '__main__':
    main()

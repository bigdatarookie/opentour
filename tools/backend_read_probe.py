#!/usr/bin/env python3
"""Exercise the real read backend over HTTP; print aggregates, never records or credentials.

This creates one ephemeral diagnostic read grant in memory, not a human account.
Use --crm-credential-file only with a scoped runtime reference authorized by its owner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.adapters import EspoCRM, NativeWork
from backend.core import Auth, MISSION, Service
from backend.server import make_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--crm-credential-file', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    token = secrets.token_urlsafe(32)
    auth = Auth(grants=[{'subject': 'local-diagnostic-process', 'role': 'user', 'projects': ['opentour'],
                        'tokenSha256': hashlib.sha256(token.encode()).hexdigest()}])
    service = Service(EspoCRM(credential_file=args.crm_credential_file), NativeWork(root / 'opentour-rig', MISSION))
    server = make_server(service, auth, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    results = {'probe': 'real_backend_http_reads', 'human_identity_proven': False,
               'contact_values_emitted': False, 'credentials_emitted': False, 'writes_exercised': False}

    def get(path, etag=None, authenticated=True):
        headers = {'Authorization': 'Bearer ' + token} if authenticated else {}
        if etag:
            headers['If-None-Match'] = etag
        req = urllib.request.Request(base + path, headers=headers)
        try:
            res = urllib.request.urlopen(req, timeout=90)
        except urllib.error.HTTPError as exc:
            res = exc
        with res:
            raw = res.read()
            return res.status, json.loads(raw) if raw else None, res.headers

    try:
        status, _, _ = get('/api/board', authenticated=False)
        results['unauthenticated_read_http'] = status
        assert status == 401
        status, board, headers = get('/api/board')
        results['board_http'] = status
        assert status == 200 and board['source'] == 'live_native_work'
        results['board_card_count'] = len(board['items'])
        results['board_queue_window_complete'] = board['queueWindowComplete']
        assert len(board['items']) == 5
        results['conditional_board_read_http'] = get('/api/board', headers.get('ETag'))[0]
        assert results['conditional_board_read_http'] == 304
        first = board['items'][0]
        status, detail, _ = get('/api/board/' + first['id'])
        results['board_detail_http'] = status
        assert status == 200 and detail['id'] == first['id']
        if args.crm_credential_file:
            status, people, _ = get('/api/clients?kind=person&limit=2')
            results['crm_people_http'] = status
            assert status == 200 and people['source'] == 'live_crm'
            results['crm_person_total'] = people['total']
            status, orgs, _ = get('/api/clients?kind=organization&limit=2')
            results['crm_organizations_http'] = status
            assert status == 200
            results['crm_organization_total'] = orgs['total']
            if people['items']:
                record = people['items'][0]
                status, card, _ = get('/api/clients/' + record['id'])
                results['crm_detail_http'] = status
                assert status == 200 and card['id'] == record['id'] and card['version'] == record['version']
                # Inspect only in-process, no values persisted or emitted. No import/retry occurs.
                results['crm_source_marker_present'] = 'import' in card['provenance']
                results['crm_placeholder_metadata_present'] = card['surname']['status'] == 'technical_placeholder_observed'
            else:
                results['crm_detail_http'] = 'NOT_RUN_no_person_records'
            status, page, _ = get('/api/clients?limit=1&offset=0')
            results['crm_combined_list_http'] = status
            assert status == 200 and page['total'] == people['total'] + orgs['total']
            results['crm_filter_http'] = get('/api/clients?kind=person&hasEmail=true&limit=2')[0]
            assert results['crm_filter_http'] == 200
            # Deliberately synthetic search criterion; no real name/channel enters a URL or output.
            results['crm_search_http'] = get('/api/clients?q=opentour-synthetic-unmatched-probe-4fba&limit=2')[0]
            assert results['crm_search_http'] == 200
        else:
            status, error, _ = get('/api/clients')
            assert status == 503 and error['error'] == 'crm_read_credential_not_configured'
            results['crm_integration'] = 'NOT_RUN_read_credential_not_configured'
            results['missing_crm_credential_http'] = status
        results['outcome'] = 'observed_reads_passed'
        print(json.dumps(results, sort_keys=True))
        return 0
    except Exception:
        results['outcome'] = 'failed_no_private_error_details_emitted'
        print(json.dumps(results, sort_keys=True))
        return 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == '__main__':
    sys.exit(main())

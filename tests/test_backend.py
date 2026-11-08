"""Synthetic, isolated checks. Never touch owner exports or the live CRM."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from backend.adapters import EspoCRM, Failure, JsonGET, NativeWork
from backend.core import Auth, MISSION, Service, board_card, client_card
from backend.server import make_server

TOKEN = 'synthetic-test-token-long-enough-123456'
GRANT = {'subject': 'synthetic-reader', 'role': 'user', 'projects': ['opentour'],
         'tokenSha256': hashlib.sha256(TOKEN.encode()).hexdigest()}
MARKER = 'opentour-source-v2:source-01:' + 'a' * 64 + ':2:mapping-v2'


class CRMFixture:
    base = 'http://127.0.0.1:18082'

    def __init__(self):
        self.calls = []
        self.records = {
            'Contact': [{'id': 'p1', 'name': 'None', 'lastName': 'None', 'description': MARKER,
                         'emailAddress': 'synthetic@example.invalid', 'modifiedAt': '2026-11-09 01:00:00'},
                        {'id': 'p2', 'name': 'Synthetic Person', 'lastName': 'Person', 'phoneNumber': '+10000000000'}],
            'Account': [{'id': 'o1', 'name': 'Synthetic School', 'type': 'School'}]}

    def list(self, entity, *, offset, limit, query, has_email, has_phone):
        self.calls.append((entity, offset, limit, query, has_email, has_phone))
        rows = self.records[entity]
        if query:
            rows = [r for r in rows if any(query.casefold() in str(r.get(f, '')).casefold() for f in ('name', 'emailAddress', 'phoneNumber'))]
        for flag, field in ((has_email, 'emailAddress'), (has_phone, 'phoneNumber')):
            if flag is not None:
                rows = [r for r in rows if bool(r.get(field)) == flag]
        return {'list': rows[offset:offset + limit], 'total': len(rows)}

    def detail(self, entity, key):
        for row in self.records[entity]:
            if row['id'] == key:
                return row
        raise Failure('source_object_not_found', 404)


def row(key='q1', state='in-progress', owner='platform-developer@opentour-rig', **extra):
    return {'qitemId': key, 'state': state, 'destinationSession': owner,
            'summary': 'Synthetic requested action', 'tsUpdated': '2026-11-09T00:00:00Z', **extra}


def slice_fixture(**extra):
    return {'name': '03-operator-board', 'sourceId': 'OT.0.1.0.3', 'title': 'Synthetic board work',
            'authoredStatus': 'planned', 'nativeStatus': 'active', 'readiness': 'unknown',
            'lastActivityAt': '2026-11-09T00:00:00Z', 'lastResult': 'Synthetic result',
            'currentContext': 'Synthetic next step', 'queue': [row()], **extra}


class NativeFixture:
    def __init__(self):
        self.items = [slice_fixture()]
        self.complete = True

    def snapshot(self):
        return copy.deepcopy(self.items), self.complete


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.crm, self.native = CRMFixture(), NativeFixture()
        self.service = Service(self.crm, self.native)

    def test_combined_pagination_crosses_entity_boundary_without_duplicates(self):
        first = self.service.clients({'limit': '2'})
        second = self.service.clients({'limit': '2', 'offset': str(first['nextOffset'])})
        self.assertEqual(first['total'], 3)
        self.assertEqual([x['id'] for x in first['items'] + second['items']], ['crm:Contact:p1', 'crm:Contact:p2', 'crm:Account:o1'])
        self.assertIsNone(second['nextOffset'])

    def test_search_type_and_contact_channel_filters(self):
        found = self.service.clients({'kind': 'person', 'hasPhone': 'true'})
        self.assertEqual([i['id'] for i in found['items']], ['crm:Contact:p2'])
        self.assertEqual(self.service.clients({'kind': 'organization', 'q': 'School'})['total'], 1)
        self.assertEqual(self.service.clients({'q': 'unmatched'})['items'], [])

    def test_none_is_technical_metadata_and_marker_provenance_survives(self):
        obj = self.service.client('crm:Contact:p1')
        self.assertIsNone(obj['displayName'])
        self.assertEqual(obj['surname']['technicalValue'], 'None')
        self.assertFalse(obj['surname']['deduplicationKey'])
        self.assertEqual(obj['provenance']['import']['sourceIdentity'], 'source-01')
        self.assertNotIn('description', obj)
        unmarked = client_card('Contact', {'id': 'x', 'name': 'None', 'lastName': 'None'}, self.crm.base)
        self.assertEqual(unmarked['displayName'], 'None')
        self.assertIsNone(unmarked['surname']['technicalValue'])

    def test_client_detail_and_list_share_identity_and_version(self):
        listed = self.service.clients({'kind': 'person'})['items'][0]
        self.assertEqual(self.service.client(listed['id']), listed)
        with self.assertRaises(Failure):
            self.service.client('crm:User:admin')

    def test_board_aggregates_many_qitems_and_never_treats_handoff_as_done(self):
        self.native.items[0]['queue'] = [row(str(i), 'done', closureReason='handed_off_to') for i in range(20)]
        board = self.service.board()
        self.assertEqual(len(board['items']), 1)
        self.assertNotEqual(board['items'][0]['column'], 'done')
        self.assertEqual(board['items'][0]['nativeFacts']['qitemCount'], 20)

    def test_human_review_and_blocker_states(self):
        s = slice_fixture(queue=[row(state='blocked', blockedOn='external:crm-read-access')])
        card = board_card(s, True)
        self.assertEqual(card['column'], 'in_progress')
        self.assertEqual(card['blockers'][0]['reason'], 'external:crm-read-access')
        s['queue'] = [row(owner='person@external', humanIntent='question')]
        self.assertEqual(board_card(s, True)['column'], 'needs_human')
        s['queue'] = [row(owner='platform-qa-code@opentour-rig')]
        self.assertEqual(board_card(s, True)['column'], 'review')

    def test_required_action_tracks_the_human_request_in_a_mixed_slice(self):
        s = slice_fixture(queue=[row('human', owner='person@external', summary='Synthetic human answer needed'),
                                 row('team', tsUpdated='2026-11-10T00:00:00Z', summary='Synthetic team activity')])
        card = board_card(s, True)
        self.assertEqual(card['column'], 'needs_human')
        self.assertEqual(card['requiredNextAction'], 'Synthetic human answer needed')

    def test_only_explicit_completed_and_ready_scope_can_be_done(self):
        s = slice_fixture(queue=[], authoredStatus='complete', nativeStatus='done', readiness='ready')
        self.assertEqual(board_card(s, True)['column'], 'done')
        self.assertEqual(board_card(s, False)['column'], 'unknown')
        s['readiness'] = 'unknown'
        self.assertNotEqual(board_card(s, True)['column'], 'done')

    def test_refresh_duplicate_and_changed_versions_with_restart_epoch(self):
        first, duplicate = self.service.board(), self.service.board()
        self.assertEqual(first['version'], duplicate['version'])
        self.assertEqual(first['cursor'], duplicate['cursor'])
        self.native.items[0]['queue'] = [row(state='blocked', blockedOn='external:next')]
        changed = self.service.board()
        self.assertEqual(first['items'][0]['id'], changed['items'][0]['id'])
        self.assertNotEqual(first['items'][0]['version'], changed['items'][0]['version'])
        self.assertGreater(changed['cursor']['sequence'], first['cursor']['sequence'])
        resumed = Service(self.crm, self.native).board()
        self.assertEqual(resumed['version'], changed['version'])
        self.assertNotEqual(resumed['cursor']['epoch'], changed['cursor']['epoch'])

    def test_sensitive_or_terminal_fields_are_not_forwarded(self):
        self.native.items[0].update(lastResult='password=synthetic-secret synthetic@example.invalid /Users/synthetic/private',
                                    story={'events': ['RAW TERMINAL']})
        self.native.items[0]['queue'][0]['body'] = 'RAW PRIVATE BODY'
        raw = json.dumps(self.service.board())
        for secret in ('synthetic-secret', 'synthetic@example.invalid', '/Users/synthetic/private', 'RAW TERMINAL', 'RAW PRIVATE BODY'):
            self.assertNotIn(secret, raw)


class PublicPathTests(unittest.TestCase):
    def setUp(self):
        self.service = Service(CRMFixture(), NativeFixture())
        self.auth = Auth(grants=[dict(GRANT), {**GRANT, 'role': 'administrator',
                     'tokenSha256': hashlib.sha256((TOKEN + '-admin').encode()).hexdigest()}])
        self.server = make_server(self.service, self.auth, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, method='GET', token=TOKEN, **headers):
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request(self.base + path, headers=headers, method=method)
        try:
            response = urllib.request.urlopen(req, timeout=3)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None, response.headers

    def test_public_client_list_filter_and_detail(self):
        status, body, _ = self.request('/api/clients?kind=person&hasEmail=true')
        self.assertEqual(status, 200)
        self.assertEqual(body['total'], 1)
        status, detail, _ = self.request('/api/clients/' + body['items'][0]['id'])
        self.assertEqual(status, 200)
        self.assertEqual(detail['provenance']['entity'], 'Contact')

    def test_public_board_detail_and_conditional_polling(self):
        status, body, headers = self.request('/api/board')
        self.assertEqual(status, 200)
        self.assertEqual(self.request('/api/board/' + body['items'][0]['id'])[1]['version'], body['items'][0]['version'])
        self.assertEqual(self.request('/api/board', **{'If-None-Match': headers['ETag']})[0], 304)
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_server_auth_scope_role_and_identity_spoofing(self):
        self.assertEqual(self.request('/api/board', token=None)[0], 401)
        self.assertEqual(self.request('/api/board?project=other')[0], 403)
        self.assertEqual(self.request('/api/board?role=administrator')[0], 400)
        self.auth.grants = [{**GRANT, 'projects': ['other']}]
        self.assertEqual(self.request('/api/board')[0], 403)

    def test_all_mutations_closed_for_both_roles(self):
        for token in (TOKEN, TOKEN + '-admin'):
            for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                self.assertEqual(self.request('/api/board/work:any/reply', method=method, token=token)[0], 403)

    def test_origin_host_bounds_and_no_arbitrary_proxy_or_shell(self):
        self.assertEqual(self.request('/api/clients', Origin='https://attacker.invalid')[0], 403)
        self.assertEqual(self.request('/api/clients', Host='attacker.invalid')[0], 403)
        self.assertEqual(self.request('/api/clients?limit=1000')[0], 400)
        self.assertEqual(self.request('/api/clients?kind=User')[0], 400)
        self.assertEqual(self.request('/api/clients?q=a&q=b')[0], 400)
        self.assertEqual(self.request('/api/clients?url=http://attacker.invalid')[0], 400)
        self.assertEqual(self.request('/api/board/work:other:secret')[0], 404)

    def test_upstream_failure_is_an_error_not_an_empty_list_or_leaked_exception(self):
        self.service.crm.list = lambda *a, **k: (_ for _ in ()).throw(Failure('source_unavailable', 503))
        status, body, _ = self.request('/api/clients')
        self.assertEqual(status, 503)
        self.assertEqual(body, {'error': 'source_unavailable'})


class AdapterTests(unittest.TestCase):
    def test_espo_search_wire_contract_does_not_silently_drop_filters(self):
        # Mirrors the installed SearchParamsFetcher boundary: a plain string
        # `where` query is ignored; searchParams JSON keeps typed arrays/ints.
        class EspoBoundary(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                search = json.loads(query['searchParams'][0]) if 'searchParams' in query else {}
                where = search.get('where') if isinstance(search.get('where'), list) else []
                matched = not where
                data = {'list': [{'id': 'synthetic1', 'name': 'Synthetic'}] if matched else [],
                        'total': int(matched)}
                raw = json.dumps(data).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        server = ThreadingHTTPServer(('127.0.0.1', 0), EspoBoundary)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            crm = EspoCRM()
            crm._client = lambda: JsonGET('http://127.0.0.1:' + str(server.server_port))
            result = crm.list('Contact', offset=0, limit=2, query='unmatched-synthetic-term', has_email=None, has_phone=None)
            self.assertEqual(result, {'list': [], 'total': 0})
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_http_adapter_rejects_remote_urls_and_redirects(self):
        for url in ('https://example.invalid', 'http://localhost:7433', 'http://127.0.0.1:7433?token=secret'):
            with self.assertRaises(Failure):
                JsonGET(url)

    def test_espo_query_is_bounded_and_only_gets_allowlisted_fields(self):
        seen = []
        class Client:
            def get(self, path, params):
                seen.append((path, params))
                return {'list': [], 'total': 0}
        crm = EspoCRM()
        crm._client = lambda: Client()
        crm.list('Contact', offset=2, limit=7, query='Synthetic', has_email=True, has_phone=None)
        path, params = seen[0]
        self.assertEqual(path, '/Contact')
        search = json.loads(params['searchParams'])
        self.assertEqual(search['offset'], 2)
        self.assertEqual(search['maxSize'], 7)
        self.assertNotIn('password', search['select'])
        self.assertIsInstance(search['select'], list)
        self.assertEqual(search['order'], 'ASC')
        self.assertIn({'type': 'isNotNull', 'attribute': 'emailAddress'}, search['where'])

    def test_native_adapter_explicit_scope_and_cross_project_detail_refusal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'missions' / MISSION / 'slices' / '03-operator-board'
            path.mkdir(parents=True)
            (path / 'PROGRESS.md').write_text('## Current state\nSynthetic\n## Outcomes\n- Result\n')
            adapter = NativeWork(root, MISSION)
            catalog = {'ok': True, 'slices': [{'mission': MISSION, 'name': '03-operator-board', 'path': str(path), 'id': 'OT.0.1.0.3', 'status': 'planned'}]}
            detail = {'name': '03-operator-board', 'missionId': MISSION, 'slicePath': str(path), 'status': 'active'}
            good = row(tags=['project:opentour', 'mission:' + MISSION, 'slice:03-operator-board'])
            other = row('secret', tags=['project:other', 'mission:' + MISSION, 'slice:03-operator-board'])
            calls = []
            def get(route, params):
                calls.append((route, params))
                return [good, other] if route == '/api/queue/list' else detail
            adapter.client.get = get
            completed = type('Done', (), {'stdout': json.dumps(catalog).encode()})()
            with patch('backend.adapters.subprocess.run', return_value=completed) as run:
                slices, complete = adapter.snapshot()
                self.assertTrue(complete)
                self.assertEqual([q['qitemId'] for q in slices[0]['queue']], ['q1'])
                self.assertIn('--workspace', run.call_args[0][0])
                self.assertEqual(calls[1][1]['project'], 'opentour')
                detail['slicePath'] = str(root / 'other')
                with self.assertRaises(Failure):
                    adapter.snapshot()


if __name__ == '__main__':
    unittest.main()

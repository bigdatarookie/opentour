"""Focused synthetic relation, migration and HTTP scope tests; no providers/native sends."""
import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from backend.adapters import Failure
from backend.board_store import BoardStore
from backend.core import Auth, Principal, Service
from backend.server import make_server
from test_backend import CRMFixture, NativeFixture
from test_board_conversations import ADMIN, USER

CONTACT = {'entity': 'Contact', 'externalId': 'p2'}
ACCOUNT = {'entity': 'Account', 'externalId': 'o1'}


class RelationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='opentour-client-links-')
        self.path = Path(self.tmp.name) / 'private' / 'board.sqlite3'
        self.store = BoardStore(self.path)

    def tearDown(self): self.tmp.cleanup()

    def create(self, request_id='client-create-0001', ref=CONTACT):
        body = {'requestId': request_id, 'title': 'Synthetic related work', 'description': 'Synthetic work only',
                'section': 'clients', 'requestText': 'Synthetic client question'}
        if ref is not None: body['clientRef'] = ref
        return self.store.create(ADMIN, body)

    def test_contact_account_reference_persists_without_copied_crm_fields(self):
        contact = self.create(); account = self.create('client-create-0002', ACCOUNT)
        store = BoardStore(self.path)
        self.assertEqual(store.detail(USER, contact['id'])['clientRef'], CONTACT)
        self.assertEqual(store.detail(USER, account['id'])['clientRef'], ACCOUNT)
        self.assertEqual(store.related(USER, CONTACT)['items'][0]['id'], contact['id'])
        self.assertEqual(store.related(USER, ACCOUNT)['items'][0]['id'], account['id'])
        with store.db() as db:
            payload = json.loads(db.execute('SELECT payload FROM outbox WHERE message_id=?', (contact['messages'][0]['id'],)).fetchone()[0])
            self.assertEqual(payload['clientRef'], CONTACT)
            self.assertEqual([r['name'] for r in db.execute('PRAGMA table_info(task_clients)')], ['task_id', 'entity', 'external_id'])
        self.assertEqual(self.create()['id'], contact['id'])
        with self.assertRaises(Failure) as exc: self.create(ref=ACCOUNT)
        self.assertEqual(exc.exception.code, 'request_content_conflict')

    def test_v1_migration_preserves_tasks_messages_outbox_and_old_replay(self):
        task = self.create(ref=None)
        with self.store.db() as db:
            db.execute('DROP TABLE task_clients')
            for table in ('processing_events','delivery_worker','task_execution'):
                db.execute('DROP TABLE '+table)
            for column in ('sender','native_body','delivered_at','received_at','accepted_at','continued_at','processing_reason','result_text','evidence_ref'):
                db.execute('ALTER TABLE outbox DROP COLUMN '+column)
            db.execute('PRAGMA user_version=1')
            columns={name:[r['name'] for r in db.execute('PRAGMA table_info('+name+')')] for name in ('tasks','messages','outbox','requests')}
            before={name:[tuple(r) for r in db.execute('SELECT '+','.join(cols)+' FROM '+name)] for name,cols in columns.items()}
        store = BoardStore(self.path)
        with store.db() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 3)
            after={name:[tuple(r) for r in db.execute('SELECT '+','.join(cols)+' FROM '+name)] for name,cols in columns.items()}
        self.assertEqual(before, after)
        self.assertIsNone(store.detail(USER, task['id'])['clientRef'])
        self.assertEqual(store.related(USER, CONTACT)['items'], [])
        self.assertEqual(self.create(ref=None)['id'], task['id'])
        self.assertIsNone(BoardStore(self.path).detail(USER, task['id'])['clientRef'])

    def test_relation_projection_filters_before_limit_and_navigation_denies_scope(self):
        allowed = self.create(); hidden = self.create('client-create-0002')
        user = Principal('synthetic-scoped', 'user', ('opentour',), True, True, False, (allowed['id'],))
        for i in range(101): self.create('bounded-create-' + str(i))
        result = self.store.related(user, CONTACT)
        self.assertEqual([r['id'] for r in result['items']], [allowed['id']])
        self.assertTrue(result['complete'])
        self.assertFalse(self.store.related(USER, CONTACT)['complete'])
        with self.assertRaises(Failure): self.store.detail(user, hidden['id'])
        with self.assertRaises(Failure): self.store.related(Principal('no-board', 'user', ('opentour',)), CONTACT)
        with self.assertRaises(Failure): self.store.related(Principal('other', 'user', ('other',), True, True, False, ('*',)), CONTACT)
        with self.store.db() as db: db.execute("UPDATE tasks SET project='other' WHERE id=?", (hidden['id'],))
        self.assertNotIn(hidden['id'], [r['id'] for r in self.store.related(USER, CONTACT)['items']])

    def test_link_task_and_outbox_roll_back_together(self):
        with self.store.db() as db:
            db.execute("CREATE TRIGGER synthetic_abort BEFORE INSERT ON outbox BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.create()
        with self.store.db() as db:
            for table in ('task_clients','tasks','messages','outbox','requests'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_bad_reference_and_user_creation_cannot_write_relation(self):
        for ref in ({'entity':'Lead','externalId':'p2'}, {'entity':'Contact','externalId':'../p2'},
                    {'entity':'Contact','externalId':'p2','name':'do not copy'}, {'entity':'Contact','externalId':12}):
            with self.assertRaises(Failure): self.create(ref=ref)
        with self.assertRaises(Failure):
            self.store.create(USER, {'clientRef': CONTACT})
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM tasks').fetchone()[0], 0)


class RelationHTTPTests(unittest.TestCase):
    def setUp(self):
        RelationTests.setUp(self)
        self.token = 'synthetic-client-link-token-' + 'x'*30
        self.grant = {'subject': ADMIN.subject, 'role': 'administrator', 'projects': ['opentour'],
            'tokenSha256': hashlib.sha256(self.token.encode()).hexdigest(),
            'board': {'read': True,'respond': True,'create': True,'tasks':['*']}}
        self.crm = CRMFixture()
        self.server = make_server(Service(self.crm, NativeFixture()), Auth(grants=[self.grant]), 0, data_mode='synthetic', board_store=self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True);self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();RelationTests.tearDown(self)

    def request(self, route, body=None, etag=None):
        request = urllib.request.Request(self.base+route, headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'},
                                        data=json.dumps(body).encode() if body is not None else None)
        if etag: request.add_header('If-None-Match', etag)
        try:
            with urllib.request.urlopen(request) as response:
                self.etag = response.headers.get('ETag')
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc: return exc.code,json.load(exc)

    def test_scoped_http_projection_existing_client_validation_and_navigation(self):
        body = {'requestId':'http-client-create-1','title':'Synthetic linked task','description':'Synthetic only','section':'clients','clientRef':CONTACT}
        status, task = self.request('/api/board-tasks', body)
        self.assertEqual(status,200)
        route = '/api/clients/crm:Contact:p2'
        status, client = self.request(route)
        self.assertEqual(status,200)
        self.assertEqual(client['relatedWork']['items'], [{'id':task['id'],'title':task['title']}])
        self.assertEqual(client['relatedWork']['status'],'available')
        client_etag = self.etag
        self.assertEqual(self.request('/api/board-tasks/'+task['id'])[1]['clientRef'],CONTACT)
        self.grant['board']['tasks'] = []
        self.assertEqual(self.request(route, etag=client_etag)[1]['relatedWork']['items'],[])
        self.assertNotEqual(self.etag, client_etag)
        self.assertEqual(self.request('/api/board-tasks/'+task['id'])[0],404)
        self.grant.pop('board')
        self.assertEqual(self.request(route)[1]['relatedWork']['status'],'board_access_not_granted')
        self.assertEqual(self.request(route)[1]['relatedWork']['items'],[])
        self.grant['board']={'read':True,'respond':True,'create':True,'tasks':['*']}
        status,_ = self.request('/api/board-tasks',{**body,'requestId':'http-client-create-2','clientRef':{'entity':'Contact','externalId':'missing'}})
        self.assertEqual(status,404)
        with self.store.db() as db: self.assertEqual(db.execute('SELECT count(*) FROM tasks').fetchone()[0],1)
        status, account = self.request('/api/board-tasks', {**body,'requestId':'http-account-create-1','clientRef':ACCOUNT})
        self.assertEqual(status,200)
        self.assertEqual(self.request('/api/clients/crm:Account:o1')[1]['relatedWork']['items'],
                         [{'id':account['id'],'title':account['title']}])


if __name__ == '__main__': unittest.main()

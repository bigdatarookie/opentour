import concurrent.futures
import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from backend.adapters import Failure
from backend.board_store import BoardStore, DESTINATIONS
from backend.context_delivery import PREFIX, SOURCE, Rejected, deliver_one, receive_context, run_batch
from backend.core import Auth, Principal, Service
from backend.server import make_server
from test_backend import CRMFixture, NativeFixture

ADMIN = Principal('synthetic-admin', 'administrator', ('opentour',), True, True, True, ('*',))
USER = Principal('synthetic-user', 'user', ('opentour',), True, True, False, ('*',))


class SyntheticTransport:
    def __init__(self, mode='ok'):
        self.rows = {}; self.sends = 0; self.mode = mode

    def lookup(self, native_id):
        return self.rows.get(native_id)

    def send(self, row):
        self.sends += 1
        if self.mode == 'reject':
            raise Rejected('synthetic before-send refusal')
        if self.mode == 'before':
            raise TimeoutError('synthetic unknown before commit')
        item = {'qitemId': row['native_id'], 'sourceSession': SOURCE, 'destinationSession': row['destination'],
                'body': PREFIX + row['payload'], 'tags': ['project:opentour', 'type:opentour-task-context', 'delivery:' + row['id']]}
        self.rows[row['native_id']] = item
        if self.mode == 'after':
            raise TimeoutError('synthetic committed response loss')
        return item


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='opentour-synthetic-board-')
        self.path = Path(self.tmp.name) / 'private' / 'board.sqlite3'
        self.store = BoardStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, request_id='create-0001', **extra):
        return self.store.create(ADMIN, {'requestId': request_id, 'title': 'Synthetic campaign review',
            'description': 'Synthetic task context only', 'section': 'tasks', 'requestText': 'Check synthetic draft?', **extra})

    def answer(self, task, request_id='answer-0001', **extra):
        return self.store.append(USER, task['id'], {'requestId': request_id, 'kind': 'answer',
            'replyTo': task['messages'][0]['id'], 'text': 'Synthetic review response', **extra})

    def code(self, code, fn):
        with self.assertRaises(Failure) as exc:
            fn()
        self.assertEqual(exc.exception.code, code)

    def test_restart_exact_idempotency_and_linkage(self):
        task = self.create(); result = self.answer(task)
        self.store = BoardStore(self.path)
        self.assertEqual(self.create()['id'], task['id'])
        self.assertEqual(self.answer(task)['messageId'], result['messageId'])
        detail = self.store.detail(USER, task['id'])
        self.assertEqual(len(detail['messages']), 2)
        self.assertEqual(detail['messages'][1]['reply_to'], detail['messages'][0]['id'])
        self.assertEqual(detail['messages'][1]['author'], USER.subject)
        self.assertEqual(detail['messages'][1]['delivery']['state'], 'pending')
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0], 2)
        self.code('request_content_conflict', lambda: self.answer(task, text='Changed content'))
        self.code('request_content_conflict', lambda: self.create(title='Changed title'))

    def test_atomic_task_message_and_outbox_rollback(self):
        with self.store.db() as db:
            db.execute("CREATE TRIGGER synthetic_abort BEFORE INSERT ON outbox BEGIN SELECT RAISE(ABORT,'synthetic abort'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.create()
        with self.store.db() as db:
            for table in ('tasks', 'messages', 'requests', 'outbox'):
                self.assertEqual(db.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)

    def test_scopes_roles_and_foreign_link(self):
        task = self.create(); other = self.create('create-0002')
        scoped = Principal('scoped', 'user', ('opentour',), True, True, False, (task['id'],))
        self.assertEqual([r['id'] for r in self.store.list(scoped)['items']], [task['id']])
        self.code('board_task_not_found', lambda: self.store.detail(scoped, other['id']))
        self.code('board_access_forbidden', lambda: self.store.list(Principal('read-only', 'user', ('opentour',))))
        self.code('board_access_forbidden', lambda: self.store.detail(Principal('foreign', 'user', ('other',), True, True, False, ('*',)), task['id']))
        self.code('board_create_forbidden', lambda: self.store.create(USER, {}))
        self.code('board_message_kind_forbidden', lambda: self.store.append(USER, task['id'], {'kind': 'request'}))
        self.code('answer_request_not_found', lambda: self.answer(task, replyTo=other['messages'][0]['id']))
        self.code('invalid_board_fields', lambda: self.answer(task, destinationSession='arbitrary@kernel'))
        self.code('invalid_board_fields', lambda: self.create(section='tasks', command='arbitrary'))
        self.code('board_section_forbidden', lambda: self.create(section=[]))

    def test_private_storage_and_schema_version(self):
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
        with self.store.db() as db:
            self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            self.assertEqual(db.execute('PRAGMA busy_timeout').fetchone()[0], 5000)
            db.execute('PRAGMA user_version=2')
        self.code('board_schema_unsupported', lambda: BoardStore(self.path))
        os.chmod(self.path, 0o644)
        self.code('board_database_not_private', lambda: BoardStore(self.path))
        self.code('board_database_must_be_private_app_data', lambda: BoardStore(Path(__file__).resolve().parents[1] / 'synthetic.sqlite3'))

    def test_symlinked_artifacts_parent_is_refused_without_creating_target_data(self):
        # Entirely synthetic: never references the owner's artifacts directory.
        root = Path(self.tmp.name)
        protected = root / 'synthetic-source' / '.artifacts'
        protected.mkdir(parents=True, mode=0o700)
        alias = root / 'aliased-app-data'
        alias.symlink_to(protected, target_is_directory=True)
        self.code('board_database_must_be_private_app_data',
                  lambda: BoardStore(alias / 'new-private-directory' / 'board.sqlite3'))
        self.assertEqual(list(protected.iterdir()), [])

    def test_validated_canonical_parent_is_used_after_alias_changes(self):
        root = Path(self.tmp.name)
        safe = root / 'canonical-private'
        safe.mkdir(mode=0o700)
        protected = root / 'synthetic-source' / '.artifacts'
        protected.mkdir(parents=True, mode=0o700)
        alias = root / 'aliased-app-data'
        alias.symlink_to(safe, target_is_directory=True)
        store = BoardStore(alias / 'board.sqlite3')
        self.assertEqual(store.path, safe.resolve() / 'board.sqlite3')
        alias.unlink()
        alias.symlink_to(protected, target_is_directory=True)
        task = store.create(ADMIN, {'requestId': 'canonical-create-0001', 'title': 'Synthetic task',
                   'description': 'Synthetic only', 'section': 'tasks'})
        self.assertEqual(store.detail(USER, task['id'])['title'], 'Synthetic task')
        self.assertEqual(list(protected.iterdir()), [])
        # Canonicalizing the parent must not remove the final-component no-follow protection.
        final_alias = safe / 'alias.sqlite3'
        final_alias.symlink_to(store.path)
        before = store.path.read_bytes()
        with self.assertRaises(OSError):
            BoardStore(final_alias)
        self.assertEqual(store.path.read_bytes(), before)

    def test_concurrent_duplicate_submission(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(lambda _: self.create()['id'], range(8)))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(len(self.store.detail(USER, ids[0])['messages']), 1)

    def test_delivery_after_commit_loss_reconciles_exact_key(self):
        task = self.create(); transport = SyntheticTransport('after')
        delivery_id = task['messages'][0]['delivery']['id']
        self.assertEqual(deliver_one(self.store, transport, delivery_id), 'unknown')
        self.store = BoardStore(self.path)
        self.assertEqual(deliver_one(self.store, transport, delivery_id), 'delivered')
        self.assertEqual(deliver_one(self.store, transport, delivery_id), 'delivered')
        self.assertEqual(transport.sends, 1)
        self.code('agent_context_forbidden', lambda: receive_context(self.store, delivery_id, 'arbitrary@kernel'))
        context = receive_context(self.store, delivery_id, DESTINATIONS['tasks'])
        self.assertEqual(context['taskId'], task['id'])
        self.assertEqual(context['messageId'], task['messages'][0]['id'])
        self.assertEqual(self.store.detail(USER, task['id'])['messages'][0]['delivery']['processing'], 'received')

    def test_unknown_absence_never_replays_and_refusal_is_failed(self):
        task = self.create(); transport = SyntheticTransport('before')
        delivery_id = task['messages'][0]['delivery']['id']
        self.assertEqual(deliver_one(self.store, transport, delivery_id), 'unknown')
        self.assertEqual(deliver_one(self.store, transport, delivery_id), 'unknown')
        self.assertEqual(transport.sends, 1)
        second = self.create('create-0002'); rejected = SyntheticTransport('reject')
        self.assertEqual(deliver_one(self.store, rejected, second['messages'][0]['delivery']['id']), 'failed')
        self.assertNotIn('synthetic', self.store.detail(USER, second['id'])['messages'][0]['delivery']['error'])

    def test_reference_conflict_never_sends(self):
        task = self.create(); transport = SyntheticTransport()
        delivery_id = task['messages'][0]['delivery']['id']
        with self.store.db() as db:
            native_id = db.execute('SELECT native_id FROM outbox WHERE id=?', (delivery_id,)).fetchone()[0]
        transport.rows[native_id] = {'qitemId': native_id, 'body': 'unrelated'}
        self.assertEqual(deliver_one(self.store, transport, delivery_id), 'unknown')
        self.assertEqual(transport.sends, 0)

    def test_concurrent_workers_send_once(self):
        task = self.create(); transport = SyntheticTransport(); started = threading.Event(); finish = threading.Event()
        original_send = transport.send
        def send(row):
            started.set(); finish.wait(5); return original_send(row)
        transport.send = send
        delivery_id = task['messages'][0]['delivery']['id']
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(deliver_one, self.store, transport, delivery_id)
            self.assertTrue(started.wait(5))
            second = pool.submit(deliver_one, self.store, transport, delivery_id)
            self.assertEqual(second.result(5), 'unknown')
            finish.set(); self.assertEqual(first.result(5), 'delivered')
        self.assertEqual(transport.sends, 1)


class HTTPTests(unittest.TestCase):
    # Separate HTTP tests reuse setup, not the StoreTests methods.
    def setUp(self):
        StoreTests.setUp(self)
        self.token = 'synthetic-board-token-' + 'x' * 32
        grant = {'subject': 'synthetic-admin', 'role': 'administrator', 'projects': ['opentour'],
                 'tokenSha256': hashlib.sha256(self.token.encode()).hexdigest(),
                 'board': {'read': True, 'respond': True, 'create': True, 'tasks': ['*']}}
        self.auth = Auth(grants=[grant])
        self.server = make_server(Service(CRMFixture(), NativeFixture()), self.auth, 0, data_mode='synthetic', board_store=self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        StoreTests.tearDown(self)

    def request(self, path, body=None, token=True):
        headers = {'Authorization': 'Bearer ' + self.token} if token else {}
        if body is not None: headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(self.base + path, headers=headers, data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req) as response: return response.status, json.load(response)
        except urllib.error.HTTPError as exc: return exc.code, json.load(exc)

    def test_http_save_replay_scope_and_native_write_boundary(self):
        self.assertTrue(self.request('/api/capabilities')[1]['boardConversations']['create'])
        self.assertEqual(self.request('/api/capabilities')[1]['writes']['scope'], 'native_actions')
        body = {'requestId': 'http-create-1', 'title': 'Synthetic HTTP task', 'description': 'No private data', 'section': 'clients', 'requestText': 'Synthetic request'}
        status, task = self.request('/api/board-tasks', body)
        self.assertEqual(status, 200)
        status, same = self.request('/api/board-tasks', body)
        self.assertEqual(same['id'], task['id'])
        answer = {'requestId': 'http-answer-1', 'kind': 'answer', 'text': 'Synthetic HTTP answer', 'replyTo': task['messages'][0]['id']}
        status, saved = self.request('/api/board-tasks/' + task['id'] + '/messages', answer)
        self.assertEqual(status, 200); self.assertEqual(saved['persistence'], 'saved')
        self.assertEqual(self.request('/api/board-tasks/' + task['id'])[1]['messages'][-1]['body'], answer['text'])
        self.assertEqual(self.request('/api/board-tasks?project=other')[0], 403)
        self.assertEqual(self.request('/api/board-tasks', token=False)[0], 401)
        self.assertEqual(self.request('/api/board/reply', {'decision': 'not allowed'})[0], 403)
        self.assertEqual(self.request('/api/board-tasks', {**body, 'destinationSession': 'arbitrary'})[0], 400)
        self.auth.grants[0]['board']['tasks'] = []
        self.assertFalse(self.request('/api/capabilities')[1]['boardConversations']['create'])
        self.assertEqual(self.request('/api/board-tasks/' + task['id'])[0], 404)
        self.auth.grants[0].pop('board')
        self.assertEqual(self.request('/api/board-tasks')[0], 403)


class TransportWireTests(unittest.TestCase):
    def test_native_http_committed_response_loss_reconciles_by_exact_id(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from backend.context_delivery import NativeContext
        from backend.adapters import JsonGET
        rows = {}; posts = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                item = rows.get(self.path.rsplit('/', 1)[-1])
                self.send_response(200 if item else 404);self.end_headers()
                self.wfile.write(json.dumps(item or {'error': 'qitem_not_found'}).encode())
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                posts.append((self.path, self.headers.get('X-OpenRig-Session'), body))
                rows[body['qitemId']] = {**body, 'sourceSession': self.headers['X-OpenRig-Session']}
                self.send_response(200);self.end_headers();self.wfile.write(b'incomplete-json')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix='opentour-wire-synthetic-') as tmp:
                store = BoardStore(Path(tmp) / 'data' / 'board.sqlite3')
                task = store.create(ADMIN, {'requestId': 'wire-create-0001', 'title': 'Synthetic context', 'description': 'Synthetic only', 'section': 'tasks'})
                transport = object.__new__(NativeContext)
                transport.client = JsonGET('http://127.0.0.1:' + str(server.server_port), {'X-OpenRig-Session': SOURCE})
                delivery_id = task['messages'][0]['delivery']['id']
                self.assertEqual(deliver_one(store, transport, delivery_id), 'unknown')
                self.assertEqual(deliver_one(BoardStore(store.path), transport, delivery_id), 'delivered')
                self.assertEqual(len(posts), 1)
                route, sender, sent = posts[0]
                self.assertEqual(route, '/api/queue/create');self.assertEqual(sender, SOURCE)
                self.assertEqual(sent['destinationSession'], DESTINATIONS['tasks'])
                self.assertEqual(set(sent), {'qitemId', 'destinationSession', 'body', 'summary', 'tags', 'targetRepo'})
                self.assertIn(task['id'], sent['body']);self.assertIn(task['messages'][0]['id'], sent['body'])
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__ == '__main__':
    unittest.main()

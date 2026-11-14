"""Private application conversations and transactional context outbox (no business actions)."""
from __future__ import annotations
import hashlib
import json
import os
import re
import sqlite3
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path
from .adapters import Failure
from .core import ID, PROJECT, now, version
from .client_conversations import ClientConversations, CONVERSATION_SCHEMA

DESTINATIONS = {'tasks': 'operator-agent@kernel', 'clients': 'campaign-creative@opentour-rig',
                'campaigns': 'campaign-operator@opentour-rig'}
KEY = re.compile(r'[A-Za-z0-9_-]{8,128}')


def text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise Failure('invalid_board_text', 400)
    return value.strip()


def key(value):
    if not isinstance(value, str) or not KEY.fullmatch(value):
        raise Failure('invalid_request_id', 400)
    return value


def fields(body, allowed):
    if not isinstance(body, dict) or set(body) - set(allowed):
        raise Failure('invalid_board_fields', 400)


def client_reference(value):
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != {'entity', 'externalId'}
            or value.get('entity') not in ('Contact', 'Account')
            or not isinstance(value.get('externalId'), str) or not ID.fullmatch(value['externalId'])):
        raise Failure('invalid_client_reference', 400)
    return {'entity': value['entity'], 'externalId': value['externalId']}


class BoardStore(ClientConversations):
    def __init__(self, path):
        requested = Path(path).expanduser().absolute()
        # Pin the resolved parent for validation, creation and every later connection.
        # Leave the final component unresolved so O_NOFOLLOW still refuses a file symlink.
        path = requested.parent.resolve() / requested.name
        destination = path.resolve()
        repo = Path(__file__).resolve().parents[1]
        # Also reject the common checkout when this module runs from a worktree.
        roots = [repo.resolve()]
        git_file = repo / '.git'
        if git_file.is_file():
            pointer = git_file.read_text().strip()
            if pointer.startswith('gitdir: '):
                git_dir = Path(pointer[8:])
                if not git_dir.is_absolute():
                    git_dir = repo / git_dir
                common_file = git_dir / 'commondir'
                if common_file.is_file():
                    roots.append((git_dir / common_file.read_text().strip()).resolve().parent)
        if (any(destination.is_relative_to(root) for root in roots)
                or '.artifacts' in requested.parts or '.artifacts' in destination.parts):
            raise Failure('board_database_must_be_private_app_data', 503)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent = path.parent.stat()
        if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) & 0o077:
            raise Failure('board_directory_not_private', 503)
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise Failure('board_database_not_private', 503)
        finally:
            os.close(fd)
        self.path = path
        with self.db() as db:
            schema = db.execute('PRAGMA user_version').fetchone()[0]
            if schema not in (0, 1, 2, 3, 4, 5):
                raise Failure('board_schema_unsupported', 503)
            if schema == 0:
                for sql in SCHEMA:
                    db.execute(sql)
            if schema < 2:
                for sql in CLIENT_SCHEMA:
                    db.execute(sql)
                db.execute('PRAGMA user_version=2')
            if schema < 3:
                for sql in DELIVERY_SCHEMA:
                    db.execute(sql)
                db.execute('PRAGMA user_version=3')
            if schema < 4:
                db.execute('ALTER TABLE task_execution ADD COLUMN destination TEXT')
                db.execute('ALTER TABLE outbox ADD COLUMN routing_ref TEXT')
                db.execute('PRAGMA user_version=4')
            if schema < 5:
                for sql in CONVERSATION_SCHEMA:db.execute(sql)
                db.execute('PRAGMA user_version=5')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA busy_timeout=5000')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def permit(self, principal, task_id=None, write=False, create=False, _db=None):
        if PROJECT not in principal.projects or not principal.board_read:
            raise Failure('board_access_forbidden', 403)
        if write and not principal.board_respond:
            raise Failure('board_response_forbidden', 403)
        if create and (principal.role != 'administrator' or not principal.board_create or '*' not in principal.board_tasks):
            raise Failure('board_create_forbidden', 403)
        if task_id is not None and '*' not in principal.board_tasks and task_id not in principal.board_tasks and not self.context_allowed(principal,task_id,_db):
            raise Failure('board_task_not_found', 404)

    def task(self, db, principal, task_id, **permissions):
        self.permit(principal, task_id, _db=db, **permissions)
        row = db.execute('SELECT * FROM tasks WHERE id=? AND project=?', (task_id, PROJECT)).fetchone()
        if row is None:
            raise Failure('board_task_not_found', 404)
        return row

    def replay(self, db, principal, operation, request_id, payload):
        digest = version(payload)
        row = db.execute('SELECT digest,result_id FROM requests WHERE subject=? AND operation=? AND request_key=?',
                         (principal.subject, operation, key(request_id))).fetchone()
        if row and row['digest'] != digest:
            raise Failure('request_content_conflict', 409)
        return row['result_id'] if row else None

    def remember(self, db, principal, operation, request_id, payload, result_id):
        db.execute('INSERT INTO requests VALUES(?,?,?,?,?)',
                   (principal.subject, operation, request_id, version(payload), result_id))

    def create(self, principal, body, validate_client=None, resolve_obligation=None):
        self.permit(principal, create=True)
        fields(body, ('requestId', 'title', 'description', 'section', 'requestText', 'clientRef', 'continuationRef'))
        payload = {'title': text(body.get('title'), 240), 'description': text(body.get('description'), 4000),
                   'section': body.get('section')}
        if not isinstance(payload['section'], str) or payload['section'] not in DESTINATIONS:
            raise Failure('board_section_forbidden', 400)
        question = text(body['requestText'], 4000) if 'requestText' in body else None
        payload['requestText'] = question
        continuation = body.get('continuationRef')
        if continuation is not None:
            if not isinstance(continuation, str) or not re.fullmatch(r'qitem-[A-Za-z0-9_-]{1,160}', continuation):
                raise Failure('invalid_continuation_reference', 400)
            payload['continuationRef'] = continuation
        reference = client_reference(body.get('clientRef'))
        if reference is not None:
            payload['clientRef'] = reference
        with self.db() as db:
            existing = self.replay(db, principal, 'create', body.get('requestId'), payload)
        if existing:
            return self.detail(principal, existing)
        if reference is not None and validate_client:
            validate_client(reference)
        destination = None
        if continuation is not None:
            if resolve_obligation is None:
                raise Failure('native_obligation_lookup_required', 503)
            destination = resolve_obligation(continuation)
            if not isinstance(destination,str) or not destination:
                raise Failure('native_obligation_destination_invalid',409)
        with self.db() as db:
            task_id = self.replay(db, principal, 'create', body.get('requestId'), payload)
            if not task_id:
                task_id = 'task_' + uuid.uuid4().hex
                db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?)',
                           (task_id, PROJECT, payload['title'], payload['description'], payload['section'], principal.subject, now()))
                if continuation is not None:
                    db.execute('INSERT INTO task_execution(task_id,native_ref,destination) VALUES(?,?,?)', (task_id, continuation, destination))
                if reference is not None:
                    db.execute('INSERT INTO task_clients VALUES(?,?,?)', (task_id, reference['entity'], reference['externalId']))
                self.remember(db, principal, 'create', body['requestId'], payload, task_id)
                self.insert_message(db, task_id, principal, 'request' if question else 'comment', question or payload['description'], None)
        return self.detail(principal, task_id)

    def insert_message(self, db, task_id, principal, kind, content, reply_to):
        message_id = 'message_' + uuid.uuid4().hex
        db.execute('INSERT INTO messages(id,task_id,author,author_role,kind,body,reply_to,created_at) VALUES(?,?,?,?,?,?,?,?)',
                   (message_id, task_id, principal.subject, principal.role, kind, content, reply_to, now()))
        task = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        parent = db.execute('SELECT * FROM messages WHERE id=?', (reply_to,)).fetchone() if reply_to else None
        context = {'project': PROJECT, 'taskId': task_id, 'messageId': message_id, 'replyTo': reply_to,
                   'title': task['title'], 'kind': kind, 'text': content, 'requestText': parent['body'] if parent else None,
                   'notice': 'OpenTour saved conversation context. Not a native human decision or permission for business action.'}
        context.update(author=principal.subject, authorRole=principal.role,
                       continuationRef=self.execution_ref(db, task_id),
                       requestVersion=self.message_version(parent) if parent else None)
        reference = self.client_ref(db, task_id)
        if reference is not None:
            context['clientRef'] = reference
        if db.execute('SELECT 1 FROM client_conversations WHERE task_id=?',(task_id,)).fetchone():
            context['conversationMode']='client'
            context['proposal']=self.proposal(db,task_id)
            context['history']=[dict(r) for r in reversed(db.execute('SELECT id,kind,body,author,author_role,reply_to FROM messages WHERE task_id=? ORDER BY seq DESC LIMIT 12',(task_id,)).fetchall())]
        # The body is deterministic and persisted before delivery; no mutable task reread on retry.
        raw = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        outbox_id = 'context_' + hashlib.sha256((PROJECT + ':' + message_id).encode()).hexdigest()
        native_id = 'qitem-opentour-context-' + hashlib.sha256(outbox_id.encode()).hexdigest()[:32]
        routing = db.execute('SELECT native_ref,destination FROM task_execution WHERE task_id=?', (task_id,)).fetchone()
        destination = routing['destination'] if routing and routing['destination'] else DESTINATIONS[task['section']]
        routing_ref = routing['native_ref'] if routing and routing['destination'] else None
        db.execute('INSERT INTO outbox(id,message_id,destination,native_id,payload,digest,state,updated_at,routing_ref) VALUES(?,?,?,?,?,?,?,?,?)',
                   (outbox_id, message_id, destination, native_id, raw, version(context), 'pending', now(), routing_ref))
        return message_id

    def append(self, principal, task_id, body, resolve_obligation=None):
        fields(body, ('requestId', 'kind', 'text', 'replyTo', 'replyVersion'))
        kind = body.get('kind')
        if kind not in ('answer', 'comment', 'request') or (kind == 'request' and principal.role != 'administrator'):
            raise Failure('board_message_kind_forbidden', 403)
        payload = {'kind': kind, 'text': text(body.get('text'), 4000), 'replyTo': body.get('replyTo')}
        if 'replyVersion' in body:
            payload['replyVersion'] = body['replyVersion']
        if (kind == 'answer') != isinstance(payload['replyTo'], str) or (kind != 'answer' and payload['replyTo'] is not None):
            raise Failure('answer_request_link_required', 400)
        with self.db() as db:
            self.task(db, principal, task_id, write=True)
            existing = self.replay(db, principal, 'message:' + task_id, body.get('requestId'), payload)
            routing = db.execute('SELECT native_ref,destination FROM task_execution WHERE task_id=?', (task_id,)).fetchone()
        if existing:
            return {'taskId': task_id, 'messageId': existing, 'persistence': 'saved', **self.message(principal, task_id, existing)}
        if routing and routing['destination']:
            if resolve_obligation is None:
                raise Failure('native_obligation_lookup_required', 503)
            if resolve_obligation(routing['native_ref'], routing['destination']) != routing['destination']:
                raise Failure('native_obligation_owner_changed',409)
        with self.db() as db:
            self.task(db, principal, task_id, write=True)
            message_id = self.replay(db, principal, 'message:' + task_id, body.get('requestId'), payload)
            if not message_id:
                if kind == 'answer':
                    parent = db.execute('SELECT * FROM messages WHERE id=?', (payload['replyTo'],)).fetchone()
                    if not parent or parent['kind'] != 'request' or parent['task_id'] != task_id:
                        raise Failure('answer_request_not_found', 404)
                    if 'replyVersion' in payload and payload['replyVersion'] != self.message_version(parent):
                        raise Failure('answer_request_version_conflict', 409)
                    accepted = db.execute("SELECT 1 FROM messages m JOIN outbox o ON o.message_id=m.id WHERE m.reply_to=? AND o.processing IN ('accepted','continued')", (parent['id'],)).fetchone()
                    if accepted:
                        raise Failure('answer_request_already_accepted', 409)
                message_id = self.insert_message(db, task_id, principal, kind, payload['text'], payload['replyTo'])
                self.remember(db, principal, 'message:' + task_id, body['requestId'], payload, message_id)
        return {'taskId': task_id, 'messageId': message_id, 'persistence': 'saved', **self.message(principal, task_id, message_id)}

    @staticmethod
    def message_version(row):
        return version({k: row[k] for k in ('id', 'task_id', 'kind', 'body', 'author', 'author_role', 'created_at')})

    def execution_ref(self, db, task_id):
        row = db.execute('SELECT native_ref FROM task_execution WHERE task_id=?', (task_id,)).fetchone()
        return row['native_ref'] if row else None

    def request_state(self, db, task_id):
        if db.execute('SELECT 1 FROM client_conversations WHERE task_id=?',(task_id,)).fetchone():
            latest=db.execute(MESSAGE_SELECT+' WHERE m.task_id=? ORDER BY m.seq DESC LIMIT 1',(task_id,)).fetchone()
            if latest and latest['kind']=='agent_reply':return 'agent_replied'
            return ('saved' if latest['state']=='pending' else latest['state']) if latest else 'comment_only'
        request = db.execute("SELECT id FROM messages WHERE task_id=? AND kind='request' ORDER BY seq DESC LIMIT 1", (task_id,)).fetchone()
        if not request:
            return 'comment_only'
        answer = db.execute(MESSAGE_SELECT + " WHERE m.reply_to=? ORDER BY CASE o.processing WHEN 'continued' THEN 0 WHEN 'accepted' THEN 1 ELSE 2 END,m.seq DESC LIMIT 1", (request['id'],)).fetchone()
        if not answer:
            return 'awaiting_answer'
        if answer['processing'] != 'unconfirmed':
            return answer['processing']
        return 'saved' if answer['state'] == 'pending' else answer['state']

    def project_message(self, row):
        return {k: row[k] for k in ('id', 'kind', 'body', 'reply_to', 'author', 'author_role', 'created_at')} | {
            'version': self.message_version(row), 'persistence': 'saved', 'delivery': {'id': row['outbox_id'], 'state': row['state'] or 'not_applicable',
                'executionRef': row['native_id'] if row['state'] == 'delivered' else None,
                'processing': row['processing'] or 'returned', 'error': row['error'],
                'reason': row['processing_reason'], 'result': row['result_text'], 'evidenceRef': row['evidence_ref'],
                'timestamps': {k: row[k] for k in ('delivered_at','received_at','accepted_at','continued_at')}}}

    def message(self, principal, task_id, message_id):
        with self.db() as db:
            self.task(db, principal, task_id)
            row = db.execute(MESSAGE_SELECT + ' WHERE m.task_id=? AND m.id=?', (task_id, message_id)).fetchone()
            if row is None:
                raise Failure('board_message_not_found', 404)
            return self.project_message(row)

    def detail(self, principal, task_id):
        with self.db() as db:
            task = dict(self.task(db, principal, task_id))
            rows = db.execute(MESSAGE_SELECT + ' WHERE m.task_id=? ORDER BY m.seq DESC LIMIT 101', (task_id,)).fetchall()
            task['clientRef'] = self.client_ref(db, task_id)
            task['continuationRef'] = self.execution_ref(db, task_id)
            task['requestState'] = self.request_state(db, task_id)
            contextual=bool(db.execute('SELECT 1 FROM client_conversations WHERE task_id=?',(task_id,)).fetchone())
            task['conversation']={'enabled':contextual,'recipient':db.execute('SELECT destination FROM task_execution WHERE task_id=?',(task_id,)).fetchone()[0] if contextual else None,
                'canMessage':contextual and principal.board_respond,
                'canEditProposal':contextual and principal.board_respond and principal.proposal_edit and self.client_key(task['clientRef']) in principal.conversation_clients}
            task['proposal']=self.proposal(db,task_id) if contextual else None
            task['proposalHistory']=[dict(r) for r in db.execute('SELECT revision,base_revision,author,author_role,source_message,created_at FROM proposal_revisions WHERE task_id=? ORDER BY revision DESC LIMIT 50',(task_id,))] if contextual else []
            task['messages'] = [self.project_message(r) for r in reversed(rows[:100])]
            task['historyComplete'] = len(rows) <= 100
            task['version'] = version(task)
            return task

    def client_ref(self, db, task_id):
        row = db.execute('SELECT entity,external_id FROM task_clients WHERE task_id=?', (task_id,)).fetchone()
        return {'entity': row['entity'], 'externalId': row['external_id']} if row else None

    def related(self, principal, reference):
        self.permit(principal)
        reference = client_reference(reference)
        if reference is None:
            raise Failure('invalid_client_reference', 400)
        with self.db() as db:
            params = [PROJECT, reference['entity'], reference['externalId']]
            sql = """SELECT t.id,t.title FROM tasks t JOIN task_clients c ON c.task_id=t.id
                     WHERE t.project=? AND c.entity=? AND c.external_id=?"""
            if '*' not in principal.board_tasks:
                sql += ' AND (t.id IN (' + ','.join('?' for _ in principal.board_tasks) + ') OR (EXISTS(SELECT 1 FROM client_conversations x WHERE x.task_id=t.id) AND ? IN (' + ','.join('?' for _ in principal.conversation_clients) + ')))'
                params.extend(principal.board_tasks);params.append(self.client_key(reference));params.extend(principal.conversation_clients)
            rows = db.execute(sql + ' ORDER BY t.created_at DESC,t.id LIMIT 101', params).fetchall()
            return {'items': [dict(r) for r in rows[:100]], 'status': 'available', 'complete': len(rows) <= 100}

    def list(self, principal):
        self.permit(principal)
        with self.db() as db:
            params = [PROJECT]
            sql = 'SELECT * FROM tasks WHERE project=?'
            if '*' not in principal.board_tasks:
                sql += " AND (id IN (" + ','.join('?' for _ in principal.board_tasks) + ") OR id IN (SELECT x.task_id FROM client_conversations x JOIN task_clients c ON c.task_id=x.task_id WHERE 'crm:'||c.entity||':'||c.external_id IN (" + ','.join('?' for _ in principal.conversation_clients) + ')))'
                params.extend(principal.board_tasks);params.extend(principal.conversation_clients)
            rows = db.execute(sql + ' ORDER BY created_at DESC,id LIMIT 101', params).fetchall()
            return {'project': PROJECT, 'items': [{**dict(r), 'requestState': self.request_state(db,r['id'])} for r in rows[:100]], 'complete': len(rows) <= 100}


MESSAGE_SELECT = '''SELECT m.*,o.id AS outbox_id,o.state,o.native_id,o.processing,o.error,o.processing_reason,o.result_text,o.evidence_ref,o.delivered_at,o.received_at,o.accepted_at,o.continued_at
FROM messages m LEFT JOIN outbox o ON o.message_id=m.id'''
SCHEMA = [
'''CREATE TABLE tasks(id TEXT PRIMARY KEY,project TEXT NOT NULL,title TEXT NOT NULL,description TEXT NOT NULL,
section TEXT NOT NULL,created_by TEXT NOT NULL,created_at TEXT NOT NULL)''',
'''CREATE TABLE messages(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,task_id TEXT NOT NULL REFERENCES tasks(id),
author TEXT NOT NULL,author_role TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL,
reply_to TEXT REFERENCES messages(id),created_at TEXT NOT NULL)''',
'''CREATE TABLE requests(subject TEXT NOT NULL,operation TEXT NOT NULL,request_key TEXT NOT NULL,digest TEXT NOT NULL,
result_id TEXT NOT NULL,PRIMARY KEY(subject,operation,request_key))''',
'''CREATE TABLE outbox(id TEXT PRIMARY KEY,message_id TEXT UNIQUE NOT NULL REFERENCES messages(id),destination TEXT NOT NULL,
native_id TEXT UNIQUE NOT NULL,payload TEXT NOT NULL,digest TEXT NOT NULL,
state TEXT NOT NULL CHECK(state IN ('pending','delivered','failed','unknown')),error TEXT,
processing TEXT NOT NULL DEFAULT 'unconfirmed',updated_at TEXT NOT NULL)''',
'CREATE INDEX messages_task_sequence ON messages(task_id,seq)',
'CREATE INDEX outbox_state ON outbox(state,updated_at)']


CLIENT_SCHEMA = [
"""CREATE TABLE task_clients(task_id TEXT PRIMARY KEY REFERENCES tasks(id),
entity TEXT NOT NULL CHECK(entity IN ('Contact','Account')),external_id TEXT NOT NULL)""",
'CREATE INDEX task_clients_reference ON task_clients(entity,external_id,task_id)']


DELIVERY_SCHEMA = [
"CREATE TABLE task_execution(task_id TEXT PRIMARY KEY REFERENCES tasks(id),native_ref TEXT NOT NULL)",
"ALTER TABLE outbox ADD COLUMN sender TEXT NOT NULL DEFAULT 'platform-developer@opentour-rig'",
"ALTER TABLE outbox ADD COLUMN native_body TEXT",
"ALTER TABLE outbox ADD COLUMN delivered_at TEXT",
"ALTER TABLE outbox ADD COLUMN received_at TEXT",
"ALTER TABLE outbox ADD COLUMN accepted_at TEXT",
"ALTER TABLE outbox ADD COLUMN continued_at TEXT",
"ALTER TABLE outbox ADD COLUMN processing_reason TEXT",
"ALTER TABLE outbox ADD COLUMN result_text TEXT",
"ALTER TABLE outbox ADD COLUMN evidence_ref TEXT",
"CREATE TABLE processing_events(outbox_id TEXT NOT NULL REFERENCES outbox(id),state TEXT NOT NULL,reason TEXT NOT NULL,result_text TEXT,evidence_ref TEXT,at TEXT NOT NULL,PRIMARY KEY(outbox_id,state))",
"CREATE TABLE delivery_worker(id INTEGER PRIMARY KEY CHECK(id=1),sender TEXT NOT NULL,heartbeat TEXT NOT NULL,last_error TEXT)"
]

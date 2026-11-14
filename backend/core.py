"""Stateless source projections; local snapshot cursors are disposable UI hints."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from .adapters import Failure, private_json

PROJECT = 'opentour'
MISSION = '01-local-information-layer'
ID = re.compile(r'[A-Za-z0-9_-]{1,128}')
MARKER = re.compile(r'^opentour-source-v2:(source-[0-9]{2}):([0-9a-f]{64}):([0-9]+):([A-Za-z0-9-]+)$')
COLUMNS = [
    {'id': 'planned', 'label': 'Запланировано'}, {'id': 'in_progress', 'label': 'В работе'},
    {'id': 'needs_human', 'label': 'Требуется человек'}, {'id': 'review', 'label': 'На проверке'},
    {'id': 'done', 'label': 'Выполнено'}, {'id': 'unknown', 'label': 'Состояние неизвестно'}]
TITLES = {'01-local-crm': 'Подключить локальную CRM', '02-contact-import': 'Подготовить клиентские данные',
          '03-operator-board': 'Подключить доску и диалог с оператором', '04-campaign-draft': 'Подготовить пакет кампании',
          '05-journey-qa': 'Проверить путь менеджера'}
WRITE_LIMITATION = 'manager_identity_and_native_action_authorization_unavailable'


def version(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def safe_text(value, limit=1600):
    if not isinstance(value, str):
        return None
    text = re.sub(r'(?i)(bearer\s+|(?:password|api[_-]?key|token)\s*[=:]\s*)\S+', '[redacted]', value)
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[email]', text)
    text = re.sub(r'(?<!\w)\+?\d[\d ()-]{8,}\d(?!\w)', '[number]', text)
    text = re.sub(r'/(?:Users|private|home|tmp|var)/[^\s)]+', '[local path]', text)
    return ''.join(c for c in text if c in '\n\t' or ord(c) >= 32)[:limit]


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    projects: tuple
    board_read: bool = False
    board_respond: bool = False
    board_create: bool = False
    board_tasks: tuple = ()
    board_only: bool = False


class Auth:
    """Server-owned hashed bearer grants; not browser-selected roles or human identities."""
    def __init__(self, path=None, grants=None):
        self.path, self.grants = path, grants

    def authorize(self, header):
        if not header or not header.startswith('Bearer ') or len(header) > 1024:
            raise Failure('authentication_required', 401)
        token = header[7:]
        if len(token) < 24:
            raise Failure('authentication_required', 401)
        grants = self.grants
        if grants is None:
            if not self.path:
                raise Failure('read_access_not_configured', 503)
            grants = private_json(self.path).get('principals')
        if not isinstance(grants, list):
            raise Failure('read_access_not_configured', 503)
        digest = hashlib.sha256(token.encode()).hexdigest()
        for g in grants:
            if not isinstance(g, dict) or not isinstance(g.get('tokenSha256'), str):
                continue
            if hmac.compare_digest(digest, g['tokenSha256']):
                if g.get('role') not in ('user', 'administrator') or not isinstance(g.get('subject'), str) or not isinstance(g.get('projects'), list):
                    raise Failure('invalid_read_grant', 403)
                if PROJECT not in g['projects']:
                    raise Failure('project_forbidden', 403)
                if type(g.get('boardOnly',False)) is not bool:
                    raise Failure('invalid_board_grant',403)
                board = g.get('board', {})
                if (not isinstance(board, dict) or set(board) - {'read', 'respond', 'create', 'tasks'}
                        or any(type(board.get(k, False)) is not bool for k in ('read', 'respond', 'create'))
                        or not isinstance(board.get('tasks', []), list)
                        or len(board.get('tasks', [])) > 1000
                        or any(not isinstance(t, str) or len(t) > 128 for t in board.get('tasks', []))):
                    raise Failure('invalid_board_grant', 403)
                if g.get('boardOnly') and (not board.get('tasks') or '*' in board['tasks']):
                    raise Failure('board_only_requires_exact_task_scope',403)
                return Principal(g['subject'], g['role'], tuple(g['projects']), board.get('read', False),
                                 board.get('respond', False), board.get('create', False), tuple(board.get('tasks', [])), g.get('boardOnly',False))
        raise Failure('authentication_required', 401)


def client_card(entity, obj, base):
    key = obj.get('id')
    if not isinstance(key, str) or not ID.fullmatch(key):
        raise Failure('crm_record_identity_invalid')
    marker = MARKER.fullmatch(obj.get('description') or '') if entity == 'Contact' else None
    placeholder = bool(marker and obj.get('lastName') == 'None')
    if entity == 'Contact' and placeholder:
        display = obj.get('firstName') or None
    else:
        display = obj.get('name') or (' '.join(x for x in (obj.get('firstName'), obj.get('lastName')) if x) or None)
    provenance = {'system': 'espocrm', 'entity': entity, 'externalId': key}
    if marker:
        provenance['import'] = {'markerVersion': 2, 'sourceIdentity': marker[1],
                                'sourceRevision': marker[2], 'logicalRow': int(marker[3]), 'mappingVersion': marker[4]}
    card = {'id': 'crm:' + entity + ':' + key,
            'kind': 'person' if entity == 'Contact' else 'organization',
            'displayName': display, 'email': obj.get('emailAddress') or None,
            'phone': obj.get('phoneNumber') or None,
            'attributes': {'crmType': obj.get('type')} if entity == 'Account' else {'jobTitle':obj.get('title')},
            'surname': {'status': 'technical_placeholder_observed' if placeholder else 'source_value_or_unknown',
                        'technicalValue': 'None' if placeholder else None,
                        'deduplicationKey': False if placeholder else None},
            'provenance': provenance, 'sourceLink': base.rstrip('/') + '/#' + entity + '/view/' + key,
            'modifiedAt': obj.get('modifiedAt'),
            'relatedWork': {'items': [], 'status': 'relationship_not_available'}}
    card['version'] = version(card)
    return card


def is_human(q):
    dest, blocker = q.get('destinationSession') or '', q.get('blockedOn') or ''
    return ((dest.endswith('@external') and q.get('humanIntent') != 'update')
            or bool(re.fullmatch(r'(?:human[^@]*|operator-human)@(?:kernel|host)', dest))
            or (q.get('state') == 'blocked' and (blocker.endswith('@external')
                or bool(re.fullmatch(r'(?:human[^@]*|operator-human)@(?:kernel|host)', blocker)))))


def board_card(s, complete):
    rows = s['queue']
    active = [q for q in rows if q.get('state') in ('pending', 'in-progress', 'blocked')]
    human = [q for q in active if is_human(q)]
    review = [q for q in active if (q.get('destinationSession') or '').startswith('platform-qa-')]
    blockers = [{'sourceId': q['qitemId'], 'reason': safe_text(q.get('blockedOn'), 300),
                 'requestedAction': safe_text(q.get('summary'), 500)} for q in active if q.get('state') == 'blocked']
    # Proof plus explicit authored completion is required. Internal task closure never completes a slice.
    done = s.get('authoredStatus') in ('done', 'complete', 'completed') and s.get('readiness') == 'ready'
    if human:
        column = 'needs_human'
    elif review:
        column = 'review'
    elif active:
        column = 'in_progress'
    elif done and complete:
        column = 'done'
    elif not complete or s.get('nativeStatus') not in ('active', 'blocked', 'done', 'planned'):
        column = 'unknown'
    elif s.get('nativeStatus') in ('active', 'blocked'):
        column = 'in_progress'
    else:
        column = 'planned' if s.get('authoredStatus') == 'planned' else 'unknown'
    latest = sorted(active, key=lambda q: (q.get('tsUpdated') or '', q['qitemId']), reverse=True)
    actionable = sorted(human or review or active, key=lambda q: (q.get('tsUpdated') or '', q['qitemId']), reverse=True)
    owners = []
    for q in latest:
        session = q.get('destinationSession')
        if session and session not in {o['sourceId'] for o in owners}:
            # This is a native seat reference, not a claim that a person is authenticated.
            role = session.split('@')[0].partition('-')[2] if session.endswith('@opentour-rig') else None
            owners.append({'sourceId': session, 'kind': 'human_request' if is_human(q) else 'agent', 'role': role})
    card = {'id': 'work:' + PROJECT + ':' + MISSION + ':' + s['name'], 'project': PROJECT,
            'mission': MISSION, 'slice': s['name'], 'title': TITLES.get(s['name'], safe_text(s['title'], 240)),
            'sourceTitle': safe_text(s['title'], 240), 'column': column, 'owners': owners,
            'lastResult': safe_text(s.get('lastResult')), 'currentContext': safe_text(s.get('currentContext'), 2400),
            'blockers': blockers, 'requiredNextAction': safe_text(actionable[0].get('summary'), 600) if actionable else None,
            'lastActivityAt': s.get('lastActivityAt'),
            'nativeFacts': {'sourceId': s['sourceId'], 'authoredStatus': s.get('authoredStatus'),
                            'nativeStatus': s.get('nativeStatus'), 'readiness': s.get('readiness'),
                            'activeQitems': len(active), 'qitemCount': len(rows), 'queueWindowComplete': complete},
            'sourceRefs': [{'system': 'openrig', 'type': 'slice', 'id': s['sourceId']}]
                          + [{'system': 'openrig', 'type': 'qitem', 'id': q['qitemId']} for q in latest],
            'actions': {'reply': {'enabled': False, 'reason': WRITE_LIMITATION},
                        'clarify': {'enabled': False, 'reason': WRITE_LIMITATION}}}
    card['version'] = version(card)
    return card


class Service:
    def __init__(self, crm, native):
        self.crm, self.native = crm, native
        self.epoch, self.sequence, self.last_version = uuid.uuid4().hex, 0, None
        self.lock = threading.Lock()

    def clients(self, params):
        def integer(name, default, lo, hi):
            raw = params.get(name, str(default))
            if not re.fullmatch(r'\d{1,6}', raw) or not lo <= int(raw) <= hi:
                raise Failure('invalid_' + name, 400)
            return int(raw)
        kind, query = params.get('kind', 'all'), params.get('q', '')
        if kind not in ('all', 'person', 'organization') or len(query) > 200 or any(ord(c) < 32 for c in query):
            raise Failure('invalid_client_filter', 400)
        offset, limit = integer('offset', 0, 0, 100000), integer('limit', 25, 1, 100)
        flags = {}
        for name in ('hasEmail', 'hasPhone'):
            value = params.get(name)
            if value is not None and value not in ('true', 'false'):
                raise Failure('invalid_client_filter', 400)
            flags[name] = None if value is None else value == 'true'
        kwargs = {'query': query, 'has_email': flags['hasEmail'], 'has_phone': flags['hasPhone']}
        entities = ['Contact', 'Account'] if kind == 'all' else ['Contact' if kind == 'person' else 'Account']
        items, totals, skip = [], {}, offset
        for entity in entities:
            result = self.crm.list(entity, offset=skip, limit=max(1, limit - len(items)), **kwargs)
            total = result['total']
            totals[entity] = total
            if skip < total and len(items) < limit:
                items.extend(client_card(entity, obj, self.crm.base) for obj in result['list'] if not obj.get('deleted'))
            skip = max(0, skip - total)
        total = sum(totals.values())
        return {'source': 'live_crm', 'project': PROJECT, 'items': items, 'total': total,
                'offset': offset, 'limit': limit, 'nextOffset': offset + len(items) if offset + len(items) < total else None,
                'ordering': 'Contact_then_Account_id_asc', 'totalsByEntity': totals}

    def client(self, key):
        parts = key.split(':')
        if len(parts) != 3 or parts[0] != 'crm' or parts[1] not in ('Contact', 'Account') or not ID.fullmatch(parts[2]):
            raise Failure('client_not_found', 404)
        return client_card(parts[1], self.crm.detail(parts[1], parts[2]), self.crm.base)

    def native_decisions(self, work_id, original_id):
        from .native_observations import observe
        prefix = 'work:' + PROJECT + ':' + MISSION + ':'
        if (not work_id.startswith(prefix) or self.native.project != PROJECT
                or self.native.mission != MISSION):
            raise Failure('work_not_found', 404)
        return observe(self.native, work_id[len(prefix):], original_id)

    def board(self):
        # Serialize snapshots so slower earlier reads cannot obtain a newer cursor.
        with self.lock:
            slices, complete = self.native.snapshot()
            items = sorted((board_card(s, complete) for s in slices), key=lambda x: x['id'])
            data = {'project': PROJECT, 'mission': MISSION, 'columns': COLUMNS, 'items': items,
                    'source': 'live_native_work', 'queueWindowComplete': complete,
                    'writes': {'enabled': False, 'reason': WRITE_LIMITATION}}
            rev = version(data)
            if rev != self.last_version:
                self.sequence += 1
                self.last_version = rev
            return {**data, 'version': rev, 'cursor': {'epoch': self.epoch, 'sequence': self.sequence}, 'observedAt': now()}

"""Guarded maintenance of an existing client conversation's native anchor.

No HTTP route, message, outbox send or native queue mutation is introduced.
The desired anchor comes only from the existing private server-owned controls.
"""
from .adapters import Failure
from .core import PROJECT, version

DESTINATION = 'campaign-creative@opentour-rig'


def binding_snapshot(db, task_id):
    row = db.execute('SELECT t.project,e.native_ref,e.destination,c.entity,c.external_id '
        'FROM tasks t JOIN client_conversations x ON x.task_id=t.id '
        'JOIN task_execution e ON e.task_id=t.id JOIN task_clients c ON c.task_id=t.id '
        'WHERE t.id=?', (task_id,)).fetchone()
    if not row or row['project'] != PROJECT or row['destination'] != DESTINATION:
        raise Failure('client_binding_context_invalid', 409)
    state = dict(row)
    records = {}
    for table in ('messages', 'proposal_revisions'):
        records[table] = [dict(r) for r in db.execute('SELECT * FROM '+table+' WHERE task_id=? ORDER BY rowid', (task_id,))]
    records['outbox'] = [dict(r) for r in db.execute('SELECT o.* FROM outbox o JOIN messages m ON m.id=o.message_id WHERE m.task_id=? ORDER BY o.rowid', (task_id,))]
    # A bound event already in flight must be reconciled, never rerouted.
    for outbox in records['outbox']:
        returned = db.execute("SELECT 1 FROM messages WHERE task_id=? AND reply_to=? AND kind='agent_reply'", (task_id, outbox['message_id'])).fetchone()
        if outbox['state'] != 'delivered' or not returned:
            raise Failure('client_binding_delivery_unresolved', 409)
    return state, version({'routing': state, 'records': records})


def plan_binding(db, task_id, previous_ref, event_request_id, controls, native):
    from .board_store import key
    key(event_request_id)
    state, fingerprint = binding_snapshot(db, task_id)
    if state['native_ref'] != previous_ref:
        raise Failure('client_binding_previous_changed', 409)
    if db.execute('SELECT 1 FROM requests WHERE operation=? AND request_key=?',
                  ('message:'+task_id, event_request_id)).fetchone():
        raise Failure('client_binding_original_event_already_saved', 409)
    client = {'entity': state['entity'], 'externalId': state['external_id']}
    current_ref = controls.resolve(client)
    if current_ref == previous_ref:
        raise Failure('client_binding_current_anchor_required', 409)
    # Terminal history remains terminal. The current active anchor is a distinct
    # business-owner continuation, not a manufactured app delivery receipt.
    native.resolve(previous_ref, DESTINATION, states=('done',))
    old = native.client.get('/api/queue/'+previous_ref)
    if (not isinstance(old, dict) or old.get('qitemId') != previous_ref or
            old.get('state') != 'done' or old.get('closureReason') != 'no-follow-on'):
        raise Failure('client_binding_previous_not_completed', 409)
    native.resolve(current_ref, DESTINATION)
    plan = {'schema': 'opentour.client-binding-plan/1', 'taskId': task_id,
        'previousRef': previous_ref, 'currentRef': current_ref, 'destination': DESTINATION,
        'clientIdentitySha256': version(client), 'stateSha256': fingerprint,
        'originalEventRequestId': event_request_id,
        'nativeGate': 'COMPLETED_PRIOR_AND_ACTIVE_CURRENT_SAME_REGISTERED_OWNER'}
    return plan


def validate_plan(plan, expected_sha256):
    import re
    from .board_store import key
    required = {'schema', 'taskId', 'previousRef', 'currentRef', 'destination',
                'clientIdentitySha256', 'stateSha256', 'originalEventRequestId', 'nativeGate'}
    if (not isinstance(plan, dict) or set(plan) != required or
            plan.get('schema') != 'opentour.client-binding-plan/1' or
            not all(isinstance(v, str) for v in plan.values()) or
            not re.fullmatch(r'task_[a-f0-9]{32}', plan['taskId']) or
            any(not re.fullmatch(r'qitem-[A-Za-z0-9_-]{1,160}', plan[k]) for k in ('previousRef', 'currentRef')) or
            plan['previousRef'] == plan['currentRef'] or plan['destination'] != DESTINATION or
            plan['nativeGate'] != 'COMPLETED_PRIOR_AND_ACTIVE_CURRENT_SAME_REGISTERED_OWNER' or
            any(not re.fullmatch(r'[a-f0-9]{64}', plan[k]) for k in ('clientIdentitySha256', 'stateSha256')) or
            not isinstance(expected_sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', expected_sha256) or
            version(plan) != expected_sha256):
        raise Failure('client_binding_plan_invalid', 400)
    key(plan['originalEventRequestId'])


def apply_binding(store, plan, expected_sha256, request_id, actor, controls, native):
    from .board_store import key
    key(request_id)
    validate_plan(plan, expected_sha256)
    if actor not in ('native:engineering-platform@engineering-rig', 'native:infrastructure-engineer@engineering-rig'):
        raise Failure('client_binding_actor_forbidden', 403)
    operation = 'client-binding:'+plan['taskId']
    # Existing request audit supplies idempotency; no second maintenance ledger.
    with store.db() as db:
        saved = db.execute('SELECT digest,result_id FROM requests WHERE subject=? AND operation=? AND request_key=?',
                           (actor, operation, request_id)).fetchone()
        if saved:
            if saved['digest'] != expected_sha256:
                raise Failure('request_content_conflict', 409)
            return {'status': 'REPLAYED', 'taskId': plan['taskId'], 'continuationRef': saved['result_id']}
    current = plan_binding_read(store.path, plan['taskId'], plan['previousRef'],
                                plan['originalEventRequestId'], controls, native)
    if version(current) != expected_sha256 or version(plan) != expected_sha256:
        raise Failure('client_binding_plan_changed', 409)
    with store.db() as db:
        saved = db.execute('SELECT digest,result_id FROM requests WHERE subject=? AND operation=? AND request_key=?',
                           (actor, operation, request_id)).fetchone()
        if saved:
            if saved['digest'] != expected_sha256:raise Failure('request_content_conflict', 409)
            return {'status': 'REPLAYED', 'taskId': plan['taskId'], 'continuationRef': saved['result_id']}
        if db.execute('SELECT 1 FROM requests WHERE operation=? AND request_key=?',
                      ('message:'+plan['taskId'], plan['originalEventRequestId'])).fetchone():
            raise Failure('client_binding_original_event_already_saved', 409)
        _, fingerprint = binding_snapshot(db, plan['taskId'])
        if fingerprint != plan['stateSha256']:
            raise Failure('client_binding_plan_changed', 409)
        # Compare-and-set of the single existing route. Historical payloads,
        # messages, proposals and the rejected QA request are untouched.
        changed = db.execute('UPDATE task_execution SET native_ref=? WHERE task_id=? AND native_ref=? AND destination=?',
            (plan['currentRef'], plan['taskId'], plan['previousRef'], DESTINATION)).rowcount
        if changed != 1:raise Failure('client_binding_previous_changed', 409)
        db.execute('INSERT INTO requests VALUES(?,?,?,?,?)',
                   (actor, operation, request_id, expected_sha256, plan['currentRef']))
    return {'status': 'REBOUND', 'taskId': plan['taskId'], 'continuationRef': plan['currentRef']}


def plan_binding_read(path, task_id, previous_ref, event_request_id, controls, native):
    from tools.local_board_release import _connect_readonly
    import sqlite3
    db = _connect_readonly(path)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        return plan_binding(db, task_id, previous_ref, event_request_id, controls, native)
    finally:
        db.close()

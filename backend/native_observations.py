"""Bounded native evidence reads. Observations are never human authentication or action receipts."""
import re
from .adapters import Failure

STATES = {'pending', 'in-progress', 'blocked', 'done', 'failed', 'denied', 'canceled', 'handed-off'}
QID = re.compile(r'[A-Za-z0-9_-]{1,160}')


def scoped(row, project, mission, slice_name):
    return isinstance(row, dict) and all(tag in (row.get('tags') or []) for tag in (
        'project:' + project, 'mission:' + mission, 'slice:' + slice_name))


def observe(native, slice_name, original_id):
    if not QID.fullmatch(original_id):
        raise Failure('native_work_not_found', 404)
    slices, complete = native.snapshot()
    selected = next((s for s in slices if s['name'] == slice_name), None)
    if not selected:
        raise Failure('work_not_found', 404)
    rows = {q.get('qitemId'): q for q in selected['queue'] if scoped(q, native.project, native.mission, slice_name)}
    listed = rows.get(original_id)
    if not listed:
        raise Failure('native_work_not_found', 404)
    # Scope is established from the existing catalog before any full-row/audit read.
    original = native.client.get('/api/queue/' + original_id)
    if not scoped(original, native.project, native.mission, slice_name) or original.get('qitemId') != original_id:
        raise Failure('native_observation_scope_mismatch', 503)
    for key in ('state', 'destinationSession', 'blockedOn', 'tsUpdated'):
        if original.get(key) != listed.get(key):
            raise Failure('native_observation_changed', 503)
    targets = [(original, 'resolve')]
    blocker = original.get('blockedOn')
    if original.get('state') == 'blocked' and isinstance(blocker, str) and blocker in rows:
        ask = native.client.get('/api/queue/' + blocker)
        if (not scoped(ask, native.project, native.mission, slice_name) or ask.get('qitemId') != blocker
                or ask.get('sourceSession') != original.get('destinationSession')):
            raise Failure('native_observation_scope_mismatch', 503)
        # This checks native routing, not that the addressed person is the app user.
        if (ask.get('humanIntent') != 'update' and
                re.fullmatch(r'[A-Za-z0-9_-]+@external', ask.get('destinationSession') or '')):
            targets.append((ask, 'answer'))
    observations = []
    audit_complete = True
    for target, verb in targets:
        target_id = target['qitemId']
        if not QID.fullmatch(target_id):
            raise Failure('native_observation_invalid', 503)
        result = native.client.get('/api/mission-control/audit', {
            'qitem_id': target_id, 'action_verb': verb, 'limit': 20})
        if (not isinstance(result, dict) or not isinstance(result.get('rows'), list)
                or len(result['rows']) > 20 or type(result.get('hasMore')) is not bool):
            raise Failure('native_audit_invalid', 503)
        audit_complete = audit_complete and not result['hasMore']
        for event in result['rows']:
            if (not isinstance(event, dict) or event.get('qitemId') != target_id
                    or event.get('actionVerb') != verb or not QID.fullmatch(event.get('actionId') or '')):
                raise Failure('native_audit_scope_mismatch', 503)
            before, after = event.get('beforeState'), event.get('afterState')
            if (not isinstance(before, dict) or not isinstance(after, dict)
                    or before.get('qitemId') != target_id or after.get('qitemId') != target_id
                    or before.get('state') not in STATES or after.get('state') not in STATES):
                raise Failure('native_audit_invalid', 503)
            # Never emit decision words, actors, audit notes, bodies or question answers.
            observations.append({'actionId': event['actionId'], 'targetTaskId': target_id,
                                 'verb': verb, 'beforeState': before.get('state'),
                                 'afterState': after.get('state'),
                                 'status': 'native_audit_entry_observed'})
    replies = []
    reply_complete = complete
    for target, verb in targets:
        if verb != 'answer':
            continue
        candidates = [q for q in rows.values() if 'human-answer' in (q.get('tags') or [])
                      and q.get('sourceSession') == target.get('destinationSession')
                      and q.get('destinationSession') == original.get('destinationSession')]
        reply_complete = reply_complete and len(candidates) <= 20
        for candidate in sorted(candidates, key=lambda q: q['qitemId'])[:20]:
            key = candidate['qitemId']
            if not QID.fullmatch(key):
                raise Failure('native_observation_invalid', 503)
            reply = native.client.get('/api/queue/' + key)
            if not scoped(reply, native.project, native.mission, slice_name) or reply.get('qitemId') != key:
                raise Failure('native_observation_scope_mismatch', 503)
            if (reply.get('replyTo') == target['qitemId'] and 'human-answer' in (reply.get('tags') or [])
                    and reply.get('sourceSession') == target.get('destinationSession')
                    and reply.get('destinationSession') == original.get('destinationSession')):
                replies.append({'askTaskId': target['qitemId'], 'replyTaskId': key,
                                'status': 'native_linked_reply_observed'})
    # Not a transaction: recheck observed task identities/custody after source reads.
    for target, _ in targets:
        current = native.client.get('/api/queue/' + target['qitemId'])
        if any(current.get(k) != target.get(k) for k in (
                'qitemId', 'tags', 'state', 'sourceSession', 'destinationSession', 'blockedOn', 'tsUpdated')):
            raise Failure('native_observation_changed', 503)
    return {'project': native.project, 'mission': native.mission, 'slice': slice_name,
            'originalTaskId': original_id, 'originalState': original.get('state') if original.get('state') in STATES else None,
            'currentAsk': next(({'taskId': row['qitemId'], 'state': row.get('state') if row.get('state') in STATES else None}
                                for row, verb in targets if verb == 'answer'), None),
            'source': 'native_read_observation',
            'status': 'observed' if observations or replies else 'unconfirmed', 'observations': observations,
            'linkedReplies': replies, 'replyWindowComplete': reply_complete,
            'queueWindowComplete': complete, 'auditWindowComplete': audit_complete,
            'humanIdentityVerified': False, 'decisionAccepted': False,
            'ownerActionObserved': False, 'executionEnabled': False, 'retryAllowed': False,
            'limitations': ['No authenticated human binding or validated application intent.',
                            'Historical asks no longer linked by the current blocker are not searched.',
                            'Audit/reply presence does not prove accepted decision content, current human identity or resumed owner work.']}

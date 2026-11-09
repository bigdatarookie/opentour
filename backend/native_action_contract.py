"""Pure preparation/reconciliation model. No transport, persistence, identities or native effects.

This module is deliberately not imported by server.py. An Authority is a future
server-side input, NOT proof of authentication and never a browser-supplied DTO.
All examples/tests use synthetic authorities and native-shaped observations.
"""
from dataclasses import dataclass, field
import hashlib
import json
import re


class ContractError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def native_revision(row):
    """A content precondition, not a native compare-and-swap token or board version."""
    return digest({key: row.get(key) for key in (
        'qitemId', 'state', 'sourceSession', 'destinationSession', 'blockedOn',
        'tsUpdated', 'tags', 'humanIntent', 'humanQuestions', 'humanAnswers')})


@dataclass(frozen=True)
class Authority:
    subject: str
    role: str
    project: str
    person: str
    binding_revision: str
    allowed_original_ids: frozenset


@dataclass(frozen=True)
class Intent:
    request_key: str
    content_digest: str
    action: str
    original_id: str
    target_id: str
    actor: str = field(repr=False)
    owner: str
    binding_revision: str
    subject: str
    expected_revision: str
    decision: str = field(repr=False)
    question_id: str = ''
    option_id: str = ''
    execution_enabled: bool = field(default=False, init=False)

    def native_preview(self):
        """Source-shaped payload for review ONLY; no actor/header or submit capability."""
        body = {'verb': self.action, 'qitemId': self.target_id, 'auditNotes': {'opentour': {
            'requestKey': self.request_key, 'contentDigest': self.content_digest,
            'originalTaskId': self.original_id, 'bindingRevision': self.binding_revision}}}
        if self.question_id:
            body.update(questionId=self.question_id, optionId=self.option_id)
        else:
            body['decision'] = self.decision
        return body


def authorize(authority, original):
    if not isinstance(authority, Authority) or authority.role not in ('user', 'administrator'):
        raise ContractError('authority_required')
    if (authority.project != 'opentour' or not authority.subject or not authority.binding_revision
            or not re.fullmatch(r'[A-Za-z0-9_-]+@external', authority.person or '')):
        raise ContractError('human_binding_required')
    if original.get('qitemId') not in authority.allowed_original_ids:
        raise ContractError('object_forbidden')
    scoped(original)


def scoped(row):
    tags = row.get('tags') or []
    if ('project:opentour' not in tags or 'mission:01-local-information-layer' not in tags
            or not any(isinstance(tag, str) and tag.startswith('slice:') for tag in tags)):
        raise ContractError('native_scope_mismatch')


def prepare(request, authority, original, target):
    """Validate one synthetic/preparatory action against trusted native-shaped snapshots."""
    authorize(authority, original)
    allowed = {'requestId', 'action', 'originalTaskId', 'targetTaskId', 'expectedRevision',
               'decision', 'questionId', 'optionId'}
    if not isinstance(request, dict) or set(request) - allowed:
        raise ContractError('unexpected_action_fields')
    if request.get('action') not in ('answer', 'resolve'):
        raise ContractError('action_unsupported')  # Free-agent clarification has no selected safe route.
    request_id = request.get('requestId')
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', request_id):
        raise ContractError('request_identity_required')
    scoped(target)
    if request.get('originalTaskId') != original.get('qitemId') or request.get('targetTaskId') != target.get('qitemId'):
        raise ContractError('native_object_mismatch')
    if not (set(original['tags']) & set(target['tags']) & {t for t in original['tags'] if t.startswith('slice:')}):
        raise ContractError('native_scope_mismatch')
    expected = request.get('expectedRevision')
    if not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected):
        raise ContractError('native_revision_required')
    if expected != native_revision(target):
        raise ContractError('stale_native_revision')
    owner = original.get('destinationSession', '')
    if not re.fullmatch(r'[a-z0-9-]+@opentour-rig', owner):
        raise ContractError('original_owner_unsupported')
    text = request.get('decision', '')
    question, option = request.get('questionId', ''), request.get('optionId', '')
    if not all(isinstance(value, str) for value in (text, question, option)):
        raise ContractError('decision_invalid')
    text = text.strip()
    if len(text) > 4000 or any(ord(c) < 32 and c not in '\n\t' for c in text):
        raise ContractError('decision_invalid')
    if bool(question) != bool(option) or (text and question) or (not text and not question):
        raise ContractError('exactly_one_answer_required')
    action = request['action']
    if action == 'resolve':
        if (target['qitemId'] != original['qitemId'] or original.get('state') != 'blocked'
                or original.get('blockedOn') != authority.person or question):
            raise ContractError('not_own_human_park')
    else:
        if (target.get('state') != 'pending' or target.get('humanIntent') == 'update'
                or target.get('destinationSession') != authority.person
                or target.get('sourceSession') != owner or original.get('state') != 'blocked'
                or original.get('blockedOn') != target['qitemId']):
            raise ContractError('not_own_pending_ask')
        if question:
            questions = [q for q in (target.get('humanQuestions') or []) if q.get('id') == question]
            if (len(questions) != 1 or option not in [o.get('id') for o in questions[0].get('options', [])]
                    or question in (target.get('humanAnswers') or {})):
                raise ContractError('invalid_or_answered_option')
    request_key = digest([authority.project, authority.subject, authority.binding_revision, request_id])
    content = digest([action, original['qitemId'], target['qitemId'], expected, text, question, option])
    return Intent(request_key, content, action, original['qitemId'], target['qitemId'],
                  authority.person, owner, authority.binding_revision, authority.subject, expected, text, question, option)


def reconcile(intent, authority, original, audit=None, reply=None, target=None):
    """Project trusted native evidence; never retry, write, invent a receipt or claim owner work."""
    authorize(authority, original)
    if (original.get('qitemId') != intent.original_id or original.get('destinationSession') != intent.owner
            or authority.person != intent.actor or authority.binding_revision != intent.binding_revision
            or authority.subject != intent.subject):
        raise ContractError('binding_or_custody_changed')
    result = {'originalTaskId': intent.original_id, 'targetTaskId': intent.target_id,
              'status': 'unconfirmed', 'nativeReadyToContinue': False,
              'ownerActionObserved': False, 'retryAllowed': False, 'executionEnabled': False}
    if not audit:
        return result
    notes = (audit.get('auditNotes') or {}).get('opentour', {})
    if notes.get('requestKey') != intent.request_key:
        return result
    if (notes.get('contentDigest') != intent.content_digest or notes.get('originalTaskId') != intent.original_id
            or notes.get('bindingRevision') != intent.binding_revision):
        raise ContractError('request_identity_conflict')
    if (audit.get('qitemId') != intent.target_id or audit.get('actionVerb') != intent.action
            or audit.get('actorSession') != intent.actor or not audit.get('actionId')
            or audit.get('identityProvenance') not in ('transport:v1', 'relay:v1')):
        raise ContractError('receipt_identity_mismatch')
    # Provenance is checked in addition to the external binding precondition;
    # a transport:v1 label alone is NOT human authentication.
    after = audit.get('afterState') or {}
    if after.get('qitemId') != intent.target_id:
        raise ContractError('receipt_target_mismatch')
    if intent.question_id:
        if target:
            scoped(target)
        if (not target or target.get('qitemId') != intent.target_id
                or target.get('destinationSession') != intent.actor
                or (target.get('humanAnswers') or {}).get(intent.question_id) != intent.option_id):
            result['status'] = 'decision_content_unconfirmed'
            return result
    elif audit.get('reason') != intent.decision:
        # Native answer retries return the ORIGINAL committed words. A new
        # correlation note alone must not falsely confirm a later decision.
        result['status'] = 'decision_content_unconfirmed'
        return result
    if intent.action == 'resolve':
        if after.get('state') != 'in-progress' or after.get('blockedOn') is not None or after.get('destinationSession') != intent.owner:
            raise ContractError('receipt_effect_mismatch')
        result['status'] = 'decision_recorded'
    else:
        if after.get('destinationSession') != intent.actor:
            raise ContractError('receipt_identity_mismatch')
        if after.get('state') == 'pending':
            result['status'] = 'partial_answer_recorded'
            return result
        if after.get('state') != 'done':
            raise ContractError('receipt_effect_mismatch')
        if not reply:
            result['status'] = 'answer_return_unconfirmed'
            return result
        if (reply.get('replyTo') != intent.target_id or reply.get('sourceSession') != intent.actor
                or reply.get('destinationSession') != intent.owner or not reply.get('qitemId')
                or 'human-answer' not in (reply.get('tags') or [])):
            raise ContractError('reply_link_mismatch')
        result.update(status='answer_returned', replyTaskId=reply['qitemId'])
    result['nativeReadyToContinue'] = original.get('state') in ('pending', 'in-progress') and original.get('blockedOn') is None
    return result


def refresh_policy(current, incoming, *, authoritative_reconnect=False):
    """Choose how to read a snapshot. Neither a changed card nor reconnect retries an action."""
    for index, cursor in enumerate((current, incoming)):
        if index == 0 and cursor is None:
            continue
        if (not isinstance(cursor, dict) or not isinstance(cursor.get('epoch'), str) or not cursor['epoch']
                or type(cursor.get('sequence')) is not int or cursor['sequence'] < 0
                or not isinstance(cursor.get('version'), str) or not re.fullmatch(r'[a-f0-9]{64}', cursor['version'])):
            raise ContractError('refresh_cursor_invalid')
    if current is None:
        return 'replace_snapshot'
    if current['epoch'] != incoming['epoch']:
        return 'replace_snapshot' if authoritative_reconnect else 'resync_required'
    if incoming['sequence'] < current['sequence']:
        return 'ignore_stale'
    if incoming['sequence'] == current['sequence']:
        return 'unchanged' if incoming['version'] == current['version'] else 'resync_required'
    return 'replace_snapshot'

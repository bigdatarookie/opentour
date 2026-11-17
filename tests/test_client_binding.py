"""Invented stale-anchor repair; no native daemon, CRM or actual app operation."""
from copy import deepcopy
import unittest
from backend.adapters import Failure, NativeObligation
from backend.client_binding import apply_binding, plan_binding_read
from backend.core import version
import test_client_conversations as fixtures
from test_client_conversations import REF, OWNER, OBLIGATION, USER

CURRENT = 'qitem-synthetic-current-client'
EVENT = 'original-rejected-event'
ACTOR = 'native:engineering-platform@engineering-rig'


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.ConversationTests(methodName='runTest')
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.task = self.h.open()
        delivery, _ = self.h.receive(self.task)
        self.h.reply(delivery)
        self.h.transport.rows[OBLIGATION].update(state='done', closureReason='no-follow-on')
        self.h.transport.rows[CURRENT] = {**self.h.transport.rows[OBLIGATION],
            'qitemId': CURRENT, 'state': 'in-progress', 'closureReason': None}
        self.h.controls.records = [{'clientRef': REF, 'continuationRef': CURRENT}]
        class Client:
            def get(_, path):
                return self.h.transport.lookup(path.rsplit('/', 1)[-1])
        def seat(dest):
            return {'canonicalSessionName':dest,'rigName':'opentour-rig',
                    'runtime':'codex','logicalId':'campaign.creative','lifecycleState':'running'}
        self.native = NativeObligation(Client(), seat)

    def plan(self):
        return plan_binding_read(self.h.store.path, self.task['id'], OBLIGATION,
                                 EVENT, self.h.controls, self.native)

    def apply(self, plan, request='binding-maintenance-001', actor=ACTOR):
        return apply_binding(self.h.store, plan, version(plan), request, actor,
                             self.h.controls, self.native)

    def fail(self, code, fn):
        with self.assertRaises(Failure) as c:
            fn()
        self.assertEqual(c.exception.code, code)

    def records(self):
        with self.h.store.db() as db:
            return {table:[tuple(r) for r in db.execute('SELECT * FROM '+table+' ORDER BY rowid')]
                    for table in ('messages','proposal_revisions','outbox')}

    def test_plan_readonly_apply_replay_and_same_event_actual_fixture_round(self):
        before = self.records()
        db_bytes = self.h.store.path.read_bytes()
        plan = self.plan()
        self.assertEqual(db_bytes, self.h.store.path.read_bytes())
        self.assertEqual(self.apply(plan)['status'], 'REBOUND')
        self.assertEqual(self.records(), before)
        with self.h.store.db() as db:
            self.assertEqual(db.execute('SELECT native_ref FROM task_execution').fetchone()[0], CURRENT)
            self.assertIsNone(db.execute('SELECT 1 FROM requests WHERE request_key=?',(EVENT,)).fetchone())
            self.assertEqual(db.execute('SELECT count(*) FROM requests WHERE operation LIKE ?',('client-binding:%',)).fetchone()[0], 1)
        # An unknown apply response is retried by exact identity even when the
        # current obligation has since completed; no second route change occurs.
        self.h.transport.rows[CURRENT]['state'] = 'done'
        self.assertEqual(self.apply(plan)['status'], 'REPLAYED')
        self.h.transport.rows[CURRENT]['state'] = 'in-progress'
        sent = self.h.store.append(USER, self.task['id'],
            {'requestId':EVENT,'kind':'comment','text':'Invented current follow-up'},
            resolve_obligation=self.native.resolve)
        from backend.context_delivery import deliver_one, receive_context
        delivery=sent['delivery']['id']
        self.assertEqual(deliver_one(self.h.store,self.h.transport,delivery),'delivered')
        receive_context(self.h.store,delivery,OWNER)
        self.h.reply(delivery,'current-reply-001',1)
        detail=self.h.store.detail(USER,self.task['id'])
        self.assertEqual(len(detail['messages']),4)
        self.assertEqual(detail['proposal']['revision'],2)
        self.assertEqual(self.h.store.append(USER,self.task['id'],
            {'requestId':EVENT,'kind':'comment','text':'Invented current follow-up'},
            resolve_obligation=self.native.resolve)['messageId'],sent['messageId'])

    def test_refuses_unchanged_closed_wrong_owner_and_scope(self):
        original=deepcopy(self.h.transport.rows[CURRENT])
        for change,code in (({'state':'done'},'native_obligation_state_ineligible'),
            ({'destinationSession':'campaign-operator@opentour-rig'},'native_obligation_owner_changed'),
            ({'tags':['project:foreign','mission:01-local-information-layer']},'native_obligation_scope_mismatch')):
            self.h.transport.rows[CURRENT]={**original,**change}
            self.fail(code,self.plan)
        self.h.transport.rows[CURRENT]=original
        self.h.controls.records[0]['continuationRef']=OBLIGATION
        self.fail('client_binding_current_anchor_required',self.plan)

    def test_old_anchor_must_be_completed_without_reopening(self):
        self.h.transport.rows[OBLIGATION]['state']='in-progress'
        self.fail('native_obligation_state_ineligible',self.plan)
        self.h.transport.rows[OBLIGATION].update(state='done',closureReason='handed_off_to')
        self.fail('client_binding_previous_not_completed',self.plan)

    def test_unreturned_event_blocks_plan_and_race_blocks_apply(self):
        plan=self.plan()
        self.h.store.append(USER,self.task['id'],
            {'requestId':'unresolved-event-001','kind':'comment','text':'Invented pending'},
            resolve_obligation=lambda *a:OWNER)
        self.fail('client_binding_delivery_unresolved',self.plan)
        self.fail('client_binding_delivery_unresolved',lambda:self.apply(plan))

    def test_human_edit_after_plan_preserved_and_apply_refused(self):
        plan=self.plan()
        self.h.store.save_proposal(USER,self.task['id'],
            {'requestId':'human-edit-after-plan','baseRevision':1,'title':'Human','body':'Preserve invented manual edit'})
        before=self.records()
        self.fail('client_binding_plan_changed',lambda:self.apply(plan))
        self.assertEqual(self.records(),before)

    def test_change_during_native_revalidation_is_rejected_in_write_transaction(self):
        plan=self.plan()
        resolve=self.native.resolve
        changed=[]
        def raced(*args,**kwargs):
            if not changed:
                changed.append(True)
                self.h.store.save_proposal(USER,self.task['id'],
                    {'requestId':'racing-human-edit','baseRevision':1,'title':'Human','body':'Keep concurrent edit'})
            return resolve(*args,**kwargs)
        self.native.resolve=raced
        self.fail('client_binding_plan_changed',lambda:self.apply(plan))
        with self.h.store.db() as db:
            self.assertEqual(db.execute('SELECT native_ref FROM task_execution').fetchone()[0],OBLIGATION)
            self.assertEqual(db.execute('SELECT count(*) FROM requests WHERE operation LIKE ?',('client-binding:%',)).fetchone()[0],0)
        self.assertEqual(self.h.store.detail(USER,self.task['id'])['proposal']['revision'],2)

    def test_replay_conflict_malformed_plan_and_wrong_actor(self):
        plan=self.plan()
        self.fail('client_binding_actor_forbidden',lambda:self.apply(plan,actor='browser-owner'))
        self.fail('client_binding_plan_invalid',lambda:self.apply({**plan,'extra':'forged'}))
        self.fail('client_binding_plan_invalid',lambda:apply_binding(self.h.store,[], 'a'*64,'binding-key-001',ACTOR,self.h.controls,self.native))
        self.apply(plan)
        self.fail('request_content_conflict',lambda:self.apply({**plan,'stateSha256':'a'*64}))

class BindingCommandTests(unittest.TestCase):
    def test_only_actual_supported_engineering_identity_is_accepted(self):
        import json
        from types import SimpleNamespace
        from unittest.mock import patch
        from tools.reconcile_client_binding import actual_actor
        good={'rigName':'engineering-rig','nodeId':'invented-node',
              'logicalId':'engineering.platform','sessionName':'engineering-platform@engineering-rig'}
        with patch('tools.reconcile_client_binding.subprocess.run',return_value=SimpleNamespace(stdout=json.dumps({'identity':good}).encode())) as run:
            self.assertEqual(actual_actor(),ACTOR)
            self.assertEqual(run.call_args.args[0],['rig','whoami','--json'])
        for changed in ({'rigName':'foreign'},{'nodeId':None},{'logicalId':'org.lead'},
                        {'sessionName':'campaign-creative@opentour-rig'}):
            with patch('tools.reconcile_client_binding.subprocess.run',return_value=SimpleNamespace(stdout=json.dumps({'identity':{**good,**changed}}).encode())):
                with self.assertRaises(Failure) as c:
                    actual_actor()
                self.assertEqual(c.exception.code,'client_binding_actor_forbidden')


if __name__ == '__main__':
    unittest.main()

"""Preparation-only synthetic contracts. No native daemon or real identity is touched."""
import copy
from dataclasses import replace
import json
import threading
import unittest
import urllib.error
import urllib.request

from backend.native_action_contract import Authority, ContractError, digest, native_revision, prepare, reconcile, refresh_policy
from backend.core import Auth, Service
from backend.server import make_server
from test_backend import CRMFixture, NativeFixture, GRANT, TOKEN


TAGS = ['project:opentour', 'mission:01-local-information-layer', 'slice:03-operator-board']


class NativeContractTests(unittest.TestCase):
    def setUp(self):
        self.actor = Authority('synthetic-subject', 'user', 'opentour', 'synthetic-person@external', 'binding-v1', frozenset({'original-1'}))
        self.original = {'qitemId':'original-1','tags':TAGS,'state':'blocked','blockedOn':'ask-1',
                         'sourceSession':'orch-lead@opentour-rig','destinationSession':'platform-developer@opentour-rig','tsUpdated':'2026-11-09T00:00:00Z'}
        self.ask = {'qitemId':'ask-1','tags':TAGS,'state':'pending','humanIntent':'decision',
                    'sourceSession':'platform-developer@opentour-rig','destinationSession':self.actor.person,
                    'tsUpdated':'2026-11-09T00:00:00Z','humanQuestions':[{'id':'q1','options':[{'id':'yes'},{'id':'no'}]}]}
        self.request = {'requestId':'synthetic-request-1','action':'answer','originalTaskId':'original-1','targetTaskId':'ask-1',
                        'expectedRevision':native_revision(self.ask),'decision':'Synthetic conditional response, not send approval.'}

    def intent(self):
        return prepare(self.request,self.actor,self.original,self.ask)

    def audit(self,intent,state='done'):
        return {'actionId':'native-audit-1','actionVerb':intent.action,'qitemId':intent.target_id,
                'actorSession':intent.actor,'identityProvenance':'transport:v1',
                'reason':intent.decision,
                'auditNotes':intent.native_preview()['auditNotes'],
                'afterState':{'qitemId':intent.target_id,'state':state,'blockedOn':None,
                              'destinationSession':intent.owner if intent.action=='resolve' else intent.actor}}

    def reply(self,intent):
        return {'qitemId':'native-reply-1','replyTo':intent.target_id,'sourceSession':intent.actor,
                'destinationSession':intent.owner,'tags':TAGS+['human-answer']}

    def test_repeat_delivery_has_stable_keys_and_does_not_enable_execution(self):
        first,second=self.intent(),self.intent()
        self.assertEqual(first,second)
        self.assertFalse(first.execution_enabled)
        self.assertNotIn('actorSession',first.native_preview())
        self.assertNotIn(self.request['decision'],repr(first))

    def test_duplicate_receipt_is_read_only_and_same_original_survives_refresh(self):
        intent=self.intent();audit=self.audit(intent);reply=self.reply(intent)
        resumed={**self.original,'state':'in-progress','blockedOn':None,'tsUpdated':'2026-11-09T00:01:00Z'}
        first=reconcile(intent,self.actor,resumed,audit,reply)
        self.assertEqual(first,reconcile(intent,self.actor,copy.deepcopy(resumed),copy.deepcopy(audit),copy.deepcopy(reply)))
        self.assertEqual(first['originalTaskId'],'original-1')
        self.assertTrue(first['nativeReadyToContinue'])
        self.assertFalse(first['ownerActionObserved'])
        self.assertFalse(first['retryAllowed'])

    def test_same_request_identity_with_changed_content_conflicts(self):
        original=self.intent()
        changed=prepare({**self.request,'decision':'A different decision'},self.actor,self.original,self.ask)
        self.assertEqual(original.request_key,changed.request_key)
        self.assertNotEqual(original.content_digest,changed.content_digest)
        with self.assertRaisesRegex(ContractError,'request_identity_conflict'):
            reconcile(changed,self.actor,self.original,self.audit(original),self.reply(original))

    def test_stale_native_revision_is_rejected(self):
        with self.assertRaisesRegex(ContractError,'stale_native_revision'):
            prepare(self.request,self.actor,self.original,{**self.ask,'tsUpdated':'2026-11-10T00:00:00Z'})

    def test_invalid_and_already_answered_options_are_rejected(self):
        for option in ('unknown','yes'):
            target=copy.deepcopy(self.ask)
            if option=='yes':target['humanAnswers']={'q1':'yes'}
            req={**self.request,'decision':'','questionId':'q1','optionId':option,'expectedRevision':native_revision(target)}
            with self.assertRaisesRegex(ContractError,'invalid_or_answered_option'):
                prepare(req,self.actor,self.original,target)

    def test_empty_mixed_control_and_oversize_answers_are_rejected(self):
        for patch in ({'decision':' '},{'decision':'x','questionId':'q1','optionId':'yes'},
                      {'decision':'x\x00'},{'decision':'x'*4001},{'decision':'','questionId':'q1'}):
            with self.assertRaises(ContractError):prepare({**self.request,**patch},self.actor,self.original,self.ask)

    def test_arbitrary_message_actor_destination_and_authority_fields_are_rejected(self):
        for patch in ({'action':'send'},{'action':'clarify'},{'destinationSession':'operator-agent@kernel'},
                      {'actorSession':self.actor.person},{'authority':'primary-user'},{'hostId':'other'}):
            with self.assertRaises(ContractError):prepare({**self.request,**patch},self.actor,self.original,self.ask)

    def test_role_project_object_person_and_source_scope_cannot_be_bypassed(self):
        for actor in (replace(self.actor,role='viewer'),replace(self.actor,project='other'),
                      replace(self.actor,allowed_original_ids=frozenset()),replace(self.actor,person='operator-human@kernel')):
            with self.assertRaises(ContractError):prepare(self.request,actor,self.original,self.ask)
        with self.assertRaises(ContractError):prepare(self.request,self.actor,self.original,{**self.ask,'tags':['project:other']})

    def test_ask_owner_and_original_parent_link_are_required(self):
        for target in ({**self.ask,'sourceSession':'campaign-operator@opentour-rig'},
                       {**self.ask,'destinationSession':'someone-else@external'}, {**self.ask,'humanIntent':'update'}):
            req={**self.request,'expectedRevision':native_revision(target)}
            with self.assertRaisesRegex(ContractError,'not_own_pending_ask'):prepare(req,self.actor,self.original,target)

    def test_resolve_observes_same_original_nonterminal_state_without_claiming_owner_work(self):
        parked={**self.original,'blockedOn':self.actor.person}
        req={**self.request,'action':'resolve','targetTaskId':'original-1','expectedRevision':native_revision(parked)}
        intent=prepare(req,self.actor,parked,parked)
        current={**parked,'state':'in-progress','blockedOn':None}
        result=reconcile(intent,self.actor,current,self.audit(intent,'in-progress'))
        self.assertEqual(result['status'],'decision_recorded')
        self.assertEqual(result['originalTaskId'],'original-1')
        self.assertFalse(result['ownerActionObserved'])
        other={**parked,'blockedOn':'external:any-gate'}
        with self.assertRaisesRegex(ContractError,'not_own_human_park'):
            prepare({**req,'expectedRevision':native_revision(other)},self.actor,other,other)

    def test_partial_unknown_and_missing_return_are_not_resume_success(self):
        intent=self.intent()
        self.assertEqual(reconcile(intent,self.actor,self.original)['status'],'unconfirmed')
        self.assertEqual(reconcile(intent,self.actor,self.original,self.audit(intent,'pending'))['status'],'partial_answer_recorded')
        self.assertEqual(reconcile(intent,self.actor,self.original,self.audit(intent))['status'],'answer_return_unconfirmed')

    def test_correlation_note_cannot_replace_the_original_committed_decision(self):
        intent=self.intent()
        audit={**self.audit(intent),'reason':'A prior committed answer'}
        result=reconcile(intent,self.actor,self.original,audit,self.reply(intent))
        self.assertEqual(result['status'],'decision_content_unconfirmed')
        self.assertFalse(result['nativeReadyToContinue'])

    def test_choice_confirmation_needs_the_native_answer_value(self):
        req={**self.request,'decision':'','questionId':'q1','optionId':'yes'}
        intent=prepare(req,self.actor,self.original,self.ask)
        audit=self.audit(intent,'pending')
        self.assertEqual(reconcile(intent,self.actor,self.original,audit)['status'],'decision_content_unconfirmed')
        observed={**self.ask,'humanAnswers':{'q1':'yes'}}
        self.assertEqual(reconcile(intent,self.actor,self.original,audit,target=observed)['status'],'partial_answer_recorded')

    def test_spoofed_receipt_reply_and_changed_binding_fail_closed(self):
        intent=self.intent()
        for patch in ({'actorSession':'other@external'},{'identityProvenance':'claimed:v1'},{'qitemId':'other-task'}):
            with self.assertRaises(ContractError):reconcile(intent,self.actor,self.original,{**self.audit(intent),**patch})
        with self.assertRaisesRegex(ContractError,'reply_link_mismatch'):
            reconcile(intent,self.actor,self.original,self.audit(intent),{**self.reply(intent),'replyTo':'wrong-task'})
        with self.assertRaisesRegex(ContractError,'binding_or_custody_changed'):
            reconcile(intent,replace(self.actor,subject='another-subject'),self.original,self.audit(intent))

    def test_refresh_duplicates_stale_and_restart_require_no_action_replay(self):
        before={'epoch':'process-a','sequence':2,'version':digest('before')}
        self.assertEqual(refresh_policy(before,dict(before)),'unchanged')
        self.assertEqual(refresh_policy(before,{**before,'sequence':1}),'ignore_stale')
        self.assertEqual(refresh_policy(before,{**before,'sequence':3,'version':digest('after')}),'replace_snapshot')
        self.assertEqual(refresh_policy(before,{**before,'version':digest('conflict')}),'resync_required')
        restarted={**before,'epoch':'process-b','sequence':1}
        self.assertEqual(refresh_policy(before,restarted),'resync_required')
        self.assertEqual(refresh_policy(before,restarted,authoritative_reconnect=True),'replace_snapshot')
        with self.assertRaises(ContractError):refresh_policy(before,{**before,'sequence':True})
        with self.assertRaises(ContractError):refresh_policy(None,None)


class CurrentHTTPBoundaryTests(unittest.TestCase):
    def test_preparation_does_not_enable_native_action_or_arbitrary_message_routes(self):
        for role in ('user','administrator'):
            native=NativeFixture()
            native.snapshot=lambda: (_ for _ in ()).throw(AssertionError('No source read or write expected'))
            server=make_server(Service(CRMFixture(),native),Auth(grants=[{**GRANT,'role':role}]),0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                for path in ('/api/board/original-1/reply','/api/decisions','/api/messages'):
                    req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+path,
                        data=json.dumps({'actorSession':'synthetic-person@external','decision':'Synthetic only'}).encode(),
                        headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'},method='POST')
                    with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req,timeout=3)
                    self.assertEqual(error.exception.code,403)
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()

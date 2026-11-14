"""Synthetic client messaging/proposals; no CRM, daemon or actual agent invocation."""
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from dataclasses import replace
from backend.adapters import Failure
from backend.board_store import BoardStore
from backend.client_conversations import ClientControls
from backend.core import Auth, Principal, PROJECT
from backend.context_delivery import deliver_one, receive_context
from backend.server import make_server
from test_board_continuation import Delivery

REF={'entity':'Contact','externalId':'synthetic-client'}
OWNER='campaign-creative@opentour-rig'
OBLIGATION='qitem-synthetic-client-proposal'
USER=Principal('synthetic-user','user',(PROJECT,),True,True,False,(),False,('crm:Contact:synthetic-client',),True)


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=BoardStore(Path(self.tmp.name)/'data'/'board.sqlite3')
        self.controls=ClientControls(records=[{'clientRef':REF,'continuationRef':OBLIGATION}])
        self.transport=Delivery();self.transport.rows[OBLIGATION]={'qitemId':OBLIGATION,'destinationSession':OWNER,'state':'in-progress','tags':['project:opentour','mission:01-local-information-layer']}
        self.resolutions=[];self.client_reads=[]

    def resolve(self,ref,expected):
        self.resolutions.append((ref,expected))
        if self.transport.rows[ref]['destinationSession']!=expected:raise Failure('native_obligation_owner_changed',409)
        return expected

    def open(self,request='open-synthetic-001',content='Synthetic first brief',principal=USER,**extra):
        return self.store.open_client_conversation(principal,REF,{'requestId':request,'text':content,**extra},self.client_reads.append,self.controls,self.resolve)

    def fail(self,code,fn):
        with self.assertRaises(Failure) as caught:fn()
        self.assertEqual(caught.exception.code,code)

    def receive(self,task):
        msg=task['messages'][-1];delivery=msg['delivery']['id']
        self.assertEqual(deliver_one(self.store,self.transport,delivery),'delivered')
        return delivery,receive_context(self.store,delivery,OWNER)

    def reply(self,delivery,request='reply-synthetic-001',base=0,content='Synthetic itinerary. Price/availability/terms UNKNOWN.',**extra):
        return self.store.agent_reply(delivery,OWNER,{'requestId':request,'text':'Synthetic useful reply','proposal':{'baseRevision':base,'title':'Synthetic draft','body':content},**extra},self.transport)

    def test_granted_user_opens_same_context_replays_and_preserves_actor_recipient(self):
        task=self.open();self.assertEqual(self.open()['id'],task['id'])
        self.assertEqual(len(task['messages']),1);self.assertEqual(task['clientRef'],REF)
        self.assertEqual(task['messages'][0]['author'],USER.subject)
        self.assertEqual(task['conversation']['recipient'],OWNER)
        self.assertEqual(self.resolutions,[(OBLIGATION,OWNER)])
        self.assertEqual(self.open('open-synthetic-002','Synthetic second brief')['id'],task['id'])
        self.assertEqual(len(self.store.detail(USER,task['id'])['messages']),2)
        self.fail('request_content_conflict',lambda:self.open(content='changed'))

    def test_no_implicit_user_grant_and_no_browser_routing_or_author_fields(self):
        self.fail('client_conversation_forbidden',lambda:self.open(principal=replace(USER,conversation_clients=())))
        self.fail('client_conversation_forbidden',lambda:self.open(principal=replace(USER,board_respond=False)))
        for field in ('author','recipient','destinationSession','host','command','continuationRef','project','clientRef'):
            self.fail('invalid_board_fields',lambda:self.open(**{field:'forged'}))
        self.assertEqual(self.client_reads,[])

    def test_unavailable_or_changed_control_does_not_create_context(self):
        self.controls.records=[]
        self.fail('client_conversation_control_unavailable',self.open)
        self.assertEqual(self.store.list(USER)['items'],[])
        self.controls.records=[{'clientRef':REF,'continuationRef':OBLIGATION}]
        self.transport.rows[OBLIGATION]['destinationSession']='operator-agent@kernel'
        self.fail('native_obligation_owner_changed',self.open)
        self.assertEqual(self.store.list(USER)['items'],[])

    def test_agent_reply_has_no_echo_and_second_round_revises_same_draft(self):
        task=self.open();delivery,context=self.receive(task)
        self.assertEqual(context['conversationMode'],'client');self.assertEqual(context['clientRef'],REF)
        returned=self.reply(delivery);self.assertTrue(self.reply(delivery)['replayed'])
        task=self.store.detail(USER,task['id']);self.assertEqual(len(task['messages']),2)
        self.assertEqual(task['messages'][1]['author'],OWNER);self.assertEqual(task['proposal']['revision'],1)
        self.assertEqual(task['proposal']['source_message'],returned['messageId'])
        self.assertEqual(task['messages'][1]['delivery']['state'],'not_applicable')
        edit={'requestId':'edit-synthetic-001','baseRevision':1,'title':'Edited draft','body':'Synthetic user edit. UNKNOWN supplier terms.'}
        self.store.save_proposal(USER,task['id'],edit)
        self.assertEqual(self.store.save_proposal(USER,task['id'],edit)['revision'],2)
        message=self.store.append(USER,task['id'],{'requestId':'clarify-synthetic-001','kind':'comment','text':'Add an eight-year-old; shorten to two days.'},resolve_obligation=self.resolve)
        delivery=message['delivery']['id'];deliver_one(self.store,self.transport,delivery)
        context=receive_context(self.store,delivery,OWNER)
        self.assertEqual(context['proposal']['revision'],2);self.assertEqual(context['currentProposal']['body'],edit['body'])
        self.reply(delivery,'reply-synthetic-002',2,'Synthetic revised two-day itinerary with child. Supplier price UNKNOWN.')
        restarted=BoardStore(self.store.path);final=restarted.detail(USER,task['id'])
        self.assertEqual(final['proposal']['revision'],3);self.assertEqual(final['proposal']['base_revision'],2)
        self.assertEqual(len(final['messages']),4);self.assertEqual(len(final['proposalHistory']),3)
        with restarted.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0],2)
        self.assertEqual(self.transport.sends,2)

    def test_foreign_task_grant_revocation_and_edit_permission(self):
        task=self.open();delivery,_=self.receive(task);self.reply(delivery)
        self.fail('board_task_not_found',lambda:self.store.detail(replace(USER,conversation_clients=()),task['id']))
        self.assertEqual(self.store.list(replace(USER,conversation_clients=()))['items'],[])
        self.assertEqual(self.store.related(USER,REF)['items'][0]['id'],task['id'])
        edit={'requestId':'edit-synthetic-001','baseRevision':1,'title':'Title','body':'Body'}
        self.fail('client_conversation_forbidden',lambda:self.store.save_proposal(replace(USER,proposal_edit=False),task['id'],edit))
        self.fail('board_access_forbidden',lambda:self.store.save_proposal(replace(USER,projects=('other',)),task['id'],edit))

    def test_agent_cannot_forge_scope_or_write_before_receipt(self):
        task=self.open();delivery=task['messages'][0]['delivery']['id']
        body={'requestId':'agent-synthetic-001','text':'Synthetic clarification question'}
        self.fail('agent_context_forbidden',lambda:self.store.agent_reply(delivery,OWNER,body,self.transport))
        self.receive(task)
        self.fail('agent_context_forbidden',lambda:self.store.agent_reply(delivery,'operator-agent@kernel',body,self.transport))
        self.fail('invalid_board_fields',lambda:self.store.agent_reply(delivery,OWNER,{**body,'author':'human'},self.transport))
        self.store.agent_reply(delivery,OWNER,body,self.transport)
        self.fail('request_content_conflict',lambda:self.store.agent_reply(delivery,OWNER,{**body,'text':'changed'},self.transport))
        self.fail('agent_reply_already_saved',lambda:self.store.agent_reply(delivery,OWNER,{**body,'requestId':'new-agent-synthetic-key'},self.transport))

    def test_stale_agent_proposal_rolls_back_reply_without_losing_human_edit(self):
        task=self.open();delivery,_=self.receive(task);self.reply(delivery)
        message=self.store.append(USER,task['id'],{'requestId':'second-synthetic-001','kind':'comment','text':'Second clarification'},resolve_obligation=self.resolve)
        second=message['delivery']['id'];deliver_one(self.store,self.transport,second);receive_context(self.store,second,OWNER)
        self.store.save_proposal(USER,task['id'],{'requestId':'human-synthetic-001','baseRevision':1,'title':'Human edit','body':'Keep this human edit.'})
        self.fail('proposal_revision_conflict',lambda:self.reply(second,'second-reply-synthetic',1))
        detail=self.store.detail(USER,task['id']);self.assertEqual(len(detail['messages']),3)
        self.assertEqual(detail['proposal']['body'],'Keep this human edit.')
        self.reply(second,'second-reply-synthetic',2)
        self.assertEqual(self.store.detail(USER,task['id'])['proposal']['revision'],3)

    def test_proposal_unknown_retry_returns_its_revision_after_later_changes(self):
        task=self.open();delivery,_=self.receive(task);self.reply(delivery)
        edit={'requestId':'edit-synthetic-001','baseRevision':1,'title':'Edited','body':'Version2'}
        self.store.save_proposal(USER,task['id'],edit)
        self.store.save_proposal(USER,task['id'],{**edit,'requestId':'edit-synthetic-002','baseRevision':2,'body':'Version3'})
        self.assertEqual(self.store.save_proposal(USER,task['id'],edit)['revision'],2)
        self.fail('proposal_revision_conflict',lambda:self.store.save_proposal(USER,task['id'],{**edit,'requestId':'new-stale-synthetic'}))

    def test_insufficient_input_can_return_question_without_invented_proposal(self):
        task=self.open();delivery,_=self.receive(task)
        self.store.agent_reply(delivery,OWNER,{'requestId':'clarify-agent-001','text':'Which destination and dates? No proposal yet.'},self.transport)
        detail=self.store.detail(USER,task['id'])
        self.assertIsNone(detail['proposal']);self.assertEqual(len(detail['messages']),2)
        self.assertEqual(detail['messages'][1]['reply_to'],task['messages'][0]['id'])

    def test_schema5_pretraffic_rollback_rejects_any_new_data_or_old_receipt_change(self):
        from tools.local_board_release import backup_database,restore_schema4_backup,ReleaseError
        with self.store.db() as db:
            db.execute('DROP TABLE proposal_revisions');db.execute('DROP TABLE client_conversations');db.execute('PRAGMA user_version=4')
        backup,_,_=backup_database(self.store.path,Path(self.tmp.name)/'backup')
        self.store=BoardStore(self.store.path)
        with self.assertRaisesRegex(ReleaseError,'services_must_be_stopped'):
            restore_schema4_backup(self.store.path,backup,False)
        restore_schema4_backup(self.store.path,backup,True)
        with sqlite3.connect(self.store.path) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],4)
        self.store=BoardStore(self.store.path);self.open()
        with self.assertRaisesRegex(ReleaseError,'new_schema_data'):
            restore_schema4_backup(self.store.path,backup,True)
        # Even a worker heartbeat with no conversation data forbids snapshot replacement.
        with self.store.db() as db:
            db.execute('DELETE FROM client_conversations')
        with self.assertRaisesRegex(ReleaseError,'database_changed_since_backup'):
            restore_schema4_backup(self.store.path,backup,True)

    def test_schema4_migration_preserves_messages_and_outbox(self):
        legacy=self.store.create(Principal('synthetic-admin','administrator',(PROJECT,),True,True,True,('*',)),{'requestId':'legacy-synthetic-001','title':'Legacy task','description':'Keep this legacy task','section':'tasks'})
        with self.store.db() as db:
            before={table:[tuple(row) for row in db.execute('SELECT * FROM '+table)] for table in ('tasks','messages','outbox')}
        # Remove only the new empty tables from a disposable DB to represent schema4.
        with self.store.db() as db:
            db.execute('DROP TABLE proposal_revisions');db.execute('DROP TABLE client_conversations');db.execute('PRAGMA user_version=4')
        store=BoardStore(self.store.path)
        with store.db() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],5)
            self.assertEqual(before,{table:[tuple(row) for row in db.execute('SELECT * FROM '+table)] for table in before})
        self.store=store;task=self.open();self.assertEqual(task['clientRef'],REF)


class ConversationHTTPTests(unittest.TestCase):
    setUp=ConversationTests.setUp
    resolve=ConversationTests.resolve
    receive=ConversationTests.receive
    reply=ConversationTests.reply
    # HTTP case gets the same wholly synthetic setup, without inheriting/repeating store cases.
    def test_scoped_http_open_proposal_auth_and_native_mutation_denial(self):
        token='synthetic-context-http-'+'x'*32
        grant={'subject':USER.subject,'role':'user','projects':[PROJECT],
            'tokenSha256':hashlib.sha256(token.encode()).hexdigest(),
            'board':{'read':True,'respond':True,'tasks':[]},
            'clientConversations':{'clients':['crm:Contact:synthetic-client'],'editProposal':True}}
        class Source:
            def client(_self,ref):
                if ref!='crm:Contact:synthetic-client':raise AssertionError('foreign_source_read')
                return {'id':ref,'provenance':{'entity':'Contact','externalId':'synthetic-client'}}
        class Obligations:
            def resolve(_self,ref,expected=None):return self.resolve(ref,expected)
        server=make_server(Source(),Auth(grants=[grant]),0,board_store=self.store,client_controls=self.controls,obligations=Obligations())
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(path,body=None,bearer=True):
            headers={'Authorization':'Bearer '+token} if bearer else {}
            if body is not None:headers['Content-Type']='application/json'
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
            conn.request('POST' if body is not None else 'GET',path,json.dumps(body).encode() if body is not None else None,headers)
            response=conn.getresponse();raw=response.read();result=(response.status,json.loads(raw) if raw else None);conn.close();return result
        try:
            path='/api/clients/crm:Contact:synthetic-client/conversation'
            self.assertEqual(request(path,{'requestId':'http-context-001','text':'Synthetic first brief'},False)[0],401)
            status,task=request(path,{'requestId':'http-context-001','text':'Synthetic first brief'});self.assertEqual(status,200)
            self.assertEqual(request('/api/board-tasks/'+task['id'])[0],200)
            self.assertEqual(request('/api/board-tasks/task_foreign')[0],404)
            delivery,_=self.receive(task);self.reply(delivery)
            status,proposal=request('/api/board-tasks/'+task['id']+'/proposal',{'requestId':'http-proposal-001','baseRevision':1,'title':'Edited','body':'Synthetic edit'})
            self.assertEqual(status,200);self.assertEqual(proposal['author'],USER.subject)
            self.assertEqual(request('/api/board-tasks/'+task['id']+'/proposal',{'requestId':'http-forged-001','baseRevision':2,'title':'x','body':'x','author':OWNER})[0],400)
            self.assertEqual(request('/api/board/reply',{'decision':'forged'})[0],403)
            grant['clientConversations']['clients']=[]
            self.assertEqual(request('/api/board-tasks/'+task['id'])[0],404)
        finally:server.shutdown();server.server_close();thread.join()

"""Synthetic continuation receipts and operational worker safety; no real queue/CRM."""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from backend.adapters import Failure, NativeObligation
from backend.board_store import BoardStore
from backend.context_delivery import (NativeContext, SERVICE_SOURCE, SOURCE, Rejected, deliver_one,
    receive_context, report_context, serve_worker, delivery_status)
from test_board_conversations import ADMIN, USER, SyntheticTransport


class Delivery(SyntheticTransport):
    source=SERVICE_SOURCE
    def validate_destination(self,row,continued=False):
        class Client:
            def get(_self,path):return self.lookup(path.rsplit('/',1)[-1])
        def seat(destination):return {'canonicalSessionName':destination,'rigName':destination.rsplit('@',1)[1],'logicalId':'synthetic.agent','lifecycleState':'running','runtime':'codex'}
        return NativeObligation(Client(),seat).resolve(row['routing_ref'],row['destination'],('in-progress','done') if continued else ('pending','in-progress','blocked'))
    def send(self,row):
        self.sends+=1
        item={'qitemId':row['native_id'],'destinationSession':row['destination'],'sourceSession':self.source,
            'body':row['native_body'],'tags':['project:opentour','type:opentour-task-context','delivery:'+row['id']]}
        self.rows[row['native_id']]=item
        if self.mode=='after':raise TimeoutError('synthetic response loss')
        return item


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='opentour-continuation-synthetic-');self.addCleanup(self.tmp.cleanup)
        self.store=BoardStore(Path(self.tmp.name)/'data'/'board.sqlite3')
        self.task=self.store.create(ADMIN,{'requestId':'create-v012-0001','title':'Synthetic work',
            'description':'Synthetic only','section':'clients','requestText':'Which synthetic choice?',
            'continuationRef':'qitem-synthetic-original'},resolve_obligation=lambda ref,expected=None:'campaign-creative@opentour-rig')
        self.request=self.task['messages'][0]
        self.transport=Delivery()
        self.session='campaign-creative@opentour-rig'
        self.transport.rows['qitem-synthetic-original']={'qitemId':'qitem-synthetic-original','destinationSession':self.session,'state':'in-progress','tags':['project:opentour','mission:01-local-information-layer']}

    def answer(self,request_id='answer-v012-0001',**extra):
        return self.store.append(USER,self.task['id'],{'requestId':request_id,'kind':'answer',
            'replyTo':self.request['id'],'replyVersion':self.request['version'],'text':'Synthetic choice B',**extra},resolve_obligation=lambda ref,expected=None:'campaign-creative@opentour-rig')

    def delivered(self):
        answer=self.answer();outbox=answer['delivery']['id']
        self.assertEqual(deliver_one(self.store,self.transport,outbox),'delivered')
        return outbox

    def report(self,outbox,state,reason='Synthetic assessment',**extra):
        return report_context(self.store,outbox,self.session,state,reason,transport=self.transport,**extra)

    def failure(self,code,fn):
        with self.assertRaises(Failure) as caught:fn()
        self.assertEqual(caught.exception.code,code)

    def test_version_actor_link_and_double_submit_are_server_authored(self):
        self.failure('answer_request_version_conflict',lambda:self.answer(replyVersion='stale'))
        answer=self.answer();self.assertEqual(self.answer()['messageId'],answer['messageId'])
        self.assertEqual(answer['author'],USER.subject)
        with self.store.db() as db:
            context=json.loads(db.execute('SELECT payload FROM outbox WHERE message_id=?',(answer['messageId'],)).fetchone()[0])
            self.assertEqual(db.execute('SELECT count(*) FROM messages').fetchone()[0],2)
        self.assertEqual(context['requestVersion'],self.request['version'])
        self.assertEqual(context['author'],USER.subject)
        self.assertEqual(context['continuationRef'],'qitem-synthetic-original')
        self.failure('invalid_board_fields',lambda:self.answer(author='invented-human'))

    def test_receipt_acceptance_continuation_are_distinct_persistent_and_idempotent(self):
        outbox=self.delivered()
        self.failure('agent_context_forbidden',lambda:self.report(outbox,'accepted'))
        receive_context(self.store,outbox,self.session)
        self.report(outbox,'accepted')
        self.assertEqual(self.store.detail(USER,self.task['id'])['requestState'],'accepted')
        result=self.report(outbox,'continued',result='Prepared a synthetic choice B itinerary.',evidence='qitem-synthetic-original')
        self.assertFalse(result['replayed'])
        self.store=BoardStore(self.store.path)
        self.assertTrue(self.report(outbox,'continued',result='Prepared a synthetic choice B itinerary.',evidence='qitem-synthetic-original')['replayed'])
        context=receive_context(self.store,outbox,self.session)
        self.assertEqual(context['processing'],'continued')
        detail=self.store.detail(USER,self.task['id']);delivery=detail['messages'][-1]['delivery']
        self.assertEqual(detail['requestState'],'continued')
        self.assertTrue(all(delivery['timestamps'].values()))
        self.assertEqual(self.store.list(USER)['items'][0]['requestState'],'continued')
        self.failure('processing_receipt_conflict',lambda:self.report(outbox,'continued',result='Changed result',evidence='qitem-synthetic-original'))
        self.assertEqual(self.transport.sends,1)

    def test_comment_does_not_close_request_and_insufficient_answer_stays_open(self):
        self.store.append(USER,self.task['id'],{'requestId':'comment-v012-001','kind':'comment','text':'Synthetic aside'},resolve_obligation=lambda ref,expected=None:'campaign-creative@opentour-rig')
        self.assertEqual(self.store.detail(USER,self.task['id'])['requestState'],'awaiting_answer')
        outbox=self.delivered();receive_context(self.store,outbox,self.session)
        self.report(outbox,'needs_clarification',reason='Need the synthetic date.')
        self.assertEqual(self.store.detail(USER,self.task['id'])['requestState'],'needs_clarification')
        self.failure('processing_transition_forbidden',lambda:self.report(outbox,'continued',result='ACK only',evidence='qitem-synthetic-original'))

    def test_recipient_original_obligation_and_evidence_are_scoped(self):
        outbox=self.delivered()
        self.failure('agent_context_forbidden',lambda:receive_context(self.store,outbox,SOURCE))
        receive_context(self.store,outbox,self.session)
        self.transport.rows['qitem-synthetic-original']['destinationSession']='arbitrary@kernel'
        self.failure('original_obligation_not_owned',lambda:self.report(outbox,'accepted'))
        self.transport.rows['qitem-synthetic-original']['destinationSession']=self.session
        self.report(outbox,'accepted')
        self.failure('continuation_evidence_must_reference_original',lambda:self.report(outbox,'continued',result='Synthetic work',evidence='qitem-other'))
        self.failure('invalid_board_text',lambda:self.report(outbox,'continued',evidence='qitem-synthetic-original'))

    def test_two_answers_cannot_both_be_accepted(self):
        first=self.answer();second=self.answer('answer-v012-0002')
        ids=[a['delivery']['id'] for a in (first,second)]
        for outbox in ids:
            deliver_one(self.store,self.transport,outbox);receive_context(self.store,outbox,self.session)
        self.report(ids[0],'accepted')
        self.failure('answer_request_already_accepted',lambda:self.report(ids[1],'accepted'))
        self.failure('answer_request_already_accepted',lambda:self.answer('answer-v012-0003'))
        self.assertEqual(self.answer()['messageId'],first['messageId'])

    def test_unknown_send_reconciles_exact_sender_without_duplicate(self):
        outbox=self.answer()['delivery']['id'];self.transport.mode='after'
        self.assertEqual(deliver_one(self.store,self.transport,outbox),'unknown')
        self.store=BoardStore(self.store.path)
        self.assertEqual(deliver_one(self.store,self.transport,outbox),'delivered')
        self.assertEqual(self.transport.sends,1)
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT sender FROM outbox WHERE id=?',(outbox,)).fetchone()[0],SERVICE_SOURCE)

    def test_lookup_failure_before_send_remains_retryable_pending(self):
        outbox=self.answer()['delivery']['id'];lookup=self.transport.lookup
        self.transport.lookup=lambda _: (_ for _ in ()).throw(TimeoutError('synthetic lookup failure'))
        self.assertEqual(deliver_one(self.store,self.transport,outbox),'pending')
        self.assertEqual(self.transport.sends,0)
        self.transport.lookup=lookup
        self.assertEqual(deliver_one(self.store,self.transport,outbox),'delivered')
        self.assertEqual(self.transport.sends,1)

    def test_service_sender_is_explicit_and_refuses_any_seat_context(self):
        for name in ('OPENRIG_SESSION_NAME','OPENRIG_NODE_ID','OPENRIG_NODE'):
            with patch.dict(os.environ,{name:'synthetic-seat'}):
                with self.assertRaises(Rejected):NativeContext(self.store.path,service=True)
        with patch.dict(os.environ,{},clear=True):
            transport=NativeContext(self.store.path,service=True)
            self.assertEqual(transport.source,SERVICE_SOURCE)
            self.assertNotIn('X-OpenRig-Session',transport.client.headers)

    def test_operational_loop_drains_without_manual_calls_and_records_backlog(self):
        self.answer();stop=threading.Event();sent=threading.Event()
        original_send=self.transport.send
        def send(row):
            result=original_send(row);sent.set();return result
        self.transport.send=send
        thread=threading.Thread(target=serve_worker,args=(self.store,self.transport),kwargs={'interval':0.1,'stop':stop})
        thread.start()
        try:self.assertTrue(sent.wait(5))
        finally:stop.set();thread.join(5)
        status=delivery_status(self.store)
        self.assertIsNotNone(status['worker']['heartbeat'])
        self.assertEqual(status['backlog'].get('pending',0),0)
        self.assertEqual(status['backlog']['delivered'],2)

    def test_accepted_comment_cannot_continue_or_close_original_request(self):
        comment=self.store.append(USER,self.task['id'],{'requestId':'comment-v012-002','kind':'comment','text':'Synthetic aside'},resolve_obligation=lambda ref,expected=None:'campaign-creative@opentour-rig')
        outbox=comment['delivery']['id'];deliver_one(self.store,self.transport,outbox);receive_context(self.store,outbox,self.session)
        self.report(outbox,'accepted')
        self.failure('only_answer_can_continue_request',lambda:self.report(outbox,'continued',result='Only a comment',evidence='qitem-synthetic-original'))
        self.assertEqual(self.store.detail(USER,self.task['id'])['requestState'],'awaiting_answer')

    def test_changed_original_request_version_refuses_acceptance(self):
        outbox=self.delivered();receive_context(self.store,outbox,self.session)
        with self.store.db() as db:db.execute('UPDATE messages SET body=? WHERE id=?',('Synthetic changed request',self.request['id']))
        self.failure('answer_request_version_conflict',lambda:self.report(outbox,'accepted'))

    def test_service_wire_body_has_declared_actor_without_seat_header(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from backend.adapters import JsonGET
        captured=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                captured.append((body,self.headers.get('X-OpenRig-Session')))
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps({**body,'identityProvenance':'claimed:v1'}).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch.dict(os.environ,{},clear=True):transport=NativeContext(self.store.path,service=True)
            transport.client=JsonGET('http://127.0.0.1:'+str(server.server_port),{})
            result=transport.send({'native_id':'qitem-synthetic-service','destination':self.session,'payload':'{}','id':'context_synthetic','native_body':'Synthetic only'})
            self.assertEqual(result['sourceSession'],SERVICE_SOURCE)
            self.assertIsNone(captured[0][1]);self.assertEqual(captured[0][0]['sourceSession'],SERVICE_SOURCE)
        finally:server.shutdown();server.server_close();thread.join()

    def test_recipient_reconciles_unknown_receipt_without_sending(self):
        outbox=self.answer()['delivery']['id'];self.transport.mode='after'
        self.assertEqual(deliver_one(self.store,self.transport,outbox),'unknown')
        context=receive_context(self.store,outbox,self.session,self.transport)
        self.assertEqual(context['processing'],'received');self.assertEqual(self.transport.sends,1)

    def test_accept_replay_after_original_completed_does_not_repeat_decision(self):
        outbox=self.delivered();receive_context(self.store,outbox,self.session);self.report(outbox,'accepted')
        self.transport.rows['qitem-synthetic-original']['state']='done'
        self.report(outbox,'continued',result='Synthetic work completed.',evidence='qitem-synthetic-original')
        self.assertTrue(self.report(outbox,'accepted')['replayed'])

    def test_foreign_project_original_is_not_an_authorized_continuation(self):
        outbox=self.delivered();receive_context(self.store,outbox,self.session)
        self.transport.rows['qitem-synthetic-original']['tags']=['project:other']
        self.failure('original_obligation_not_owned',lambda:self.report(outbox,'accepted'))

    def test_unknown_reconciliation_backs_off_bounded_without_second_send(self):
        # Complete unrelated seed delivery so only the ambiguous answer is retried.
        deliver_one(self.store,Delivery(),self.request['delivery']['id'])
        outbox=self.answer()['delivery']['id'];self.transport.mode='after'
        self.assertEqual(deliver_one(self.store,self.transport,outbox),'unknown')
        class CapturedWait:
            def __init__(self):self.delays=[]
            def is_set(self):return len(self.delays)>=7
            def wait(self,delay):self.delays.append(delay)
        for unavailable in (True,False):
            with self.subTest(lookup_raises=unavailable):
                def lookup(_):
                    if unavailable:raise TimeoutError('synthetic reconciliation outage')
                    return None  # Absence after unknown never permits replay either.
                self.transport.lookup=lookup
                stop=CapturedWait()
                serve_worker(self.store,self.transport,interval=2,stop=stop)
                self.assertEqual(stop.delays,[4,8,16,32,60,60,60])
                self.assertEqual(self.transport.sends,1)
                self.assertEqual(delivery_status(self.store)['backlog'].get('unknown'),1)


class BoardOnlyHTTPTests(unittest.TestCase):
    def test_board_only_exact_scope_never_reaches_configured_sources(self):
        import hashlib
        import urllib.error
        import urllib.request
        from backend.core import Auth
        from backend.server import make_server
        with tempfile.TemporaryDirectory(prefix='opentour-board-only-') as tmp:
            store=BoardStore(Path(tmp)/'data'/'board.sqlite3')
            task=store.create(ADMIN,{'requestId':'board-only-create','title':'Synthetic allowed','description':'Synthetic only','section':'tasks'})
            other=store.create(ADMIN,{'requestId':'board-only-other','title':'Synthetic forbidden','description':'Synthetic only','section':'tasks'})
            token='synthetic-board-only-token-'+'x'*24
            grant={'subject':'synthetic-board-only','role':'user','projects':['opentour'],'boardOnly':True,
                'tokenSha256':hashlib.sha256(token.encode()).hexdigest(),'board':{'read':True,'respond':True,'tasks':[task['id']]}}
            class NoSources:
                def __getattr__(self,_):raise AssertionError('source_must_not_be_reached')
            server=make_server(NoSources(),Auth(grants=[grant]),0,board_store=store)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(path):
                req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+path,headers={'Authorization':'Bearer '+token})
                try:
                    with urllib.request.urlopen(req) as response:return response.status,json.load(response)
                except urllib.error.HTTPError as error:return error.code,json.load(error)
            try:
                self.assertFalse(request('/api/capabilities')[1]['sourceReads'])
                self.assertEqual(len(request('/api/board-tasks')[1]['items']),1)
                self.assertEqual(request('/api/board-tasks/'+other['id'])[0],404)
                for path in ('/api/clients','/api/clients/crm:Contact:synthetic','/api/board','/api/campaigns'):
                    status,data=request(path);self.assertEqual(status,403);self.assertEqual(data['error'],'board_only_source_access_forbidden')
                grant['board']['tasks']=['*']
                self.assertEqual(request('/api/board-tasks')[0],403)
            finally:server.shutdown();server.server_close();thread.join()

    def test_explicit_https_prefix_preserves_local_root_and_rejects_foreign_origin(self):
        import urllib.request
        import urllib.error
        from backend.core import Auth
        from backend.server import make_server
        server=make_server(object(),Auth(grants=[]),0,public_base_url='https://board.example.invalid/opentour')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base='http://127.0.0.1:'+str(server.server_port)
            for path in ('/','/opentour/'):
                with urllib.request.urlopen(base+path) as response:
                    html=response.read().decode()
                    self.assertIn('content="/opentour"',html)
                    self.assertIn('src="/opentour/ui/app.js"',html)
            with urllib.request.urlopen(base+'/opentour/ui/styles.css') as response:
                self.assertIn("'/opentour/ui/atlas.css'",response.read().decode())
            for origin,expected in [('https://board.example.invalid',200),('https://foreign.invalid',403),('http://board.example.invalid',403)]:
                req=urllib.request.Request(base+'/opentour/healthz',headers={'Host':'board.example.invalid','Origin':origin})
                try:
                    with urllib.request.urlopen(req) as response:status=response.status
                except urllib.error.HTTPError as error:status=error.code
                self.assertEqual(status,expected)
        finally:server.shutdown();server.server_close();thread.join()
        for bad in ('http://board.invalid/opentour','https://board.invalid/../bad','https://board.invalid/path?x=y'):
            with self.assertRaises(ValueError):make_server(object(),Auth(grants=[]),0,public_base_url=bad)

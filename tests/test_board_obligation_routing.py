"""Synthetic exact-obligation recipient binding; never reads/writes the real native queue."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from backend.adapters import Failure, NativeObligation
from backend.board_store import BoardStore, DESTINATIONS
from backend.context_delivery import deliver_one, receive_context, report_context
from test_board_conversations import ADMIN,USER
from test_board_continuation import Delivery

REF='qitem-synthetic-qa-system-original'
OWNER='platform-qa-system@opentour-rig'


class NativeFixture:
    def __init__(self):
        self.item={'qitemId':REF,'state':'in-progress','destinationSession':OWNER,
            'tags':['project:opentour','mission:01-local-information-layer']}
        self.calls=[];self.unavailable=False
    def get(self,path):
        self.calls.append(path)
        if self.unavailable:raise Failure('synthetic_lookup_unavailable',503)
        return copy.deepcopy(self.item)
    def seat(self,destination):
        if destination not in (OWNER,'platform-developer@opentour-rig','operator-agent@kernel'):return None
        return {'canonicalSessionName':destination,'rigName':destination.rsplit('@',1)[1],
            'logicalId':'platform.qa-system','lifecycleState':'running','runtime':'codex'}
    def resolver(self):return NativeObligation(self,self.seat)


class ObligationRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='opentour-routing-synthetic-');self.addCleanup(self.tmp.cleanup)
        self.store=BoardStore(Path(self.tmp.name)/'data'/'board.sqlite3')
        self.native=NativeFixture();self.lookup=self.native.resolver()
        self.body={'requestId':'routing-create-001','title':'Synthetic QA task','description':'Synthetic only',
            'requestText':'Choose the synthetic fixture option.','section':'tasks','continuationRef':REF}
    def create(self,**fields):return self.store.create(ADMIN,{**self.body,**fields},resolve_obligation=self.lookup.resolve)
    def answer(self,task,**fields):
        request=task['messages'][0]
        return self.store.append(USER,task['id'],{'requestId':'routing-answer-001','kind':'answer','text':'Synthetic option B',
            'replyTo':request['id'],'replyVersion':request['version'],**fields},resolve_obligation=self.lookup.resolve)
    def row(self,outbox):
        with self.store.db() as db:return dict(db.execute('SELECT * FROM outbox WHERE id=?',(outbox,)).fetchone())
    def counts(self):
        with self.store.db() as db:return tuple(db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('tasks','messages','outbox'))
    def fails(self,code,fn):
        with self.assertRaises(Failure) as caught:fn()
        self.assertEqual(caught.exception.code,code)

    def test_qa_system_owner_overrides_section_default_and_survives_restart(self):
        task=self.create();answer=self.answer(task)
        for message in (task['messages'][0],answer):
            row=self.row(message['delivery']['id']);self.assertEqual(row['destination'],OWNER);self.assertEqual(row['routing_ref'],REF)
        self.assertNotEqual(DESTINATIONS['tasks'],OWNER)
        self.store=BoardStore(self.store.path)
        before=len(self.native.calls)
        self.assertEqual(self.create()['id'],task['id'])
        self.assertEqual(self.answer(task)['messageId'],answer['messageId'])
        self.assertEqual(len(self.native.calls),before)
        self.assertEqual(self.counts(),(1,2,2))

    def test_forged_identity_foreign_project_mission_and_closed_reference_rejected(self):
        cases=[({'qitemId':'qitem-another'},'native_obligation_identity_mismatch'),
            ({'tags':['project:other','mission:01-local-information-layer']},'native_obligation_scope_mismatch'),
            ({'tags':['project:opentour','mission:other']},'native_obligation_scope_mismatch'),
            ({'tags':['project:opentour','project:other','mission:01-local-information-layer']},'native_obligation_scope_mismatch'),
            ({'state':'done'},'native_obligation_state_ineligible'),
            ({'state':'handed-off'},'native_obligation_state_ineligible'),
            ({'destinationSession':'user@external'},'native_obligation_destination_invalid'),
            ({'destinationSession':'invented-agent@opentour-rig'},'native_obligation_destination_invalid')]
        original=copy.deepcopy(self.native.item)
        for changes,code in cases:
            with self.subTest(changes=changes):
                self.native.item={**original,**changes};self.fails(code,self.create);self.assertEqual(self.counts(),(0,0,0))

    def test_no_caller_recipient_field_or_unvalidated_new_reference(self):
        for field in ('destination','destinationSession','assignedRecipient','session'):
            self.fails('invalid_board_fields',lambda:self.create(**{field:OWNER}))
        self.fails('native_obligation_lookup_required',lambda:self.store.create(ADMIN,self.body))
        self.assertEqual(self.counts(),(0,0,0))
        self.fails('invalid_continuation_reference',lambda:self.create(continuationRef='qitem-x/../foreign'))
        self.assertEqual(self.native.calls,[])

    def test_owner_change_and_closed_state_reject_new_answer_but_not_committed_replay(self):
        task=self.create()
        self.native.item['destinationSession']='platform-developer@opentour-rig'
        self.fails('native_obligation_owner_changed',lambda:self.answer(task));self.assertEqual(self.counts(),(1,1,1))
        self.native.item['destinationSession']=OWNER
        answer=self.answer(task)
        self.native.item['state']='done';before=len(self.native.calls)
        self.assertEqual(self.answer(task)['messageId'],answer['messageId'])
        self.assertEqual(len(self.native.calls),before)
        self.fails('native_obligation_state_ineligible',lambda:self.answer(task,requestId='routing-answer-002'))
        self.assertEqual(self.counts(),(1,2,2))

    def transport(self):
        transport=Delivery();transport.rows[REF]=copy.deepcopy(self.native.item)
        return transport

    def test_pending_delivery_revalidates_binding_before_send(self):
        task=self.create();outbox=task['messages'][0]['delivery']['id'];transport=self.transport()
        transport.rows[REF]['destinationSession']='platform-developer@opentour-rig'
        self.assertEqual(deliver_one(self.store,transport,outbox),'failed')
        self.assertEqual(transport.sends,0)
        self.assertEqual(self.row(outbox)['destination'],OWNER)

    def test_lookup_failure_preserves_pending_and_never_sends(self):
        task=self.create();outbox=task['messages'][0]['delivery']['id'];transport=self.transport()
        def unavailable(_row):raise Failure('synthetic_unavailable',503)
        transport.validate_destination=unavailable
        self.assertEqual(deliver_one(self.store,transport,outbox),'pending');self.assertEqual(transport.sends,0)

    def test_unknown_send_reconciles_pinned_recipient_after_owner_change_without_repost(self):
        task=self.create();answer=self.answer(task);outbox=answer['delivery']['id'];transport=self.transport();transport.mode='after'
        self.assertEqual(deliver_one(self.store,transport,outbox),'unknown');frozen=self.row(outbox)
        transport.rows[REF]['destinationSession']='platform-developer@opentour-rig'
        self.store=BoardStore(self.store.path)
        self.assertEqual(deliver_one(self.store,transport,outbox),'delivered')
        self.assertEqual(transport.sends,1)
        after=self.row(outbox)
        self.assertEqual((after['destination'],after['routing_ref'],after['native_body']),
                         (frozen['destination'],frozen['routing_ref'],frozen['native_body']))
        receive_context(self.store,outbox,OWNER)
        self.fails('original_obligation_not_owned',lambda:report_context(self.store,outbox,OWNER,'accepted','Synthetic assessment',transport=transport))

    def test_valid_owner_can_receive_accept_and_return_continuation(self):
        task=self.create();answer=self.answer(task);outbox=answer['delivery']['id'];transport=self.transport()
        self.assertEqual(deliver_one(self.store,transport,outbox),'delivered')
        self.fails('agent_context_forbidden',lambda:receive_context(self.store,outbox,DESTINATIONS['tasks']))
        receive_context(self.store,outbox,OWNER)
        report_context(self.store,outbox,OWNER,'accepted','Synthetic sufficient answer',transport=transport)
        transport.rows[REF]['state']='done'
        report_context(self.store,outbox,OWNER,'continued','Synthetic result produced',result='Synthetic scoped result.',evidence=REF,transport=transport)
        self.assertEqual(self.store.detail(USER,task['id'])['requestState'],'continued')
        self.assertEqual(transport.sends,1)

    def test_legacy_without_validated_binding_keeps_section_destination(self):
        task=self.store.create(ADMIN,{k:v for k,v in self.body.items() if k!='continuationRef'})
        row=self.row(task['messages'][0]['delivery']['id'])
        self.assertEqual(row['destination'],DESTINATIONS['tasks']);self.assertIsNone(row['routing_ref'])
        # Genuine schema3 rows are not backfilled into a guessed new recipient.
        with self.store.db() as db:
            db.execute('INSERT INTO task_execution(task_id,native_ref) VALUES(?,?)',(task['id'],REF))
            db.execute('ALTER TABLE task_execution DROP COLUMN destination')
            db.execute('ALTER TABLE outbox DROP COLUMN routing_ref')
            db.execute('PRAGMA user_version=3')
        self.store=BoardStore(self.store.path)
        request=self.store.detail(USER,task['id'])['messages'][0]
        answer=self.store.append(USER,task['id'],{'requestId':'legacy-answer-001','kind':'answer','replyTo':request['id'],'text':'Synthetic legacy answer'})
        self.assertEqual(self.row(answer['delivery']['id'])['destination'],DESTINATIONS['tasks'])
        self.assertIsNone(self.row(answer['delivery']['id'])['routing_ref'])

    def test_http_create_and_answer_derive_recipient_without_source_access(self):
        import hashlib,threading,urllib.request,urllib.error
        from backend.core import Auth
        from backend.server import make_server
        token='synthetic-routing-admin-'+'x'*32
        auth=Auth(grants=[{'subject':ADMIN.subject,'role':'administrator','projects':['opentour'],
            'tokenSha256':hashlib.sha256(token.encode()).hexdigest(),
            'board':{'read':True,'respond':True,'create':True,'tasks':['*']}}])
        server=make_server(object(),auth,0,board_store=self.store,obligations=self.lookup)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def post(path,body):
            req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+path,method='POST',data=json.dumps(body).encode(),
                headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as error:return error.code,json.load(error)
        try:
            status,task=post('/api/board-tasks',self.body);self.assertEqual(status,200)
            question=task['messages'][0]
            status,answer=post('/api/board-tasks/'+task['id']+'/messages',{'requestId':'http-routing-answer','kind':'answer',
                'text':'Synthetic choice B','replyTo':question['id'],'replyVersion':question['version']})
            self.assertEqual(status,200);self.assertEqual(self.row(answer['delivery']['id'])['destination'],OWNER)
            status,_=post('/api/board-tasks',{**self.body,'requestId':'forged-http-create','destinationSession':OWNER})
            self.assertEqual(status,400);self.assertEqual(self.counts(),(1,2,2))
            self.assertTrue(all(path=='/api/queue/'+REF for path in self.native.calls))
        finally:server.shutdown();server.server_close();thread.join()

    def test_registered_seat_read_uses_exact_projection_without_cleanup(self):
        import subprocess
        from unittest.mock import patch
        payload={'entries':[self.native.seat(OWNER)],'totalNodes':1,'truncated':False}
        with patch('backend.adapters.subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(payload).encode())) as call:
            self.assertEqual(NativeObligation._seat(OWNER)['canonicalSessionName'],OWNER)
        args=call.call_args.args[0]
        self.assertIn('--no-cleanup',args);self.assertEqual(args[args.index('--session')+1],OWNER)
        self.assertEqual(args[args.index('--rig')+1],'opentour-rig')
        self.assertEqual(args[args.index('--fields')+1],'canonicalSessionName,rigName,logicalId,lifecycleState,runtime')
        payload['truncated']=True
        with patch('backend.adapters.subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(payload).encode())):
            self.fails('native_obligation_destination_invalid',lambda:NativeObligation._seat(OWNER))

    def test_exact_native_get_wire_and_missing_reference_fail_closed(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        import threading
        from backend.adapters import JsonGET
        fixture=self.native;calls=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_GET(self):
                calls.append(('GET',self.path))
                exists=self.path=='/api/queue/'+REF
                self.send_response(200 if exists else 404);self.end_headers()
                self.wfile.write(json.dumps(fixture.item if exists else {'error':'qitem_not_found'}).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            lookup=NativeObligation(JsonGET('http://127.0.0.1:'+str(server.server_port)),self.native.seat)
            self.assertEqual(lookup.resolve(REF),OWNER)
            self.fails('native_obligation_not_found',lambda:lookup.resolve('qitem-missing'))
            self.assertEqual(calls,[('GET','/api/queue/'+REF),('GET','/api/queue/qitem-missing')])
        finally:server.shutdown();server.server_close();thread.join()

    def test_registered_identity_mismatch_or_human_runtime_is_rejected(self):
        seat=self.native.seat(OWNER)
        for changes in ({'canonicalSessionName':'platform-developer@opentour-rig'},{'runtime':'human'}, {'lifecycleState':'retired'}):
            with self.subTest(changes=changes):
                self.lookup.seat_lookup=lambda _: {**seat,**changes}
                self.fails('native_obligation_destination_invalid',self.create)
                self.assertEqual(self.counts(),(0,0,0))

    def test_new_destination_is_not_a_global_legacy_allowlist_expansion(self):
        task=self.store.create(ADMIN,{k:v for k,v in self.body.items() if k!='continuationRef'})
        outbox=task['messages'][0]['delivery']['id']
        with self.store.db() as db:db.execute('UPDATE outbox SET destination=? WHERE id=?',(OWNER,outbox))
        transport=self.transport()
        self.assertEqual(deliver_one(self.store,transport,outbox),'failed')
        self.assertEqual(transport.sends,0)

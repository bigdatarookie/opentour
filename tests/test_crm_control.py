"""Denied-by-default synthetic upstream; real Espo/ORM integration remains independent."""
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from backend.adapters import Failure
from backend.core import Auth,Principal
from backend.crm_control import CRMTitleControl,title_scope
from backend.server import make_server

ID='00000000000000001';CLIENT='crm:Contact:'+ID
ADMIN=Principal('synthetic-admin','administrator',('opentour',))
TOKEN='synthetic-control-capability-'+'x'*32


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.reference=Path(self.tmp.name)/'writer.json';self.reference.write_text(json.dumps({'contactId':ID,'token':TOKEN}));self.reference.chmod(0o600)
        self.title='Initial synthetic title';self.revision=1;self.receipts={};self.calls=[];self.posts=0;self.lose=False;self.fail_lookup=False
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def response(self,status,data):
                self.send_response(status);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(data).encode())
            def do_GET(self):
                fixture.calls.append((self.command,self.path,dict(self.headers)))
                if self.headers.get('X-OpenTour-Control')!=TOKEN:return self.response(403,{})
                if self.path=='/api/v1/OpenTourControlTitle':return self.response(200,fixture.snapshot())
                if self.path.startswith('/api/v1/OpenTourControlTitle/status/'):
                    if fixture.fail_lookup:return self.response(503,{})
                    row=fixture.receipts.get(self.path.rsplit('/',1)[1]);return self.response(200 if row else 404,row or {})
                return self.response(403,{})
            def do_POST(self):
                fixture.calls.append((self.command,self.path,dict(self.headers)))
                if self.path!='/api/v1/OpenTourControlTitle' or self.headers.get('X-OpenTour-Control')!=TOKEN:return self.response(403,{})
                data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if set(data)!={'operationId','title','baseVersion','actor'}:return self.response(400,{})
                if data['operationId'] in fixture.receipts:
                    old=fixture.receipts[data['operationId']]
                    return self.response(200 if all(old[k]==data[k] for k in ('title','baseVersion','actor')) else 409,old)
                if data['baseVersion']!=fixture.snapshot()['version']:return self.response(409,{})
                fixture.title=data['title'];fixture.revision+=1;fixture.posts+=1
                result={**fixture.snapshot(),**{k:data[k] for k in ('operationId','baseVersion','actor')},'saved':True};fixture.receipts[data['operationId']]=result
                if fixture.lose:
                    fixture.lose=False;self.send_response(200);self.end_headers();self.wfile.write(b'incomplete-json');return
                return self.response(200,result)
            def do_PUT(self):return self.response(403,{})
            do_DELETE=do_PUT
        self.upstream=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.upstream.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.close)
        self.control=CRMTitleControl(self.reference,'http://127.0.0.1:'+str(self.upstream.server_port))
        self.scope=(CLIENT,)

    def close(self):self.upstream.shutdown();self.upstream.server_close();self.thread.join()
    def snapshot(self):return {'entity':'Contact','id':ID,'title':self.title,'version':hashlib.sha256(str(self.revision).encode()).hexdigest()}
    def body(self,request='synthetic-edit-001',**extra):return {'requestId':request,'title':'Updated synthetic title','baseVersion':self.snapshot()['version'],**extra}
    def failure(self,code,fn):
        with self.assertRaises(Failure) as caught:fn()
        self.assertEqual(caught.exception.code,code)

    def test_general_contact_list_and_detail_never_project_title(self):
        from backend.core import Service
        from backend.adapters import CRM_FIELDS
        from test_backend import CRMFixture,NativeFixture
        crm=CRMFixture()
        for index,record in enumerate(crm.records['Contact']):record['title']='SYNTHETIC PRIVATE TITLE '+str(index)
        service=Service(crm,NativeFixture())
        listing=service.clients({'kind':'person','limit':'2'})
        detail=service.client('crm:Contact:'+crm.records['Contact'][0]['id'])
        self.assertNotIn('jobTitle',json.dumps([listing,detail]))
        self.assertNotIn('SYNTHETIC PRIVATE TITLE',json.dumps([listing,detail]))
        self.assertNotIn('title',CRM_FIELDS.split(','))

    def test_correct_edit_reload_stable_retry_and_field_is_only_title(self):
        body=self.body();result=self.control.edit(ADMIN,self.scope,CLIENT,body)
        self.assertTrue(result['saved']);self.assertEqual(self.control.read(ADMIN,self.scope,CLIENT)['title'],body['title'])
        self.assertEqual(self.control.edit(ADMIN,self.scope,CLIENT,body),result);self.assertEqual(self.posts,1)
        for _,path,headers in self.calls:
            self.assertTrue(path.startswith('/api/v1/OpenTourControlTitle'))
            self.assertNotIn('X-Api-Key',headers);self.assertNotIn('Authorization',headers)

    def test_unknown_commit_reconciles_without_second_post(self):
        body=self.body();self.lose=True
        self.failure('crm_control_effect_unknown',lambda:self.control.edit(ADMIN,self.scope,CLIENT,body))
        self.assertEqual(self.posts,1)
        result=self.control.edit(ADMIN,self.scope,CLIENT,body)
        self.assertTrue(result['saved']);self.assertEqual(self.posts,1)

    def test_unavailable_exact_lookup_never_posts(self):
        self.fail_lookup=True
        self.failure('crm_control_upstream_unavailable',lambda:self.control.edit(ADMIN,self.scope,CLIENT,self.body()))
        self.assertEqual(self.posts,0)

    def test_stale_and_changed_same_key_conflict_without_overwrite(self):
        old=self.body();self.control.edit(ADMIN,self.scope,CLIENT,old)
        self.failure('crm_control_conflict',lambda:self.control.edit(ADMIN,self.scope,CLIENT,{**old,'title':'changed'}))
        self.failure('crm_control_conflict',lambda:self.control.edit(ADMIN,self.scope,CLIENT,{**old,'requestId':'different-stale-key'}))
        self.assertEqual(self.posts,1)

    def test_record_entity_role_and_scope_denials_precede_upstream(self):
        user=Principal('synthetic-user','user',('opentour',))
        for principal,scope,client in ((user,self.scope,CLIENT),(ADMIN,(),CLIENT),(ADMIN,self.scope,'crm:Account:'+ID),(ADMIN,self.scope,'crm:Contact:00000000000000002')):
            self.failure('crm_control_forbidden',lambda:self.control.edit(principal,scope,client,self.body()))
        foreign='crm:Contact:00000000000000002'
        self.failure('crm_control_object_forbidden',lambda:self.control.edit(ADMIN,(foreign,),foreign,self.body()))
        self.assertEqual(self.calls,[])

    def test_bad_fields_values_and_private_reference_are_denied(self):
        for value in ('x'*101,'bad\nvalue',123):
            self.failure('crm_control_value_invalid',lambda:self.control.edit(ADMIN,self.scope,CLIENT,self.body(title=value)))
        for field in ('description','status','entity','id','host','author','command'):
            self.failure('crm_control_value_invalid',lambda:self.control.edit(ADMIN,self.scope,CLIENT,{**self.body(),field:'forged'}))
        self.reference.chmod(0o644)
        with self.assertRaises(Failure):self.control.read(ADMIN,self.scope,CLIENT)
        self.assertEqual(self.posts,0)

    def test_grant_does_not_imply_writer_and_regular_role_cannot_use_it(self):
        access='synthetic-app-access-'+'x'*32
        grant={'subject':ADMIN.subject,'role':'administrator','projects':['opentour'],'tokenSha256':hashlib.sha256(access.encode()).hexdigest()}
        auth=Auth(grants=[grant]);header='Bearer '+access
        self.assertEqual(title_scope(auth,ADMIN,header),())
        grant['crmControlTitle']=[CLIENT];self.assertEqual(title_scope(auth,ADMIN,header),(CLIENT,))
        grant['role']='user';self.assertEqual(title_scope(auth,Principal(ADMIN.subject,'user',('opentour',)),header),())
        grant['crmControlTitle']=['*'];self.failure('crm_control_grant_invalid',lambda:title_scope(auth,ADMIN,header))

    def test_http_object_scope_auth_and_return_to_same_card(self):
        token='synthetic-control-http-'+'x'*32
        grant={'subject':ADMIN.subject,'role':'administrator','projects':['opentour'],'tokenSha256':hashlib.sha256(token.encode()).hexdigest(),'crmControlTitle':[CLIENT]}
        fixture=self
        class Service:
            def client(self,key):return {'id':key,'kind':'person','attributes':{},'provenance':{'entity':'Contact','externalId':ID}}
        server=make_server(Service(),Auth(grants=[grant]),0,crm_title_control=self.control)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(path,body=None,authorized=True):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port);headers={'Authorization':'Bearer '+token} if authorized else {}
            if body is not None:headers['Content-Type']='application/json'
            conn.request('GET' if body is None else 'POST',path,body=json.dumps(body).encode() if body is not None else None,headers=headers)
            response=conn.getresponse();data=json.loads(response.read());status=response.status;conn.close();return status,data
        path='/api/clients/'+CLIENT+'/title-control'
        try:
            self.assertEqual(request(path,authorized=False)[0],401)
            self.assertEqual(request('/api/clients/'+CLIENT)[1]['titleControl'],{'enabled':True})
            self.assertEqual(request(path,self.body())[0],200)
            self.assertEqual(request(path)[1]['title'],'Updated synthetic title')
            self.assertNotIn('Updated synthetic title',json.dumps(request('/api/clients/'+CLIENT)[1]))
            self.assertEqual(request('/api/clients/crm:Account:'+ID+'/title-control',self.body())[0],403)
            grant['crmControlTitle']=[];self.assertEqual(request(path,self.body())[0],403)
            self.assertEqual(request('/api/clients/'+CLIENT+'/description',{'text':'forged'})[0],403)
        finally:server.shutdown();server.server_close();thread.join()

"""Fixed native field boundary with disposable upstream only; actual ORM QA remains separate."""
import hashlib
import http.client
import json
import threading
import unittest
from backend.core import Auth, Principal
from backend.crm_control import CRMFirstNameControl, first_name_scope
from backend.server import make_server
import test_crm_control as fixture_module
from test_crm_control import ADMIN, CLIENT, ID


class FirstNameTests(unittest.TestCase):
    route='/OpenTourContactFirstName'
    field='firstName'
    value_key='firstName'
    control_class=CRMFirstNameControl
    setUp=fixture_module.ControlTests.setUp
    close=fixture_module.ControlTests.close
    snapshot=fixture_module.ControlTests.snapshot
    body=fixture_module.ControlTests.body
    failure=fixture_module.ControlTests.failure

    def test_persistent_reload_retry_unknown_and_field_scope(self):
        body=self.body();self.lose=True
        self.failure('crm_control_effect_unknown',lambda:self.control.edit(ADMIN,(CLIENT,),CLIENT,body))
        self.assertEqual(self.posts,1)
        result=self.control.edit(ADMIN,(CLIENT,),CLIENT,body)
        self.assertTrue(result['saved']);self.assertEqual(result['actor'],ADMIN.subject)
        fresh=CRMFirstNameControl(self.reference,self.control.base)
        self.assertEqual(fresh.read(ADMIN,(CLIENT,),CLIENT)['firstName'],body['firstName'])
        self.assertEqual(self.posts,1)
        for extra in ({'field':'description'},{'title':'forged'},{'author':'forged'}):
            self.failure('crm_control_value_invalid',lambda:self.control.edit(ADMIN,(CLIENT,),CLIENT,{**body,**extra}))
        for value in ('', '   ', 'x'*101, 'bad\nname', 3):
            self.failure('crm_control_value_invalid',lambda:self.control.edit(ADMIN,(CLIENT,),CLIENT,{**body,'firstName':value}))
        self.failure('crm_control_conflict',lambda:self.control.edit(ADMIN,(CLIENT,),CLIENT,{**body,'firstName':'different'}))
        self.failure('crm_control_conflict',lambda:self.control.edit(ADMIN,(CLIENT,),CLIENT,{**body,'requestId':'stale-new-id'}))
        self.assertEqual(self.posts,1)

    def test_explicit_field_grant_and_http_card_projection(self):
        token='synthetic-name-access-'+'x'*32
        grant={'subject':ADMIN.subject,'role':'administrator','projects':['opentour'],'tokenSha256':hashlib.sha256(token.encode()).hexdigest(),'crmControlTitle':[CLIENT]}
        auth=Auth(grants=[grant]);header='Bearer '+token
        self.assertEqual(first_name_scope(auth,ADMIN,header),())
        grant['crmFirstName']=['*']
        self.failure('crm_control_grant_invalid',lambda:first_name_scope(auth,ADMIN,header))
        grant['crmFirstName']=[CLIENT]
        fixture=self
        class Service:
            def client(self,key):return {'id':key,'kind':'person','name':fixture.title,'attributes':{'firstName':fixture.title},'provenance':{'entity':'Contact','externalId':ID}}
        server=make_server(Service(),auth,0,crm_first_name_control=self.control)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(path,body=None):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
            conn.request('GET' if body is None else 'POST',path,body=json.dumps(body) if body is not None else None,headers={'Authorization':header,'Content-Type':'application/json'})
            response=conn.getresponse();data=json.loads(response.read());status=response.status;conn.close();return status,data
        path='/api/clients/'+CLIENT+'/first-name'
        try:
            self.assertTrue(request('/api/clients/'+CLIENT)[1]['firstNameEdit']['enabled'])
            self.assertEqual(request(path,self.body())[0],200)
            self.assertEqual(request('/api/clients/'+CLIENT)[1]['attributes']['firstName'],'Updated synthetic title')
            self.assertEqual(request(path)[1]['firstName'],'Updated synthetic title')
            self.assertEqual(request('/api/clients/crm:Account:'+ID+'/first-name',self.body())[0],403)
            grant['crmFirstName']=[];self.assertEqual(request(path,self.body())[0],403)
            grant['crmFirstName']=[CLIENT];grant['role']='user'
            self.assertEqual(request(path,self.body())[0],403)
        finally:server.shutdown();server.server_close();thread.join()

    def test_foreign_pinned_record_and_lookup_failure_never_write(self):
        foreign='crm:Contact:00000000000000002'
        self.failure('crm_control_object_forbidden',lambda:self.control.edit(ADMIN,(foreign,),foreign,self.body()))
        self.fail_lookup=True
        self.failure('crm_control_upstream_unavailable',lambda:self.control.edit(ADMIN,(CLIENT,),CLIENT,self.body()))
        self.assertEqual(self.posts,0)

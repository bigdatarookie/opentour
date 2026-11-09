"""Executable read seam with synthetic sources; no business effects or human identity."""
import copy
import json
import threading
import unittest
import urllib.error
import urllib.request
from backend.adapters import Failure
from backend.core import Auth, Service
from backend.native_observations import observe
from backend.server import make_server
from test_backend import GRANT, TOKEN, CRMFixture

SLICE='03-operator-board'
WORK='work:opentour:01-local-information-layer:'+SLICE
TAGS=['project:opentour','mission:01-local-information-layer','slice:'+SLICE]
OWNER='platform-developer@opentour-rig'


def row(key, **extra):
    return {'qitemId':key,'state':'blocked','sourceSession':'orch-lead@opentour-rig',
            'destinationSession':OWNER,'blockedOn':'human@external','tags':TAGS[:],
            'tsUpdated':'2026-11-09T00:00:00Z','body':'PRIVATE BODY','summary':'PRIVATE SUMMARY',**extra}


def audit(key='original',verb='resolve'):
    return {'actionId':'action-1','qitemId':key,'actionVerb':verb,'reason':'PRIVATE DECISION',
            'actorSession':'PRIVATE ACTOR','auditNotes':{'secret':'PRIVATE NOTE'},
            'beforeState':{'qitemId':key,'state':'blocked'},'afterState':{'qitemId':key,'state':'in-progress'}}


class Native:
    project='opentour';mission='01-local-information-layer'
    def __init__(self):
        self.rows={'original':row('original')};self.events=[audit()];self.calls=[]
        self.complete=True;self.has_more=False;self.mutate=None;self.client=self
    def snapshot(self):
        return [{'name':SLICE,'queue':copy.deepcopy(list(self.rows.values()))}],self.complete
    def get(self,path,params=None):
        self.calls.append((path,params))
        if path=='/api/mission-control/audit':
            if self.mutate:self.mutate(self)
            return {'rows':copy.deepcopy([x for x in self.events if x.get('qitemId')==params['qitem_id']]),'hasMore':self.has_more}
        return copy.deepcopy(self.rows[path.removeprefix('/api/queue/')])


class SourceTests(unittest.TestCase):
    def test_scoped_audit_metadata_is_read_without_acceptance_or_private_content(self):
        source=Native();result=observe(source,SLICE,'original')
        self.assertEqual(result['observations'][0]['actionId'],'action-1')
        self.assertEqual(result['status'],'observed')
        self.assertEqual(result['originalState'],'blocked');self.assertIsNone(result['currentAsk'])
        for flag in ('humanIdentityVerified','decisionAccepted','ownerActionObserved','executionEnabled','retryAllowed'):
            self.assertFalse(result[flag])
        self.assertNotIn('PRIVATE',json.dumps(result))
        self.assertIn(('/api/mission-control/audit',{'qitem_id':'original','action_verb':'resolve','limit':20}),source.calls)
        self.assertTrue(all(path.startswith(('/api/queue/','/api/mission-control/audit')) for path,_ in source.calls))

    def test_current_states_are_bounded_and_never_emit_unknown_source_words(self):
        source=Native();source.events=[];source.rows['original']['state']='PRIVATE UNKNOWN STATE'
        result=observe(source,SLICE,'original')
        self.assertIsNone(result['originalState']);self.assertNotIn('PRIVATE',json.dumps(result))
        source.rows['original']['state']='blocked';source.rows['original']['blockedOn']='ask'
        source.rows['ask']=row('ask',state='PRIVATE UNKNOWN STATE',sourceSession=OWNER,destinationSession='human@external')
        result=observe(source,SLICE,'original')
        self.assertEqual(result['currentAsk'],{'taskId':'ask','state':None})
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_membership_checked_before_any_row_or_audit_read(self):
        for key,slice_name in [('foreign',SLICE),('original','other'),('../private',SLICE)]:
            source=Native()
            with self.assertRaises(Failure):observe(source,slice_name,key)
            self.assertEqual(source.calls,[])
        source=Native();source.rows['original']['tags']=['project:other']
        with self.assertRaises(Failure):observe(source,SLICE,'original')
        self.assertEqual(source.calls,[])

    def test_service_refuses_misconfigured_source_project(self):
        source=Native();source.project='other'
        with self.assertRaisesRegex(Failure,'work_not_found'):
            Service(CRMFixture(),source).native_decisions(WORK,'original')
        self.assertEqual(source.calls,[])

    def test_changed_scope_or_custody_fails_closed(self):
        for field,value in [('destinationSession','someone@external'),('tags',['project:other']),('tsUpdated','later')]:
            source=Native();source.mutate=lambda s,f=field,v=value:s.rows['original'].__setitem__(f,v)
            with self.assertRaisesRegex(Failure,'native_observation_changed'):observe(source,SLICE,'original')

    def test_audit_malformed_or_cross_target_never_becomes_observation(self):
        for field,value in [('actionVerb','send'),('actionId','../private'),('afterState',{'qitemId':'foreign','state':'done'}),('beforeState',{'qitemId':'original','state':'PRIVATE STATE'})]:
            source=Native();source.events[0][field]=value
            with self.assertRaises(Failure):observe(source,SLICE,'original')

    def test_no_match_or_incomplete_window_remains_honest(self):
        source=Native();source.events=[];source.complete=False;source.has_more=True
        result=observe(source,SLICE,'original')
        self.assertEqual(result['status'],'unconfirmed');self.assertEqual(result['observations'],[])
        self.assertFalse(result['queueWindowComplete']);self.assertFalse(result['auditWindowComplete'])
        self.assertFalse(result['replyWindowComplete'])

    def test_current_ask_and_native_reply_are_read_and_correlated(self):
        source=Native();source.rows['original']['blockedOn']='ask'
        source.rows['ask']=row('ask',state='done',sourceSession=OWNER,destinationSession='human@external',blockedOn=None)
        source.rows['reply']=row('reply',state='pending',sourceSession='human@external',destinationSession=OWNER,replyTo='ask',tags=TAGS+['human-answer'])
        source.rows['unrelated']=row('unrelated',state='pending',sourceSession='human@external',destinationSession=OWNER,replyTo='different-ask',tags=TAGS+['human-answer'])
        source.events=[audit('ask','answer')]
        result=observe(source,SLICE,'original')
        self.assertEqual(result['currentAsk'],{'taskId':'ask','state':'done'})
        self.assertEqual(result['linkedReplies'],[{'askTaskId':'ask','replyTaskId':'reply','status':'native_linked_reply_observed'}])
        self.assertFalse(result['decisionAccepted']);self.assertFalse(result['ownerActionObserved'])
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_same_slice_different_owner_does_not_create_ask_lineage(self):
        source=Native();source.rows['original']['blockedOn']='ask'
        source.rows['ask']=row('ask',sourceSession='other@opentour-rig',destinationSession='human@external')
        with self.assertRaisesRegex(Failure,'native_observation_scope_mismatch'):observe(source,SLICE,'original')
        self.assertFalse(any(path=='/api/mission-control/audit' for path,_ in source.calls))


class HTTPTests(unittest.TestCase):
    def test_existing_auth_scope_and_http_write_denial_apply(self):
        source=Native();server=make_server(Service(CRMFixture(),source),Auth(grants=[GRANT]),0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        def get(suffix='',token=TOKEN,method='GET'):
            request=urllib.request.Request(base+'/api/board/'+WORK+'/native-decisions/original'+suffix,
                headers={'Authorization':'Bearer '+token} if token else {},method=method)
            try:response=urllib.request.urlopen(request,timeout=3)
            except urllib.error.HTTPError as error:response=error
            with response:return response.status,json.loads(response.read())
        try:
            self.assertEqual(get(token=None)[0],401);self.assertEqual(source.calls,[])
            self.assertEqual(get('?project=other')[0],403);self.assertEqual(source.calls,[])
            status,result=get();self.assertEqual(status,200);self.assertEqual(result['originalTaskId'],'original')
            self.assertFalse(result['executionEnabled']);self.assertNotIn('PRIVATE',json.dumps(result))
            self.assertEqual(get(method='POST')[0],403)
            self.assertEqual(get('/../private')[0],404)
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()

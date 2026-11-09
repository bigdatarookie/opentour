#!/usr/bin/env python3
"""Read-only native observation HTTP probe. Never accesses CRM, auth files or owner data."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import threading
import urllib.error
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.adapters import NativeWork
from backend.core import Auth, MISSION, Service
from backend.server import make_server


class NoCRM:
    def __getattr__(self, name):
        raise AssertionError('CRM is outside this native-only probe')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-root',required=True,type=Path,help='Existing specification root containing missions/')
    parser.add_argument('--original-id',required=True,help='Existing scoped native task; no task is created')
    parser.add_argument('--slice',default='03-operator-board')
    args=parser.parse_args()
    token=secrets.token_urlsafe(32)
    grant={'subject':'native-observation-diagnostic','role':'user','projects':['opentour'],
           'tokenSha256':hashlib.sha256(token.encode()).hexdigest()}
    native=NativeWork(args.work_root,MISSION)
    server=make_server(Service(NoCRM(),native),Auth(grants=[grant]),0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    path='/api/board/work:opentour:'+MISSION+':'+args.slice+'/native-decisions/'+args.original_id
    base='http://127.0.0.1:'+str(server.server_port)
    def get(path,authenticated=True):
        req=urllib.request.Request(base+path,headers={'Authorization':'Bearer '+token} if authenticated else {})
        try:response=urllib.request.urlopen(req,timeout=90)
        except urllib.error.HTTPError as error:response=error
        with response:return response.status,json.loads(response.read())
    result={'probe':'native_read_observation_http','crm_access':False,'private_credentials_access':False,
            'native_writes':False,'human_identity_proven':False,'private_values_emitted':False}
    try:
        status,_=get(path,False);result['unauthenticated_http']=status;assert status==401
        status,body=get(path);result['observation_http']=status
        if status!=200:result['error_code']=body.get('error');raise AssertionError()
        assert body['originalTaskId']==args.original_id
        assert not any(body[key] for key in ('humanIdentityVerified','decisionAccepted','ownerActionObserved','executionEnabled','retryAllowed'))
        result.update(status=body['status'],audit_entry_count=len(body['observations']),linked_reply_count=len(body['linkedReplies']),
                      queue_window_complete=body['queueWindowComplete'],audit_window_complete=body['auditWindowComplete'])
        result['outcome']='read_passed_no_decision_or_resume_claim'
        print(json.dumps(result,sort_keys=True));return 0
    except Exception:
        result['outcome']='failed_no_private_details_emitted';print(json.dumps(result,sort_keys=True));return 1
    finally:server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':raise SystemExit(main())

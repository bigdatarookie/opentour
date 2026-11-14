"""Separate capability for a pinned synthetic Contact.title; never an Espo API-user key."""
import hashlib
import hmac
import json
import re
import urllib.error
import urllib.request
from .adapters import Failure, JsonGET, private_json
from .core import PROJECT


def title_scope(auth, principal, authorization):
    # Extend the existing server-owned bearer grant; no new browser identity mechanism.
    rows=auth.grants if auth.grants is not None else private_json(auth.path).get('principals',[])
    digest=hashlib.sha256(authorization[7:].encode()).hexdigest()
    for row in rows:
        if isinstance(row,dict) and isinstance(row.get('tokenSha256'),str) and hmac.compare_digest(row['tokenSha256'],digest):
            scope=row.get('crmControlTitle',[])
            if (not isinstance(scope,list) or len(scope)>100 or any(not isinstance(v,str) or not re.fullmatch(r'crm:Contact:[A-Za-z0-9]{17,24}',v) for v in scope)):
                raise Failure('crm_control_grant_invalid',403)
            if (principal.role!='administrator' or row.get('role')!=principal.role or row.get('subject')!=principal.subject
                    or PROJECT not in row.get('projects',[])):
                return ()
            return tuple(scope)
    return ()


class CRMTitleControl:
    def __init__(self, reference_file=None, base='http://127.0.0.1:18082'):
        self.reference_file=reference_file;self.base=base

    def _config(self):
        if not self.reference_file:raise Failure('crm_control_not_configured',503)
        config=private_json(self.reference_file)
        if (not isinstance(config,dict) or set(config)!={'contactId','token'}
                or not isinstance(config['contactId'],str) or not re.fullmatch(r'[A-Za-z0-9]{17,24}',config['contactId'])
                or not isinstance(config['token'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',config['token'])):
            raise Failure('crm_control_reference_invalid',503)
        return config

    def enabled(self, principal, scope, client_id):
        if principal.role!='administrator' or client_id not in scope or not self.reference_file:return False
        return client_id=='crm:Contact:'+self._config()['contactId']

    def _authorized(self, principal, scope, client_id):
        if principal.role!='administrator' or PROJECT not in principal.projects or client_id not in scope:
            raise Failure('crm_control_forbidden',403)
        config=self._config()
        if client_id!='crm:Contact:'+config['contactId']:raise Failure('crm_control_object_forbidden',403)
        return config,JsonGET(self.base+'/api/v1',{'X-OpenTour-Control':config['token']})

    def _request(self, client, method, path, body=None):
        request=urllib.request.Request(client.base+path,method=method,headers={**client.headers,**({'Content-Type':'application/json'} if body is not None else {})},data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None)
        try:
            with client.opener.open(request,timeout=6) as response:
                raw=response.read(65537)
                if len(raw)>65536:raise ValueError('large_response')
                return json.loads(raw)
        except urllib.error.HTTPError as error:
            if error.code in (400,409):raise Failure('crm_control_conflict' if error.code==409 else 'crm_control_value_invalid',error.code) from None
            if error.code==404:raise Failure('crm_control_operation_not_found',404) from None
            raise Failure('crm_control_upstream_unavailable',503) from None
        except (urllib.error.URLError,OSError,ValueError,TimeoutError):
            raise Failure('crm_control_effect_unknown' if method=='POST' else 'crm_control_read_unavailable',503) from None

    def _snapshot(self, config, data, operation=None, title=None):
        if (not isinstance(data,dict) or data.get('entity')!='Contact' or data.get('id')!=config['contactId']
                or not isinstance(data.get('title'),str) or len(data['title'])>100
                or not isinstance(data.get('version'),str) or not re.fullmatch(r'[a-f0-9]{64}',data['version'])
                or (operation is not None and (data.get('operationId')!=operation or data.get('saved') is not True or data['title']!=title))):
            raise Failure('crm_control_response_invalid',503)
        return data

    def read(self, principal, scope, client_id):
        config,client=self._authorized(principal,scope,client_id)
        return self._snapshot(config,self._request(client,'GET','/OpenTourControlTitle'))

    def edit(self, principal, scope, client_id, body):
        config,client=self._authorized(principal,scope,client_id)
        if (not isinstance(body,dict) or set(body)!={'requestId','title','baseVersion'}
                or not isinstance(body['requestId'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',body['requestId'])
                or not isinstance(body['title'],str) or len(body['title'])>100 or any(ord(c)<32 or ord(c)==127 for c in body['title'])
                or not isinstance(body['baseVersion'],str) or not re.fullmatch(r'[a-f0-9]{64}',body['baseVersion'])):
            raise Failure('crm_control_value_invalid',400)
        operation=hashlib.sha256(json.dumps([principal.subject,client_id,body['requestId']],separators=(',',':')).encode()).hexdigest()
        payload={'operationId':operation,'title':body['title'],'baseVersion':body['baseVersion'],'actor':principal.subject}
        # Always reconcile exact operation before a possible POST; no automatic second POST.
        try:
            prior=self._request(client,'GET','/OpenTourControlTitle/status/'+operation)
        except Failure as error:
            if error.status!=404:raise
        else:
            result=self._snapshot(config,prior)
            if prior.get('operationId')!=operation or prior.get('saved') is not True:raise Failure('crm_control_response_invalid',503)
            # Upstream also checks the full digest for POST replay; status must prove the same input.
            if prior.get('baseVersion')!=body['baseVersion'] or prior.get('actor')!=principal.subject or prior['title']!=body['title']:
                raise Failure('crm_control_conflict',409)
            return result
        result=self._request(client,'POST','/OpenTourControlTitle',payload)
        return self._snapshot(config,result,operation,body['title'])

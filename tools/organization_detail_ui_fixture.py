"""Focused disposable Organization fixture for the existing browser harness. No live source."""
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from backend.adapters import Failure
from test_backend import CRMFixture


class OrganizationFixture(CRMFixture):
    def __init__(self):
        super().__init__();self.fail_detail=False
        self.records={'Contact':[], 'Account':[{'id':'org-synthetic',
            'name':'Синтетическая организация — проверка подробной карточки клиента',
            'type':'School','emailAddress':'organization@example.invalid','phoneNumber':'SYNTHETIC_PHONE',
            'modifiedAt':'2026-11-09 00:00:00'}]}
    def detail(self,entity,key):
        if self.fail_detail:raise Failure('synthetic_organization_detail_unavailable',503)
        return super().detail(entity,key)


class EmptyNative:
    def snapshot(self):return [],True


def exercise(run,evaluate,wait,check,click,crm,token,port,checks):
    base='http://127.0.0.1:'+str(port);key='crm:Account:org-synthetic'
    def get(path,authenticated=True):
        request=urllib.request.Request(base+path,headers={'Authorization':'Bearer '+token} if authenticated else {})
        try:response=urllib.request.urlopen(request,timeout=5)
        except urllib.error.HTTPError as error:response=error
        with response:return response.status,json.loads(response.read())
    def api_check(name,condition):
        if not condition:raise RuntimeError('organization_api_assertion_'+name)
        checks.append(name)
    status,page=get('/api/clients?kind=organization&limit=2')
    api_check('populated_organization_list_http',status==200 and page['total']==1 and len(page['items'])==1 and page['items'][0]['kind']=='organization')
    status,detail=get('/api/clients/'+key)
    api_check('account_detail_identity_version_fields',status==200 and detail['id']==key and detail['version']==page['items'][0]['version'] and detail['attributes']['crmType']=='School' and detail['provenance']['entity']=='Account')
    api_check('organization_detail_requires_auth',get('/api/clients/'+key,False)[0]==401)
    api_check('organization_detail_project_scope',get('/api/clients/'+key+'?project=other')[0]==403)
    api_check('unknown_account_is_404',get('/api/clients/crm:Account:unknown-synthetic')[0]==404)
    run('open',base);run('set','viewport','1440','1000')
    check('no_clients_before_access','!document.querySelector(".client-row:not(.client-header)")')
    evaluate('document.querySelector("#access-token").value='+json.dumps(token)+';document.querySelector("#connect-form").requestSubmit();true;')
    wait('!document.querySelector("#workspace").hidden')
    check('synthetic_mode_visible','!document.querySelector("#synthetic-banner").hidden')
    evaluate('document.querySelector("#client-kind").value="organization";true;');click('[data-view="clients"]')
    wait('document.querySelectorAll(".client-row:not(.client-header)").length===1')
    click('.client-row:not(.client-header)');wait('document.querySelector("#detail-body .detail-grid")!==null')
    record=crm.records['Account'][0]
    check('organization_name_contacts_and_category_visible','document.querySelector("#detail-title").textContent === '+json.dumps(record['name'])+' && ["organization@example.invalid","SYNTHETIC_PHONE","School","Организация"].every(value=>document.querySelector("#detail-body").textContent.includes(value))')
    check('organization_crm_link_is_account','document.querySelector("#detail-body .source-link").href === "http://127.0.0.1:18082/#Account/view/org-synthetic" && document.querySelector("#detail-body .source-link").rel === "noopener noreferrer"')
    check('organization_read_only_no_person_placeholder','!document.querySelector("#detail-dialog input,#detail-dialog textarea,#detail-dialog .technical-note") && document.querySelector("#detail-body").textContent.includes("ничего не сохраняет")')
    run('press','Escape');check('organization_keyboard_focus_returns','document.activeElement.dataset.objectId === '+json.dumps(key))
    run('set','viewport','390','844');click('.client-row:not(.client-header)');wait('document.querySelector("#detail-body .detail-grid")!==null')
    check('long_organization_mobile_detail_and_close_fit','document.documentElement.scrollWidth<=innerWidth && document.querySelector("#detail-dialog").getBoundingClientRect().right<=innerWidth && document.querySelector(".dialog-footer button").getBoundingClientRect().bottom <= document.querySelector("#detail-dialog").getBoundingClientRect().bottom')
    run('scrollintoview','#detail-body .source-link')
    check('organization_mobile_body_scroll_reaches_source','(()=>{const body=document.querySelector("#detail-body"),link=body.querySelector(".source-link"),a=body.getBoundingClientRect(),b=link.getBoundingClientRect();return body.scrollTop>0 && b.top>=a.top && b.bottom<=a.bottom;})()')
    run('press','Escape');crm.fail_detail=True;click('.client-row:not(.client-header)')
    wait('document.querySelector("#detail-body .state-box")!==null')
    check('organization_source_error_not_empty_success','!document.querySelector("#detail-body .detail-grid") && document.querySelector("#detail-body .state-box").textContent.includes("Не удалось открыть")')
    crm.fail_detail=False;click('#detail-body .state-box button');wait('document.querySelector("#detail-body .detail-grid")!==null')
    check('organization_retry_restores_same_record','document.querySelector("#detail-title").textContent === '+json.dumps(record['name']))
    run('press','Escape');record.update(name='<img src=x onerror="window.organizationInjected=true">',emailAddress=None,phoneNumber=None,type=None)
    click('#refresh');wait('document.querySelector("#client-list").getAttribute("aria-busy")==="false"')
    click('.client-row:not(.client-header)');wait('document.querySelector("#detail-body .detail-grid")!==null')
    check('organization_unknown_fields_not_invented','document.querySelector("#detail-body").textContent.includes("Email не указан") && document.querySelector("#detail-body").textContent.includes("Телефон не указан") && !document.querySelector("#detail-body").textContent.includes("School")')
    check('organization_source_text_not_executable','document.querySelector("#detail-title").textContent.startsWith("<img") && !document.querySelector("#detail-dialog img") && !window.organizationInjected')
    run('press','Escape');click('#disconnect')
    check('organization_disconnect_cleanup','!document.querySelector(".client-row:not(.client-header)") && document.querySelector("#workspace").hidden && !document.querySelector("#detail-dialog").open')
    raw=json.loads(run('network','requests'));urls=[]
    def collect(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key=='url' and isinstance(item,str) and item.startswith(('http://','https://')):urls.append(item)
                else:collect(item)
        elif isinstance(value,list):
            for item in value:collect(item)
    collect(raw)
    api_check('no_live_service_requests',bool(urls) and all(urlsplit(url).netloc==urlsplit(base).netloc for url in urls))
    print(json.dumps({'mode':'organization-synthetic','outcome':'passed','checks':checks,'fixture':'in_memory_crm_through_existing_backend_http_and_ui','production_access':False,'owner_values_emitted':False,'credentials_emitted':False,'screenshots':'none','writes_exercised':False}));return 0

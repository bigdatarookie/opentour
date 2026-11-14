#!/usr/bin/env python3
"""Isolated UI of a denied-by-default synthetic upstream. Not real Espo integration."""
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tools')]
from test_crm_control import ControlTests,ID,CLIENT
from test_backend import CRMFixture,NativeFixture
from backend.core import Auth,Service
from backend.server import make_server


def main():
    fixture=ControlTests();fixture.setUp();checks=[]
    session=subprocess.check_output(['agent-browser','session','id','--scope','worktree','--prefix','crm-title-synthetic'],text=True).strip()
    with tempfile.TemporaryDirectory(prefix='opentour-crm-title-browser-') as private:
        token=secrets.token_urlsafe(32)
        grant={'subject':'synthetic-control-admin','role':'administrator','projects':['opentour'],
               'tokenSha256':hashlib.sha256(token.encode()).hexdigest(),'crmControlTitle':[CLIENT]}
        class CRM(CRMFixture):
            def __init__(self):
                super().__init__();self.records['Contact']=[{'id':ID,'name':'Synthetic control','firstName':'Synthetic','lastName':'Control','title':fixture.title}]
            def detail(self,entity,key):
                self.records['Contact'][0]['title']=fixture.title
                return super().detail(entity,key)
        server=make_server(Service(CRM(),NativeFixture()),Auth(grants=[grant]),0,data_mode='synthetic',crm_title_control=fixture.control)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        prefix=['agent-browser','--session',session,'--profile',str(Path(private)/'profile'),'--executable-path','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','--json']
        def run(*args,script=None):
            result=subprocess.run(prefix+list(args),input=script,capture_output=True,text=True,timeout=40)
            if result.returncode:raise RuntimeError('synthetic_crm_title_probe_failed '+args[0]+': '+(result.stderr+result.stdout).replace(token,'[redacted]')[:500])
            return result.stdout
        def js(script):return run('eval','--stdin',script='(async()=>{'+script+'})()')
        def wait(expr):run('wait','--fn',expr)
        def check(name,expr):js('if(!('+expr+'))throw new Error('+json.dumps(name)+');true;');checks.append(name)
        try:
            run('open','http://127.0.0.1:'+str(server.server_port))
            js('document.querySelector("#access-token").value='+json.dumps(token)+';document.querySelector("#connect-form").requestSubmit();true;')
            wait('!document.querySelector("#workspace").hidden')
            js('openDetails("client",'+json.dumps(CLIENT)+',document.querySelector("[data-view=clients]"));true;')
            wait('!!document.querySelector("#crm-control-title") && !document.querySelector(".crm-title-form button[type=submit]").disabled')
            check('pinned_card_title_read','document.querySelector("#crm-control-title").value==="Initial synthetic title" && state.modal.id==='+json.dumps(CLIENT))
            run('fill','#crm-control-title','Synthetic edited title')
            js('document.querySelector(".crm-title-form").requestSubmit();true;')
            wait('document.querySelector("#crm-control-title").value==="Synthetic edited title" && !document.querySelector(".crm-title-form button[type=submit]").disabled')
            check('edit_returns_to_same_crm_card','state.modal.id==='+json.dumps(CLIENT)+' && document.querySelector("#crm-control-title").value==="Synthetic edited title"')
            fixture.lose=True
            run('fill','#crm-control-title','Synthetic unknown response title')
            js('document.querySelector(".crm-title-form").requestSubmit();true;')
            wait('document.querySelector(".crm-title-form .connection-status").textContent.includes("Результат неизвестен")')
            check('unknown_save_retains_frozen_text','document.querySelector("#crm-control-title").readOnly && document.querySelector("#crm-control-title").value.includes("unknown response")')
            js('document.querySelector(".crm-title-form").requestSubmit();true;')
            wait('!document.querySelector("#crm-control-title").readOnly && !document.querySelector(".crm-title-form button[type=submit]").disabled')
            assert fixture.posts==2
            check('exact_receipt_retry_reloads_saved_title','document.querySelector("#crm-control-title").value==="Synthetic unknown response title"')
            fixture.title='Synthetic concurrent title';fixture.revision+=1
            run('fill','#crm-control-title','UNSAVED user title after conflict')
            js('document.querySelector(".crm-title-form").requestSubmit();true;')
            wait('document.querySelector(".crm-title-form .connection-status").textContent.includes("отклонено")')
            check('conflict_keeps_editable_local_text','!document.querySelector("#crm-control-title").readOnly && document.querySelector("#crm-control-title").value.startsWith("UNSAVED")')
            js('document.querySelector(".crm-title-form button[type=button]").click();true;')
            wait('document.querySelector("#crm-control-title").value==="Synthetic concurrent title"')
            grant['role']='user'
            js('await loadDetail();true;')
            check('ordinary_role_has_no_write_control','!document.querySelector("#crm-control-title")')
            check('ordinary_role_card_has_no_title_value','!document.querySelector("#detail-body").textContent.includes("Synthetic concurrent title")')
            js('window.__ordinaryCard=(await api("/api/clients/"+'+json.dumps(CLIENT)+')).data;true;')
            check('ordinary_read_api_has_no_title_projection','!JSON.stringify(window.__ordinaryCard).includes("jobTitle") && !JSON.stringify(window.__ordinaryCard).includes("Synthetic concurrent title")')
            print(json.dumps({'mode':'SYNTHETIC UPSTREAM ONLY','passed':len(checks),'checks':checks,'upstreamTitleWrites':fixture.posts,'actualEspoIntegration':'NOT RUN','ownerRecords':False,'nativeQueue':False}))
        finally:
            try:run('close')
            finally:server.shutdown();server.server_close();thread.join();fixture.doCleanups()

if __name__=='__main__':main()

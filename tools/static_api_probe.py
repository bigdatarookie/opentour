#!/usr/bin/env python3
"""Affected static/protected-API browser checks. Disposable loopback only; no worker/native/CRM."""
import functools
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.core import Auth, Principal
from backend.board_store import BoardStore
from backend.server import make_server
from tools.build_static_ui import build


def main():
    started=time.monotonic(); checks=[]; calls=0
    session=subprocess.check_output(['agent-browser','session','id','--scope','worktree','--prefix','static-api-synthetic'],text=True,cwd=ROOT).strip()
    with tempfile.TemporaryDirectory(prefix='opentour-static-api-synthetic-') as tmp:
        root=Path(tmp)
        class Static(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        handler=functools.partial(Static,directory=str(root/'public'))
        ui=ThreadingHTTPServer(('127.0.0.1',0),handler)
        denied=ThreadingHTTPServer(('127.0.0.1',0),handler)
        ui_origin='http://127.0.0.1:'+str(ui.server_port)
        denied_origin='http://127.0.0.1:'+str(denied.server_port)
        store=BoardStore(root/'data'/'board.sqlite3')
        admin=Principal('synthetic-static-admin','administrator',frozenset(['opentour']),True,True,True,frozenset(['*']))
        task=store.create(admin,{'requestId':'static-probe-task','title':'Synthetic static API task','description':'Synthetic only','section':'tasks'})
        other=store.create(admin,{'requestId':'static-probe-other','title':'Synthetic forbidden task','description':'Synthetic only','section':'tasks'})
        token=secrets.token_urlsafe(32)
        grant={'subject':'synthetic-static-reader','role':'user','projects':['opentour'],'boardOnly':True,
               'tokenSha256':hashlib.sha256(token.encode()).hexdigest(),'board':{'read':True,'respond':True,'tasks':[task['id']]}}
        class NoSources:
            def __getattr__(self,_):raise AssertionError('sources_forbidden')
        api_server=make_server(NoSources(),Auth(grants=[grant]),0,data_mode='synthetic',board_store=store,
                               public_base_url='https://protected.example.invalid/bridge',allowed_ui_origins=[ui_origin])
        api_origin='http://127.0.0.1:'+str(api_server.server_port)
        build(root/'public'/'opentour',api_origin+'/bridge')
        servers=[ui,denied,api_server];threads=[]
        for server in servers:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();threads.append(thread)
        prefix=['agent-browser','--session',session,'--profile',str(root/'profile'),'--executable-path','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','--json']
        def run(*args,script=None):
            nonlocal calls
            calls+=1
            result=subprocess.run(prefix+list(args),input=script,capture_output=True,text=True,timeout=40,cwd=ROOT)
            if result.returncode:
                raise RuntimeError('synthetic_static_api_probe_failed '+args[0]+': '+(result.stderr+result.stdout).replace(token,'[redacted]')[:500])
            return result.stdout
        def js(script):return run('eval','--stdin',script=script)
        def check(name,expression):
            js('if(!('+expression+'))throw new Error('+json.dumps(name)+');true;');checks.append(name)
        def login():
            js('document.querySelector("#access-token").value='+json.dumps(token)+';document.querySelector("#connect-form").requestSubmit();true;')
            run('wait','--fn','!!document.querySelector("#app-task-list button")')
        try:
            run('open',ui_origin+'/opentour/?apiBase=https://untrusted.example.invalid#token=ignored')
            check('trusted_metadata_overrides_no_caller_url', 'API_BASE==='+json.dumps(api_origin+'/bridge')+' && BASE_PATH==="/opentour" && state.token===""')
            login()
            check('configured_api_renders_exact_scoped_task', 'document.querySelectorAll("#app-task-list button").length===1 && document.querySelector("#app-task-list").textContent.includes("Synthetic static API task") && !state.sourceReads')
            check('static_prefix_styles_loaded','getComputedStyle(document.body).fontFamily.includes("Commissioner") && Array.from(document.styleSheets).some(s=>s.href?.endsWith("/opentour/ui/styles.css"))')
            js('window.__unauth=await fetch(API_BASE+"/api/capabilities",{credentials:"omit"}).then(r=>r.status);true;')
            check('cors_does_not_replace_bearer_auth','window.__unauth===401')
            js('window.__saved=(await api("/api/board-tasks/'+task['id']+'/messages",{body:{requestId:"static-probe-comment",kind:"comment",text:"Synthetic configured API comment"}})).data;true;')
            check('configured_post_keeps_server_authorship','window.__saved.author==="synthetic-static-reader" && window.__saved.persistence==="saved"')
            js('try {await api("/api/board-tasks/'+other['id']+'");window.__foreign=0;}catch(e){window.__foreign=e.status;}true;')
            check('configured_api_foreign_task_denied','window.__foreign===404')
            js('const one=await api("/api/capabilities");window.__conditional=!!one.etag && (await api("/api/capabilities",{etag:one.etag})).unchanged;true;')
            check('cors_etag_exposed_and_conditional_read_works','window.__conditional===true')
            js('window.__csp=false;document.addEventListener("securitypolicyviolation",e=>{if(e.effectiveDirective==="connect-src")window.__csp=true;});try{await fetch('+json.dumps(denied_origin+'/unlisted')+');}catch(e){}true;')
            run('wait','--fn','window.__csp===true')
            check('static_csp_blocks_unconfigured_api','window.__csp===true')
            run('open',denied_origin+'/opentour/')
            js('try{await fetch('+json.dumps(api_origin+'/bridge/api/capabilities')+',{headers:{Authorization:'+json.dumps('Bearer '+token)+'}});window.__denied=false;}catch(e){window.__denied=true;}true;')
            check('unlisted_ui_origin_cannot_read_protected_api','window.__denied===true')
            for path in ('/','/bridge/'):
                run('open',api_origin+path);login()
                check('same_origin_'+('root' if path=='/' else 'prefix')+'_unchanged','API_BASE==="/bridge" && document.querySelectorAll("#app-task-list button").length===1')
            print(json.dumps({'mode':'SYNTHETIC ONLY','passed':len(checks),'checks':checks,
                              'elapsedSeconds':round(time.monotonic()-started,3),'browserCalls':calls,
                              'actualNativeDelivery':'NOT RUN','crmAccess':False,'canonicalRuntimeTouched':False,
                              'modelCost':'UNKNOWN','nativeUsage':'UNKNOWN'}))
        finally:
            try:run('close')
            finally:
                for server in servers:server.shutdown();server.server_close()
                for thread in threads:thread.join()

if __name__=='__main__':main()

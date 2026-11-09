#!/usr/bin/env python3
"""Browser proof for the pinned campaign FIXTURE. No CRM/native/provider/credential access."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.core import Auth, version
from backend.server import make_server


class FixtureShellOnly:
    def board(self):
        data={'source':'synthetic_fixture_shell','items':[],'columns':[],'queueWindowComplete':True}
        return {**data,'version':version(data),'cursor':{'epoch':'fixture-shell','sequence':1}}

    def clients(self,*_args,**_kwargs):raise AssertionError('CRM access is forbidden for this probe')
    def client(self,*_args,**_kwargs):raise AssertionError('CRM access is forbidden for this probe')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof-dir',type=Path)
    parser.add_argument('--browser',default='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    args=parser.parse_args()
    token=secrets.token_urlsafe(32)
    auth=Auth(grants=[{'subject':'fixture-campaign-probe','role':'user','projects':['opentour'],'tokenSha256':hashlib.sha256(token.encode()).hexdigest()}])
    server=make_server(FixtureShellOnly(),auth,0,data_mode='synthetic')
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    session=subprocess.check_output(['agent-browser','session','id','--scope','worktree','--prefix','opentour-campaign-fixture'],text=True,timeout=10).strip()
    checks=[]
    with tempfile.TemporaryDirectory(prefix='opentour-campaign-browser-') as temporary:
        prefix=['agent-browser','--session',session,'--profile',str(Path(temporary)/'profile'),'--executable-path',args.browser,'--json']
        def run(*cmd,script=None):
            result=subprocess.run(prefix+list(cmd),input=script,capture_output=True,text=True,timeout=45)
            if result.returncode:
                print(json.dumps({'browser_error':(result.stdout+result.stderr).replace(token,'[redacted]')[:1200]}))
                raise RuntimeError('browser_command_failed_'+cmd[0])
            return result.stdout
        def evaluate(script):return run('eval','--stdin',script=script)
        def wait(expression):run('wait','--fn',expression)
        def check(name,expression):
            evaluate('if (!('+expression+')) throw new Error("campaign_probe_assertion");true;');checks.append(name)
        def click(selector):
            run('snapshot','-i');run('scrollintoview',selector);run('click',selector)
        def screenshot(name):
            if args.proof_dir:
                args.proof_dir.mkdir(parents=True,exist_ok=True);run('screenshot',str(args.proof_dir.resolve()/name))
        try:
            run('open',base);run('set','viewport','1440','1000')
            evaluate('document.querySelector("#access-token").value='+json.dumps(token)+';document.querySelector("#connect-form").requestSubmit();true;')
            wait('!document.querySelector("#workspace").hidden')
            click('[data-view="campaigns"]');wait('document.querySelectorAll(".campaign-card").length===1')
            check('fixture_labels_visible','["FIXTURE","PREVIEW-ONLY","NOT CONTENT-APPROVED","NOT SENT"].every(label=>document.querySelector("#campaigns-view").textContent.includes(label))')
            check('audience_unselected_not_zero','document.querySelector(".campaign-card").textContent.includes("Аудитория не выбрана") && document.querySelector(".campaign-card").textContent.includes("число получателей недоступно")')
            screenshot('campaign-list-desktop.png')
            click('.campaign-card');wait('document.querySelector(".email-preview-frame")!==null')
            check('opaque_sandbox_without_permissions','document.querySelector(".email-preview-frame").getAttribute("sandbox")==="" && document.querySelector(".email-preview-frame").getAttribute("referrerpolicy")==="no-referrer"')
            check('detail_has_no_sender_provider_or_delivery_claim','document.querySelector(".campaign-facts").textContent.includes("Не настроен") && document.querySelector(".campaign-facts").textContent.includes("provider ID отсутствует")')
            screenshot('campaign-preview-desktop.png')
            check('frame_is_opaque_to_application','document.querySelector(".email-preview-frame").contentDocument === null')
            click('.preview-switch button:nth-child(2)')
            check('text_alternative_preserved','[...document.querySelectorAll(".campaign-source")].some(el=>!el.hidden && el.textContent.includes("160 000") && el.textContent.includes("октябрь"))')
            click('.preview-switch button:nth-child(3)')
            check('original_manifest_preserved','[...document.querySelectorAll(".campaign-source")].some(el=>!el.hidden && el.textContent.includes("retain r01 unchanged as preview-only"))')
            click('.preview-switch button:nth-child(1)')
            run('set','viewport','390','844')
            check('mobile_shell_and_dialog_fit','document.documentElement.scrollWidth<=innerWidth && document.querySelector("#detail-dialog").getBoundingClientRect().width<=innerWidth')
            check('mobile_close_button_visible','document.querySelector(".dialog-footer button").getBoundingClientRect().bottom <= document.querySelector("#detail-dialog").getBoundingClientRect().bottom')
            screenshot('campaign-preview-mobile.png')
            evaluate('document.querySelector("#detail-body").scrollTop=600;true;')
            screenshot('campaign-email-mobile.png')
            raw=json.loads(run('network','requests'))
            urls=[]
            def find(value):
                if isinstance(value,dict):
                    for key,item in value.items():
                        if key=='url' and isinstance(item,str) and item.startswith(('http://','https://')):urls.append(item)
                        else:find(item)
                elif isinstance(value,list):
                    for item in value:find(item)
            find(raw)
            if not urls:raise RuntimeError('network_observation_unavailable')
            if any(urlsplit(url).netloc != urlsplit(base).netloc for url in urls):raise RuntimeError('unexpected_external_request')
            checks.append('no_external_requests_during_preview')
            run('press','Escape');check('focus_returns_to_campaign','document.activeElement.classList.contains("campaign-card")')
            click('#disconnect');check('disconnect_removes_preview','document.querySelectorAll(".campaign-card,.email-preview-frame").length===0')
            print(json.dumps({'mode':'FIXTURE','outcome':'passed','checks':checks,'crm_access':False,'credential_access':False,'provider_access':False,'source_writes':False,'external_request_count':0,'limitations':['agent-browser cannot select the opaque srcdoc frame; child DOM/style/mobile overflow checks NOT RUN; rendering inspected in screenshots']} ))
            return 0
        except Exception as error:
            print(json.dumps({'mode':'FIXTURE','outcome':'failed','passed_checks':checks,'error_type':str(error),'crm_access':False,'credential_access':False,'provider_access':False}))
            return 1
        finally:
            try:run('close')
            except Exception:pass
            server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':raise SystemExit(main())

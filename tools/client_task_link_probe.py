#!/usr/bin/env python3
"""Synthetic client -> persisted app discussion -> client browser journey, no live sources."""
import hashlib
import json
import secrets
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from backend.board_store import BoardStore
from backend.core import Auth, Service
from backend.server import make_server
from test_backend import CRMFixture, NativeFixture
from test_board_conversations import ADMIN


def main():
    checks = []
    session = subprocess.check_output(['agent-browser','session','id','--scope','worktree','--prefix','opentour-client-task-synthetic'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='opentour-client-task-browser-') as private:
        store = BoardStore(Path(private) / 'db' / 'board.sqlite3')
        crm = CRMFixture()
        for i in range(3,21): crm.records['Contact'].append({'id':'p'+str(i),'name':'Synthetic Person '+str(i)})
        def task(key, title, entity, external_id):
            return store.create(ADMIN, {'requestId':key,'title':title,'description':'Synthetic linked work',
                'section':'clients','requestText':'Synthetic linked request?', 'clientRef':{'entity':entity,'externalId':external_id}})
        contact = task('browser-contact-0001','Synthetic contact work','Contact','p14')
        hidden = task('browser-contact-0002','Hidden synthetic work','Contact','p14')
        account = task('browser-account-0001','Synthetic organization work with a long title to check the mobile task dialog and its return controls','Account','o1')
        token = secrets.token_urlsafe(32)
        grant = {'subject':'synthetic-link-user','role':'user','projects':['opentour'],
            'tokenSha256':hashlib.sha256(token.encode()).hexdigest(),
            'board':{'read':True,'respond':True,'tasks':[contact['id'],account['id']]}}
        server = make_server(Service(crm, NativeFixture()),Auth(grants=[grant]),0,data_mode='synthetic',board_store=store)
        thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        prefix = ['agent-browser','--session',session,'--profile',str(Path(private)/'profile'),
            '--executable-path','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','--json']
        def run(*args, script=None):
            result = subprocess.run(prefix+list(args),input=script,capture_output=True,text=True,timeout=45)
            if result.returncode:
                raise RuntimeError('synthetic_browser_failure:'+args[0]+' '+(result.stderr+result.stdout).replace(token,'[redacted]')[:500])
            return result.stdout
        def evaluate(js): return run('eval','--stdin',script=js)
        def wait(js): run('wait','--fn',js)
        def check(name, js):
            evaluate('if (!('+js+')) throw new Error('+json.dumps(name)+');true;');checks.append(name)
        def click(js): evaluate(js+'.click();true;')
        def open_client(external_id, entity='Contact'):
            selector='[data-object-id="crm:'+entity+':'+external_id+'"]'
            run('scrollintoview',selector);run('click',selector)
            wait('!!document.querySelector(".related-tasks")')
        def open_related():
            click('document.querySelector("[data-related-task]")')
            wait('!!document.querySelector(".app-task-detail")')
        try:
            run('open','http://127.0.0.1:'+str(server.server_port))
            evaluate('document.querySelector("#access-token").value='+json.dumps(token)+';document.querySelector("#connect-form").requestSubmit();true;')
            wait('!document.querySelector("#workspace").hidden')
            click('document.querySelector("[data-view=clients]")')
            wait('document.querySelectorAll(".client-row:not(.client-header)").length > 0')
            run('select','#client-kind','person');run('fill','#client-search','Synthetic');run('press','Enter')
            wait('document.querySelector("#client-total").textContent === "20" && document.querySelector("#client-list").getAttribute("aria-busy") === "false"')
            click('document.querySelector("#next-page")')
            wait('!!document.querySelector("[data-object-id=\\"crm:Contact:p14\\"]")')
            open_client('p14')
            check('related_work_is_scoped','document.querySelectorAll("[data-related-task]").length === 1 && !document.querySelector(".related-tasks").textContent.includes("Hidden synthetic work")')
            check('person_task_link_identity','document.querySelector("[data-related-task]").dataset.relatedTask === '+json.dumps(contact['id']))
            open_related()
            check('same_task_conversation_opened','document.querySelector("#detail-title").textContent === "Synthetic contact work" && document.querySelector(".app-message").textContent.includes("Synthetic linked request?")')
            check('forward_navigation_focus','document.activeElement === document.querySelector("[data-return-client]")')
            run('fill','#app-response-text','Synthetic response from client context')
            evaluate('document.querySelector(".app-response").requestSubmit();true;')
            wait('document.querySelectorAll(".app-message").length === 2')
            check('same_task_answer_saved','document.querySelectorAll(".app-message")[1].textContent.includes("Synthetic response from client context")')
            click('document.querySelector("[data-return-client]")');wait('!!document.querySelector(".related-tasks")')
            check('return_restores_client_modal_focus','document.querySelector("#detail-title").textContent === "Synthetic Person 14" && document.activeElement === document.querySelector("[data-related-task]")')
            check('filters_and_page_preserved','document.querySelector("#client-kind").value === "person" && document.querySelector("#client-search").value === "Synthetic" && document.querySelector("#page-range").textContent.startsWith("13")')
            run('press','Escape')
            wait('!document.querySelector("#detail-dialog").open && document.activeElement.dataset.objectId === "crm:Contact:p14"')
            check('close_returns_original_client_row','document.activeElement.dataset.objectId === "crm:Contact:p14"')
            run('select','#client-kind','organization')
            wait('!!document.querySelector("[data-object-id=\\"crm:Account:o1\\"]")')
            run('set','viewport','390','844');open_client('o1','Account')
            check('organization_task_link_identity','document.querySelector("[data-related-task]").dataset.relatedTask === '+json.dumps(account['id']))
            evaluate('document.querySelector("#detail-body").scrollTop=150;window.sourceClientScroll=document.querySelector("#detail-body").scrollTop;true;')
            open_related()
            check('mobile_task_and_close_fit','document.documentElement.scrollWidth <= innerWidth && document.querySelector("#done-detail").getBoundingClientRect().bottom <= document.querySelector("#detail-dialog").getBoundingClientRect().bottom')
            click('document.querySelector("[data-return-client]")');wait('!!document.querySelector(".related-tasks")')
            check('return_restores_client_scroll','Math.abs(document.querySelector("#detail-body").scrollTop-window.sourceClientScroll)<2')
            # The stale client link cannot bypass current task grant checks.
            grant['board']['tasks'] = []
            click('document.querySelector("[data-related-task]")');wait('!!document.querySelector("#detail-body .state-box")')
            check('revoked_task_not_rendered','!document.querySelector(".app-task-detail") && !document.querySelector(".app-message") && !!document.querySelector("[data-return-client]")')
            click('document.querySelector("[data-return-client]")');wait('!!document.querySelector(".related-tasks")')
            check('revoked_relation_hidden_on_return','document.querySelectorAll("[data-related-task]").length === 0 && document.querySelector("#detail-title").textContent === "Synthetic School"')
            with store.db() as db:
                saved = db.execute("SELECT task_id,reply_to FROM messages WHERE body='Synthetic response from client context'").fetchone()
                if saved['task_id'] != contact['id'] or saved['reply_to'] != contact['messages'][0]['id']:
                    raise RuntimeError('wrong_conversation_link')
                if db.execute("SELECT count(*) FROM outbox WHERE state!='pending'").fetchone()[0]:
                    raise RuntimeError('unexpected_delivery')
            print(json.dumps({'mode':'SYNTHETIC ONLY','checks':checks,'passed':len(checks),
                'native_sends':False,'live_crm_access':False,'temporary_db_server_profile_cleaned_on_exit':True}))
        finally:
            run('close');server.shutdown();server.server_close();thread.join()


if __name__ == '__main__': main()

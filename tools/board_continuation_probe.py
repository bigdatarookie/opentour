#!/usr/bin/env python3
"""Synthetic browser receipt projection; actual agent continuation belongs to System QA."""
import json
import argparse
from pathlib import Path
import subprocess
import tempfile
import threading
from atlas_preview import prepare
from backend.core import Auth
from backend.server import make_server
from backend.context_delivery import receive_context,report_context,serve_worker
from test_board_continuation import Delivery


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prefix',action='store_true');args=parser.parse_args()
    checks=[]
    session=subprocess.check_output(['agent-browser','session','id','--scope','worktree','--prefix','board-continuation-synthetic'],text=True).strip()
    with tempfile.TemporaryDirectory(prefix='opentour-receipt-browser-') as private:
        store,task,keys,grants,_,_=prepare(private)
        # The published test grant is explicitly board-only and exact-task scoped.
        for grant in grants:grant['boardOnly']=True
        with store.db() as db:
            db.execute('INSERT INTO task_execution(task_id,native_ref) VALUES(?,?)',(task['id'],'qitem-synthetic-original'))
        class NoSources:
            def __getattr__(self,_):raise AssertionError('no_source_access_permitted')
        server=make_server(NoSources(),Auth(grants=grants),0,data_mode='synthetic',board_store=store,public_base_url='https://board.example.invalid/opentour' if args.prefix else None)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        prefix=['agent-browser','--session',session,'--profile',str(Path(private)/'profile'),'--executable-path','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','--json']
        def run(*args,script=None):
            result=subprocess.run(prefix+list(args),input=script,capture_output=True,text=True,timeout=40)
            if result.returncode:
                message=result.stderr+result.stdout
                for token in keys.values():message=message.replace(token,'[redacted]')
                raise RuntimeError('synthetic_receipt_browser_failed '+args[0]+': '+message[:500])
            return result.stdout
        def js(script):return run('eval','--stdin',script=script)
        def wait(expression):run('wait','--fn',expression)
        def check(name,expression):
            js('if(!('+expression+'))throw new Error('+json.dumps(name)+');true;');checks.append(name)
        def refresh():js('document.querySelector("#refresh").click();true;')
        def card_state(state):wait('document.querySelector(".app-processing-status").textContent.includes('+json.dumps(state)+')')
        stop=threading.Event();worker=None
        try:
            run('open','http://127.0.0.1:'+str(server.server_port)+('/opentour/' if args.prefix else '/'))
            js('document.querySelector("#access-token").value='+json.dumps(keys['user'])+';document.querySelector("#connect-form").requestSubmit();true;')
            wait('!!document.querySelector("#app-task-list button")')
            check('board_only_discussion_usable_no_source_board','!document.querySelector("#workspace").hidden && document.querySelector("#board").hidden && !state.sourceReads')
            js('document.querySelector("[data-view=clients]").click();true;')
            check('source_section_explains_restricted_access','document.querySelector("#client-list").textContent.includes("Доступны обсуждения") && !document.querySelector("#workspace").hidden')
            js('document.querySelector("[data-view=tasks]").click();document.querySelector("#app-task-list button").click();true;')
            wait('!!document.querySelector("#app-response-text")')
            run('fill','#app-response-text','Synthetic choice B')
            js('document.querySelector(".app-response").requestSubmit();document.querySelector(".app-response").requestSubmit();true;')
            wait('document.querySelectorAll(".app-message").length===2')
            check('double_submit_one_saved_answer','document.querySelectorAll(".app-message").length===2 && document.querySelector("#app-response-text").value===""')
            transport=Delivery();transport.rows['qitem-synthetic-original']={'qitemId':'qitem-synthetic-original','destinationSession':'campaign-creative@opentour-rig','state':'in-progress','tags':['project:opentour']}
            worker=threading.Thread(target=serve_worker,args=(store,transport),kwargs={'interval':0.1,'stop':stop},daemon=True);worker.start()
            with store.db() as db:answer=dict(db.execute("SELECT * FROM outbox ORDER BY rowid DESC LIMIT 1").fetchone())
            refresh();wait('document.querySelectorAll(".app-message")[1].textContent.includes("Контекст доставлен")')
            check('delivered_distinct_from_received','document.querySelectorAll(".app-message")[1].textContent.includes("Обработка агентом: не подтверждена")')
            receive_context(store,answer['id'],'campaign-creative@opentour-rig')
            refresh();wait('document.querySelectorAll(".app-message")[1].textContent.includes("Контекст получен")')
            report_context(store,answer['id'],'campaign-creative@opentour-rig','accepted','Synthetic sufficient answer',transport=transport)
            refresh();card_state('Ответ принят')
            check('accepted_updates_modal_and_card','document.querySelector("#detail-dialog").open && document.querySelectorAll(".app-message")[1].textContent.includes("Ответ принят")')
            report_context(store,answer['id'],'campaign-creative@opentour-rig','continued','Synthetic fixture result',result='Prepared a synthetic itinerary for choice B.',evidence='qitem-synthetic-original',transport=transport)
            refresh();card_state('Работа продолжена')
            wait('document.querySelectorAll(".app-message")[1].textContent.includes("Prepared a synthetic itinerary")')
            check('substantive_fixture_return_visible','document.querySelector("#detail-dialog").open && document.querySelectorAll(".app-message")[1].textContent.includes("Работа продолжена")')
            js('document.querySelector("#done-detail").click();true;');wait('!document.querySelector("#detail-dialog").open')
            run('reload');wait('!document.querySelector("#connect-panel").hidden')
            js('document.querySelector("#access-token").value='+json.dumps(keys['user'])+';document.querySelector("#connect-form").requestSubmit();true;')
            card_state('Работа продолжена')
            check('reload_reads_durable_state','document.querySelectorAll("#app-task-list button").length===1')
            print(json.dumps({'mode':'SYNTHETIC ONLY','actual_agent':False,'prefix':args.prefix,'passed':len(checks),'checks':checks,
                'crm_access':False,'native_queue_access':False,'fixture_answer_count':1}))
        finally:
            stop.set()
            if worker:worker.join(5)
            run('close');server.shutdown();server.server_close();thread.join()

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Synthetic browser rendering of explicit fixture agent returns, never a fake live agent."""
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
from backend.board_store import BoardStore
from backend.client_conversations import ClientControls
from backend.core import Auth, Service
from backend.context_delivery import deliver_one,receive_context
from backend.server import make_server
from test_board_continuation import Delivery
from ui_browser_probe import SyntheticCRM,synthetic_native


def main():
    checks=[]
    session=subprocess.check_output(['agent-browser','session','id','--scope','worktree','--prefix','client-proposal-fixture'],text=True).strip()
    with tempfile.TemporaryDirectory(prefix='opentour-client-proposal-fixture-') as private:
        root=Path(private);store=BoardStore(root/'data'/'board.sqlite3')
        token=secrets.token_urlsafe(32)
        grant={'subject':'synthetic-client-user','role':'user','projects':['opentour'],
               'tokenSha256':hashlib.sha256(token.encode()).hexdigest(),'board':{'read':True,'respond':True,'tasks':[]},
               'clientConversations':{'clients':['crm:Contact:p2'],'editProposal':True}}
        reference={'entity':'Contact','externalId':'p2'};obligation='qitem-synthetic-client-obligation';owner='campaign-creative@opentour-rig'
        transport=Delivery();transport.rows[obligation]={'qitemId':obligation,'destinationSession':owner,'state':'in-progress','tags':['project:opentour','mission:01-local-information-layer']}
        class Obligations:
            def resolve(self,ref,expected=None):
                if ref!=obligation or expected!=owner:raise AssertionError('synthetic_binding_mismatch')
                return owner
        server=make_server(Service(SyntheticCRM(),synthetic_native()),Auth(grants=[grant]),0,data_mode='synthetic',board_store=store,
                           client_controls=ClientControls(records=[{'clientRef':reference,'continuationRef':obligation}]),obligations=Obligations())
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        prefix=['agent-browser','--session',session,'--profile',str(root/'profile'),'--executable-path','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','--json']
        def run(*args,script=None):
            result=subprocess.run(prefix+list(args),input=script,capture_output=True,text=True,timeout=45)
            if result.returncode:raise RuntimeError('synthetic_client_probe_failed '+args[0]+': '+(result.stderr+result.stdout).replace(token,'[redacted]')[:500])
            return result.stdout
        def js(script):return run('eval','--stdin',script='(async()=>{'+script+'})()')
        def wait(expression):run('wait','--fn',expression)
        def check(name,expression):js('if(!('+expression+'))throw new Error('+json.dumps(name)+');true;');checks.append(name)
        def fixture_reply(round_no,base,title,body):
            # Explicit authored fixture injection, not an agent implementation/receipt claim.
            with store.db() as db:row=db.execute('SELECT id FROM outbox ORDER BY rowid DESC LIMIT 1').fetchone()
            delivery=row['id'];deliver_one(store,transport,delivery);receive_context(store,delivery,owner)
            store.agent_reply(delivery,owner,{'requestId':'fixture-agent-round-'+str(round_no),'text':'SYNTHETIC FIXTURE reply '+str(round_no),
                'proposal':{'baseRevision':base,'title':title,'body':body}},transport)
        try:
            run('open','http://127.0.0.1:'+str(server.server_port))
            js('document.querySelector("#access-token").value='+json.dumps(token)+';document.querySelector("#connect-form").requestSubmit();true;')
            wait('!document.querySelector("#workspace").hidden')
            js('document.querySelector("[data-view=clients]").click();true;')
            wait('!!document.querySelector("[data-client-id]") || !!document.querySelector(".client-row")')
            js('openDetails("client","crm:Contact:p2",document.querySelector("[data-view=clients]"));true;')
            wait('!!document.querySelector("#client-conversation-text")')
            run('fill','#client-conversation-text','FICTIONAL first brief: two adults, Kazan March12-14, budget ceiling60000RUB. Supplier price UNKNOWN.')
            js('document.querySelector(".client-conversation-form").requestSubmit();true;')
            wait('!!document.querySelector(".proposal-editor")')
            check('client_context_created_with_fixed_agent','state.panelTask.clientRef.externalId==="p2" && state.panelTask.conversation.recipient==="campaign-creative@opentour-rig"')
            fixture_reply(1,0,'FICTIONAL Kazan draft','FICTIONAL three-day itinerary, two adults. Supplier price/availability/terms UNKNOWN.')
            js('await loadDetail();true;');wait('!!document.querySelector("#proposal-body")')
            check('agent_return_and_editable_proposal_rendered','document.querySelectorAll(".app-message").length===2 && document.querySelector("#proposal-body").value.includes("three-day")')
            run('fill','#proposal-body','FICTIONAL human-edited draft. Keep breakfast. Supplier price UNKNOWN.')
            js('window.__realFetch=window.fetch;window.__loseOnce=true;window.fetch=async(...args)=>{const response=await window.__realFetch(...args);if(window.__loseOnce && String(args[0]).endsWith("/proposal") && args[1]?.method==="POST"){window.__loseOnce=false;throw new TypeError("synthetic committed response loss");}return response;};document.querySelector(".proposal-form").requestSubmit();true;')
            wait('document.querySelector(".proposal-form .connection-status").textContent.includes("Сохранение неизвестно")')
            check('unknown_save_freezes_exact_payload_with_local_text','document.querySelector("#proposal-body").readOnly && document.querySelector("#proposal-body").value.includes("human-edited")')
            js('document.querySelector(".proposal-form").requestSubmit();true;')
            wait('document.querySelector(".proposal-editor").textContent.includes("Версия 2")')
            js('window.fetch=window.__realFetch;true;')
            js('document.querySelector("#done-detail").click();true;')
            wait('!document.querySelector("#detail-dialog").open')
            run('fill','#chat-text','FICTIONAL clarification: add an8-year-old, shorten to March13-14; quiet child-friendly pace. Nothing booked.')
            js('document.querySelector("#chat-send").click();true;')
            wait('document.querySelectorAll("#messages .message").length===3')
            check('second_round_same_context_input_remains_enabled','!document.querySelector("#chat-text").disabled && document.querySelector("#chat-text").value===""')
            fixture_reply(2,2,'FICTIONAL revised Kazan draft','FICTIONAL two-day itinerary, two adults and child8. March13-14. Budget ceiling remains60000RUB, not price. UNKNOWN supplier price/availability/terms.')
            js('await refreshAtlasTask();openDetails("app",state.panelTask.id,document.querySelector("#dialog-toggle"));true;')
            wait('document.querySelector(".proposal-editor")?.textContent.includes("Версия 3")')
            check('second_reply_and_revised_draft_same_client','document.querySelectorAll(".app-message").length===4 && document.querySelector("#proposal-body").value.includes("two-day") && state.panelTask.clientRef.externalId==="p2"')
            # Keep local edits across an HTTP error and a remote version refresh.
            run('fill','#proposal-body','UNSAVED FICTIONAL draft that must survive a stale conflict.')
            js('window.__clientTask=state.panelTask.id;true;')
            with store.db() as db:task_id=db.execute('SELECT task_id FROM client_conversations').fetchone()[0]
            principal=Auth(grants=[grant]).authorize('Bearer '+token)
            store.save_proposal(principal,task_id,{'requestId':'fixture-concurrent-edit','baseRevision':3,'title':'Remote edit','body':'SYNTHETIC concurrent version4.'})
            js('document.querySelector(".proposal-form").requestSubmit();true;')
            wait('document.querySelector(".proposal-form .connection-status").textContent.includes("Версия изменилась")')
            check('stale_save_keeps_local_text','document.querySelector("#proposal-body").value.includes("UNSAVED FICTIONAL")')
            js('await loadDetail();true;')
            check('poll_refresh_keeps_conflicting_local_draft','document.querySelector("#proposal-body").value.includes("UNSAVED FICTIONAL") && !!document.querySelector(".proposal-conflict")')
            # Close/reopen DB object simulates backend reconstruction over the saved state.
            reopened=BoardStore(store.path).detail(principal,task_id)
            assert len(reopened['messages'])==4 and reopened['proposal']['revision']==4
            run('reload');wait('!document.querySelector("#connect-panel").hidden')
            js('document.querySelector("#access-token").value='+json.dumps(token)+';document.querySelector("#connect-form").requestSubmit();true;')
            wait('!!document.querySelector("#app-task-list button")')
            js('document.querySelector("#app-task-list button").click();true;')
            wait('document.querySelector(".proposal-editor")?.textContent.includes("Версия 4")')
            check('reload_reads_saved_history_and_latest_revision','document.querySelectorAll(".app-message").length===4 && document.querySelector("#proposal-body").value.includes("concurrent version4")')
            # Revocation hides the same object; no cross-client grant is inferred.
            grant['clientConversations']['clients']=[]
            js('try{await api("/api/board-tasks/"+state.panelTask.id);window.__foreign=0;}catch(e){window.__foreign=e.status;}true;')
            check('revoked_exact_client_grant_denied','window.__foreign===404')
            print(json.dumps({'mode':'SYNTHETIC FIXTURE ONLY','passed':len(checks),'checks':checks,'actualAgentJourney':'NOT RUN','crmAccess':False,'nativeQueueAccess':False,'workerStarted':False,'fixtureReplies':2}))
        finally:
            try:run('close')
            finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':main()

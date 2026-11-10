#!/usr/bin/env python3
"""Synthetic source-driven board transitions only; no CRM, native daemon or sends."""
import json
from pathlib import Path
import subprocess
import tempfile
import threading
from atlas_preview import prepare
from backend.adapters import Failure
from backend.core import Auth, Service
from backend.server import make_server
from test_backend import row


def main():
    checks = []
    session = subprocess.check_output(['agent-browser','session','id','--scope','worktree','--prefix','board-transition-synthetic'],text=True).strip()
    with tempfile.TemporaryDirectory(prefix='opentour-transition-') as private:
        store, task, keys, grants, crm, native = prepare(private)
        original_snapshot = native.snapshot
        failure = [False]
        def snapshot():
            if failure[0]: raise Failure('source_unavailable',503)
            return original_snapshot()
        native.snapshot = snapshot
        service=Service(crm,native)
        server = make_server(service,Auth(grants=grants),0,data_mode='synthetic',board_store=store)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        prefix=['agent-browser','--session',session,'--profile',str(Path(private)/'profile'),'--executable-path','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','--json']
        def run(*args, script=None):
            result=subprocess.run(prefix+list(args),input=script,capture_output=True,text=True,timeout=40)
            if result.returncode:
                error=result.stderr+result.stdout
                for token in keys.values():error=error.replace(token,'[redacted]')
                raise RuntimeError('synthetic_transition_failed '+args[0]+': '+error[:500])
            return result.stdout
        def js(script):return run('eval','--stdin',script=script)
        def wait(expression):run('wait','--fn',expression)
        def check(name,expression):
            js('if(!('+expression+'))throw new Error('+json.dumps(name)+');true;');checks.append(name)
        def refresh():js('document.querySelector("#refresh").click();true;')
        def update(status):
            native.items[0].update(authoredStatus='complete' if status=='done' else 'planned',readiness='ready' if status=='done' else 'unknown',nativeStatus='done' if status=='done' else 'active',queue=[] if status=='done' else [row(owner='platform-qa-code@opentour-rig' if status=='review' else 'platform-developer@opentour-rig')])
        def settled():wait('!state.boardBusy && state.boardAnimations.every(a=>a.playState==="finished" || a.playState==="idle")')
        try:
            run('set','viewport','1100','800');run('open','http://127.0.0.1:'+str(server.server_port))
            js('document.querySelector("#access-token").value='+json.dumps(keys['user'])+';document.querySelector("#connect-form").requestSubmit();true;')
            wait('!!document.querySelector("[data-column=done] .task-wrap") && !!document.querySelector("#app-task-list button")')
            js('clearInterval(state.poll);true;')
            js('window.card=document.querySelector("[data-column=done] .task-wrap");window.cardButton=card.querySelector("button");window.motion=[];window.holdMotion=true;window.realAnimate=Element.prototype.animate;Element.prototype.animate=function(...args){const a=realAnimate.apply(this,args);if(this.classList.contains("task-wrap")){motion.push({a,node:this,column:this.closest(".column").dataset.column,frames:args[0]});if(holdMotion)a.pause()}return a};true;')
            update('in_progress');refresh();wait('motion.length===1')
            check('collapse_in_original_column_single_noninteractive_node','card.closest(".column").dataset.column==="done" && card.inert && document.querySelectorAll(`[data-task-id="${card.dataset.taskId}"]`).length===1')
            js('motion[0].a.currentTime=65;true;')
            check('collapse_reduces_vertical_space','card.offsetHeight>0 && card.offsetHeight<parseFloat(motion[0].frames[0].height) && motion[0].frames[1].height==="0px"')
            js('motion[0].a.finish();true;');wait('motion.length===2')
            check('expand_follows_collapse_in_new_column_same_node','motion[0].column==="done" && motion[1].column==="in_progress" && motion[1].node===card && document.querySelectorAll(`[data-task-id="${card.dataset.taskId}"]`).length===1 && !card.inert && card.querySelector("button")===cardButton')
            js('motion[1].a.currentTime=75;true;')
            check('expand_restores_vertical_space','card.offsetHeight>0 && card.offsetHeight<parseFloat(motion[1].frames[1].height)')
            js('motion[1].a.finish();window.holdMotion=false;true;');settled()
            refresh();settled();check('duplicate_refresh_does_not_repeat_motion','motion.length===2')
            # A failure breaks continuity; reconnect should show current state directly.
            failure[0]=True;refresh();wait('!document.querySelector("#board-notice").hidden && !state.boardBusy')
            failure[0]=False;update('done');refresh();settled()
            check('reconnect_uses_current_state_without_replay','motion.length===2 && card.closest(".column").dataset.column==="done"')
            # Native detail remains open and receives the source status.
            js('cardButton.click();true;');wait('!!document.querySelector("#detail-body .detail-grid")')
            update('in_progress');refresh();settled()
            wait('document.querySelector("#detail-body").textContent.includes("В работе")')
            check('native_modal_stays_open_and_updates','document.querySelector("#detail-dialog").open && state.modal.id===cardButton.dataset.objectId')
            js('document.querySelector("#done-detail").click();true;');wait('!document.querySelector("#detail-dialog").open')
            check('modal_close_returns_to_same_card','document.activeElement===cardButton')
            # App input remains outside board DOM reconciliation; no app DB writes.
            js('document.querySelector("#app-task-list button").click();true;');wait('!!document.querySelector("#app-response-text")')
            run('fill','#app-response-text','Synthetic unsent transition draft')
            js('document.querySelector("#app-response-text").setSelectionRange(4,9);window.draftInput=document.querySelector("#app-response-text");true;')
            update('done');refresh();settled()
            check('app_modal_input_focus_selection_retained','document.querySelector("#detail-dialog").open && document.querySelector("#app-response-text")===draftInput && draftInput.value==="Synthetic unsent transition draft" && document.activeElement===draftInput && draftInput.selectionStart===4 && draftInput.selectionEnd===9')
            js('document.querySelector("#done-detail").click();true;');wait('!document.querySelector("#detail-dialog").open')
            # Reduced motion skips both stages.
            js('window.originalMatchMedia=window.matchMedia;window.matchMedia=q=>q.includes("prefers-reduced-motion")?{matches:true}:originalMatchMedia(q);window.beforeMotion=motion.length;true;')
            update('review');refresh();settled()
            check('reduced_motion_direct_move_same_identity','motion.length===beforeMotion && card.closest(".column").dataset.column==="review" && card.querySelector("button")===cardButton')
            js('window.matchMedia=originalMatchMedia;cardButton.focus();window.holdMotion=true;window.beforeMotion=motion.length;true;')
            update('in_progress');refresh();wait('motion.length===beforeMotion+1')
            # User focus after refresh must not be stolen back when collapse ends.
            js('document.querySelector("#work-filter").focus();true;')
            js('motion.at(-1).a.finish();true;');wait('motion.length===beforeMotion+2')
            js('motion.at(-1).a.finish();true;');settled()
            check('new_user_focus_not_stolen','document.activeElement.id==="work-filter"')
            # New source update supersedes an unfinished transition, no stale move.
            js('cardButton.focus();window.beforeMotion=motion.length;true;');update('done');refresh();wait('motion.length===beforeMotion+1')
            update('review');refresh();wait('motion.length===beforeMotion+2')
            js('motion.at(-1).a.finish();true;');wait('motion.length===beforeMotion+3')
            js('motion.at(-1).a.finish();window.holdMotion=false;true;');settled()
            check('interrupted_refresh_keeps_latest_source_one_card','card.closest(".column").dataset.column==="review" && document.querySelectorAll(`[data-task-id="${card.dataset.taskId}"]`).length===1 && !card.inert && document.activeElement===cardButton')
            # Filter/view changes and disconnect cancel pending work without resurrection.
            js('document.querySelector("#board").scrollLeft=100;window.boardScroll=document.querySelector("#board").scrollLeft;window.beforeMotion=motion.length;true;')
            js('window.holdMotion=true;true;');update('done');refresh();wait('motion.length===beforeMotion+1')
            js('document.querySelector("#board").scrollLeft=130;window.boardScroll=document.querySelector("#board").scrollLeft;document.querySelector("#main").scrollTop=50;window.mainScroll=document.querySelector("#main").scrollTop;motion.at(-1).a.finish();true;')
            wait('motion.length===beforeMotion+2');js('motion.at(-1).a.finish();window.holdMotion=false;true;');settled()
            check('latest_vertical_scroll_preserved','mainScroll>0 && document.querySelector("#main").scrollTop===mainScroll')
            check('horizontal_scroll_preserved','document.querySelector("#board").scrollLeft===boardScroll && document.querySelector("#work-filter").value==="all"')
            js('window.beforeMotion=motion.length;true;');service.epoch='synthetic-restart-epoch';update('review');refresh();settled()
            check('new_source_epoch_skips_history','motion.length===beforeMotion && card.closest(".column").dataset.column==="review"')
            js('window.syntheticHidden=true;Object.defineProperty(document,"hidden",{configurable:true,get:()=>syntheticHidden});document.dispatchEvent(new Event("visibilitychange"));true;')
            update('in_progress');refresh();settled()
            check('hidden_document_never_animates','motion.length===beforeMotion && card.closest(".column").dataset.column==="in_progress"')
            js('window.syntheticHidden=false;document.dispatchEvent(new Event("visibilitychange"));true;')
            update('done');refresh();settled()
            check('return_from_hidden_uses_current_state','motion.length===beforeMotion && card.closest(".column").dataset.column==="done"')
            js('delete document.hidden;window.holdMotion=true;window.beforeMotion=motion.length;true;');update('in_progress');refresh();wait('motion.length===beforeMotion+1')
            js('document.querySelector("#work-filter").value="review";document.querySelector("#work-filter").dispatchEvent(new Event("change"));true;')
            wait('state.boardAnimations.length===0')
            check('filter_cancels_stale_transition','!document.querySelector(`[data-task-id="${card.dataset.taskId}"]`) && document.querySelector("#work-filter").value==="review"')
            js('document.querySelector("#work-filter").value="all";document.querySelector("#work-filter").dispatchEvent(new Event("change"));true;')
            wait('!!document.querySelector(`[data-task-id="${card.dataset.taskId}"]`)')
            js('window.beforeMotion=motion.length;true;');update('done');refresh();wait('motion.length===beforeMotion+1')
            js('document.querySelector("#disconnect").click();true;')
            check('disconnect_cancels_without_private_dom_resurrection','document.querySelector("#workspace").hidden && !document.querySelector("#board .task-card") && state.boardAnimations.length===0')
            print(json.dumps({'mode':'SYNTHETIC ONLY','passed':len(checks),'checks':checks,'crm_access':False,'native_writes':False,'app_replies_sent':False,'fixture_task_seeded':True}))
        finally:
            run('close');server.shutdown();server.server_close();thread.join()

if __name__=='__main__':main()

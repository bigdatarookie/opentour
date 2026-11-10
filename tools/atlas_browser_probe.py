#!/usr/bin/env python3
"""Bounded synthetic Atlas integration proof; no CRM/daemon or business writes."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import threading
from atlas_preview import prepare
from backend.core import Auth, Service
from backend.server import make_server
from test_board_conversations import ADMIN, USER, SyntheticTransport
from backend.context_delivery import run_batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof-dir', type=Path, help='Synthetic screenshots only')
    args = parser.parse_args()
    checks = []
    session = subprocess.check_output(['agent-browser', 'session', 'id', '--scope', 'worktree', '--prefix', 'atlas-integration-synthetic'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='atlas-integration-') as private:
        store, task, keys, grants, crm, native = prepare(private)
        server = make_server(Service(crm, native), Auth(grants=grants), 0, data_mode='synthetic', board_store=store)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        prefix = ['agent-browser', '--session', session, '--profile', str(Path(private) / 'profile'), '--executable-path', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--json']
        def run(*command, script=None):
            result = subprocess.run(prefix + list(command), input=script, capture_output=True, text=True, timeout=45)
            if result.returncode:
                message = result.stderr + result.stdout
                for value in keys.values(): message = message.replace(value, '[redacted]')
                raise RuntimeError('synthetic_browser_failed: ' + command[0] + ' ' + message[:500])
            return result.stdout
        def js(script): return run('eval', '--stdin', script=script)
        def wait(expression): run('wait', '--fn', expression)
        def check(name, expression):
            js('if (!(' + expression + ')) throw new Error(' + json.dumps(name) + ');true;')
            checks.append(name)
        def click(selector): js('document.querySelector(' + json.dumps(selector) + ').click();true;')
        def screenshot(name):
            if args.proof_dir:
                args.proof_dir.mkdir(parents=True, exist_ok=True)
                run('screenshot', str(args.proof_dir / (name + '.png')))
        def connect(role):
            js('document.querySelector("#access-token").value=' + json.dumps(keys[role]) + ';document.querySelector("#connect-form").requestSubmit();true;')
            wait('!!document.querySelector("#board .task-card") && !!document.querySelector("#app-task-list button")')
        try:
            run('set', 'viewport', '1440', '1000')
            run('open', 'http://127.0.0.1:' + str(server.server_port))
            check('no_private_data_before_access', 'document.querySelector("#workspace").hidden && !document.querySelector(".app-message")')
            connect('user')
            wait('document.fonts.check("14px Commissioner") && document.fonts.check("24px Prata")')
            check('local_atlas_fonts_loaded', 'getComputedStyle(document.body).fontFamily.includes("Commissioner") && getComputedStyle(document.querySelector(".brand")).fontFamily.includes("Prata")')
            check('intro_removed_without_reserved_space', '!document.querySelector(".project-line") && document.querySelector(".navline").getBoundingClientRect().top-document.querySelector(".topline").getBoundingClientRect().bottom<2')
            check('role_from_server_no_demo_controls', 'state.role==="user" && !document.querySelector("#role-select") && !document.querySelector("script[src*=fixture]") && document.querySelector("#chat-text").disabled')
            check('no_drag_or_synthetic_event_action', '!document.querySelector("[draggable=true],#simulate-event")')
            screenshot('atlas-tasks-desktop')
            # Native source changes drive the existing card node, not a demo event.
            js('window.atlasMotionCount=0;window.realAtlasAnimate=Element.prototype.animate;Element.prototype.animate=function(...args){if(this.classList.contains("task-wrap")) atlasMotionCount++;return realAtlasAnimate.apply(this,args)};true;')
            js('window.savedAtlasCard=document.querySelector("[data-column=done] [data-task-id]");true;')
            native.items[0].update(authoredStatus='planned', readiness='unknown', nativeStatus='active', queue=[{'qitemId':'synthetic-transition','state':'in-progress','destinationSession':'platform-developer@opentour-rig','summary':'Synthetic active work'}])
            click('#refresh')
            wait('savedAtlasCard.closest(".column")?.dataset.column==="in_progress"')
            check('source_transition_one_stable_card', 'document.querySelectorAll(`[data-task-id="${savedAtlasCard.dataset.taskId}"]`).length===1 && document.querySelector(`[data-task-id="${savedAtlasCard.dataset.taskId}"]`)===savedAtlasCard')
            check('vertical_collapse_expand_ran', 'atlasMotionCount===2')
            js('window.realAtlasMatchMedia=window.matchMedia;window.matchMedia=q=>q.includes("prefers-reduced-motion") ? {matches:true} : realAtlasMatchMedia(q);true;')
            native.items[0].update(authoredStatus='complete', readiness='ready', nativeStatus='done', queue=[])
            click('#refresh');wait('savedAtlasCard.closest(".column")?.dataset.column==="done"')
            check('reduced_motion_skips_animation', 'atlasMotionCount===2')
            js('window.matchMedia=window.realAtlasMatchMedia;true;')
            click('#refresh');click('#refresh')
            check('duplicate_refresh_no_duplicate_card', 'document.querySelectorAll(`[data-task-id="${savedAtlasCard.dataset.taskId}"]`).length===1')
            click('[data-view=clients]');wait('!!document.querySelector(".client-row[data-object-id]")')
            check('two_equal_width_rounded_client_blocks', '(()=>{const a=document.querySelector(".client-filters-block"),b=document.querySelector(".client-table-block"),h=document.querySelector(".client-base-heading");return Math.abs(a.getBoundingClientRect().width-b.getBoundingClientRect().width)<1 && a.getBoundingClientRect().bottom<h.getBoundingClientRect().top && h.getBoundingClientRect().bottom<b.getBoundingClientRect().top && parseFloat(getComputedStyle(a).borderRadius)>0 && parseFloat(getComputedStyle(b).borderRadius)>0})()')
            check('actual_count_source_not_dossier_fixture', 'document.querySelector("#client-total").textContent===String(state.clients.total) && !document.querySelector(".dossier") && document.querySelector(".client-base-heading").textContent.includes("CRM")')
            screenshot('atlas-clients-desktop')
            js('document.querySelectorAll(".client-row[data-object-id]")[1].click();true;')
            wait('!!document.querySelector(".related-tasks button")')
            click('.related-tasks button');wait('!!document.querySelector("#app-response-text")')
            run('fill', '#app-response-text', 'Synthetic Atlas retained draft')
            click('#refresh')
            wait('!state.appBusy && !state.boardBusy')
            check('refresh_retains_linked_reply_draft', 'document.querySelector("#app-response-text").value==="Synthetic Atlas retained draft"')
            click('.app-response button');wait('document.querySelectorAll(".app-message").length===2 && document.querySelector("#app-response-text").value===""')
            check('saved_reply_in_actual_right_panel', 'document.querySelectorAll("#messages .message").length===2 && document.querySelector("#messages").textContent.includes("Synthetic Atlas retained draft")')
            run_batch(store, SyntheticTransport())
            click('.app-task-detail > button:not([data-return-client])')
            wait('document.querySelector("#messages").textContent.includes("Контекст доставлен")')
            check('real_delivery_readback_not_processing_claim', 'document.querySelector(".app-history").textContent.includes("Обработка агентом: не подтверждена")')
            click('#done-detail');wait('!document.querySelector("#detail-dialog").open')
            run('set', 'viewport', '390', '844')
            wait('document.querySelector("#conversation").hidden')
            check('mobile_client_blocks_fit', 'document.documentElement.scrollWidth<=innerWidth && Math.abs(document.querySelector(".client-filters-block").offsetWidth-document.querySelector(".client-table-block").offsetWidth)<1')
            screenshot('atlas-clients-mobile')
            run('click', '#dialog-toggle')
            check('mobile_panel_traps_background', 'document.querySelector("#main").inert && document.querySelector("#conversation").getAttribute("aria-modal")==="true" && document.activeElement.id==="dialog-close"')
            run('press', 'Shift+Tab')
            check('mobile_panel_keyboard_wrap', 'document.querySelector("#conversation").contains(document.activeElement)')
            run('press', 'Escape')
            check('mobile_panel_close_returns_focus', '!document.querySelector("#main").inert && document.activeElement.id==="dialog-toggle"')
            click('#disconnect');connect('administrator')
            check('administrator_role_server_observed', 'state.role==="administrator" && document.querySelector("#session-role").textContent.includes("Администратор") && document.querySelector("#chat-text").disabled')
            click('[data-view=campaigns]');wait('!!document.querySelector(".campaign-card")')
            check('existing_campaign_stays_fixture_unsent', 'document.querySelector("#campaigns-view").textContent.includes("NOT SENT") && document.querySelector("#campaigns-view").textContent.includes("FIXTURE")')
            click('#disconnect')
            check('disconnect_clears_panel_history', 'document.querySelector("#workspace").hidden && !document.querySelector("#messages .message") && !state.drafts.size')
            detail = store.detail(USER, task['id'])
            if len(detail['messages']) != 2 or detail['messages'][1]['reply_to'] != detail['messages'][0]['id']:
                raise RuntimeError('synthetic_database_linkage_failed')
            print(json.dumps({'mode':'SYNTHETIC ONLY','passed':len(checks),'checks':checks,'crm_access':False,'native_business_writes':False}))
        finally:
            run('close');server.shutdown();server.server_close();thread.join()


if __name__ == '__main__': main()

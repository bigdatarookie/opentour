"""Synthetic native source and targeted workflow for the existing UI browser harness."""
import copy
import json
import threading
from backend.adapters import Failure
from backend.core import Service
from test_backend import slice_fixture
from test_native_observations import Native, row, audit, TAGS, OWNER, WORK


class NoCRM:
    def __getattr__(self, name):raise AssertionError('No CRM in observation UI proof')


class ObservationNative(Native):
    def __init__(self):
        super().__init__()
        self.rows['original']=row('original',blockedOn='ask',tsUpdated='2026-11-09T02:00:00Z')
        self.rows['ask']=row('ask',state='pending',sourceSession=OWNER,destinationSession='human@external',blockedOn=None)
        self.rows['other']=row('other',state='in-progress',blockedOn=None)
        self.events=[];self.fail=False;self.response_project=None
        self.hold=False;self.waiting=threading.Event();self.release=threading.Event()
    def snapshot(self):
        rows=copy.deepcopy(list(self.rows.values()))
        for item in rows:item['summary']='Синтетическое поручение: проверка состояния'
        return [slice_fixture(queue=rows,title='Наблюдения ответа: проверка состояния исходного поручения',currentContext='Синтетический источник для проверки чтения. Реальных решений нет.',lastResult='Подготовлена синтетическая проверка нативных наблюдений.'),
                slice_fixture(name='05-journey-qa',sourceId='OT.0.1.0.5',queue=[],title='Работа без текущих поручений')],self.complete
    def get(self,path,params=None):
        if path=='/api/mission-control/audit':
            if self.fail:raise Failure('native_audit_unavailable',503)
            if self.hold and params['qitem_id']=='original':
                self.hold=False;self.waiting.set()
                if not self.release.wait(timeout=10):raise Failure('synthetic_timeout',503)
        return super().get(path,params)


class ObservationService(Service):
    def native_decisions(self,*args):
        result=super().native_decisions(*args)
        if self.native.response_project:result['project']=self.native.response_project
        return result


def answer_event():
    event=audit('ask','answer');event['beforeState']['state']='pending';event['afterState']['state']='done'
    return event


def exercise(args,run,evaluate,wait,check,click,native,auth,token,port,checks):
    panel='.native-observation'
    def loaded(value='unconfirmed'):wait('document.querySelector(".native-observation")?.dataset.state==='+json.dumps(value))
    def refresh():click('.observation-controls button')
    def shot(name):
        if args.proof_dir:
            args.proof_dir.mkdir(parents=True,exist_ok=True)
            run('screenshot',str(args.proof_dir.resolve()/name))
    def open_task(work=WORK):
        click('[data-object-id="'+work+'"]');wait('document.querySelector(".native-observation")!==null')
    run('open','http://127.0.0.1:'+str(port));run('set','viewport','1440','1000')
    check('no_observations_before_access','!document.querySelector(".native-observation") && !document.querySelector(".task-card")')
    evaluate('document.querySelector("#access-token").value='+json.dumps(token)+';document.querySelector("#connect-form").requestSubmit();true;')
    wait('document.querySelectorAll(".task-card").length===2')
    check('synthetic_mode_visible','!document.querySelector("#synthetic-banner").hidden')
    open_task();loaded()
    run('select','.observation-select','original');loaded()
    check('unconfirmed_is_not_empty_success','document.querySelector(".observation-empty").textContent.includes("не подтверждён") && document.querySelector(".observation-result").textContent.includes("Ожидает действия")')
    check('current_ask_state_visible','[...document.querySelectorAll(".native-observation dd")].some(el=>el.textContent === "Ожидает")')
    check('no_reply_or_mutation_controls','!document.querySelector("#detail-dialog textarea,#detail-dialog input") && ![...document.querySelectorAll("#detail-dialog button")].some(el=>/Ответить|Возобновить|Отправить|Утвердить/.test(el.textContent))')
    evaluate('document.querySelector(".native-observation").scrollIntoView();true;');shot('native-unconfirmed-desktop.png')
    native.rows['ask']['state']='done';native.rows['reply']=row('reply',state='pending',sourceSession='human@external',destinationSession=OWNER,replyTo='ask',tags=TAGS+['human-answer'])
    native.events=[answer_event()]
    refresh();loaded('observed')
    check('audit_and_linked_reply_displayed','document.querySelector(".observation-events").textContent.includes("Запись аудита ответа") && document.querySelector(".observation-events").textContent.includes("возврат ответа наблюдался")')
    check('observation_does_not_claim_identity_or_resume','document.querySelector(".native-observation").textContent.includes("Личность менеджера, принятие решения и продолжение работы не подтверждены") && document.querySelector(".observation-events").textContent.includes("не подтверждены")')
    native.complete=False;native.has_more=True;refresh();loaded('observed')
    check('incomplete_window_disclosed','document.querySelector(".native-observation").textContent.includes("Окно наблюдений неполное")')
    native.complete=True;native.has_more=False
    native.fail=True;refresh();loaded('error')
    check('source_failure_not_no_observations','!!document.querySelector(".observation-error") && !document.querySelector(".observation-empty") && document.querySelector("#detail-dialog").open')
    native.fail=False;refresh();loaded('observed')
    check('retry_keeps_task_and_selection','document.querySelector(".observation-select").value === "original" && document.querySelector("#detail-dialog").open')
    native.response_project='other';refresh();loaded('error')
    check('mismatched_response_scope_refused','!!document.querySelector(".observation-error") && !document.querySelector(".observation-events")')
    native.response_project=None;refresh();loaded('observed')
    run('set','viewport','390','844');evaluate('document.querySelector(".native-observation").scrollIntoView();true;')
    check('mobile_layout_and_close_reachable','document.documentElement.scrollWidth<=innerWidth && document.querySelector(".native-observation").getBoundingClientRect().right<=innerWidth && document.querySelector(".dialog-footer button").getBoundingClientRect().bottom<=document.querySelector("#detail-dialog").getBoundingClientRect().bottom')
    shot('native-observed-mobile.png')
    evaluate('document.querySelector(".observation-select").focus({preventScroll:true});window.observationScroll=document.querySelector("#detail-body").scrollTop;loadBoard(true);true;')
    wait('!state.boardBusy && state.modal.version === state.board.items.find(item=>item.id===state.modal.id)?.version && document.querySelector(".native-observation")?.dataset.state==="observed"')
    check('board_refresh_preserves_observation_focus_and_scroll','document.activeElement.matches(".observation-select") && Math.abs(document.querySelector("#detail-body").scrollTop-window.observationScroll)<2')
    check('board_refresh_preserves_modal_selection','document.querySelector("#detail-dialog").open && document.querySelector(".observation-select").value === "original"')
    # Board content is unchanged now, but source audit can change independently.
    native.events=[];native.rows.pop('reply');refresh();loaded()
    evaluate('loadBoard(true);true;');wait('!state.boardBusy');loaded()
    native.events=[answer_event()]
    evaluate('loadBoard(true);true;');loaded('observed')
    check('unchanged_board_refresh_reads_observations','document.querySelector(".observation-select").value === "original" && document.querySelector(".observation-events").textContent.includes("Запись аудита ответа")')
    native.events=[];native.rows['ask']['state']='pending'
    refresh();loaded();native.hold=True;refresh()
    if not native.waiting.wait(timeout=5):raise RuntimeError('synthetic_delayed_read_not_started')
    # Selection change can finish while the original request is still in flight.
    run('select','.observation-select','other');loaded()
    native.release.set()
    run('wait','--load','networkidle')
    check('late_response_cannot_replace_new_selection','document.querySelector(".observation-select").value === "other" && document.querySelector(".observation-result").textContent.includes("Исходное поручение: other") && !document.querySelector(".observation-result").textContent.includes("Текущий запрос: ask")')
    run('press','Escape');check('escape_restores_original_card_focus','document.activeElement.dataset.objectId === '+json.dumps(WORK))
    open_task('work:opentour:01-local-information-layer:05-journey-qa')
    check('no_current_original_is_explicit','document.querySelector(".native-observation").dataset.state === "no-source" && !document.querySelector(".observation-select")')
    run('press','Escape');open_task();loaded()
    auth.grants.clear();refresh();wait('document.querySelector("#workspace").hidden')
    check('revoked_auth_clears_visible_observations','!document.querySelector(".native-observation") && !document.querySelector("#detail-dialog").open && !document.querySelector(".task-card")')
    forbidden=[path for path,_ in native.calls if not path.startswith(('/api/queue/','/api/mission-control/audit'))]
    if forbidden:raise RuntimeError('unexpected_source_path')
    print(json.dumps({'mode':'native-synthetic','outcome':'passed','checks':checks,'crm_access':False,'private_credential_files_access':False,'native_writes':False,'real_human_identity':False,'screenshots':'synthetic_only' if args.proof_dir else 'none'}));return 0


def exercise_live(args,run,evaluate,wait,check,click,native,auth,token,port,checks):
    run('open','http://127.0.0.1:'+str(port));run('set','viewport','1440','1000')
    check('no_observations_before_access','!document.querySelector(".native-observation") && !document.querySelector(".task-card")')
    evaluate('document.querySelector("#access-token").value='+json.dumps(token)+';document.querySelector("#connect-form").requestSubmit();true;')
    wait('document.querySelectorAll(".task-card").length>0')
    check('real_native_mode_visible','document.querySelector("#synthetic-banner").hidden')
    click('[data-object-id="'+WORK+'"]');wait('document.querySelector(".observation-select")!==null')
    run('select','.observation-select',args.native_original_id)
    wait('["observed","unconfirmed"].includes(document.querySelector(".native-observation")?.dataset.state)')
    check('real_native_observation_displayed','document.querySelector(".observation-select").value === '+json.dumps(args.native_original_id)+' && document.querySelector(".observation-result").textContent.includes("Исходное поручение")')
    check('no_human_authority_or_action_claim','document.querySelector(".native-observation").textContent.includes("Личность менеджера, принятие решения и продолжение работы не подтверждены") && !document.querySelector("#detail-dialog textarea,#detail-dialog input")')
    click('.observation-controls button')
    wait('["observed","unconfirmed"].includes(document.querySelector(".native-observation")?.dataset.state)')
    check('refresh_keeps_real_task','document.querySelector("#detail-dialog").open && document.querySelector(".observation-select").value === '+json.dumps(args.native_original_id))
    run('set','viewport','390','844');evaluate('document.querySelector(".native-observation").scrollIntoView();true;')
    check('real_mobile_layout_fits','document.documentElement.scrollWidth<=innerWidth && document.querySelector(".native-observation").getBoundingClientRect().right<=innerWidth && document.querySelector(".dialog-footer button").getBoundingClientRect().bottom<=document.querySelector("#detail-dialog").getBoundingClientRect().bottom')
    run('press','Escape');check('real_focus_returns_to_task','document.activeElement.dataset.objectId === '+json.dumps(WORK))
    click('#disconnect');check('disconnect_clears_real_observations','!document.querySelector(".native-observation") && !document.querySelector(".task-card")')
    print(json.dumps({'mode':'live-native','outcome':'passed','checks':checks,'crm_access':False,'private_credential_files_access':False,'native_writes':False,'real_human_identity':False,'source_values_emitted':False,'screenshots':'none'}));return 0

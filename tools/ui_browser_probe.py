#!/usr/bin/env python3
"""Isolated browser read-path checks. Screenshots are synthetic-only; live output is aggregate-only."""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from backend.adapters import EspoCRM, Failure, NativeWork
from backend.core import Auth, MISSION, Service
from backend.server import make_server
from test_backend import CRMFixture, NativeFixture, row, slice_fixture


class SyntheticCRM(CRMFixture):
    def __init__(self):
        super().__init__()
        self.fail = False
        self.records['Contact'][1].update(name='Анна Примерова', firstName='Анна', lastName='Примерова', emailAddress='anna@example.invalid')
        self.records['Account'][0].update(name='Школа «Пример»', emailAddress='school@example.invalid')
        for i in range(3, 16):
            self.records['Contact'].append({'id': 'p' + str(i), 'name': 'Клиент Пример ' + str(i), 'emailAddress':'example' + str(i) + '@example.invalid'})

    def list(self, *args, **kwargs):
        if self.fail:
            raise Failure('source_unavailable', 503)
        if kwargs.get('query') == 'slow':
            time.sleep(1)
        return super().list(*args, **kwargs)


def synthetic_native():
    native = NativeFixture()
    native.items = [
        slice_fixture(name='01-local-crm', sourceId='OT.0.1.0.1', authoredStatus='complete', nativeStatus='done', readiness='ready', queue=[],
                      lastResult='Локальная CRM подключена. Проверены чтение и сохранность данных.', currentContext='Окружение готово для следующего этапа.'),
        slice_fixture(name='02-contact-import', sourceId='OT.0.1.0.2', queue=[row(state='blocked',blockedOn='external:mapping',summary='Уточнить сопоставление полей источника')],
                      lastResult='Подготовлено сопоставление полей. Спорные записи выделены отдельно.', currentContext='Импорт не повторяется до уточнения сопоставления.'),
        slice_fixture(name='03-operator-board',sourceId='OT.0.1.0.3',queue=[row(owner='platform-qa-code@opentour-rig')],
                      lastResult='Клиенты и задачи доступны в режиме просмотра. Идёт независимая проверка.', currentContext='Проверяется путь от доски к деталям задачи.'),
        slice_fixture(name='04-campaign-draft',sourceId='OT.0.1.0.4',queue=[row(owner='example-person@external',humanIntent='decision',summary='Проверить условия оффера и цену')],
                      lastResult='Подготовлен первый пакет: оффер, письмо и условия для проверки.',currentContext='Нужна проверка предложения. Рассылка не отправлена.'),
        slice_fixture(name='05-journey-qa',sourceId='OT.0.1.0.5',nativeStatus='planned',queue=[],lastResult=None,currentContext='Проверка начнётся после готовности основных связей.')]
    return native


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--organization-detail',action='store_true',help='Focused synthetic populated Organization detail proof; no live sources or screenshots')
    parser.add_argument('--native-observations', action='store_true', help='Targeted native-observation UI checks; no CRM')
    parser.add_argument('--native-work-root',type=Path,help='With native-observations: existing native specification root, no screenshots')
    parser.add_argument('--native-original-id',help='With native-work-root: existing original task in the selected board slice')
    parser.add_argument('--crm-credential-file', type=Path)
    parser.add_argument('--proof-dir', type=Path, help='Synthetic screenshots only')
    parser.add_argument('--browser', default='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    args = parser.parse_args()
    if args.native_work_root and (not args.native_observations or not args.native_original_id or args.proof_dir):
        parser.error('native-work-root requires native-observations and native-original-id; screenshots forbidden')
    if args.native_original_id and not args.native_work_root:
        parser.error('native-original-id requires native-work-root')
    if args.organization_detail and (args.live or args.native_observations or args.native_work_root or args.crm_credential_file or args.proof_dir):
        parser.error('organization-detail is isolated synthetic-only and forbids credential files/screenshots')
    sensitive_live=bool(args.live or args.native_work_root)
    if args.native_observations and args.live:
        parser.error('native-observations is synthetic-only')
    if args.live and (not args.crm_credential_file or args.proof_dir):
        parser.error('live requires a CRM reference and forbids screenshots')
    if args.crm_credential_file and not args.live:
        parser.error('synthetic runs never use a CRM credential')
    crm = EspoCRM(credential_file=args.crm_credential_file) if args.live else SyntheticCRM()
    native = NativeWork(ROOT / 'opentour-rig', MISSION) if args.live else synthetic_native()
    if args.native_observations:
        from native_observation_ui_fixture import ObservationNative, NoCRM
        native,crm=(NativeWork(args.native_work_root,MISSION) if args.native_work_root else ObservationNative()),NoCRM()
    if args.organization_detail:
        from organization_detail_ui_fixture import OrganizationFixture, EmptyNative
        crm,native=OrganizationFixture(),EmptyNative()
    token = secrets.token_urlsafe(32)
    auth = Auth(grants=[{'subject':'ephemeral-browser-diagnostic','role':'user','projects':['opentour'],
                        'tokenSha256':hashlib.sha256(token.encode()).hexdigest()}])
    service=Service(crm,native)
    if args.native_observations and not args.native_work_root:
        from native_observation_ui_fixture import ObservationService
        service=ObservationService(crm,native)
    server = make_server(service,auth,0,data_mode='live' if sensitive_live else 'synthetic')
    thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    mode='organization-synthetic' if args.organization_detail else 'live-native' if args.native_work_root else 'native-synthetic' if args.native_observations else 'live' if args.live else 'synthetic'
    session_result = subprocess.run(['agent-browser','session','id','--scope','worktree','--prefix','opentour-ui-'+mode],capture_output=True,text=True,timeout=10)
    session = session_result.stdout.strip()
    if session_result.returncode or not session:
        server.shutdown();server.server_close();raise RuntimeError('browser_session_unavailable')
    checks=[]
    with tempfile.TemporaryDirectory(prefix='opentour-ui-browser-') as private:
        prefix=['agent-browser','--session',session,'--profile',str(Path(private)/'profile'),'--executable-path',args.browser,'--json']
        def run(*command, script=None):
            result=subprocess.run(prefix+list(command),input=script,capture_output=True,text=True,timeout=45)
            if result.returncode:
                # Never forward browser page content, selectors with data, or errors from a live page.
                if not sensitive_live:
                    print(json.dumps({'synthetic_browser_error':(result.stderr+result.stdout).replace(token,'[redacted]')[:1600]}))
                else:
                    message=(result.stderr+result.stdout).lower()
                    flags=[name for name in ('timeout','strict mode','not found','outside','covered','not visible','not attached') if name in message]
                    print(json.dumps({'live_browser_failure':command[0],'diagnostic_flags':flags}))
                raise RuntimeError('browser_command_failed_'+command[0])
            return result.stdout
        def evaluate(script):
            return run('eval','--stdin',script=script)
        def wait(condition):
            run('wait','--fn',condition)
        def check(name,condition):
            evaluate('if (!('+condition+')) throw new Error("probe_assertion"); true;')
            checks.append(name)
        def click(selector):
            run('snapshot','-i')  # Read only within this isolated process; never print page content.
            run('scrollintoview',selector)
            run('click',selector)
        try:
            if args.organization_detail:
                from organization_detail_ui_fixture import exercise
                return exercise(run,evaluate,wait,check,click,crm,token,server.server_port,checks)
            if args.native_observations:
                from native_observation_ui_fixture import exercise, exercise_live
                exercise_mode=exercise_live if args.native_work_root else exercise
                return exercise_mode(args,run,evaluate,wait,check,click,native,auth,token,server.server_port,checks)
            run('open','http://127.0.0.1:'+str(server.server_port))
            check('shell_without_data_before_access','!document.querySelector("#connect-panel").hidden && !document.querySelector(".task-card")')
            evaluate('document.querySelector("#access-token").value='+json.dumps(token)+';document.querySelector("#connect-form").requestSubmit();true;')
            wait('document.querySelectorAll(".task-card").length > 0')
            check('authorized_board_rendered','document.querySelectorAll(".task-card").length === 5')
            check('mode_label_correct',('document.querySelector("#synthetic-banner").hidden' if args.live else '!document.querySelector("#synthetic-banner").hidden'))
            run('set','viewport','1440','1000')
            if args.proof_dir:
                args.proof_dir.mkdir(parents=True,exist_ok=True)
                run('screenshot',str(args.proof_dir.resolve()/'tasks-desktop.png'),'--full')
            click('[data-object-id="work:opentour:01-local-information-layer:03-operator-board"]') if args.live else click('[data-column="in_progress"] .task-card')
            wait('document.querySelector("#detail-dialog").open && document.querySelector("#detail-body .detail-grid") !== null')
            check('work_details_read_only','!document.querySelector("#detail-dialog textarea") && document.querySelector("#detail-body").textContent.includes("только для просмотра")')
            run('press','Escape')
            check('escape_restores_task_focus','!document.querySelector("#detail-dialog").open && document.activeElement.classList.contains("task-card")')
            click('[data-view="clients"]')
            wait('document.querySelectorAll(".client-row:not(.client-header)").length > 0')
            check('clients_rendered','document.querySelector("#client-list").getAttribute("aria-busy") === "false"')
            if args.proof_dir:
                run('screenshot',str(args.proof_dir.resolve()/'clients-desktop.png'),'--full')
            click('.client-row:not(.client-header)')
            wait('document.querySelector("#detail-body .detail-grid") !== null')
            check('client_details_and_safe_crm_link','document.querySelector(".source-link").getAttribute("rel") === "noopener noreferrer" && document.querySelector(".source-link").href.startsWith("http://127.0.0.1:18082/#")')
            run('press','Escape')
            check('client_focus_restored','document.activeElement.classList.contains("client-row")')
            if not args.live:
                click('#next-page');wait('document.querySelector("#page-range").textContent.startsWith("13")')
                check('client_pagination','document.querySelectorAll(".client-row:not(.client-header)").length === 4')
                click('#previous-page');wait('document.querySelector("#page-range").textContent.startsWith("1–")')
            run('select','#client-kind','organization')
            wait('document.querySelector("#client-list").getAttribute("aria-busy") === "false"')
            check('organization_filter',('document.querySelector("#client-total").textContent === "0" && !!document.querySelector("#client-list .state-box")' if args.live else 'document.querySelectorAll(".client-row:not(.client-header)").length === 1'))
            run('fill','#client-search','opentour-unmatched-synthetic-query')
            run('press','Enter')
            wait('document.querySelector("#client-total").textContent === "0" && document.querySelector("#client-list").getAttribute("aria-busy") === "false"')
            check('empty_search_state','!!document.querySelector("#client-list .state-box")')
            evaluate('document.querySelector("#client-search").value="";document.querySelector("#client-kind").value="person";document.querySelector("#client-kind").dispatchEvent(new Event("change"));true;')
            wait('document.querySelectorAll(".client-row:not(.client-header)").length > 0')
            if not args.live:
                crm.fail=True
                click('#refresh');wait('document.querySelector("#client-list").getAttribute("aria-busy") === "false"')
                check('crm_error_not_empty_success','document.querySelector("#client-list").textContent.includes("CRM недоступна") && document.querySelector("#client-total").textContent === "—"')
                crm.fail=False
                click('#client-list .state-box button');wait('document.querySelectorAll(".client-row:not(.client-header)").length > 0')
                check('retry_preserves_filter','document.querySelector("#client-kind").value === "person"')
                crm.records['Contact'][1]['name']='<img src=x onerror="window.injected=true">'
                click('#refresh');wait('document.querySelector("#client-list").getAttribute("aria-busy") === "false"')
                check('crm_text_not_executable','!document.querySelector("#client-list img") && !window.injected && document.querySelector("#client-list").textContent.includes("<img")')
                crm.records['Contact'][1]['name']='Анна Примерова'
            click('[data-view="tasks"]')
            run('set','viewport','390','844')
            check('mobile_no_page_overflow','document.documentElement.scrollWidth <= innerWidth')
            if args.proof_dir:
                run('screenshot',str(args.proof_dir.resolve()/'tasks-mobile.png'))
            click('[data-object-id="work:opentour:01-local-information-layer:03-operator-board"]') if args.live else click('[data-column="in_progress"] .task-card')
            wait('document.querySelector("#detail-body .detail-grid") !== null')
            check('mobile_dialog_fits','document.querySelector("#detail-dialog").getBoundingClientRect().width <= innerWidth && document.querySelector("#detail-dialog").open')
            if not args.live:
                item=native.items[1]
                item.update(authoredStatus='complete',nativeStatus='done',readiness='ready',queue=[],lastResult='Синтетическое обновление завершено.')
                evaluate('loadBoard(true);true;')
                wait('document.querySelector("#detail-body .details-meta dd").textContent === "Выполнено"')
                check('refresh_keeps_open_dialog_and_single_card','document.querySelector("#detail-dialog").open && [...document.querySelectorAll("[data-object-id]")].filter(el => el.dataset.objectId === "work:opentour:01-local-information-layer:02-contact-import").length === 1')
            run('press','Escape')
            check('token_not_persisted','localStorage.length === 0 && sessionStorage.length === 0 && document.querySelector("#access-token").value === ""')
            evaluate('document.querySelector("#client-search").value="synthetic-search-to-clear";true;')
            click('#disconnect')
            check('disconnect_clears_data','document.querySelector("#workspace").hidden && !document.querySelector(".task-card") && !document.querySelector(".client-row:not(.client-header)") && document.querySelector("#client-search").value === "" && document.querySelector("#detail-title").textContent === "Подробности"')
            print(json.dumps({'mode':mode,'outcome':'passed','checks':checks,'screenshots':'synthetic_only' if args.proof_dir else 'none','record_values_emitted':False,'credentials_emitted':False}))
            return 0
        except Exception as error:
            print(json.dumps({'mode':mode,'outcome':'failed','passed_checks':checks,'error_type':str(error) if isinstance(error,RuntimeError) else type(error).__name__,'record_values_emitted':False,'credentials_emitted':False}))
            return 1
        finally:
            try: run('close')
            except Exception: pass
            server.shutdown();server.server_close();thread.join(timeout=5)


if __name__ == '__main__':
    sys.exit(main())

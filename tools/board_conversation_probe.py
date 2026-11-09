#!/usr/bin/env python3
"""Synthetic-only DB/HTTP/browser path; never contacts CRM or the native daemon."""
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
from test_board_conversations import ADMIN, USER, SyntheticTransport
from backend.context_delivery import run_batch


def main():
    checks = []
    session = subprocess.check_output(['agent-browser', 'session', 'id', '--scope', 'worktree', '--prefix', 'opentour-board-db-synthetic'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='opentour-board-browser-') as private:
        path = Path(private) / 'database' / 'board.sqlite3'
        store = BoardStore(path)
        task = store.create(ADMIN, {'requestId': 'browser-create-0001', 'title': 'Synthetic task discussion',
                 'description': 'Synthetic context; no real CRM or native data', 'section': 'tasks', 'requestText': 'Review synthetic draft?'})
        token = secrets.token_urlsafe(32)
        grant = {'subject': USER.subject, 'role': 'user', 'projects': ['opentour'],
                 'tokenSha256': hashlib.sha256(token.encode()).hexdigest(),
                 'board': {'read': True, 'respond': True, 'tasks': [task['id']]}}
        auth = Auth(grants=[grant])
        def start(port=0):
            server = make_server(Service(CRMFixture(), NativeFixture()), auth, port, data_mode='synthetic', board_store=BoardStore(path))
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            return server, thread
        server, thread = start()
        port = server.server_port
        prefix = ['agent-browser', '--session', session, '--profile', str(Path(private) / 'profile'),
                  '--executable-path', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--json']
        def run(*args, script=None):
            result = subprocess.run(prefix + list(args), input=script, capture_output=True, text=True, timeout=45)
            if result.returncode:
                raise RuntimeError('synthetic_browser_operation_failed: ' + args[0] + ' ' + (result.stderr + result.stdout).replace(token, '[redacted]')[:500])
            return result.stdout
        def evaluate(js): return run('eval', '--stdin', script=js)
        def wait(js): run('wait', '--fn', js)
        def check(name, js):
            evaluate('if (!(' + js + ')) throw new Error(' + json.dumps(name) + '); true;')
            checks.append(name)
        def open_task():
            evaluate('document.querySelector("#app-task-list button").click();true;')
            wait('!!document.querySelector(".app-response textarea")')
        try:
            run('open', 'http://127.0.0.1:' + str(port))
            check('no_discussion_before_access', 'document.querySelector("#app-tasks").hidden && !document.querySelector(".app-message")')
            evaluate('document.querySelector("#access-token").value=' + json.dumps(token) + ';document.querySelector("#connect-form").requestSubmit();true;')
            wait('!!document.querySelector("#app-task-list button")')
            check('existing_native_board_retained', '!!document.querySelector("#board .task-card")')
            open_task()
            check('request_visible_with_scoped_answer', 'document.querySelector(".app-message").textContent.includes("Review synthetic draft?") && document.querySelector("#app-response-target").value.startsWith("message_")')
            run('fill', '#app-response-text', 'Synthetic reply <img src=x onerror=alert(1)>')
            run('press', 'Escape')
            open_task()
            check('draft_survives_close', 'document.querySelector("#app-response-text").value.includes("Synthetic reply")')
            run('fill', '#app-response-text', '   ')
            evaluate('document.querySelector(".app-response").requestSubmit();true;')
            wait('document.querySelector(".app-response [role=status]").textContent.includes("Исправьте")')
            check('validation_error_allows_edit', '!document.querySelector("#app-response-text").readOnly && document.querySelector("#app-response-text").value === "   "')
            run('fill', '#app-response-text', 'Synthetic reply <img src=x onerror=alert(1)>')
            # Simulate HTTP response loss AFTER the app transaction has committed.
            evaluate('window.realBoardFetch=window.fetch;window.fetch=async (...args)=>{const r=await realBoardFetch(...args);if(String(args[0]).endsWith("/messages") && args[1]?.method === "POST") throw new Error("synthetic response loss");return r;};document.querySelector(".app-response").requestSubmit();true;')
            wait('document.querySelector(".app-response button").textContent.includes("Повторить")')
            check('unknown_save_keeps_frozen_intent', 'document.querySelector("#app-response-text").readOnly && document.querySelector("#app-response-text").value.includes("Synthetic reply")')
            evaluate('window.fetch=window.realBoardFetch;document.querySelector(".app-response").requestSubmit();true;')
            wait('document.querySelectorAll(".app-message").length === 2 && document.querySelector("#app-response-text").value === ""')
            check('retry_has_one_linked_answer', 'document.querySelectorAll(".app-message").length === 2 && document.querySelectorAll(".app-message")[1].textContent.includes("Ответ на запрос:")')
            check('text_is_inert', '!document.querySelector(".app-message img") && document.querySelectorAll(".app-message")[1].textContent.includes("<img")')
            check('saved_distinct_from_pending_delivery', 'document.querySelectorAll(".app-message")[1].textContent.includes("Сохранено") && document.querySelectorAll(".app-message")[1].textContent.includes("Ожидает доставки")')
            # Reopen the same database in a newly started backend, preserving only application data.
            run('press', 'Escape');server.shutdown();server.server_close();thread.join()
            server, thread = start(port)
            evaluate('document.querySelector("#refresh").click();true;')
            wait('!!document.querySelector("#app-task-list button")');open_task()
            check('restart_preserves_history', 'document.querySelectorAll(".app-message").length === 2')
            transport = SyntheticTransport();run_batch(BoardStore(path), transport)
            evaluate('document.querySelector(".app-task-detail > button").click();true;')
            wait('document.querySelector(".app-history").textContent.includes("Контекст доставлен в очередь")')
            check('delivered_not_agent_processing', 'document.querySelector(".app-history").textContent.includes("Обработка агентом: не подтверждена")')
            run('set', 'viewport', '390', '844')
            check('mobile_no_horizontal_overflow', 'document.documentElement.scrollWidth <= innerWidth')
            check('reply_mode_label', 'document.querySelector("#detail-mode").textContent.includes("сохраняется в OpenTour")')
            check('mobile_footer_reachable', 'document.querySelector("#done-detail").getBoundingClientRect().bottom <= document.querySelector("#detail-dialog").getBoundingClientRect().bottom')
            run('screenshot', '/tmp/opentour-board-conversation-synthetic.png')
            grant['board']['read'] = False
            evaluate('document.querySelector(".app-task-detail > button").click();true;')
            wait('document.querySelector("#workspace").hidden')
            check('revocation_clears_history_and_drafts', '!document.querySelector(".app-message") && document.querySelector("#app-task-list").children.length === 0')
            # Store content, not just browser count, proves the unknown response did not duplicate.
            detail = BoardStore(path).detail(USER, task['id'])
            if len(detail['messages']) != 2 or detail['messages'][1]['reply_to'] != detail['messages'][0]['id']:
                raise RuntimeError('database_link_or_duplicate_failure')
            print(json.dumps({'mode': 'SYNTHETIC ONLY', 'checks': checks, 'passed': len(checks),
                              'database_messages': 2, 'synthetic_deliveries': transport.sends,
                              'native_business_writes': False, 'crm_access': False}))
        finally:
            run('close');server.shutdown();server.server_close();thread.join()


if __name__ == '__main__':
    main()

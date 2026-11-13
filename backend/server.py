"""Run with python3 -m backend.server. Loopback, scoped application conversations and source reads."""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .adapters import EspoCRM, Failure, NativeWork, NativeObligation
from .core import Auth, MISSION, PROJECT, Service, WRITE_LIMITATION, version
from .campaign_preview import FixtureCampaign, CAMPAIGN_ID
from .board_store import BoardStore
from .web_config import deployment_url, ui_policy


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(15)
        return connection, address


STATIC = Path(__file__).resolve().parents[1] / 'ui'
UI_FILES = {'/': ('index.html', 'text/html; charset=utf-8'),
            '/ui/app.js': ('app.js', 'text/javascript; charset=utf-8'),
            '/ui/styles.css': ('styles.css', 'text/css; charset=utf-8'),
            '/ui/atlas.css': ('atlas.css', 'text/css; charset=utf-8'),
            '/ui/assets/Prata-Regular.ttf': ('assets/Prata-Regular.ttf', 'font/ttf'),
            '/ui/assets/Commissioner.ttf': ('assets/Commissioner.ttf', 'font/ttf')}


def make_server(service, auth, port=18083, data_mode='live', campaign=None, board_store=None, public_base_url=None, obligations=None, allowed_ui_origins=()):
    if data_mode not in ('live', 'synthetic'):
        raise ValueError('invalid data mode')
    ui_origins = frozenset(deployment_url(origin, origin_only=True) for origin in allowed_ui_origins)
    campaign = campaign or FixtureCampaign()
    obligations = obligations or NativeObligation()
    prefix,public_origin,public_host='','',''
    if public_base_url:
        public=urllib.parse.urlsplit(public_base_url)
        prefix=public.path.rstrip('/')
        if (public.scheme!='https' or not re.fullmatch(r'[A-Za-z0-9.-]+(?::[0-9]{1,5})?',public.netloc)
                or public.query or public.fragment or (prefix and not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)+',prefix))):
            raise ValueError('invalid_public_base_url')
        public_host=public.netloc.lower()
        public_origin='https://'+public_host
    class Handler(BaseHTTPRequestHandler):
        server_version = 'OpenTourLocal'

        def log_message(self, *_args):
            pass  # Request paths, filters, tokens and provider exceptions never enter logs.

        def respond(self, status, data=None, etag=None):
            raw = json.dumps(data, ensure_ascii=False).encode() if data is not None else b''
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'")
            self.send_header('Connection', 'close')
            self.send_header('Vary', 'Origin')
            if getattr(self, 'cors_origin', None):
                self.send_header('Access-Control-Allow-Origin', self.cors_origin)
                self.send_header('Access-Control-Expose-Headers', 'ETag')
                if status == 204:
                    self.send_header('Access-Control-Allow-Methods', 'GET, POST')
                    self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type, If-None-Match')
            if etag:
                self.send_header('ETag', etag)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def ui_file(self, path):
            if path == '/ui/campaign-email.css':
                raw, content_type = campaign.stylesheet(), 'text/css; charset=utf-8'
            else:
                filename, content_type = UI_FILES[path]
                raw = (STATIC / filename).read_bytes()
                if filename=='index.html':
                    raw=raw.replace(b'name="opentour-base" content=""',('name="opentour-base" content="'+prefix+'"').encode())
                if prefix and content_type.startswith(('text/html','text/css')):
                    raw=raw.replace(b'"/ui/',('"'+prefix+'/ui/').encode()).replace(b"'/ui/",("'"+prefix+'/ui/').encode())
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', ui_policy() + "; frame-ancestors 'none'")
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(raw)

        def handle_request(self):
            self.cors_origin = None
            try:
                allowed = {'127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)}
                if public_host:allowed.add(public_host)
                if len(self.headers.get_all('Host', [])) != 1 or self.headers.get('Host') not in allowed:
                    raise Failure('host_forbidden', 403)
                origin = self.headers.get('Origin')
                if len(self.headers.get_all('Origin', [])) > 1:
                    raise Failure('origin_forbidden', 403)
                same_origins = {'http://127.0.0.1:'+str(self.server.server_port),'http://localhost:'+str(self.server.server_port)} | ({public_origin} if public_origin else set())
                if origin and origin not in same_origins | ui_origins:
                    raise Failure('origin_forbidden', 403)
                url = urllib.parse.urlsplit(self.path)
                if url.scheme or url.netloc or len(self.path) > 4096:
                    raise Failure('invalid_request', 400)
                path = urllib.parse.unquote(url.path)
                if prefix and (path==prefix or path.startswith(prefix+'/')):
                    path=path[len(prefix):] or '/'
                if origin in ui_origins and origin not in same_origins:
                    if not path.startswith('/api/'):
                        raise Failure('cors_route_forbidden', 403)
                    self.cors_origin = origin
                    if self.command not in ('GET', 'POST', 'OPTIONS'):
                        raise Failure('cors_method_forbidden', 403)
                if self.command == 'OPTIONS':
                    requested = self.headers.get('Access-Control-Request-Method')
                    headers = self.headers.get('Access-Control-Request-Headers', '')
                    if (not self.cors_origin or requested not in ('GET', 'POST')
                            or len(self.headers.get_all('Access-Control-Request-Method', [])) != 1
                            or len(self.headers.get_all('Access-Control-Request-Headers', [])) > 1
                            or any(h.strip().lower() not in ('authorization', 'content-type', 'if-none-match') for h in headers.split(',') if h.strip())):
                        raise Failure('cors_preflight_forbidden', 403)
                    return self.respond(204)
                if self.command == 'GET' and (path in UI_FILES or path == '/ui/campaign-email.css') and not url.query:
                    # Public shell has no embedded data, tokens, source URLs or private files.
                    return self.ui_file(path)
                if self.command == 'GET' and path == '/healthz':
                    return self.respond(200, {'status': 'ok', 'service': 'opentour-read-backend', 'integrationReady': False})
                principal = auth.authorize(self.headers.get('Authorization'))
                query = urllib.parse.parse_qs(url.query, keep_blank_values=True, max_num_fields=12)
                if any(len(v) != 1 for v in query.values()):
                    raise Failure('duplicate_query_parameter', 400)
                params = {k: v[0] for k, v in query.items()}
                if params.get('project', PROJECT) != PROJECT:
                    raise Failure('project_forbidden', 403)
                params.pop('project', None)
                if principal.board_only and path != '/api/capabilities' and path != '/api/board-tasks' and not path.startswith('/api/board-tasks/'):
                    raise Failure('board_only_source_access_forbidden',403)
                if path == '/api/board-tasks' or path.startswith('/api/board-tasks/'):
                    if not board_store:
                        raise Failure('board_store_not_configured', 503)
                    if params:
                        raise Failure('unknown_query_parameter', 400)
                    parts = path[len('/api/board-tasks'):].strip('/').split('/') if path != '/api/board-tasks' else []
                    if self.command == 'GET' and len(parts) <= 1:
                        data = board_store.detail(principal, parts[0]) if parts else board_store.list(principal)
                    elif self.command == 'POST' and (not parts or len(parts) == 2 and parts[1] == 'messages'):
                        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
                            raise Failure('content_length_required', 411)
                        raw_length = self.headers.get('Content-Length', '')
                        if not raw_length.isdigit() or not 0 < int(raw_length) <= 32768:
                            raise Failure('request_body_too_large', 413)
                        if self.headers.get('Content-Type') != 'application/json':
                            raise Failure('json_required', 415)
                        raw = self.rfile.read(int(raw_length))
                        if len(raw) != int(raw_length):
                            raise Failure('incomplete_body', 400)
                        body = json.loads(raw)
                        data = board_store.append(principal, parts[0], body, resolve_obligation=obligations.resolve) if parts else board_store.create(
                            principal, body, validate_client=lambda ref: service.client('crm:' + ref['entity'] + ':' + ref['externalId']), resolve_obligation=obligations.resolve)
                        return self.respond(200, data)
                    else:
                        raise Failure('board_route_forbidden', 403)
                elif self.command != 'GET':
                    # Only OpenTour conversation writes are exposed; native decisions remain closed.
                    raise Failure(WRITE_LIMITATION, 403)
                elif path == '/api/capabilities' and not params:
                    data = {'project': PROJECT, 'sourceReads': not principal.board_only, 'role': principal.role, 'reads': ['board-tasks'] if principal.board_only else ['clients', 'board', 'campaigns'], 'dataMode': data_mode,
                            'writes': {'enabled': False, 'scope': 'native_actions', 'reason': WRITE_LIMITATION},
                            'dialogue': {'enabled': False, 'reason': WRITE_LIMITATION},
                            'boardConversations': {'read': bool(board_store and principal.board_read),
                                'respond': bool(board_store and principal.board_read and principal.board_respond),
                                'create': bool(board_store and principal.board_read and principal.board_create and principal.role == 'administrator' and '*' in principal.board_tasks)}}
                elif path == '/api/clients':
                    if set(params) - {'kind', 'q', 'offset', 'limit', 'hasEmail', 'hasPhone'}:
                        raise Failure('unknown_query_parameter', 400)
                    data = service.clients(params)
                elif path.startswith('/api/clients/') and not params:
                    data = service.client(path[len('/api/clients/'):])
                    if board_store:
                        ref = {'entity': data['provenance']['entity'], 'externalId': data['provenance']['externalId']}
                        data['relatedWork'] = board_store.related(principal, ref) if principal.board_read else {
                            'items': [], 'status': 'board_access_not_granted', 'complete': False}
                        data['version'] = version({k: v for k, v in data.items() if k != 'version'})
                elif path == '/api/campaigns' and not params:
                    data = campaign.list()
                elif path == '/api/campaigns/' + CAMPAIGN_ID and not params:
                    data = campaign.detail(CAMPAIGN_ID)
                elif path.startswith('/api/campaigns/' + CAMPAIGN_ID + '/materials/') and not params:
                    data = campaign.material(path.split('/materials/', 1)[1])
                elif path.startswith('/api/board/') and '/native-decisions/' in path and not params:
                    work_id, original_id = path[len('/api/board/'):].split('/native-decisions/', 1)
                    data = service.native_decisions(work_id, original_id)
                elif path in ('/api/board',) or path.startswith('/api/board/'):
                    if params:
                        raise Failure('unknown_query_parameter', 400)
                    data = service.board()
                    if path != '/api/board':
                        key = path[len('/api/board/'):]
                        data = next((item for item in data['items'] if item['id'] == key), None)
                        if data is None:
                            raise Failure('work_not_found', 404)
                else:
                    raise Failure('route_not_found', 404)
                rev = data.get('version') or version(data)
                etag = '"' + rev + '"'
                if self.headers.get('If-None-Match') == etag:
                    return self.respond(304, etag=etag)
                return self.respond(200, data, etag)
            except Failure as exc:
                return self.respond(exc.status, {'error': exc.code})
            except (ValueError, UnicodeError):
                return self.respond(400, {'error': 'invalid_request'})
            except Exception:
                return self.respond(503, {'error': 'projection_unavailable'})

        do_GET = handle_request
        do_POST = handle_request
        do_PUT = handle_request
        do_PATCH = handle_request
        do_DELETE = handle_request
        do_OPTIONS = handle_request

    server = Server(('127.0.0.1', port), Handler)
    server.timeout = 10
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18083)
    parser.add_argument('--auth-file', type=Path, required=True, help='Private hashed project grants; board permissions are explicit, never native human identity')
    parser.add_argument('--crm-credential-file', type=Path, help='Private JSON containing read-only EspoCRM API key')
    parser.add_argument('--board-db', type=Path, default=Path.home() / '.local/share/opentour/board/board.sqlite3',
                        help='Private OpenTour application DB outside checkout/.artifacts')
    parser.add_argument('--public-base-url',help='Explicit HTTPS origin/prefix behind a trusted proxy; backend stays loopback')
    parser.add_argument('--allowed-ui-origin', action='append', default=[], help='Exact trusted static UI origin, no path; repeat explicitly. HTTPS or loopback HTTP only; no credential cookies')
    parser.add_argument('--work-root', type=Path, help='Existing registered OpenTour work root for native read projection')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    service = Service(EspoCRM(credential_file=args.crm_credential_file), NativeWork(args.work_root or root / 'opentour-rig', MISSION))
    with make_server(service, Auth(args.auth_file), args.port, board_store=BoardStore(args.board_db),public_base_url=args.public_base_url,allowed_ui_origins=args.allowed_ui_origin) as server:
        print('OpenTour local read backend listening on 127.0.0.1:' + str(server.server_port), flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()

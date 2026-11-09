"""Run with python3 -m backend.server. Loopback, authenticated reads only."""
from __future__ import annotations

import argparse
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .adapters import EspoCRM, Failure, NativeWork
from .core import Auth, MISSION, PROJECT, Service, WRITE_LIMITATION, version


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
            '/ui/styles.css': ('styles.css', 'text/css; charset=utf-8')}


def make_server(service, auth, port=18083, data_mode='live'):
    if data_mode not in ('live', 'synthetic'):
        raise ValueError('invalid data mode')
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
            if etag:
                self.send_header('ETag', etag)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def ui_file(self, path):
            filename, content_type = UI_FILES[path]
            raw = (STATIC / filename).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(raw)

        def handle_request(self):
            try:
                allowed = {'127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)}
                if len(self.headers.get_all('Host', [])) != 1 or self.headers.get('Host') not in allowed:
                    raise Failure('host_forbidden', 403)
                origin = self.headers.get('Origin')
                if origin and origin not in {'http://' + h for h in allowed}:
                    raise Failure('origin_forbidden', 403)
                url = urllib.parse.urlsplit(self.path)
                if url.scheme or url.netloc or len(self.path) > 4096:
                    raise Failure('invalid_request', 400)
                path = urllib.parse.unquote(url.path)
                if self.command == 'GET' and path in UI_FILES and not url.query:
                    # Public shell has no embedded data, tokens, source URLs or private files.
                    return self.ui_file(path)
                if self.command == 'GET' and path == '/healthz':
                    return self.respond(200, {'status': 'ok', 'service': 'opentour-read-backend', 'integrationReady': False})
                principal = auth.authorize(self.headers.get('Authorization'))
                if self.command != 'GET':
                    # No native mutation is reachable, even with an administrator grant.
                    raise Failure(WRITE_LIMITATION, 403)
                query = urllib.parse.parse_qs(url.query, keep_blank_values=True, max_num_fields=12)
                if any(len(v) != 1 for v in query.values()):
                    raise Failure('duplicate_query_parameter', 400)
                params = {k: v[0] for k, v in query.items()}
                if params.get('project', PROJECT) != PROJECT:
                    raise Failure('project_forbidden', 403)
                params.pop('project', None)
                if path == '/api/capabilities' and not params:
                    data = {'project': PROJECT, 'role': principal.role, 'reads': ['clients', 'board'], 'dataMode': data_mode,
                            'writes': {'enabled': False, 'reason': WRITE_LIMITATION},
                            'dialogue': {'enabled': False, 'reason': WRITE_LIMITATION}}
                elif path == '/api/clients':
                    if set(params) - {'kind', 'q', 'offset', 'limit', 'hasEmail', 'hasPhone'}:
                        raise Failure('unknown_query_parameter', 400)
                    data = service.clients(params)
                elif path.startswith('/api/clients/') and not params:
                    data = service.client(path[len('/api/clients/'):])
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
    parser.add_argument('--auth-file', type=Path, required=True, help='Private hashed read grants; never creates a human')
    parser.add_argument('--crm-credential-file', type=Path, help='Private JSON containing read-only EspoCRM API key')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    service = Service(EspoCRM(credential_file=args.crm_credential_file), NativeWork(root / 'opentour-rig', MISSION))
    with make_server(service, Auth(args.auth_file), args.port) as server:
        print('OpenTour local read backend listening on 127.0.0.1:' + str(server.server_port), flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()

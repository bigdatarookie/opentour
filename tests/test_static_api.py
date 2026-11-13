"""Explicit static API deployment configuration; disposable HTTP, no live services."""
import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from backend.core import Auth
from backend.server import make_server
from backend.web_config import deployment_url
from tools.build_static_ui import build


class StaticAPITests(unittest.TestCase):
    def setUp(self):
        self.token = 'synthetic-static-api-' + 'x'*32
        self.origin = 'http://127.0.0.1:19876'
        self.grant = {'subject':'synthetic-static-reader','role':'user','projects':['opentour'],
                      'tokenSha256':hashlib.sha256(self.token.encode()).hexdigest(),
                      'boardOnly':True,'board':{'read':True,'respond':True,'tasks':['synthetic-allowed']}}
        class NoSources:
            def __getattr__(self, _): raise AssertionError('source_must_not_be_reached')
        self.server = make_server(NoSources(), Auth(grants=[self.grant]), 0, data_mode='synthetic',
                                  public_base_url='https://protected.example.invalid/bridge', allowed_ui_origins=[self.origin])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, path='/bridge/api/capabilities', method='GET', origin=None, token=True, **headers):
        if origin is not None: headers['Origin']=origin
        if token: headers['Authorization']='Bearer '+self.token
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        connection.request(method, path, headers=headers)
        response=connection.getresponse(); data=response.read(); result=(response.status, dict(response.headers), data)
        connection.close(); return result

    def test_preflight_has_exact_allowlist_and_needs_no_bearer(self):
        status, headers, _ = self.request(method='OPTIONS', origin=self.origin, token=False,
            **{'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization, content-type, if-none-match'})
        self.assertEqual(status,204); self.assertEqual(headers['Access-Control-Allow-Origin'],self.origin)
        self.assertEqual(headers['Access-Control-Allow-Methods'],'GET, POST')
        self.assertNotIn('Access-Control-Allow-Credentials',headers)
        for extra in ({'Access-Control-Request-Method':'DELETE'},
                      {'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'x-impersonate'}, {}):
            self.assertEqual(self.request(method='OPTIONS',origin=self.origin,token=False,**extra)[0],403)

    def test_cross_origin_keeps_auth_and_scope_and_exposes_etag(self):
        status,headers,raw=self.request(origin=self.origin)
        self.assertEqual(status,200);self.assertEqual(json.loads(raw)['role'],'user')
        self.assertEqual(headers['Access-Control-Allow-Origin'],self.origin)
        self.assertEqual(headers['Access-Control-Expose-Headers'],'ETag');self.assertEqual(headers['Vary'],'Origin')
        self.assertEqual(self.request(origin=self.origin,**{'If-None-Match':headers['ETag']})[0],304)
        status,headers,_=self.request(origin=self.origin,token=False)
        self.assertEqual(status,401);self.assertEqual(headers['Access-Control-Allow-Origin'],self.origin)
        self.assertEqual(self.request('/bridge/api/clients',origin=self.origin)[0],403)
        self.assertEqual(self.request('/bridge/api/capabilities?project=foreign',origin=self.origin)[0],403)

    def test_unlisted_null_and_wrong_scheme_origins_denied(self):
        for origin in ('null','https://127.0.0.1:19876','http://127.0.0.1:19877',self.origin+'.invalid'):
            status,headers,_=self.request(origin=origin)
            self.assertEqual(status,403);self.assertNotIn('Access-Control-Allow-Origin',headers)
        self.assertEqual(self.request('/',origin=self.origin)[0],403)
        self.assertEqual(self.request(method='DELETE',origin=self.origin)[0],403)

    def test_root_same_origin_and_prefix_keep_current_assets(self):
        for path in ('/','/bridge/'):
            status,headers,raw=self.request(path,token=False)
            self.assertEqual(status,200);self.assertIn(b'content="/bridge"',raw)
            self.assertIn(b'content=""',raw);self.assertIn("connect-src 'self';",headers['Content-Security-Policy'])
        own='http://127.0.0.1:'+str(self.server.server_port)
        self.assertEqual(self.request('/api/capabilities',origin=own)[0],200)
        status,headers,_=self.request('/api/capabilities')
        self.assertEqual(status,200);self.assertNotIn('Access-Control-Allow-Origin',headers)

    def test_static_build_only_public_assets_exact_api_and_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'public'
            build(out,'https://protected.example.invalid/bridge')
            html=(out/'index.html').read_text()
            self.assertIn('name="opentour-api-base" content="https://protected.example.invalid/bridge"',html)
            self.assertIn('/opentour/ui/app.js',html)
            self.assertIn('connect-src &#x27;self&#x27; https://protected.example.invalid;',html)
            self.assertIn("'/opentour/ui/atlas.css'",(out/'ui/styles.css').read_text())
            self.assertTrue((out/'ui/campaign-email.css').is_file())
            self.assertEqual({str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()}, {'index.html','.nojekyll','ui/app.js','ui/styles.css','ui/atlas.css','ui/assets/Prata-Regular.ttf','ui/assets/Commissioner.ttf','ui/campaign-email.css'})
            with self.assertRaises(FileExistsError):build(out,'https://protected.example.invalid/bridge')

    def test_config_rejects_wildcards_paths_secrets_and_unsafe_transport(self):
        for value in ('*','null','https://*.example.invalid','https://user:pass@example.invalid',
                      'https://example.invalid?token=secret','https://example.invalid/#token',
                      'http://remote.example.invalid','https://example.invalid/../other',
                      'https://example.invalid:99999','https://EXAMPLE.invalid','https://example.invalid\\evil'):
            with self.subTest(value=value),self.assertRaises(ValueError):deployment_url(value)
        for value in ('https://example.invalid/','https://example.invalid/path'):
            with self.assertRaises(ValueError):deployment_url(value,origin_only=True)
        self.assertEqual(deployment_url('https://bigdatarookie.github.io',origin_only=True),'https://bigdatarookie.github.io')

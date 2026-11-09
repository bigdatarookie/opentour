"""Fixture campaign reads only. Never connect CRM, mailer, native actions or credentials."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from backend.adapters import Failure
from backend.campaign_preview import ARTIFACTS, FILES, CAMPAIGN_ID, LABELS, FixtureCampaign
from backend.core import Auth
from backend.server import make_server
from test_backend import GRANT, TOKEN


class NoSourceAccess:
    def clients(self, *_args, **_kwargs):
        raise AssertionError('CRM access is outside this assignment')

    def client(self, *_args, **_kwargs):
        raise AssertionError('CRM access is outside this assignment')

    def board(self):
        raise AssertionError('No native service access is needed')


class FixturePackageTests(unittest.TestCase):
    def test_existing_source_bytes_are_used_unchanged_with_truthful_labels(self):
        adapter=FixtureCampaign();detail=adapter.detail()
        self.assertEqual(detail['labels'],LABELS)
        self.assertEqual(detail['mode'],'FIXTURE')
        self.assertIsNone(detail['audience']['count'])
        self.assertEqual(detail['audience']['status'],'not_selected')
        self.assertIsNone(detail['sender']);self.assertIsNone(detail['providerId'])
        for name,expected in FILES.items():
            self.assertEqual(hashlib.sha256((ARTIFACTS/name).read_bytes()).hexdigest(),expected)
            self.assertEqual(adapter.material(name)['content'],(ARTIFACTS/name).read_text())
        self.assertEqual(detail['plainText'],(ARTIFACTS/'email-preview-r01.txt').read_text())
        self.assertEqual(detail['manifest'],(ARTIFACTS/'draft-r01.md').read_text())
        self.assertEqual(adapter.list()['items'][0]['id'],detail['id'])
        self.assertEqual(adapter.list()['items'][0]['version'],detail['version'])

    def test_price_terms_attribution_and_snapshot_caveats_survive(self):
        detail=FixtureCampaign().detail();text=detail['plainText']
        for fragment in ('160 000','2–3-местном','20 января 2027','октябрь','не актуальное','Неактивная кнопка'):
            self.assertIn(fragment,text)
        self.assertEqual(len(detail['sourceLinks']),2)
        self.assertIn('NOT CONTENT-APPROVED',detail['labels'])
        self.assertTrue(any('не является одобрением' in value for value in detail['caveats']))

    def test_inert_preview_preserves_source_layout_without_inline_or_external_loads(self):
        detail=FixtureCampaign().detail();html=detail['previewDocument']
        self.assertNotRegex(html,r'<(?:script|form|iframe|img)\b')
        self.assertNotRegex(html,r'href="https?://')
        self.assertNotIn('<style>',html)
        self.assertIn('href="/ui/campaign-email.css"',html)
        self.assertIn('disabled aria-disabled="true"',html)
        self.assertIn("default-src 'none'",html)
        source=(ARTIFACTS/'email-preview-r01.html').read_text()
        self.assertEqual(FixtureCampaign().stylesheet().decode(),re.search(r'<style>(.*?)</style>',source,re.S)[1])

    def test_missing_or_tampered_package_fails_instead_of_claiming_an_empty_provider(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'package';shutil.copytree(ARTIFACTS,root)
            (root/'email-preview-r01.html').write_text('<script>unsafe()</script> FIXTURE')
            with self.assertRaisesRegex(Failure,'campaign_fixture_revision_mismatch'):FixtureCampaign(root).detail()
            (root/'draft-r01.md').unlink()
            with self.assertRaisesRegex(Failure,'campaign_fixture_unavailable'):FixtureCampaign(root).list()

    def test_unknown_material_or_campaign_never_reads_an_arbitrary_path(self):
        for name in ('../secrets','../../.artifacts/private.csv','unknown.md'):
            with self.assertRaises(Failure):FixtureCampaign().material(name)
        with self.assertRaises(Failure):FixtureCampaign().detail('provider:campaign:invented')


class CampaignHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server=make_server(NoSourceAccess(),Auth(grants=[GRANT]),0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def get(self,path,token=TOKEN,method='GET'):
        headers={'Authorization':'Bearer '+token} if token else {}
        request=urllib.request.Request(self.base+path,headers=headers,method=method)
        try:response=urllib.request.urlopen(request,timeout=3)
        except urllib.error.HTTPError as error:response=error
        with response:
            raw=response.read();return response.status,raw,response.headers

    def test_campaign_list_detail_and_source_material_reads_need_project_grant(self):
        self.assertEqual(self.get('/api/campaigns',token=None)[0],401)
        status,raw,_=self.get('/api/campaigns');self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)['mode'],'FIXTURE')
        status,raw,_=self.get('/api/campaigns/'+CAMPAIGN_ID);self.assertEqual(status,200)
        self.assertIsNone(json.loads(raw)['audience']['count'])
        self.assertEqual(self.get('/api/campaigns/'+CAMPAIGN_ID+'/materials/draft-r01.md')[0],200)
        self.assertEqual(self.get('/api/campaigns?project=other')[0],403)
        self.assertEqual(self.get('/api/campaigns/provider-unknown')[0],404)
        self.assertEqual(self.get('/api/campaigns/'+CAMPAIGN_ID+'/materials/../../secrets')[0],404)

    def test_stylesheet_contains_only_fixed_presentation_and_keeps_parent_csp_strict(self):
        status,raw,headers=self.get('/ui/campaign-email.css',token=None)
        self.assertEqual(status,200);self.assertIn('text/css',headers['Content-Type'])
        self.assertNotIn('160 000',raw.decode());self.assertNotIn(TOKEN,raw.decode())
        self.assertIn("frame-src 'self'",headers['Content-Security-Policy'])
        self.assertNotIn('unsafe-inline',headers['Content-Security-Policy'])

    def test_no_send_approval_or_other_mutation_is_admitted(self):
        for path in ('/api/campaigns/'+CAMPAIGN_ID+'/send','/api/campaigns/'+CAMPAIGN_ID+'/approve','/api/campaigns'):
            self.assertEqual(self.get(path,method='POST')[0],403)


if __name__=='__main__':unittest.main()

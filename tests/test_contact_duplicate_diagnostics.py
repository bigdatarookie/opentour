"""Synthetic-only duplicate classification and declarative channel identity policy."""
import json
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from test_contact_import_identity_policy import importer


class DuplicateDiagnosticsTests(unittest.TestCase):
    def test_observed_duplicate_header_is_preserved_without_response_values(self):
        crm=importer.CRM.__new__(importer.CRM);crm.headers={}
        error=urllib.error.HTTPError('http://127.0.0.1/synthetic',409,'private response message',
            {'X-Status-Reason':'duplicate'},BytesIO(json.dumps({'duplicates':[{'id':'private-id','name':'private-name'}]}).encode()))
        with patch.object(importer.urllib.request,'urlopen',side_effect=error):
            with self.assertRaises(importer.ImportFailure) as caught: crm.call('POST','/Contact',{})
        self.assertEqual(caught.exception.code,'crm_http_409_duplicate')
        self.assertNotIn('private',str(caught.exception))

    def test_unknown_reason_and_other_status_are_not_reclassified(self):
        self.assertEqual(importer.safe_crm_error_code(409,{},'private server detail'),'crm_http_409')
        self.assertEqual(importer.safe_crm_error_code(400,{},'duplicate'),'crm_http_400')
        self.assertEqual(importer.safe_crm_error_code(409,None),'crm_http_409')

    def test_contact_profile_retains_native_channel_checks_and_no_name_identity(self):
        profile=Path(__file__).resolve().parents[1]/'local/crm/custom/Espo/Custom/Resources/metadata/scopes/Contact.json'
        self.assertEqual(json.loads(profile.read_text()),{'duplicateCheckFieldList':['emailAddress','phoneNumber']})
        self.assertNotIn('_skipDuplicateCheck',importer.build_contact_body({
            'source_ordinal':1,'source_revision':'a'*64,'logical_row':1,'mapping_version':'synthetic',
            'last_name':'None','email_raw':'synthetic@example.invalid','normalized_phone':None}))


if __name__=='__main__': unittest.main()

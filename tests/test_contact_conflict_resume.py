"""Synthetic only: exact terminal-conflict recovery and crash/unknown safety."""
import copy
import fcntl
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_contact_import_identity_policy import importer, quality


class FakeCRM:
    def __init__(self):
        self.contacts = {}
        self.posts = 0
        self.queries = 0
        self.before_query = None
        self.mode = 'ok'

    def query(self, field, raw, key):
        self.queries += 1
        if self.before_query:
            self.before_query(self)
        return [copy.deepcopy(obj) for obj in self.contacts.values()
                if not obj.get('deleted') and str(obj.get(field, '')).casefold() in {raw.casefold(), key.casefold()}]

    def get_contact(self, contact_id):
        return copy.deepcopy(self.contacts.get(contact_id))

    def call(self, method, path, body=None):
        assert method == 'POST' and path == '/Contact'
        self.posts += 1
        if self.mode == '409':
            raise importer.ImportFailure('crm_http_409_duplicate')
        if self.mode == '400':
            raise importer.ImportFailure('crm_http_400_lastName_required')
        if self.mode == 'before':
            raise importer.ImportFailure('crm_transport_or_response_error')
        self.contacts['new'] = {'id': 'new', **body}
        if self.mode == 'crash':
            raise KeyboardInterrupt('synthetic crash after remote commit')
        if self.mode == 'after':
            raise importer.ImportFailure('crm_transport_or_response_error')
        if self.mode == 'wrong':
            self.contacts['new']['description'] = 'synthetic incorrect marker'
        return 200, self.contacts['new']


class ConflictResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='opentour-resume-synthetic-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name, value in [('PRIVATE_DIR', self.root), ('CHECKPOINT_PATH', self.root/'checkpoint.json'),
                            ('EVENTS_PATH', self.root/'events.jsonl')]:
            context = patch.object(importer, name, value); context.start();self.addCleanup(context.stop)
        self.row = {'source_ordinal':1, 'source_identity':'source-01', 'logical_row':2,
            'source_revision':'a'*64, 'mapping_version':'synthetic-v1', 'workbook_alias':None,
            'sheet_alias':None, 'surname_status':'placeholder_none', 'last_name':'None',
            'disposition':'candidate', 'email_key':'synthetic@example.invalid', 'email_raw':'Synthetic@example.invalid',
            'phone_key':None, 'phone_raw':None, 'normalized_phone':None,
            'phone_normalization_status':'missing', 'phone_normalization_reason':'phone_missing',
            'phone_normalization_version':quality.PHONE_NORMALIZATION_VERSION}
        self.mapping = {'mapping_version':'synthetic-v1', 'sources': []}
        self.ref = importer.source_reference(self.row)
        old = {key:value for key,value in self.row.items() if key not in ('email_key','email_raw','phone_key','phone_raw','last_name')}
        old.update(disposition='excluded', reason=importer.CONFLICT_REASON)
        self.cp = {'format':3, 'source_identity_scheme':'fixed_source_ordinal_v1', 'mapping_version':'synthetic-v1',
                   'phone_normalization_version':quality.PHONE_NORMALIZATION_VERSION, 'rows':{self.ref:old},
                   'legacy_rows_format2': {'synthetic-history': {'disposition':'excluded'}}}
        self.original = copy.deepcopy(self.cp)
        self.selection = {'format':1, 'mapping_version':'synthetic-v1', 'mapping_sha256':importer.mapping_digest(self.mapping),
            'phone_normalization_version':quality.PHONE_NORMALIZATION_VERSION, 'source_references':[self.ref]}
        self.crm = FakeCRM()
        self.save()

    def save(self):
        importer.atomic_private_json(importer.CHECKPOINT_PATH, self.cp)

    def run_resume(self, limit=1):
        with importer.private_import_lock():
            result = importer.resume_conflicts(self.cp, [self.row], self.mapping, self.crm,
                quality.PHONE_NORMALIZATION_VERSION, self.selection, limit)
        self.assertEqual(self.cp['rows'], self.original['rows'])
        self.assertEqual(self.cp['legacy_rows_format2'], self.original['legacy_rows_format2'])
        self.assertEqual(json.loads(importer.CHECKPOINT_PATH.read_text()), self.cp)
        return result

    def reload(self):
        self.cp = json.loads(importer.CHECKPOINT_PATH.read_text())

    def states(self):
        return [event['state'] for event in self.cp['conflict_resume']['rows'][self.ref]]

    def test_exact_old_terminal_selection_only_and_full_preflight(self):
        for disposition,reason in [('created','created_and_verified'), ('excluded','destination_validation_rejected'),
                                   ('halted','unknown_create_effect_requires_review')]:
            with self.subTest(reason=reason):
                self.cp=copy.deepcopy(self.original)
                self.cp['rows'][self.ref].update(disposition=disposition,reason=reason);self.save()
                with self.assertRaises(importer.ImportFailure):self.run_resume()
        self.assertEqual(self.crm.posts,0)
        self.assertEqual(self.crm.queries,0)

    def test_lineage_source_revision_mapping_normalizer_and_duplicates_rejected(self):
        changes = [lambda:self.cp['rows'][self.ref].update(source_revision='b'*64),
            lambda:self.cp['rows'][self.ref].update(logical_row=3),
            lambda:self.cp['rows'][self.ref].update(mapping_version='changed'),
            lambda:self.cp['rows'][self.ref].update(phone_normalization_version='old'),
            lambda:self.selection.update(mapping_sha256='changed'),
            lambda:self.selection['source_references'].append(self.ref),
            lambda:self.selection['source_references'].append('unknown-reference')]
        selection=copy.deepcopy(self.selection)
        for change in changes:
            self.cp=copy.deepcopy(self.original);self.selection=copy.deepcopy(selection);change();self.save()
            with self.assertRaises(importer.ImportFailure):self.run_resume()
        self.assertEqual(self.crm.posts,0);self.assertEqual(self.crm.queries,0)

    def test_fresh_no_match_becomes_unique_existing_before_post(self):
        def change(crm):
            if crm.queries==2:crm.contacts['existing']={'id':'existing','emailAddress':self.row['email_key']}
        self.crm.before_query=change
        self.run_resume()
        self.assertEqual(self.states(),['intent','existing']);self.assertEqual(self.crm.posts,0)
        self.reload();self.run_resume();self.assertEqual(self.crm.posts,0)

    def test_multiple_and_read_failure_never_write(self):
        for name in ('one','two'):
            self.crm.contacts[name]={'id':name,'emailAddress':self.row['email_key']}
        self.run_resume();self.assertEqual(self.states(),['ambiguous'])
        def fail(_crm):raise importer.ImportFailure('crm_match_result_truncated')
        self.crm.before_query=fail;self.run_resume()
        self.assertEqual(self.states(),['ambiguous','read_failed']);self.assertEqual(self.crm.posts,0)

    def test_second_read_failure_no_post_and_later_explicit_run_can_recheck(self):
        def fail(crm):
            if crm.queries==2:raise importer.ImportFailure('crm_transport_or_response_error')
        self.crm.before_query=fail;self.run_resume()
        self.assertEqual(self.states(),['intent','read_failed']);self.assertEqual(self.crm.posts,0)
        self.crm.before_query=None;self.run_resume();self.assertEqual(self.crm.posts,1)

    def test_create_readback_private_append_history_and_exact_repeat(self):
        result=self.run_resume()
        self.assertEqual(result['post_attempts'],1);self.assertIsNone(result['stopped_for_review'])
        self.assertEqual(self.states(),['intent','returned','created'])
        self.assertEqual(importer.CHECKPOINT_PATH.stat().st_mode&0o777,0o600)
        self.assertEqual(importer.EVENTS_PATH.stat().st_mode&0o777,0o600)
        self.reload();result=self.run_resume()
        self.assertEqual(self.crm.posts,1);self.assertEqual(result['post_attempts'],0)
        self.assertEqual(self.states(),['intent','returned','created','created'])
        self.assertEqual(len(importer.EVENTS_PATH.read_text().splitlines()),4)
        for private in (self.ref,'synthetic@example.invalid','new'):
            self.assertNotIn(private,json.dumps(result))

    def test_409_and_validation_stay_terminal_after_intent(self):
        for mode,state in [('409','conflict'),('400','validation_rejected')]:
            with self.subTest(mode=mode):
                self.cp=copy.deepcopy(self.original);self.save();self.crm=FakeCRM();self.crm.mode=mode
                self.run_resume();self.assertEqual(self.states(),['intent',state])
                self.reload();self.run_resume();self.assertEqual(self.crm.posts,1)

    def test_unknown_effect_stops_then_reconciles_after_remote_commit(self):
        self.crm.mode='after';result=self.run_resume()
        self.assertIsNotNone(result['stopped_for_review']);self.assertEqual(self.states(),['intent','unknown'])
        self.reload();result=self.run_resume()
        self.assertEqual(self.crm.posts,1);self.assertIsNone(result['stopped_for_review'])
        self.assertEqual(self.states(),['intent','unknown','create_reconciled'])

    def test_unknown_before_post_does_not_blind_retry_absence(self):
        self.crm.mode='before';self.run_resume();self.reload();result=self.run_resume()
        self.assertIsNotNone(result['stopped_for_review']);self.assertEqual(self.crm.posts,1)

    def test_crash_after_commit_restarts_without_duplicate_post(self):
        self.crm.mode='crash'
        with self.assertRaises(KeyboardInterrupt):self.run_resume()
        self.reload();self.assertEqual(self.states(),['intent'])
        result=self.run_resume();self.assertEqual(self.crm.posts,1)
        self.assertEqual(self.states(),['intent','create_reconciled'])
        self.assertIsNone(result['stopped_for_review'])

    def test_crash_before_post_is_unknown_and_never_retried(self):
        def crash(crm):
            if crm.queries==2:raise KeyboardInterrupt('synthetic crash before post')
        self.crm.before_query=crash
        with self.assertRaises(KeyboardInterrupt):self.run_resume()
        self.reload();self.crm.before_query=None;self.run_resume()
        self.assertEqual(self.crm.posts,0);self.assertEqual(self.states(),['intent','verification_failed'])

    def test_verification_failure_marker_or_channels_stops_without_retry(self):
        self.crm.mode='wrong';result=self.run_resume()
        self.assertIsNotNone(result['stopped_for_review'])
        self.reload();self.run_resume();self.assertEqual(self.crm.posts,1)
        self.crm.contacts['new'].update(description=importer.contact_marker(self.row),emailAddress='changed@example.invalid')
        self.run_resume();self.assertEqual(self.crm.posts,1)

    def test_existing_match_disappears_no_later_create(self):
        self.crm.contacts['existing']={'id':'existing','emailAddress':self.row['email_key']}
        self.run_resume();self.crm.contacts.clear();self.run_resume();self.run_resume()
        self.assertEqual(self.crm.posts,0)

    def test_checkpoint_changed_before_intent_no_post(self):
        def change(crm):
            importer.atomic_private_json(importer.CHECKPOINT_PATH,{'synthetic_other_writer':True})
        self.crm.before_query=change
        with self.assertRaises(importer.ImportFailure):self.run_resume()
        self.assertEqual(self.crm.posts,0)

    def test_lock_and_selection_file_reject_unsafe_input(self):
        with importer.private_import_lock():
            with self.assertRaises(importer.ImportFailure):
                with importer.private_import_lock():pass
        target=self.root/'selection.json';importer.atomic_private_json(target,self.selection)
        self.assertEqual(importer.read_conflict_selection(target),self.selection)
        target.chmod(0o644)
        with self.assertRaises(importer.ImportFailure):importer.read_conflict_selection(target)
        link=self.root/'alias.json';link.symlink_to(target)
        with self.assertRaises(OSError):importer.read_conflict_selection(link)

    def test_positive_bounded_limit_and_full_selection_preflight(self):
        with self.assertRaises(importer.ImportFailure):self.run_resume(0)
        extra=copy.deepcopy(self.row);extra['logical_row']=3
        ref=importer.source_reference(extra);old=copy.deepcopy(self.cp['rows'][self.ref]);old['logical_row']=3
        self.cp['rows'][ref]=old;self.original=copy.deepcopy(self.cp);self.save()
        self.selection['source_references'].append(ref)
        with importer.private_import_lock():
            result=importer.resume_conflicts(self.cp,[self.row,extra],self.mapping,self.crm,
                quality.PHONE_NORMALIZATION_VERSION,self.selection,1)
        self.assertEqual(result['not_attempted_due_to_limit'],1);self.assertEqual(self.crm.posts,1)
        self.assertNotIn(ref,self.cp['conflict_resume']['rows'])

    def test_atomic_intent_persistence_failure_never_posts(self):
        with patch.object(importer,'atomic_private_json',side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError):self.run_resume()
        self.assertEqual(self.crm.posts,0)
        self.reload();self.assertNotIn('conflict_resume',self.cp)

    def test_event_mirror_failure_after_intent_is_conservative_on_restart(self):
        with patch.object(importer,'append_private_event',side_effect=OSError('synthetic journal failure')):
            with self.assertRaises(OSError):self.run_resume()
        self.assertEqual(self.crm.posts,0)
        self.reload();self.run_resume()
        self.assertEqual(self.crm.posts,0);self.assertEqual(self.states(),['intent','verification_failed'])

    def test_created_marker_changed_or_deleted_on_repeat_never_posts(self):
        self.run_resume();self.crm.contacts.clear();result=self.run_resume()
        self.assertIsNotNone(result['stopped_for_review']);self.assertEqual(self.crm.posts,1)

    def test_corrupt_history_rejected_before_queries(self):
        self.cp['conflict_resume']={'format':1,'mapping_sha256':importer.mapping_digest(self.mapping),
            'rows':{self.ref:[{'sequence':2,'state':'intent','source_reference':self.ref}]}}
        self.save()
        with self.assertRaises(importer.ImportFailure):self.run_resume()
        self.assertEqual(self.crm.queries,0);self.assertEqual(self.crm.posts,0)

    def test_unknown_effect_stops_before_second_reference(self):
        extra=copy.deepcopy(self.row);extra.update(logical_row=3,email_key='other@example.invalid',email_raw='other@example.invalid')
        ref=importer.source_reference(extra);old=copy.deepcopy(self.cp['rows'][self.ref]);old['logical_row']=3
        self.cp['rows'][ref]=old;self.save();self.selection['source_references'].append(ref);self.crm.mode='before'
        with importer.private_import_lock():
            result=importer.resume_conflicts(self.cp,[self.row,extra],self.mapping,self.crm,
                quality.PHONE_NORMALIZATION_VERSION,self.selection,2)
        self.assertIsNotNone(result['stopped_for_review']);self.assertEqual(self.crm.posts,1)
        self.assertNotIn(ref,self.cp['conflict_resume']['rows'])

    def test_cli_selected_mode_and_normal_mode_skip_history(self):
        import contextlib
        import io
        authorization='bounded first import to selected local EspoCRM explicitly assigned by qitem-20261108184715-500ad3de; no external writes'
        self.mapping['import_authorization']=authorization
        self.selection['mapping_sha256']=importer.mapping_digest(self.mapping)
        selection_path=self.root/'selected.json';importer.atomic_private_json(selection_path,self.selection)
        self.crm.contacts['existing']={'id':'existing','emailAddress':self.row['email_key']}
        real_call=self.crm.call
        def call(method,path,body=None):
            if method=='GET' and path=='/App/user':return 200,{'user':{'type':'admin'}}
            return real_call(method,path,body)
        self.crm.call=call
        with patch.object(importer,'load_quality_module',return_value=quality), \
             patch.object(quality,'require_private_mapping',return_value=self.mapping), \
             patch.object(importer,'source_records',return_value=[self.row]), \
             patch.object(importer,'CRM',return_value=self.crm):
            for args,expected in [(['--resume-conflicts-file',str(selection_path),'--limit','1'],'exact_reference_conflict_resume'),
                                  ([], 'bounded_local_espocrm_api_create_only')]:
                output=io.StringIO()
                with patch('sys.argv',['contact_import.py']+args),contextlib.redirect_stdout(output):
                    self.assertEqual(importer.main(),0)
                data=json.loads(output.getvalue())
                self.assertEqual(data.get('operation',data.get('import_kind')),expected)
                self.assertNotIn(self.ref,output.getvalue())
        self.assertEqual(self.crm.posts,0)
        self.reload();self.assertEqual(self.cp['rows'],self.original['rows'])

    def test_phone_uses_accepted_normalizer_and_verifies_returned_channel(self):
        normalized=quality.normalize_phone('9123456789')
        self.row.update(email_key=None,email_raw=None,phone_raw='9123456789',phone_key=normalized['normalized_phone'],
            normalized_phone=normalized['normalized_phone'],assumed_calling_code=normalized['assumed_calling_code'],
            phone_normalization_status=normalized['status'],phone_normalization_reason=normalized['reason'])
        self.cp['rows'][self.ref].update(importer.checkpoint_phone_metadata(self.row));self.original=copy.deepcopy(self.cp);self.save()
        self.run_resume();self.assertEqual(self.crm.contacts['new']['phoneNumber'],normalized['normalized_phone'])
        self.run_resume();self.assertEqual(self.crm.posts,1)
        self.crm.contacts['new']['phoneNumber']='+10000000000'
        self.assertIsNotNone(self.run_resume()['stopped_for_review']);self.assertEqual(self.crm.posts,1)

    def test_final_read_becomes_ambiguous_never_posts(self):
        def change(crm):
            if crm.queries==2:
                crm.contacts.update({name:{'id':name,'emailAddress':self.row['email_key']} for name in ('one','two')})
        self.crm.before_query=change;self.run_resume()
        self.assertEqual(self.states(),['intent','ambiguous']);self.assertEqual(self.crm.posts,0)

"""Synthetic-only regression coverage for contact source identity and fallback policy."""

from __future__ import annotations

import importlib.util
import json
import urllib.error
import threading
import tempfile
import unittest
import urllib.parse
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("module_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


quality = load_module("contact_import_quality", ROOT / "tools/contact_import_quality.py")
importer = load_module("contact_import", ROOT / "tools/contact_import.py")

APPROVED_FALLBACK = {
    "enabled": True,
    "literal": "None",
    "metadata_status": "placeholder_none",
    "exclude_from_deduplication": True,
    "replace_only_after_confirmed_surname_review": True,
}


class ContactImportIdentityPolicyTests(unittest.TestCase):
    def test_crm_error_code_keeps_only_allowlisted_structured_classification(self):
        crm = importer.CRM.__new__(importer.CRM)
        crm.headers = {}
        safe_payload = {
            "messageTranslation": {"data": {
                "field": "phoneNumber", "type": "invalid", "value": "private-contact-value"
            }}
        }
        response = urllib.error.HTTPError(
            "http://127.0.0.1/synthetic", 422, "synthetic", {},
            BytesIO(json.dumps(safe_payload).encode()),
        )
        with patch.object(importer.urllib.request, "urlopen", side_effect=response):
            with self.assertRaises(importer.ImportFailure) as caught:
                crm.call("POST", "/Contact", {"phoneNumber": "private-contact-value"})
        self.assertEqual(caught.exception.code, "crm_http_422_phoneNumber_invalid")
        self.assertNotIn("private-contact-value", str(caught.exception))

    def test_crm_error_code_discards_unrecognized_types_and_arbitrary_details(self):
        payload = {"messageTranslation": {"data": {
            "field": "phoneNumber", "type": "sensitiveServerText", "value": "private"
        }}}
        self.assertEqual(importer.safe_crm_error_code(400, payload), "crm_http_400")
        self.assertEqual(importer.safe_crm_error_code(422, {"message": "private"}), "crm_http_422")

    def test_exact_channel_query_uses_typed_espo_filter_and_finds_late_synthetic_match(self):
        # Model the installed Espo boundary: plain `where=<json string>` is
        # discarded, while searchParams JSON preserves typed where/select data.
        contacts = [
            {"id": f"synthetic-{index:03d}", "emailAddress": f"filler-{index}@example.invalid"}
            for index in range(200)
        ]
        target = {"id": "synthetic-target", "emailAddress": "target@example.invalid"}
        contacts.append(target)
        observed = []

        class EspoBoundary(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                observed.append(query)
                search = json.loads(query["searchParams"][0]) if "searchParams" in query else {}
                where = search.get("where") if isinstance(search.get("where"), list) else []
                selected = contacts
                if where:
                    clause = where[0]
                    selected = [item for item in contacts
                                if item.get(clause.get("attribute")) == clause.get("value")]
                offset = search.get("offset", 0)
                limit = search.get("maxSize", 200)
                result = {"list": selected[offset:offset + limit], "total": len(selected)}
                raw = json.dumps(result).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = ThreadingHTTPServer(("127.0.0.1", 0), EspoBoundary)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        old_api = importer.API
        try:
            importer.API = f"http://127.0.0.1:{server.server_port}"
            crm = importer.CRM.__new__(importer.CRM)
            crm.headers = {}
            matches = crm.query("emailAddress", "target@example.invalid", "target@example.invalid")
            self.assertEqual([item["id"] for item in matches], ["synthetic-target"])
            self.assertEqual(len(observed), 1)
            self.assertIn("searchParams", observed[0])
            self.assertNotIn("where", observed[0])
            search = json.loads(observed[0]["searchParams"][0])
            self.assertEqual(search["where"], [{
                "type": "equals", "attribute": "emailAddress", "value": "target@example.invalid"
            }])
            self.assertIsInstance(search["where"], list)
            self.assertIsInstance(search["select"], list)
            self.assertIs(type(search["maxSize"]), int)
        finally:
            importer.API = old_api
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_identical_content_under_distinct_source_ordinals_has_distinct_identity(self):
        shared = {
            "source_revision": "a" * 64,
            "logical_row": 12,
            "mapping_version": "synthetic-map-v1",
        }
        first = {**shared, "source_ordinal": 1}
        second = {**shared, "source_ordinal": 2}

        self.assertNotEqual(importer.source_reference(first), importer.source_reference(second))
        self.assertNotEqual(importer.contact_marker(first), importer.contact_marker(second))

    def test_approved_none_tuple_is_ready_for_quality_and_import(self):
        source = {"surname_fallback": dict(APPROVED_FALLBACK)}

        self.assertTrue(quality.approved_none_fallback(source))
        self.assertEqual(quality.surname_readiness(source, None), ("placeholder_none", "None"))
        self.assertEqual(importer.resolve_surname(quality, source, None), ("None", "placeholder_none"))

    def test_disabled_or_contradictory_tuple_is_not_quality_or_import_ready(self):
        invalid_metadata = (
            {"enabled": False},
            {"metadata_status": "unreviewed"},
            {"exclude_from_deduplication": False},
            {"replace_only_after_confirmed_surname_review": False},
            {"literal": None},
            {"missing": True},
        )
        for change in invalid_metadata:
            with self.subTest(change=change):
                fallback = dict(APPROVED_FALLBACK)
                if "missing" in change:
                    fallback.pop("exclude_from_deduplication")
                else:
                    fallback.update(change)
                source = {"surname_fallback": fallback}

                self.assertFalse(quality.approved_none_fallback(source))
                self.assertEqual(quality.surname_readiness(source, None), ("unavailable", None))
                with self.assertRaises(importer.ImportFailure) as caught:
                    importer.resolve_surname(quality, source, None)
                self.assertEqual(caught.exception.code, "approved_surname_fallback_metadata_invalid")

    def test_v2_rollback_soft_deletes_only_matching_marker(self):
        row = {
            "source_ordinal": 2,
            "logical_row": 9,
            "source_revision": "b" * 64,
            "mapping_version": "synthetic-map-v2",
            "workbook_alias": None,
            "sheet_alias": None,
            "surname_status": "placeholder_none",
        }
        marker = importer.contact_marker(row)

        class FakeCRM:
            def __init__(self):
                self.contact = {"id": "synthetic-contact", "description": marker}
                self.deleted = False
                self.calls = []

            def get_contact(self, contact_id):
                self.assert_id(contact_id)
                return None if self.deleted else dict(self.contact)

            def assert_id(self, contact_id):
                if contact_id != "synthetic-contact":
                    raise AssertionError("unexpected_contact_id")

            def call(self, method, path):
                self.calls.append((method, path))
                if method != "DELETE" or path != "/Contact/synthetic-contact":
                    raise AssertionError("unexpected_crm_mutation")
                self.deleted = True
                return 200, {}

        crm = FakeCRM()
        ref = importer.source_reference(row)
        checkpoint = {"format": 2, "rows": {ref: {
            "source_ordinal": row["source_ordinal"],
            "logical_row": row["logical_row"],
            "source_revision": row["source_revision"],
            "mapping_version": row["mapping_version"],
            "disposition": "created",
            "crm_contact_id": "synthetic-contact",
        }}}

        with tempfile.TemporaryDirectory() as private_test_dir:
            old_checkpoint, old_events = importer.CHECKPOINT_PATH, importer.EVENTS_PATH
            importer.CHECKPOINT_PATH = Path(private_test_dir) / "checkpoint.json"
            importer.EVENTS_PATH = Path(private_test_dir) / "events.jsonl"
            try:
                counts, conflict = importer.rollback_created(checkpoint, [row], crm)
            finally:
                importer.CHECKPOINT_PATH, importer.EVENTS_PATH = old_checkpoint, old_events

        self.assertFalse(conflict)
        self.assertEqual(counts["soft_deleted_and_verified"], 1)
        self.assertTrue(crm.deleted)
        self.assertEqual(crm.calls, [("DELETE", "/Contact/synthetic-contact")])

    def test_v2_rollback_refuses_changed_marker_without_delete(self):
        row = {
            "source_ordinal": 3,
            "logical_row": 4,
            "source_revision": "c" * 64,
            "mapping_version": "synthetic-map-v2",
            "workbook_alias": None,
            "sheet_alias": None,
            "surname_status": "placeholder_none",
        }

        class FakeCRM:
            def __init__(self):
                self.contact = {"id": "synthetic-contact", "description": "changed-marker"}
                self.calls = []

            def get_contact(self, contact_id):
                return dict(self.contact)

            def call(self, method, path):
                self.calls.append((method, path))
                return 200, {}

        crm = FakeCRM()
        ref = importer.source_reference(row)
        checkpoint = {"format": 2, "rows": {ref: {
            "source_ordinal": row["source_ordinal"],
            "logical_row": row["logical_row"],
            "source_revision": row["source_revision"],
            "mapping_version": row["mapping_version"],
            "disposition": "created",
            "crm_contact_id": "synthetic-contact",
        }}}

        with tempfile.TemporaryDirectory() as private_test_dir:
            old_checkpoint, old_events = importer.CHECKPOINT_PATH, importer.EVENTS_PATH
            importer.CHECKPOINT_PATH = Path(private_test_dir) / "checkpoint.json"
            importer.EVENTS_PATH = Path(private_test_dir) / "events.jsonl"
            try:
                counts, conflict = importer.rollback_created(checkpoint, [row], crm)
            finally:
                importer.CHECKPOINT_PATH, importer.EVENTS_PATH = old_checkpoint, old_events

        self.assertTrue(conflict)
        self.assertEqual(counts["blocked_marker_changed"], 1)
        self.assertEqual(crm.calls, [])


if __name__ == "__main__":
    unittest.main()

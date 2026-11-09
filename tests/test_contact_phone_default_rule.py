"""Synthetic-only tests for the approved +7 phone normalization policy."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("module_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


quality = load_module("contact_import_quality_phone_test", ROOT / "tools/contact_import_quality.py")
importer = load_module("contact_import_phone_test", ROOT / "tools/contact_import.py")


def synthetic_mapping(root: Path, first_source_rows: list[list[str]]):
    artifacts = root / ".artifacts" / "client-datatables"
    artifacts.mkdir(parents=True)
    headers = ["email", "phone", "surname"]
    contents = [first_source_rows, [], []]
    mapping_sources = []
    for ordinal, (_, filename) in enumerate(quality.EXPECTED_SOURCES, 1):
        path = artifacts / filename
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerows(contents[ordinal - 1])
        raw = path.read_bytes()
        mapping_sources.append({
            "source_ordinal": ordinal,
            "private_source_path": str(path.resolve()),
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "headers": headers,
            "workbook_alias": f"synthetic-workbook-{ordinal}",
            "sheet_alias": f"synthetic-sheet-{ordinal}",
            "selected_target_columns": {
                "emailAddress": {"column_index": 0, "header": "email"},
                "phoneNumber": {"column_index": 1, "header": "phone"},
                "lastName": {"column_index": 2, "header": "surname"},
            },
            "surname_fallback": {
                "enabled": True, "literal": "None", "metadata_status": "placeholder_none",
                "exclude_from_deduplication": True,
                "replace_only_after_confirmed_surname_review": True,
            },
        })
    return artifacts, {"mapping_version": "synthetic-v1", "sources": mapping_sources}


class ContactPhoneDefaultRuleTests(unittest.TestCase):
    def test_default_10_digit_national_shape_and_idempotence(self):
        first = quality.normalize_phone("123 456-7890")
        self.assertEqual(first["status"], "normalized")
        self.assertEqual(first["normalized_phone"], "+71234567890")
        self.assertEqual(first["assumed_calling_code"], "+7")
        second = quality.normalize_phone(
            first["normalized_phone"], previous_assumption=first["assumed_calling_code"]
        )
        self.assertEqual(second["normalized_phone"], first["normalized_phone"])
        self.assertEqual(second["assumed_calling_code"], "+7")

    def test_explicit_international_code_is_preserved(self):
        result = quality.normalize_phone("+1 (202) 555-0100")
        self.assertEqual(result["normalized_phone"], "+12025550100")
        self.assertIsNone(result["assumed_calling_code"])
        explicit_seven = quality.normalize_phone("+7 (123) 456-78-90")
        self.assertEqual(explicit_seven["normalized_phone"], "+71234567890")
        self.assertIsNone(explicit_seven["assumed_calling_code"])

    def test_domestic_trunk_and_existing_seven_are_not_double_prefixed(self):
        trunk = quality.normalize_phone("8 (123) 456-78-90")
        self.assertEqual(trunk["normalized_phone"], "+71234567890")
        self.assertEqual(quality.normalize_phone("7 123 456-78-90")["normalized_phone"], "+71234567890")

    def test_invalid_and_ambiguous_shapes_are_explicit(self):
        self.assertEqual(quality.normalize_phone("12ABC")["status"], "invalid")
        self.assertEqual(quality.normalize_phone("+7 123 456")["status"], "invalid")
        self.assertEqual(quality.normalize_phone("1234567")["status"], "ambiguous")
        self.assertEqual(quality.normalize_phone("0012025550100")["status"], "ambiguous")
        zero_country_code = quality.normalize_phone("+01234567")
        self.assertEqual(zero_country_code["status"], "invalid")
        self.assertEqual(zero_country_code["reason"], "international_calling_code_starts_with_zero")

    def test_create_body_uses_normalized_phone_and_never_raw_phone(self):
        row = {
            "source_ordinal": 1, "logical_row": 2, "source_revision": "a" * 64,
            "mapping_version": "synthetic-v1", "last_name": "Synthetic",
            "email_raw": None, "phone_raw": "123 456-7890",
            "normalized_phone": "+71234567890",
        }
        body = importer.build_contact_body(row)
        self.assertEqual(body["phoneNumber"], "+71234567890")
        self.assertNotIn("123 456-7890", str(body))

    def test_distinct_source_texts_colliding_after_normalization_are_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts, mapping = synthetic_mapping(root, [
                ["", "123 456-7890", "One"], ["", "+7 (123) 456-78-90", "Two"]
            ])
            with patch.object(importer, "ROOT", root), patch.object(quality, "ARTIFACTS", artifacts):
                rows = importer.source_records(quality, mapping)
            self.assertEqual(len(rows), 2)
            self.assertEqual([row["phone_raw"] for row in rows], [
                "123 456-7890", "+7 (123) 456-78-90"
            ])
            self.assertEqual({row["normalized_phone"] for row in rows}, {"+71234567890"})
            self.assertTrue(all(row["disposition"] == "excluded" for row in rows))
            self.assertTrue(all(row["reason"] == "normalization_collision" for row in rows))
            self.assertTrue(all(row["phone_normalization_status"] == "collision" for row in rows))

    def test_zero_country_code_is_excluded_and_never_added_to_contact_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts, mapping = synthetic_mapping(root, [["", "+01234567", "Invalid"]])
            with patch.object(importer, "ROOT", root), patch.object(quality, "ARTIFACTS", artifacts):
                rows = importer.source_records(quality, mapping)
            self.assertEqual(rows[0]["disposition"], "excluded")
            self.assertEqual(rows[0]["reason"], "invalid_phone_number")
            self.assertIsNone(rows[0]["normalized_phone"])
            candidate_body = importer.build_contact_body({**rows[0], "last_name": "None"})
            self.assertNotIn("phoneNumber", candidate_body)

    def test_exact_raw_phone_match_preserves_existing_contact_without_create(self):
        raw_phone = "123 456-7890"
        existing_contact = {
            "id": "synthetic-existing-contact", "deleted": False,
            "description": "unrelated-existing-record", "phoneNumber": raw_phone,
        }

        class SyntheticCRM(importer.CRM):
            def __init__(self):
                self.headers = {}
                self.post_count = 0

            def call(self, method, path, body=None):
                if method == "GET" and path == "/App/user":
                    return 200, {"user": {"type": "admin"}}
                if method == "GET" and path.startswith("/Contact?"):
                    query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
                    search = json.loads(query["searchParams"][0])
                    clause = search["where"][0]
                    matches = [existing_contact] if clause["value"] == raw_phone else []
                    return 200, {"list": matches, "total": len(matches)}
                if method == "POST" and path == "/Contact":
                    self.post_count += 1
                    return 201, {"id": "unexpected-created-contact"}
                raise AssertionError("unexpected_synthetic_crm_call")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts, mapping = synthetic_mapping(root, [["", raw_phone, "Source"]])
            mapping["import_authorization"] = (
                "bounded first import to selected local EspoCRM explicitly assigned by "
                "qitem-20261108184715-500ad3de; no external writes"
            )
            private_dir = root / "private"
            crm = SyntheticCRM()
            output = io.StringIO()
            with (
                patch.object(importer, "ROOT", root),
                patch.object(importer, "PRIVATE_DIR", private_dir),
                patch.object(importer, "MAPPING_PATH", private_dir / "mapping.json"),
                patch.object(importer, "CHECKPOINT_PATH", private_dir / "checkpoint.json"),
                patch.object(importer, "EVENTS_PATH", private_dir / "events.jsonl"),
                patch.object(importer, "load_quality_module", return_value=quality),
                patch.object(importer, "CRM", return_value=crm),
                patch.object(quality, "ARTIFACTS", artifacts),
                patch.object(quality, "require_private_mapping", return_value=mapping),
                patch.object(importer.sys, "argv", ["contact_import.py"]),
                redirect_stdout(output),
            ):
                result = importer.main()
            summary = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertEqual(summary["aggregate_dispositions"]["unique_existing_contact_preserved"], 1)
            self.assertEqual(crm.post_count, 0)


if __name__ == "__main__":
    unittest.main()

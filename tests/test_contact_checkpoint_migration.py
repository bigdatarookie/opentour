"""Synthetic-only tests for format-2 phone-normalizer checkpoint migration."""

from __future__ import annotations

import importlib.util
import csv
import hashlib
import io
import json
import stat
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("module_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


importer = load_module("contact_import_migration_test", ROOT / "tools/contact_import.py")
quality = load_module("contact_import_quality_migration_test", ROOT / "tools/contact_import_quality.py")


def source_row(*, disposition="candidate", phone_raw="123 456-7890", phone_key="+71234567890",
               email_raw=None, email_key=None, ordinal=1):
    return {
        "source_ordinal": ordinal,
        "logical_row": 2,
        "source_revision": ("a" if ordinal == 1 else "b") * 64,
        "mapping_version": "synthetic-map-v1",
        "workbook_alias": f"synthetic-workbook-{ordinal}",
        "sheet_alias": f"synthetic-sheet-{ordinal}",
        "email_raw": email_raw,
        "email_key": email_key,
        "phone_raw": phone_raw,
        "phone_key": phone_key,
        "normalized_phone": phone_key,
        "assumed_calling_code": "+7" if phone_key else None,
        "phone_normalization_status": "normalized" if phone_key else "missing",
        "phone_normalization_reason": None if phone_key else "phone_missing",
        "phone_normalization_version": "e164-default-7-v1",
        "last_name": "None",
        "surname_status": "placeholder_none",
        "disposition": disposition,
        "reason": "awaiting_collision_and_destination_reconciliation" if disposition == "candidate" else disposition,
    }


def entry(row, disposition, reason, contact_id=None):
    value = {
        "source_ordinal": row["source_ordinal"],
        "source_identity": importer.source_identity(row),
        "logical_row": row["logical_row"],
        "source_revision": row["source_revision"],
        "mapping_version": row["mapping_version"],
        "workbook_alias": row["workbook_alias"],
        "sheet_alias": row["sheet_alias"],
        "disposition": disposition,
        "reason": reason,
        "surname_status": row["surname_status"],
    }
    if contact_id:
        value["crm_contact_id"] = contact_id
    return value


def legacy_checkpoint(rows, entries, mapping_version="synthetic-map-v1", version=None):
    checkpoint = {
        "format": 2,
        "source_identity_scheme": "fixed_source_ordinal_v1",
        "mapping_version": mapping_version,
        "rows": {importer.source_reference(row): entries[index] for index, row in enumerate(rows)},
    }
    if version is not None:
        checkpoint["phone_normalization_version"] = version
    return checkpoint


class FakeCRM:
    def __init__(self, contacts=(), error=None):
        self.contacts = {obj["id"]: dict(obj) for obj in contacts}
        self.error = error
        self.queries = []
        self.writes = 0

    def get_contact(self, contact_id):
        contact = self.contacts.get(contact_id)
        return dict(contact) if contact else None

    def query(self, field, raw_value, key_value):
        self.queries.append((field, raw_value, key_value))
        if self.error:
            raise importer.ImportFailure(self.error)
        accepted = {raw_value.strip(), key_value.strip()}
        result = []
        for contact in self.contacts.values():
            direct = contact.get(field)
            related_key = "emailAddress" if field == "emailAddress" else "phoneNumber"
            related = contact.get(field + "Data", [])
            values = ([direct] if isinstance(direct, str) else []) + [
                item[related_key] for item in related
                if isinstance(item, dict) and isinstance(item.get(related_key), str)
            ]
            if any(value.strip() in accepted for value in values):
                result.append(dict(contact))
        return result


class ContactCheckpointMigrationTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {"mapping_version": "synthetic-map-v1"}

    def migrate(self, checkpoint, rows, crm):
        return importer.migrate_checkpoint_phone_normalization(
            checkpoint, rows, self.mapping, crm, "e164-default-7-v1"
        )

    def test_created_record_requires_marker_and_raw_or_normalized_match(self):
        row = source_row()
        marker = importer.contact_marker(row)
        crm = FakeCRM([{
            "id": "synthetic-created", "description": marker,
            "phoneNumber": row["phone_raw"],
        }])
        old_entry = entry(row, "created", "created_and_verified", "synthetic-created")
        old = legacy_checkpoint([row], [old_entry])
        migrated, counts = self.migrate(old, [row], crm)
        ref = importer.source_reference(row)
        self.assertEqual(migrated["format"], 3)
        self.assertEqual(migrated["rows"][ref]["disposition"], "created")
        self.assertEqual(migrated["rows"][ref]["normalized_phone"], row["normalized_phone"])
        self.assertEqual(migrated["legacy_rows_format2"][ref], old_entry)
        self.assertEqual(counts["created_effect_verified"], 1)
        self.assertEqual(crm.writes, 0)

    def test_existing_contact_reconciles_exact_normalized_value(self):
        row = source_row(phone_raw="8 (123) 456-78-90")
        crm = FakeCRM([{
            "id": "synthetic-existing", "description": "unrelated-record",
            "phoneNumber": "+71234567890",
        }])
        old_entry = entry(row, "not_created", "unique_existing_contact_preserved", "synthetic-existing")
        migrated, counts = self.migrate(legacy_checkpoint([row], [old_entry]), [row], crm)
        self.assertEqual(migrated["rows"][importer.source_reference(row)]["crm_contact_id"], "synthetic-existing")
        self.assertEqual(counts["existing_effect_verified"], 1)

    def test_validation_rejection_without_current_match_is_only_reconsidered_later(self):
        row = source_row()
        old_entry = entry(row, "excluded", "destination_validation_rejected")
        old = legacy_checkpoint([row], [old_entry])
        migrated, counts = self.migrate(old, [row], FakeCRM())
        ref = importer.source_reference(row)
        self.assertNotIn(ref, migrated["rows"])
        self.assertEqual(migrated["legacy_rows_format2"][ref], old_entry)
        self.assertEqual(counts["validation_rejection_safe_to_reconsider"], 1)

    def test_validation_rejection_with_exact_raw_match_is_preserved_as_existing(self):
        row = source_row()
        old_entry = entry(row, "excluded", "destination_validation_rejected")
        crm = FakeCRM([{"id": "synthetic-existing", "phoneNumber": row["phone_raw"]}])
        migrated, _ = self.migrate(legacy_checkpoint([row], [old_entry]), [row], crm)
        current = migrated["rows"][importer.source_reference(row)]
        self.assertEqual(current["disposition"], "not_created")
        self.assertEqual(current["reason"], "legacy_validation_rejection_existing_match_preserved")
        self.assertEqual(crm.writes, 0)

    def test_validation_rejection_with_multiple_matches_stays_excluded(self):
        row = source_row()
        old_entry = entry(row, "excluded", "destination_validation_rejected")
        crm = FakeCRM([
            {"id": "synthetic-one", "phoneNumber": row["phone_raw"]},
            {"id": "synthetic-two", "phoneNumber": row["normalized_phone"]},
        ])
        migrated, _ = self.migrate(legacy_checkpoint([row], [old_entry]), [row], crm)
        current = migrated["rows"][importer.source_reference(row)]
        self.assertEqual(current["disposition"], "excluded")
        self.assertEqual(current["reason"], "legacy_validation_rejection_multiple_current_matches")

    def test_historical_conflict_is_preserved_and_never_reconsidered(self):
        row = source_row(email_raw="a@example.invalid", email_key="a@example.invalid")
        old_entry = entry(row, "excluded", "destination_conflict_without_channel_match")
        old = legacy_checkpoint([row], [old_entry])
        migrated, counts = self.migrate(old, [row], FakeCRM())
        ref = importer.source_reference(row)
        self.assertEqual(migrated["rows"][ref]["reason"], "destination_conflict_without_channel_match")
        self.assertEqual(migrated["legacy_rows_format2"][ref], old_entry)
        self.assertEqual(counts["destination_exclusion_preserved"], 1)

    def test_unknown_effect_requires_unique_source_marker(self):
        row = source_row()
        old_entry = entry(row, "halted", "unknown_create_effect_requires_review")
        checkpoint = legacy_checkpoint([row], [old_entry])
        with self.assertRaises(importer.ImportFailure) as caught:
            self.migrate(checkpoint, [row], FakeCRM())
        self.assertEqual(caught.exception.code, "legacy_unknown_create_effect_unresolved")
        self.assertEqual(checkpoint["rows"][importer.source_reference(row)], old_entry)

    def test_unknown_effect_with_unique_marker_becomes_reconciled(self):
        row = source_row()
        old_entry = entry(row, "halted", "unknown_create_effect_requires_review")
        crm = FakeCRM([{
            "id": "synthetic-reconciled", "description": importer.contact_marker(row),
            "phoneNumber": row["phone_raw"],
        }])
        migrated, counts = self.migrate(legacy_checkpoint([row], [old_entry]), [row], crm)
        current = migrated["rows"][importer.source_reference(row)]
        self.assertEqual(current["disposition"], "create_reconciled")
        self.assertEqual(current["crm_contact_id"], "synthetic-reconciled")
        self.assertEqual(counts["unknown_effect_reconciled"], 1)

    def test_unknown_marker_with_another_channel_match_remains_unresolved(self):
        row = source_row()
        old_entry = entry(row, "halted", "unknown_create_effect_requires_review")
        crm = FakeCRM([
            {
                "id": "synthetic-marked", "description": importer.contact_marker(row),
                "phoneNumber": row["phone_raw"],
            },
            {"id": "synthetic-other", "phoneNumber": row["normalized_phone"]},
        ])
        with self.assertRaises(importer.ImportFailure) as caught:
            self.migrate(legacy_checkpoint([row], [old_entry]), [row], crm)
        self.assertEqual(caught.exception.code, "legacy_unknown_create_effect_unresolved")
        self.assertEqual(crm.writes, 0)

    def test_unrecognized_legacy_normalizer_version_fails_closed(self):
        row = source_row()
        old_entry = entry(row, "excluded", "destination_conflict_without_channel_match")
        checkpoint = legacy_checkpoint([row], [old_entry], version="legacy-other-v9")
        crm = FakeCRM()
        with self.assertRaises(importer.ImportFailure) as caught:
            self.migrate(checkpoint, [row], crm)
        self.assertEqual(caught.exception.code, "checkpoint_phone_normalization_version_conflict")
        self.assertEqual(crm.queries, [])

    def test_halted_auth_error_is_preserved_without_automatic_retry(self):
        row = source_row()
        old_entry = entry(row, "halted", "destination_auth_or_scope_error")
        migrated, counts = self.migrate(legacy_checkpoint([row], [old_entry]), [row], FakeCRM())
        current = migrated["rows"][importer.source_reference(row)]
        self.assertEqual(current["disposition"], "halted")
        self.assertEqual(current["reason"], "destination_auth_or_scope_error")
        self.assertEqual(counts["terminal_halted_preserved"], 1)

    def test_empty_checkpoint_is_safe_only_when_source_set_is_empty(self):
        empty = legacy_checkpoint([], [])
        migrated, _ = self.migrate(empty, [], FakeCRM())
        self.assertEqual(migrated["format"], 3)
        row = source_row()
        with self.assertRaises(importer.ImportFailure) as caught:
            self.migrate(legacy_checkpoint([], []), [row], FakeCRM())
        self.assertEqual(caught.exception.code, "empty_checkpoint_source_effects_unaccounted")

    def test_changed_source_or_mapping_version_fails_before_crm_query(self):
        row = source_row()
        old_entry = entry(row, "created", "created_and_verified", "synthetic-id")
        crm = FakeCRM()
        changed = source_row()
        changed["source_revision"] = "c" * 64
        with self.assertRaises(importer.ImportFailure) as caught:
            self.migrate(legacy_checkpoint([row], [old_entry]), [changed], crm)
        self.assertEqual(caught.exception.code, "checkpoint_source_row_set_mismatch")
        self.mapping["mapping_version"] = "different-map-v2"
        with self.assertRaises(importer.ImportFailure) as caught:
            self.migrate(legacy_checkpoint([row], [old_entry]), [row], crm)
        self.assertEqual(caught.exception.code, "checkpoint_mapping_version_mismatch")
        self.assertEqual(crm.queries, [])

    def test_current_format3_is_idempotent_and_version_conflict_fails(self):
        current = {
            "format": 3, "source_identity_scheme": "fixed_source_ordinal_v1",
            "mapping_version": "synthetic-map-v1",
            "phone_normalization_version": "e164-default-7-v1", "rows": {},
        }
        returned, counts = self.migrate(current, [], FakeCRM())
        self.assertIs(returned, current)
        self.assertEqual(counts["already_current"], 1)
        current["phone_normalization_version"] = "different-version"
        with self.assertRaises(importer.ImportFailure) as caught:
            self.migrate(current, [], FakeCRM())
        self.assertEqual(caught.exception.code, "checkpoint_phone_normalization_version_conflict")

    def test_query_failure_or_incomplete_result_fails_without_mutation(self):
        row = source_row()
        old_entry = entry(row, "excluded", "destination_validation_rejected")
        checkpoint = legacy_checkpoint([row], [old_entry])
        for failure in ("crm_transport_or_response_error", "crm_match_result_truncated"):
            with self.subTest(failure=failure):
                with self.assertRaises(importer.ImportFailure) as caught:
                    self.migrate(checkpoint, [row], FakeCRM(error=failure))
                self.assertEqual(caught.exception.code, failure)
                self.assertEqual(checkpoint["rows"][importer.source_reference(row)], old_entry)

    def test_format2_backup_and_v3_checkpoint_write_are_private_and_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private = root / "private"
            checkpoint_path = private / "checkpoint.json"
            backup_path = private / "import-checkpoint-format2-before-phone-normalization.json"
            row = source_row()
            old = legacy_checkpoint([row], [entry(row, "excluded", "destination_validation_rejected")])
            checkpoint_path.parent.mkdir(mode=0o700)
            checkpoint_path.write_text(json.dumps(old), encoding="utf-8")
            checkpoint_path.chmod(0o600)
            original_bytes = checkpoint_path.read_bytes()
            migrated, counts = self.migrate(old, [row], FakeCRM())
            with patch.object(importer, "CHECKPOINT_PATH", checkpoint_path), \
                    patch.object(importer, "PRIVATE_DIR", private), \
                    patch.object(importer, "EVENTS_PATH", private / "events.jsonl"):
                event_recorded = importer.persist_phone_checkpoint_migration(old, migrated, counts)
            self.assertTrue(event_recorded)
            self.assertEqual(backup_path.read_bytes(), original_bytes)
            self.assertEqual(json.loads(checkpoint_path.read_text())["format"], 3)
            self.assertEqual(stat.S_IMODE(backup_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(checkpoint_path.stat().st_mode), 0o600)
            self.assertEqual(counts["validation_rejection_safe_to_reconsider"], 1)

    def test_explicit_migration_cli_performs_reads_and_checkpoint_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = root / ".artifacts" / "client-datatables"
            artifacts.mkdir(parents=True)
            headers = ["email", "phone", "surname"]
            source_paths = []
            mapping_sources = []
            for ordinal, (_, filename) in enumerate(quality.EXPECTED_SOURCES, 1):
                path = artifacts / filename
                with path.open("w", encoding="utf-8-sig", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(headers)
                    if ordinal == 1:
                        writer.writerow(["", "123 456-7890", "Synthetic"])
                raw = path.read_bytes()
                source_paths.append(path)
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
            mapping = {
                "mapping_version": "synthetic-map-v1",
                "import_authorization": (
                    "bounded first import to selected local EspoCRM explicitly assigned by "
                    "qitem-20261108184715-500ad3de; no external writes"
                ),
                "sources": mapping_sources,
            }
            private = root / "private"
            private.mkdir(mode=0o700)
            checkpoint_path = private / "checkpoint.json"
            event_path = private / "events.jsonl"
            first_row = {
                "source_ordinal": 1, "logical_row": 2,
                "source_revision": hashlib.sha256(source_paths[0].read_bytes()).hexdigest(),
                "mapping_version": mapping["mapping_version"],
                "workbook_alias": "synthetic-workbook-1", "sheet_alias": "synthetic-sheet-1",
                "phone_raw": "123 456-7890", "phone_key": "+71234567890",
                "normalized_phone": "+71234567890", "email_raw": None, "email_key": None,
                "last_name": "Synthetic", "surname_status": "source_confirmed",
            }
            row_ref = importer.source_reference(first_row)
            old_entry = entry(first_row, "excluded", "destination_validation_rejected")
            old = legacy_checkpoint([first_row], [old_entry])
            checkpoint_path.write_text(json.dumps(old), encoding="utf-8")
            checkpoint_path.chmod(0o600)

            class ReadOnlyCRM(importer.CRM):
                def __init__(self):
                    self.headers = {}
                    self.queries = []
                    self.write_count = 0

                def call(self, method, path, body=None):
                    if method == "GET" and path == "/App/user":
                        return 200, {"user": {"type": "admin"}}
                    if method == "POST":
                        self.write_count += 1
                        raise AssertionError("migration_attempted_contact_write")
                    raise AssertionError("unexpected_crm_call")

                def query(self, field, raw_value, key_value):
                    self.queries.append((field, raw_value, key_value))
                    return []

            crm = ReadOnlyCRM()
            output = io.StringIO()
            with (
                patch.object(importer, "ROOT", root),
                patch.object(importer, "PRIVATE_DIR", private),
                patch.object(importer, "MAPPING_PATH", private / "mapping.json"),
                patch.object(importer, "CHECKPOINT_PATH", checkpoint_path),
                patch.object(importer, "EVENTS_PATH", event_path),
                patch.object(importer, "load_quality_module", return_value=quality),
                patch.object(importer, "CRM", return_value=crm),
                patch.object(quality, "ARTIFACTS", artifacts),
                patch.object(quality, "require_private_mapping", return_value=mapping),
                patch.object(importer.sys, "argv", ["contact_import.py", "--migrate-phone-normalization"]),
                redirect_stdout(output),
            ):
                result = importer.main()
            summary = json.loads(output.getvalue())
            current = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertEqual(summary["operation"], "private_phone_normalization_checkpoint_migration")
            self.assertEqual(summary["contacts_created"], 0)
            self.assertFalse(summary["crm_contact_writes"])
            self.assertEqual(crm.queries, [("phoneNumber", "123 456-7890", "+71234567890")])
            self.assertEqual(crm.write_count, 0)
            self.assertEqual(current["format"], 3)
            self.assertNotIn(row_ref, current["rows"])
            self.assertEqual(current["legacy_rows_format2"][row_ref]["reason"], "destination_validation_rejected")
            self.assertTrue((private / "import-checkpoint-format2-before-phone-normalization.json").is_file())
            self.assertTrue(event_path.is_file())


if __name__ == "__main__":
    unittest.main()

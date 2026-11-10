#!/usr/bin/env python3
"""Bounded, resumable import from the three fixed OpenTour contact CSVs.

Owner records and CRM credentials are read only inside this process. Output is
aggregate-only; row dispositions and source lineage are kept under the private
Data Engineer seat directory.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIR = Path("/Users/garry/.openrig/topology/rigs/opentour-rig/seats/data-engineer/private-contact-import")
MAPPING_PATH = PRIVATE_DIR / "mapping-proposal.json"
CHECKPOINT_PATH = PRIVATE_DIR / "import-checkpoint.json"
EVENTS_PATH = PRIVATE_DIR / "import-events.jsonl"
SECRETS_DIR = ROOT / "local/crm/secrets"
API = "http://127.0.0.1:18082/api/v1"
QUALITY_PATH = Path(__file__).with_name("contact_import_quality.py")
CRM_ERROR_FIELD_ALLOWLIST = {"lastName", "emailAddress", "phoneNumber", "description"}
CRM_ERROR_TYPE_ALLOWLIST = {
    "required", "invalid", "notMatch", "maxLength", "minLength", "isEmpty",
    "isEmptyString", "emailAddress", "phoneNumber",
}


class ImportFailure(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def safe_crm_error_code(status: int, payload: Any, status_reason: str | None = None) -> str:
    """Return only an allowlisted, value-free CRM error classification."""
    code = f"crm_http_{status}"
    try:
        translation = payload.get("messageTranslation", {})
        detail = translation.get("data", {}) if isinstance(translation, dict) else {}
        field = detail.get("field") if isinstance(detail, dict) else None
        error_type = detail.get("type") if isinstance(detail, dict) else None
        if field in CRM_ERROR_FIELD_ALLOWLIST and error_type in CRM_ERROR_TYPE_ALLOWLIST:
            return f"{code}_{field}_{error_type}"
    except (AttributeError, TypeError):
        pass
    if status == 409 and status_reason == "duplicate":
        return f"{code}_duplicate"
    return code


def atomic_private_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, name = tempfile.mkstemp(prefix=".checkpoint-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(doc, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def append_private_event(event: dict[str, Any]) -> None:
    PRIVATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(PRIVATE_DIR, 0o700)
    fd = os.open(EVENTS_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        with os.fdopen(fd, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.chmod(EVENTS_PATH, 0o600)


def load_quality_module():
    spec = importlib.util.spec_from_file_location("contact_import_quality", QUALITY_PATH)
    if spec is None or spec.loader is None:
        raise ImportFailure("quality_module_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CRM:
    def __init__(self):
        password_path = SECRETS_DIR / "admin-password"
        if not password_path.is_file() or stat.S_IMODE(password_path.stat().st_mode) & 0o077:
            raise ImportFailure("local_crm_secret_unavailable_or_permissions_invalid")
        password = password_path.read_text(encoding="utf-8").strip()
        if not password:
            raise ImportFailure("local_crm_secret_empty")
        value = base64.b64encode(("admin:" + password).encode()).decode()
        self.headers = {"Espo-Authorization": value, "Content-Type": "application/json"}

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        req = urllib.request.Request(API + path, data=data, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            # Never expose CRM response bodies: they may contain contact data.
            payload: Any = None
            if exc.code in (400, 409, 422):
                try:
                    payload = json.loads(exc.read())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
            code = safe_crm_error_code(exc.code, payload, exc.headers.get("X-Status-Reason") if exc.headers else None)
            raise ImportFailure(code) from None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            raise ImportFailure("crm_transport_or_response_error") from None

    def get_contact(self, contact_id: str) -> dict[str, Any] | None:
        try:
            _, obj = self.call("GET", "/Contact/" + urllib.parse.quote(contact_id, safe=""))
            return obj if not obj.get("deleted") else None
        except ImportFailure as exc:
            if exc.code == "crm_http_404":
                return None
            raise

    def query(self, field: str, raw_value: str, key_value: str) -> list[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for value in dict.fromkeys((raw_value, key_value)):
            search = {
                "offset": 0,
                "maxSize": 200,
                "select": ["id", "deleted", "description", field, field + "Data"],
                "orderBy": "id",
                "order": "ASC",
                "where": [{"type": "equals", "attribute": field, "value": value}],
            }
            query = urllib.parse.urlencode({"searchParams": json.dumps(search, ensure_ascii=False)})
            _, result = self.call("GET", "/Contact?" + query)
            if int(result.get("total", 0)) > len(result.get("list", [])):
                raise ImportFailure("crm_match_result_truncated")
            for obj in result.get("list", []):
                if obj.get("deleted"):
                    continue
                values: list[str] = []
                direct = obj.get(field)
                if isinstance(direct, str):
                    values.append(direct)
                related = obj.get(field + "Data", [])
                if isinstance(related, list):
                    value_key = "emailAddress" if field == "emailAddress" else "phoneNumber"
                    values.extend(item[value_key] for item in related
                                  if isinstance(item, dict) and isinstance(item.get(value_key), str))
                if field == "emailAddress":
                    matches = any(value.strip().casefold() == key_value.casefold() for value in values)
                else:
                    accepted_phone_forms = {raw_value.strip(), key_value.strip()}
                    matches = any(value.strip() in accepted_phone_forms for value in values)
                if matches:
                    found[obj["id"]] = obj
        return list(found.values())


def source_records(module, mapping: dict[str, Any]):
    artifacts = module.ARTIFACTS.resolve(strict=True)
    if artifacts.parent != (ROOT / ".artifacts").resolve(strict=True):
        raise ImportFailure("source_root_outside_boundary")
    sources = mapping.get("sources")
    if not isinstance(sources, list) or len(sources) != len(module.EXPECTED_SOURCES):
        raise ImportFailure("mapping_source_set_invalid")
    by_ord = {item.get("source_ordinal"): item for item in sources}
    all_rows: list[dict[str, Any]] = []
    channel_groups: dict[tuple[str, str], set[tuple[int, int]]] = defaultdict(set)
    for ordinal, (_, filename) in enumerate(module.EXPECTED_SOURCES, 1):
        item = by_ord.get(ordinal)
        if not isinstance(item, dict):
            raise ImportFailure("mapping_source_set_invalid")
        path = (artifacts / filename).resolve(strict=True)
        if path.parent != artifacts or not path.is_file() or item.get("private_source_path") != str(path):
            raise ImportFailure("source_path_identity_mismatch")
        raw = path.read_bytes()
        revision = hashlib.sha256(raw).hexdigest()
        if revision != item.get("source_sha256") or not raw.startswith(b"\xef\xbb\xbf"):
            raise ImportFailure("source_revision_or_bom_mismatch")
        content = raw.decode("utf-8-sig", errors="strict")
        dialect = csv.Sniffer().sniff(content[:8192], delimiters=",;\t|")
        reader = csv.reader(io.StringIO(content, newline=""), dialect)
        headers = next(reader, None)
        if headers != item.get("headers"):
            raise ImportFailure("source_header_mapping_mismatch")
        columns = item.get("selected_target_columns", {})
        email_i = module.selected_index(columns.get("emailAddress"), headers)
        phone_i = module.selected_index(columns.get("phoneNumber"), headers)
        last_i = module.selected_index(columns.get("lastName"), headers)
        for logical_row, row in enumerate(reader, 2):
            ref = (ordinal, logical_row)
            record: dict[str, Any] = {
                "source_ordinal": ordinal, "logical_row": logical_row,
                "source_identity": source_identity({"source_ordinal": ordinal}),
                "source_revision": revision, "mapping_version": mapping["mapping_version"],
                "workbook_alias": item.get("workbook_alias"), "sheet_alias": item.get("sheet_alias"),
                "source_name": filename, "disposition": None, "reason": None,
                "email_raw": None, "email_key": None, "phone_raw": None, "phone_key": None,
                "normalized_phone": None, "assumed_calling_code": None,
                "phone_normalization_status": "missing", "phone_normalization_reason": "phone_missing",
                "phone_normalization_version": module.PHONE_NORMALIZATION_VERSION,
                "last_name": None, "surname_status": None,
            }
            if not row or all(not value.strip() for value in row):
                record.update(disposition="excluded", reason="blank_record")
            elif len(row) != len(headers):
                record.update(disposition="excluded", reason="field_width_mismatch")
            else:
                email_raw = row[email_i] if email_i is not None else ""
                phone_raw = row[phone_i] if phone_i is not None else ""
                email_key = module.parse_email(email_raw) if email_i is not None else None
                phone_result = module.normalize_phone(phone_raw) if phone_i is not None else module.normalize_phone("")
                phone_key = phone_result["normalized_phone"]
                record.update(email_raw=email_raw if email_key else None, email_key=email_key,
                              phone_raw=phone_raw if phone_raw.strip() else None, phone_key=phone_key,
                              normalized_phone=phone_key,
                              assumed_calling_code=phone_result["assumed_calling_code"],
                              phone_normalization_status=phone_result["status"],
                              phone_normalization_reason=phone_result["reason"],
                              phone_normalization_version=phone_result["normalization_version"])
                if not email_key and not phone_key:
                    if phone_result["status"] == "invalid":
                        record.update(disposition="excluded", reason="invalid_phone_number")
                    elif phone_result["status"] == "ambiguous":
                        record.update(disposition="excluded", reason="ambiguous_phone_number")
                    else:
                        record.update(disposition="excluded", reason="no_usable_channel")
                else:
                    surname_value = row[last_i] if last_i is not None else None
                    last_name, surname_status = resolve_surname(module, item, surname_value)
                    if last_name is None:
                        raise ImportFailure("approved_surname_fallback_metadata_invalid")
                    record.update(last_name=last_name, surname_status=surname_status)
                    record.update(disposition="candidate", reason="awaiting_collision_and_destination_reconciliation")
                    if email_key:
                        channel_groups[("email", email_key)].add(ref)
                    if phone_key:
                        channel_groups[("phone", phone_key)].add(ref)
            all_rows.append(record)
    collided: set[tuple[int, int]] = set()
    phone_collided: set[tuple[int, int]] = set()
    for (channel, _), refs in channel_groups.items():
        if len(refs) > 1:
            collided.update(refs)
            if channel == "phone":
                phone_collided.update(refs)
    for row in all_rows:
        if row["disposition"] == "candidate" and (row["source_ordinal"], row["logical_row"]) in collided:
            ref = (row["source_ordinal"], row["logical_row"])
            if ref in phone_collided:
                row.update(disposition="excluded", reason="normalization_collision",
                           phone_normalization_status="collision",
                           phone_normalization_reason="multiple_source_rows_share_normalized_phone")
            else:
                row.update(disposition="excluded", reason="ambiguous_source_email_collision")
    return all_rows


def source_identity(row: dict[str, Any]) -> str:
    ordinal = row.get("source_ordinal")
    if not isinstance(ordinal, int) or ordinal < 1:
        raise ImportFailure("source_identity_missing")
    return f"source-{ordinal:02d}"


def source_reference(row: dict[str, Any]) -> str:
    return f'{source_identity(row)}:{row["source_revision"]}:{row["logical_row"]}:{row["mapping_version"]}'


def legacy_source_reference(row: dict[str, Any]) -> str:
    return f'{row["source_revision"]}:{row["logical_row"]}:{row["mapping_version"]}'


def legacy_contact_marker(row: dict[str, Any]) -> str:
    return "opentour-source-v1:" + legacy_source_reference(row)


def contact_marker(row: dict[str, Any]) -> str:
    return "opentour-source-v2:" + source_reference(row)


def resolve_surname(module, source: dict[str, Any], value: str | None) -> tuple[str | None, str]:
    status, last_name = module.surname_readiness(source, value)
    if status == "unavailable" or last_name is None:
        raise ImportFailure("approved_surname_fallback_metadata_invalid")
    return last_name, status


def build_contact_body(row: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {"lastName": row["last_name"], "description": contact_marker(row)}
    if row.get("email_raw") is not None:
        body["emailAddress"] = row["email_raw"]
    if row.get("normalized_phone") is not None:
        body["phoneNumber"] = row["normalized_phone"]
    return body


def append_disposition(checkpoint: dict[str, Any], row: dict[str, Any], disposition: str,
                       reason: str, contact_id: str | None = None) -> None:
    ref = source_reference(row)
    entry = {"source_ordinal": row["source_ordinal"], "source_identity": source_identity(row), "logical_row": row["logical_row"],
             "source_revision": row["source_revision"], "mapping_version": row["mapping_version"],
             "workbook_alias": row["workbook_alias"], "sheet_alias": row["sheet_alias"],
             "disposition": disposition, "reason": reason, "surname_status": row["surname_status"]}
    for key in ("normalized_phone", "assumed_calling_code", "phone_normalization_status",
                "phone_normalization_reason", "phone_normalization_version"):
        if row.get(key) is not None:
            entry[key] = row[key]
    if contact_id:
        entry["crm_contact_id"] = contact_id
    checkpoint["rows"][ref] = entry
    safe_event = {key: value for key, value in entry.items() if key != "normalized_phone"}
    append_private_event({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **safe_event})
    atomic_private_json(CHECKPOINT_PATH, checkpoint)


def checkpoint_phone_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row.get(key) for key in (
            "normalized_phone", "assumed_calling_code", "phone_normalization_status",
            "phone_normalization_reason", "phone_normalization_version",
        ) if row.get(key) is not None
    }


def reconcile_row_channels(row: dict[str, Any], crm: CRM) -> dict[str, dict[str, Any]]:
    """Read exact source and normalized channels; never write or infer a match."""
    found: dict[str, dict[str, Any]] = {}
    if row.get("email_key"):
        found.update({obj["id"]: obj for obj in crm.query(
            "emailAddress", row["email_raw"], row["email_key"]
        )})
    if row.get("phone_key"):
        found.update({obj["id"]: obj for obj in crm.query(
            "phoneNumber", row["phone_raw"], row["phone_key"]
        )})
    return found


def atomic_private_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, name = tempfile.mkstemp(prefix=".checkpoint-backup-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def preserve_checkpoint_backup(checkpoint_path: Path, backup_path: Path) -> None:
    original = checkpoint_path.read_bytes()
    if backup_path.exists():
        if hashlib.sha256(backup_path.read_bytes()).digest() != hashlib.sha256(original).digest():
            raise ImportFailure("checkpoint_migration_backup_conflict")
        return
    atomic_private_bytes(backup_path, original)


def migrate_checkpoint_phone_normalization(checkpoint: dict[str, Any], rows: list[dict[str, Any]],
                                           mapping: dict[str, Any], crm: CRM,
                                           normalizer_version: str) -> tuple[dict[str, Any], Counter[str]]:
    """Build format 3 from a legacy format-2 checkpoint after read reconciliation.

    Historical row values are retained under legacy_rows. Only rows
    with definitive validation rejection and no current exact channel match are
    omitted from active rows, allowing a later normal importer run to use the
    newly normalized payload. This function itself never creates Contacts.
    """
    if checkpoint.get("format") == 3:
        if checkpoint.get("phone_normalization_version") == normalizer_version:
            return checkpoint, Counter({"already_current": 1})
        raise ImportFailure("checkpoint_phone_normalization_version_conflict")
    if checkpoint.get("format") != 2 or checkpoint.get("source_identity_scheme") != "fixed_source_ordinal_v1":
        raise ImportFailure("checkpoint_phone_normalization_legacy_format_unsupported")
    if checkpoint.get("mapping_version") != mapping.get("mapping_version"):
        raise ImportFailure("checkpoint_mapping_version_mismatch")
    legacy_rows = checkpoint.get("rows")
    if not isinstance(legacy_rows, dict):
        raise ImportFailure("checkpoint_rows_invalid")
    old_version = checkpoint.get("phone_normalization_version")
    if old_version not in (None, normalizer_version):
        raise ImportFailure("checkpoint_phone_normalization_version_conflict")

    by_ref: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("phone_normalization_version") != normalizer_version:
            raise ImportFailure("source_row_phone_normalizer_version_mismatch")
        if row.get("phone_key") != row.get("normalized_phone"):
            raise ImportFailure("source_row_normalized_phone_key_mismatch")
        ref = source_reference(row)
        if ref in by_ref:
            raise ImportFailure("checkpoint_source_identity_collision")
        by_ref[ref] = row
    if not legacy_rows and by_ref:
        raise ImportFailure("empty_checkpoint_source_effects_unaccounted")
    if set(legacy_rows) != set(by_ref):
        raise ImportFailure("checkpoint_source_row_set_mismatch")
    for ref, entry in legacy_rows.items():
        row = by_ref[ref]
        if not isinstance(entry, dict):
            raise ImportFailure("checkpoint_entry_invalid")
        if (entry.get("source_ordinal") != row["source_ordinal"]
                or entry.get("source_identity") != source_identity(row)
                or entry.get("source_revision") != row["source_revision"]
                or entry.get("logical_row") != row["logical_row"]
                or entry.get("mapping_version") != row["mapping_version"]):
            raise ImportFailure("checkpoint_source_lineage_mismatch")

    active_rows: dict[str, dict[str, Any]] = {}
    dispositions: Counter[str] = Counter()
    local_no_effect = {
        "blank_record", "field_width_mismatch", "no_usable_channel",
        "ambiguous_source_channel_collision", "ambiguous_source_email_collision",
        "normalization_collision", "invalid_phone_number", "ambiguous_phone_number",
    }
    destination_exclusions = {
        "destination_conflict_without_channel_match",
        "destination_channels_resolve_to_different_contacts",
        "destination_validation_rejected",
    }

    for ref, old_entry in legacy_rows.items():
        row = by_ref[ref]
        disposition = old_entry.get("disposition")
        reason = old_entry.get("reason")
        next_entry = dict(old_entry)
        next_entry.update(checkpoint_phone_metadata(row))

        if disposition in ("created", "create_reconciled"):
            contact_id = old_entry.get("crm_contact_id")
            if not isinstance(contact_id, str) or not contact_id:
                raise ImportFailure("legacy_created_contact_id_missing")
            contact = crm.get_contact(contact_id)
            if not contact or contact.get("description") != contact_marker(row):
                raise ImportFailure("legacy_created_contact_marker_mismatch")
            matches = reconcile_row_channels(row, crm)
            if set(matches) != {contact_id}:
                raise ImportFailure("legacy_created_contact_channel_reconciliation_failed")
            active_rows[ref] = next_entry
            dispositions["created_effect_verified"] += 1
            continue

        if disposition == "not_created":
            contact_id = old_entry.get("crm_contact_id")
            if not isinstance(contact_id, str) or not contact_id:
                raise ImportFailure("legacy_existing_contact_id_missing")
            contact = crm.get_contact(contact_id)
            matches = reconcile_row_channels(row, crm)
            if not contact or set(matches) != {contact_id}:
                raise ImportFailure("legacy_existing_contact_reconciliation_failed")
            active_rows[ref] = next_entry
            dispositions["existing_effect_verified"] += 1
            continue

        if disposition == "halted" and reason == "unknown_create_effect_requires_review":
            matches = reconcile_row_channels(row, crm)
            marked = [obj for obj in matches.values() if obj.get("description") == contact_marker(row)]
            if len(matches) != 1 or len(marked) != 1:
                raise ImportFailure("legacy_unknown_create_effect_unresolved")
            next_entry.update(disposition="create_reconciled",
                              reason="legacy_unknown_effect_source_marker_reconciled",
                              crm_contact_id=marked[0]["id"])
            active_rows[ref] = next_entry
            dispositions["unknown_effect_reconciled"] += 1
            continue

        if disposition == "halted" and reason == "destination_auth_or_scope_error":
            active_rows[ref] = next_entry
            dispositions["terminal_halted_preserved"] += 1
            continue

        if disposition == "excluded" and reason in local_no_effect:
            if row.get("disposition") == "candidate":
                dispositions["local_exclusion_safe_to_reconsider"] += 1
                continue
            if row.get("disposition") == "excluded":
                next_entry["reason"] = row["reason"]
            active_rows[ref] = next_entry
            dispositions["local_exclusion_preserved"] += 1
            continue

        if disposition == "excluded" and reason in destination_exclusions:
            matches = reconcile_row_channels(row, crm)
            if row.get("disposition") == "excluded":
                next_entry["reason"] = row["reason"]
                active_rows[ref] = next_entry
                dispositions["current_source_exclusion_preserved"] += 1
                continue
            if reason == "destination_validation_rejected" and row.get("disposition") == "candidate":
                if not matches:
                    # The historic 400/422 rejection is retained in legacy_rows;
                    # absence of an exact current match makes this row eligible
                    # for a future importer run with the new payload.
                    dispositions["validation_rejection_safe_to_reconsider"] += 1
                    continue
                if len(matches) == 1:
                    next_entry.update(disposition="not_created",
                                      reason="legacy_validation_rejection_existing_match_preserved",
                                      crm_contact_id=next(iter(matches)))
                else:
                    next_entry.update(reason="legacy_validation_rejection_multiple_current_matches")
            active_rows[ref] = next_entry
            dispositions["destination_exclusion_preserved"] += 1
            continue

        raise ImportFailure("legacy_checkpoint_disposition_unrecognized")

    migrated = {
        "format": 3,
        "source_identity_scheme": "fixed_source_ordinal_v1",
        "mapping_version": checkpoint["mapping_version"],
        "phone_normalization_version": normalizer_version,
        "rows": active_rows,
        "legacy_rows_format2": legacy_rows,
        "phone_normalization_migration": {
            "from_format": 2,
            "from_phone_normalization_version": old_version,
            "history_row_count": len(legacy_rows),
            "active_row_count": len(active_rows),
            "reconsidered_validation_rejection_count": dispositions["validation_rejection_safe_to_reconsider"],
        },
    }
    return migrated, dispositions


def persist_phone_checkpoint_migration(original: dict[str, Any], migrated: dict[str, Any],
                                        dispositions: Counter[str]) -> bool:
    """Atomically retain the old checkpoint, then install the reconciled format-3 state."""
    if migrated is original:
        return True
    if not CHECKPOINT_PATH.is_file():
        raise ImportFailure("legacy_checkpoint_missing_at_migration_commit")
    current = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    if current != original:
        raise ImportFailure("checkpoint_changed_during_migration")
    backup = PRIVATE_DIR / "import-checkpoint-format2-before-phone-normalization.json"
    preserve_checkpoint_backup(CHECKPOINT_PATH, backup)
    atomic_private_json(CHECKPOINT_PATH, migrated)
    try:
        append_private_event({
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": "checkpoint_phone_normalization_migrated",
            "from_format": 2,
            "to_format": 3,
            "legacy_row_count": len(migrated["legacy_rows_format2"]),
            "active_row_count": len(migrated["rows"]),
            "disposition_counts": dict(dispositions),
        })
        return True
    except OSError:
        # The authoritative checkpoint already contains a complete migration
        # receipt. Never report a failed migration that might be blindly replayed.
        return False


def migrate_checkpoint_source_identity(checkpoint: dict[str, Any], rows: list[dict[str, Any]], crm: CRM) -> tuple[int, int]:
    """Migrate v1 checkpoint keys/markers after exact legacy lineage verification."""
    if checkpoint.get("format") in (2, 3) and checkpoint.get("source_identity_scheme") == "fixed_source_ordinal_v1":
        return 0, 0
    if checkpoint.get("format") != 1 or not isinstance(checkpoint.get("rows"), dict):
        raise ImportFailure("legacy_checkpoint_format_unsupported")

    by_legacy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_legacy[legacy_source_reference(row)].append(row)
    if any(len(refs) != 1 for refs in by_legacy.values()):
        raise ImportFailure("legacy_checkpoint_source_identity_collision")
    if set(checkpoint["rows"]) != set(by_legacy):
        raise ImportFailure("legacy_checkpoint_row_set_mismatch")

    backup = PRIVATE_DIR / "import-checkpoint-v1-backup.json"
    if not backup.exists():
        shutil.copy2(CHECKPOINT_PATH, backup)
        os.chmod(backup, 0o600)

    checkpoint_rows: dict[str, dict[str, Any]] = {}
    migrated_markers = 0
    for old_ref, candidates in by_legacy.items():
        row = candidates[0]
        entry = checkpoint["rows"][old_ref]
        if (entry.get("source_ordinal") != row["source_ordinal"]
                or entry.get("source_revision") != row["source_revision"]
                or entry.get("logical_row") != row["logical_row"]
                or entry.get("mapping_version") != row["mapping_version"]):
            raise ImportFailure("legacy_checkpoint_lineage_mismatch")
        new_entry = dict(entry)
        new_entry["source_identity"] = source_identity(row)
        if entry.get("disposition") in ("created", "create_reconciled"):
            contact_id = entry.get("crm_contact_id")
            if not isinstance(contact_id, str) or not contact_id:
                raise ImportFailure("legacy_created_contact_id_missing")
            contact = crm.get_contact(contact_id)
            if contact is None:
                raise ImportFailure("legacy_created_contact_missing")
            if contact.get("description") == legacy_contact_marker(row):
                crm.call("PUT", "/Contact/" + urllib.parse.quote(contact_id, safe=""),
                         {"description": contact_marker(row)})
                migrated_markers += 1
            elif contact.get("description") != contact_marker(row):
                raise ImportFailure("legacy_created_contact_marker_mismatch")
            verified = crm.get_contact(contact_id)
            if not verified or verified.get("description") != contact_marker(row):
                raise ImportFailure("migrated_contact_marker_verification_failed")
        new_ref = source_reference(row)
        if new_ref in checkpoint_rows:
            raise ImportFailure("new_checkpoint_identity_collision")
        checkpoint_rows[new_ref] = new_entry

    checkpoint["format"] = 2
    checkpoint["source_identity_scheme"] = "fixed_source_ordinal_v1"
    checkpoint["rows"] = checkpoint_rows
    atomic_private_json(CHECKPOINT_PATH, checkpoint)
    append_private_event({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                          "event": "checkpoint_source_identity_migrated",
                          "rows_migrated": len(checkpoint_rows),
                          "crm_markers_migrated": migrated_markers})
    return len(checkpoint_rows), migrated_markers


def rollback_created(checkpoint: dict[str, Any], rows: list[dict[str, Any]], crm: CRM) -> tuple[Counter[str], bool]:
    """Soft-delete only records created here whose stable marker is intact."""
    by_ref = {
        source_reference(row): row
        for row in rows
    }
    counts: Counter[str] = Counter()
    conflict = False
    for ref, entry in checkpoint["rows"].items():
        if entry.get("disposition") not in ("created", "create_reconciled"):
            continue
        contact_id = entry.get("crm_contact_id")
        row = by_ref.get(ref)
        if not contact_id or row is None:
            counts["rollback_lineage_missing"] += 1
            conflict = True
            continue
        contact = crm.get_contact(contact_id)
        if contact is None:
            entry["rollback_status"] = "already_deleted"
            counts["already_deleted"] += 1
        elif contact.get("description") != contact_marker(row):
            entry["rollback_status"] = "blocked_marker_changed"
            counts["blocked_marker_changed"] += 1
            conflict = True
        else:
            crm.call("DELETE", "/Contact/" + urllib.parse.quote(contact_id, safe=""))
            if crm.get_contact(contact_id) is not None:
                entry["rollback_status"] = "delete_not_verified"
                counts["delete_not_verified"] += 1
                conflict = True
            else:
                entry["rollback_status"] = "soft_deleted_and_verified"
                counts["soft_deleted_and_verified"] += 1
        append_private_event({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                              "source_ordinal": entry.get("source_ordinal"),
                              "logical_row": entry.get("logical_row"),
                              "source_revision": entry.get("source_revision"),
                              "mapping_version": entry.get("mapping_version"),
                              "rollback_status": entry["rollback_status"]})
        atomic_private_json(CHECKPOINT_PATH, checkpoint)
    return counts, conflict


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="maximum new Contacts; zero means the fixed eligible set")
    parser.add_argument("--rollback", action="store_true", help="reverse only this import's marked created Contacts")
    parser.add_argument("--migrate-source-identities", action="store_true", help="migrate legacy private checkpoint keys and exact matching CRM markers")
    parser.add_argument("--migrate-phone-normalization", action="store_true",
                        help="reconcile format-2 rows and create a version-3 private checkpoint; does not import Contacts")
    args = parser.parse_args()
    if args.limit < 0:
        print(json.dumps({"error": "limit_must_be_nonnegative"}))
        return 2
    if args.migrate_phone_normalization and (args.rollback or args.migrate_source_identities or args.limit):
        print(json.dumps({"error": "phone_normalization_migration_options_conflict"}))
        return 2
    try:
        module = load_quality_module()
        mapping = module.require_private_mapping(MAPPING_PATH)
        if mapping.get("import_authorization") != "bounded first import to selected local EspoCRM explicitly assigned by qitem-20261108184715-500ad3de; no external writes":
            raise ImportFailure("bounded_import_authorization_missing")
        rows = source_records(module, mapping)
        checkpoint_exists = CHECKPOINT_PATH.exists()
        if checkpoint_exists:
            if stat.S_IMODE(CHECKPOINT_PATH.stat().st_mode) & 0o077:
                raise ImportFailure("checkpoint_permissions_too_open")
            checkpoint = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        else:
            checkpoint = {"format": 3, "source_identity_scheme": "fixed_source_ordinal_v1",
                          "mapping_version": mapping["mapping_version"],
                          "phone_normalization_version": module.PHONE_NORMALIZATION_VERSION, "rows": {}}
        if checkpoint.get("mapping_version") != mapping["mapping_version"] or not isinstance(checkpoint.get("rows"), dict):
            raise ImportFailure("checkpoint_mapping_version_mismatch")
        if args.migrate_phone_normalization:
            if not checkpoint_exists:
                raise ImportFailure("legacy_phone_normalization_checkpoint_missing")
            crm = CRM()
            _, user = crm.call("GET", "/App/user")
            if user.get("user", {}).get("type") != "admin":
                raise ImportFailure("local_import_identity_not_admin")
            migrated, migration_counts = migrate_checkpoint_phone_normalization(
                checkpoint, rows, mapping, crm, module.PHONE_NORMALIZATION_VERSION
            )
            if migrated is not checkpoint:
                event_recorded = persist_phone_checkpoint_migration(checkpoint, migrated, migration_counts)
            else:
                event_recorded = True
            print(json.dumps({
                "operation": "private_phone_normalization_checkpoint_migration",
                "checkpoint_format": migrated.get("format"),
                "phone_normalization_version": migrated.get("phone_normalization_version"),
                "legacy_rows_preserved": len(migrated.get("legacy_rows_format2", {})),
                "active_checkpoint_rows": len(migrated.get("rows", {})),
                "migration_dispositions": dict(migration_counts),
                "migration_event_recorded": event_recorded,
                "contacts_created": 0,
                "owner_sources_changed": False,
                "crm_contact_writes": False,
            }, separators=(",", ":")))
            return 0
        if checkpoint.get("phone_normalization_version") != module.PHONE_NORMALIZATION_VERSION:
            raise ImportFailure("phone_normalization_checkpoint_reconciliation_required")
        if checkpoint.get("format") != 3:
            raise ImportFailure("checkpoint_phone_normalization_migration_required")
        crm = CRM()
        _, user = crm.call("GET", "/App/user")
        if user.get("user", {}).get("type") != "admin":
            raise ImportFailure("local_import_identity_not_admin")
        if args.migrate_source_identities:
            migrated_rows, migrated_markers = migrate_checkpoint_source_identity(checkpoint, rows, crm)
            print(json.dumps({"operation": "private_source_identity_migration",
                              "checkpoint_rows_migrated": migrated_rows,
                              "crm_markers_migrated": migrated_markers,
                              "owner_sources_changed": False,
                              "external_writes": False}, separators=(",", ":")))
            return 0
        if checkpoint.get("format") != 3 or checkpoint.get("source_identity_scheme") != "fixed_source_ordinal_v1":
            raise ImportFailure("checkpoint_source_identity_migration_required")
        if args.rollback:
            rollback_counts, conflict = rollback_created(checkpoint, rows, crm)
            print(json.dumps({"operation": "bounded_private_import_rollback",
                              "owner_sources_changed": False,
                              "external_writes": False,
                              "rollback_dispositions": dict(rollback_counts),
                              "rollback_blocked_for_review": conflict}, separators=(",", ":")))
            return 1 if conflict else 0
        counts: Counter[str] = Counter()
        created_this_run = 0
        stop_reason = None
        for row in rows:
            ref = source_reference(row)
            existing_checkpoint = checkpoint["rows"].get(ref)
            if existing_checkpoint:
                if existing_checkpoint.get("disposition") in ("created", "create_reconciled"):
                    contact_id = existing_checkpoint.get("crm_contact_id")
                    contact = crm.get_contact(contact_id) if contact_id else None
                    if not contact or contact.get("description") != contact_marker(row):
                        raise ImportFailure("checkpoint_contact_marker_missing_or_changed")
                counts[existing_checkpoint.get("reason", existing_checkpoint.get("disposition", "checkpointed"))] += 1
                continue
            if row["disposition"] == "excluded":
                append_disposition(checkpoint, row, "excluded", row["reason"])
                counts[row["reason"]] += 1
                continue
            if row["disposition"] != "candidate":
                raise ImportFailure("unexpected_row_disposition")
            if args.limit and created_this_run >= args.limit:
                counts["not_attempted_due_to_limit"] += 1
                continue

            by_channel: list[dict[str, Any]] = []
            if row["email_key"]:
                by_channel.extend(crm.query("emailAddress", row["email_raw"], row["email_key"]))
            if row["phone_key"]:
                by_channel.extend(crm.query("phoneNumber", row["phone_raw"], row["phone_key"]))
            matches = {obj["id"]: obj for obj in by_channel}
            if len(matches) > 1:
                append_disposition(checkpoint, row, "excluded", "destination_channels_resolve_to_different_contacts")
                counts["destination_ambiguous_existing_match"] += 1
                continue
            if len(matches) == 1:
                contact_id = next(iter(matches))
                append_disposition(checkpoint, row, "not_created", "unique_existing_contact_preserved", contact_id)
                counts["unique_existing_contact_preserved"] += 1
                continue

            body = build_contact_body(row)
            try:
                _, created = crm.call("POST", "/Contact", body)
                contact_id = created.get("id")
                if not contact_id:
                    raise ImportFailure("create_response_missing_contact_id")
                verified = crm.get_contact(contact_id)
                if not verified or verified.get("description") != contact_marker(row):
                    raise ImportFailure("created_contact_provenance_verification_failed")
                if verified.get("lastName") != row["last_name"]:
                    raise ImportFailure("created_contact_surname_verification_failed")
                if row["email_raw"] is not None and verified.get("emailAddress", "").strip().casefold() != row["email_key"]:
                    raise ImportFailure("created_contact_email_verification_failed")
                if row["normalized_phone"] is not None and verified.get("phoneNumber", "").strip() != row["normalized_phone"].strip():
                    raise ImportFailure("created_contact_phone_verification_failed")
                append_disposition(checkpoint, row, "created", "created_and_verified", contact_id)
                created_this_run += 1
                counts["created_and_verified"] += 1
            except ImportFailure as exc:
                # The effect may have happened even when the response failed.
                # Reconcile exact channel matches before recording a retryable state.
                if exc.code.startswith("crm_http_") or exc.code in ("crm_transport_or_response_error", "create_response_missing_contact_id"):
                    reconciled: dict[str, dict[str, Any]] = {}
                    if row["email_key"]:
                        reconciled.update({x["id"]: x for x in crm.query("emailAddress", row["email_raw"], row["email_key"])})
                    if row["phone_key"]:
                        reconciled.update({x["id"]: x for x in crm.query("phoneNumber", row["phone_raw"], row["phone_key"])})
                    marked = [obj for obj in reconciled.values() if obj.get("description") == contact_marker(row)]
                    if len(marked) == 1:
                        append_disposition(checkpoint, row, "create_reconciled", "unknown_effect_reconciled_by_source_marker", marked[0]["id"])
                        counts["unknown_effect_reconciled_by_source_marker"] += 1
                        created_this_run += 1
                        continue
                    if exc.code.startswith(("crm_http_400", "crm_http_422")):
                        append_disposition(checkpoint, row, "excluded", "destination_validation_rejected")
                        append_private_event({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                              "source_ordinal": row["source_ordinal"],
                                              "logical_row": row["logical_row"],
                                              "source_revision": row["source_revision"],
                                              "mapping_version": row["mapping_version"],
                                              "failure_code": exc.code})
                        counts["destination_validation_rejected"] += 1
                        continue
                    if exc.code.startswith("crm_http_409"):
                        append_disposition(checkpoint, row, "excluded", "destination_conflict_without_channel_match")
                        append_private_event({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                              "source_ordinal": row["source_ordinal"],
                                              "logical_row": row["logical_row"],
                                              "source_revision": row["source_revision"],
                                              "mapping_version": row["mapping_version"],
                                              "failure_code": exc.code})
                        counts["destination_conflict_without_channel_match"] += 1
                        continue
                    if exc.code in ("crm_http_401", "crm_http_403"):
                        append_disposition(checkpoint, row, "halted", "destination_auth_or_scope_error")
                        counts["destination_auth_or_scope_error"] += 1
                        stop_reason = "destination_auth_or_scope_error"
                        break
                    append_disposition(checkpoint, row, "halted", "unknown_create_effect_requires_review")
                    append_private_event({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                          "source_ordinal": row["source_ordinal"],
                                          "logical_row": row["logical_row"],
                                          "source_revision": row["source_revision"],
                                          "mapping_version": row["mapping_version"],
                                          "failure_code": exc.code})
                    counts["unknown_create_effect_requires_review"] += 1
                    stop_reason = "unknown_create_effect_requires_review"
                    break
                raise
        summary = {
            "import_kind": "bounded_local_espocrm_api_create_only",
            "local_target": "EspoCRM 10.0.11 at loopback",
            "source_paths": "exact_three_spec_paths_only",
            "owner_sources_changed": False,
            "external_writes": False,
            "aggregate_dispositions": dict(counts),
            "created_this_run": created_this_run,
            "created_total_in_checkpoint": sum(x.get("disposition") in ("created", "create_reconciled") for x in checkpoint["rows"].values()),
            "checkpoint_rows": len(checkpoint["rows"]),
            "stopped_for_review": stop_reason,
        }
        print(json.dumps(summary, separators=(",", ":")))
        return 1 if stop_reason else 0
    except (ImportFailure, OSError, ValueError, KeyError, TypeError, csv.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        code = exc.code if isinstance(exc, ImportFailure) else "private_import_input_or_state_invalid"
        print(json.dumps({"error": code}))
        return 2


if __name__ == "__main__":
    sys.exit(main())

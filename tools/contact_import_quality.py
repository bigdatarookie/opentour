#!/usr/bin/env python3
"""Read-only mapped dry-run for the three CSVs named in SPEC.md.

Source selection is fixed and non-recursive. Detailed source identity and
mapping data must stay in the seat-private mapping file; stdout contains only
aggregate counts and categorical mapping states.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import stat
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".artifacts" / "client-datatables"
PRIVATE_ROOT = Path("/Users/garry/.openrig/topology/rigs/opentour-rig/seats/data-engineer").resolve()
EXPECTED_SOURCES = (
    (1275, "отчетность 2021-2026 фио и тел.__2024-2026.csv"),
    (1266, "отчетность 2021-2026 фио и тел.__2021-2024.csv"),
    (61, "Башкирия часть 1 школы сады   2 часа по Москве__Лист1.csv"),
)
DELIMITERS = {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}
EMAIL_SHAPE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE_SHAPE = re.compile(r"\+?[0-9][0-9 ()./\-]*")
PHONE_NORMALIZATION_VERSION = "e164-default-7-v1"
NONE_FALLBACK_METADATA = {
    "enabled": True,
    "literal": "None",
    "metadata_status": "placeholder_none",
    "exclude_from_deduplication": True,
    "replace_only_after_confirmed_surname_review": True,
}


def fail(code: str, ordinal: int | None = None) -> int:
    payload: dict[str, object] = {"error": code}
    if ordinal is not None:
        payload["source_ordinal"] = ordinal
    print(json.dumps(payload))
    return 2


def require_private_mapping(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(PRIVATE_ROOT) or not resolved.is_file():
        raise ValueError("private_mapping_outside_boundary")
    if stat.S_IMODE(resolved.stat().st_mode) & 0o077:
        raise ValueError("private_mapping_permissions_too_open")
    with resolved.open("r", encoding="utf-8") as stream:
        mapping = json.load(stream)
    if not isinstance(mapping, dict) or mapping.get("mapping_status") != "approved_user_fallback_applied_review_required":
        raise ValueError("private_mapping_state_invalid")
    if mapping.get("approved_policy_ref") != "qitem-20261108184527-9ce151c6c03bdd57":
        raise ValueError("private_mapping_policy_unverified")
    return mapping


def selected_index(selection: Any, headers: list[str]) -> int | None:
    if selection is None:
        return None
    if not isinstance(selection, dict):
        raise ValueError("private_mapping_shape_invalid")
    index = selection.get("column_index")
    if not isinstance(index, int) or index < 0 or index >= len(headers):
        raise ValueError("private_mapping_column_invalid")
    if selection.get("header") != headers[index]:
        raise ValueError("private_mapping_header_mismatch")
    return index


def approved_none_fallback(source: dict[str, Any]) -> bool:
    """Require the full, exact approved placeholder policy tuple."""
    fallback = source.get("surname_fallback")
    if not isinstance(fallback, dict) or set(fallback) != set(NONE_FALLBACK_METADATA):
        return False
    return (
        fallback.get("enabled") is True
        and fallback.get("literal") == "None"
        and type(fallback.get("literal")) is str
        and fallback.get("metadata_status") == "placeholder_none"
        and type(fallback.get("metadata_status")) is str
        and fallback.get("exclude_from_deduplication") is True
        and fallback.get("replace_only_after_confirmed_surname_review") is True
    )


def surname_readiness(source: dict[str, Any], value: str | None) -> tuple[str, str | None]:
    if isinstance(value, str) and value.strip():
        return "source_confirmed", value
    if approved_none_fallback(source):
        return "placeholder_none", "None"
    return "unavailable", None


def parse_email(value: str) -> str | None:
    candidate = value.strip()
    if candidate and EMAIL_SHAPE.fullmatch(candidate):
        return candidate.casefold()
    return None


def normalize_phone(value: str, *, previous_assumption: str | None = None) -> dict[str, str | None]:
    """Return a versioned E.164-shaped key without changing source text.

    Unknown calling codes use the approved +7 default. This is a formatting
    policy, not evidence of the contact's country or number ownership. The
    routine performs only explicit, deterministic parsing; it does not claim
    libphonenumber possible-number validation or reachability.
    """
    result: dict[str, str | None] = {
        "status": "missing",
        "reason": "phone_missing",
        "normalized_phone": None,
        "assumed_calling_code": None,
        "normalization_version": PHONE_NORMALIZATION_VERSION,
    }
    if not isinstance(value, str) or not value.strip():
        return result

    candidate = value.strip()
    if not PHONE_SHAPE.fullmatch(candidate) or candidate.count("+") > 1:
        result.update(status="invalid", reason="unsupported_phone_characters")
        return result

    explicit_international = candidate.startswith("+")
    digits = "".join(character for character in candidate if character.isdigit())
    if explicit_international:
        if not 8 <= len(digits) <= 15:
            result.update(status="invalid", reason="international_length_out_of_range")
            return result
        if digits.startswith("0"):
            result.update(status="invalid", reason="international_calling_code_starts_with_zero")
            return result
        if digits.startswith("7") and len(digits) != 11:
            result.update(status="invalid", reason="default_code_length_out_of_range")
            return result
        assumption = "+7" if previous_assumption == "+7" and digits.startswith("7") else None
        result.update(status="normalized", reason=None, normalized_phone="+" + digits,
                      assumed_calling_code=assumption)
        return result

    # An access prefix such as 00 can be international or local-dialing
    # notation. With no explicit '+', interpreting it as +7 is ambiguous.
    if digits.startswith(("00", "011")):
        result.update(status="ambiguous", reason="unmarked_international_access_prefix")
        return result

    assumed = "+7"
    if len(digits) == 10 and not digits.startswith("0"):
        national = digits
    elif len(digits) == 11 and digits.startswith("8"):
        # The Russian domestic trunk prefix is replaced, never concatenated.
        national = digits[1:]
    elif len(digits) == 11 and digits.startswith("7"):
        # The calling-code digits are already present; add only E.164 '+'.
        result.update(status="normalized", reason=None, normalized_phone="+" + digits,
                      assumed_calling_code=assumed)
        return result
    elif 7 <= len(digits) <= 12:
        result.update(status="ambiguous", reason="unsupported_national_length_or_prefix")
        return result
    else:
        result.update(status="invalid", reason="national_length_out_of_range")
        return result

    result.update(status="normalized", reason=None, normalized_phone="+7" + national,
                  assumed_calling_code=assumed)
    return result


def parse_phone(value: str) -> str | None:
    """Compatibility wrapper returning the normalized phone key, if usable."""
    return normalize_phone(value)["normalized_phone"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", required=True, type=Path)
    args = parser.parse_args()

    try:
        mapping = require_private_mapping(args.mapping)
    except (OSError, ValueError, json.JSONDecodeError):
        return fail("private_mapping_unavailable_or_invalid")

    expected_root = ROOT / ".artifacts"
    try:
        expected_root_real = expected_root.resolve(strict=True)
        artifacts_root = ARTIFACTS.resolve(strict=True)
    except OSError:
        return fail("expected_source_directory_missing")
    if artifacts_root.parent != expected_root_real:
        return fail("expected_source_directory_outside_boundary")

    sources = mapping.get("sources")
    if not isinstance(sources, list) or len(sources) != len(EXPECTED_SOURCES):
        return fail("private_mapping_source_set_invalid")
    by_ordinal = {item.get("source_ordinal"): item for item in sources if isinstance(item, dict)}
    if set(by_ordinal) != set(range(1, len(EXPECTED_SOURCES) + 1)):
        return fail("private_mapping_source_set_invalid")

    resolved_sources: list[tuple[int, Path, dict[str, Any]]] = []
    for ordinal, (_, filename) in enumerate(EXPECTED_SOURCES, 1):
        item = by_ordinal[ordinal]
        try:
            source_path = (ARTIFACTS / filename).resolve(strict=True)
        except OSError:
            return fail("expected_source_missing", ordinal)
        if source_path.parent != artifacts_root or not source_path.is_file():
            return fail("expected_source_outside_boundary_or_not_file", ordinal)
        if item.get("private_source_name") != filename or item.get("private_source_path") != str(source_path):
            return fail("private_mapping_source_identity_mismatch", ordinal)
        resolved_sources.append((ordinal, source_path, item))
    if len({path for _, path, _ in resolved_sources}) != len(EXPECTED_SOURCES):
        return fail("expected_sources_not_unique")

    totals: Counter[str] = Counter()
    per_source: list[dict[str, object]] = []
    email_groups: dict[str, set[tuple[int, int]]] = defaultdict(set)
    phone_groups: dict[str, set[tuple[int, int]]] = defaultdict(set)
    phone_raw_groups: dict[str, set[tuple[int, int]]] = defaultdict(set)
    row_channel_values: dict[tuple[int, int], tuple[str | None, str | None]] = {}
    row_mapping_complete: dict[tuple[int, int], bool] = {}
    row_surname_ready: dict[tuple[int, int], bool] = {}

    for ordinal, path, item in resolved_sources:
        try:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != item.get("source_sha256"):
                return fail("private_mapping_source_revision_mismatch", ordinal)
            if not raw.startswith(b"\xef\xbb\xbf"):
                return fail("utf8_bom_missing", ordinal)
            content = raw.decode("utf-8-sig", errors="strict")
            dialect = csv.Sniffer().sniff(content[:8192], delimiters=",;\t|")
            reader = csv.reader(io.StringIO(content, newline=""), dialect)
            headers = next(reader, None)
            if headers is None or headers != item.get("headers"):
                return fail("private_mapping_header_mismatch", ordinal)
            columns = item.get("selected_target_columns")
            if not isinstance(columns, dict):
                return fail("private_mapping_shape_invalid", ordinal)
            email_index = selected_index(columns.get("emailAddress"), headers)
            phone_index = selected_index(columns.get("phoneNumber"), headers)
            last_name_index = selected_index(columns.get("lastName"), headers)
            # firstName is checked for staleness even though it is not required.
            selected_index(columns.get("firstName"), headers)
        except (OSError, UnicodeDecodeError, csv.Error, ValueError, TypeError):
            return fail("mapped_source_unreadable_or_invalid", ordinal)

        local: Counter[str] = Counter()
        data_row = 0
        previous_line = reader.line_num
        for row in reader:
            current_line = reader.line_num
            multiline = current_line - previous_line > 1
            previous_line = current_line
            data_row += 1
            local["multiline_records"] += int(multiline)
            if not row or all(not value.strip() for value in row):
                local["blank_records"] += 1
                continue
            local["data_records"] += 1
            if len(row) != len(headers):
                local["width_mismatches"] += 1
                continue
            if email_index is None and phone_index is None:
                local["channel_mapping_unresolved"] += 1
                continue

            email_text = row[email_index] if email_index is not None else ""
            phone_text = row[phone_index] if phone_index is not None else ""
            email_key = parse_email(email_text) if email_index is not None else None
            phone_result = normalize_phone(phone_text) if phone_index is not None else normalize_phone("")
            phone_key = phone_result["normalized_phone"]
            if email_index is not None and email_text.strip():
                local["email_present"] += 1
                if email_key is None:
                    local["email_not_usable_candidate"] += 1
            if phone_index is not None and phone_text.strip():
                local["phone_present"] += 1
                local[f"phone_normalization_{phone_result['status']}"] += 1
                if phone_result["assumed_calling_code"] == "+7":
                    local["phone_default_calling_code_assumed"] += 1
                if phone_key is None:
                    local["phone_not_usable_candidate"] += 1
                else:
                    local["phone_text_values_leading_zero"] += int(phone_text.lstrip().startswith("0"))
                    local["phone_text_values_leading_plus"] += int(phone_text.lstrip().startswith("+"))

            row_key = (ordinal, data_row + 1)  # CSV logical row number; header is row 1.
            row_channel_values[row_key] = (email_key, phone_key)
            row_mapping_complete[row_key] = email_index is not None and phone_index is not None
            if email_key is not None:
                local["email_usable_candidates"] += 1
                email_groups[email_key].add(row_key)
            if phone_key is not None:
                local["phone_usable_candidates"] += 1
                phone_groups[phone_key].add(row_key)
                phone_raw_groups[phone_key].add(row_key)
            if email_key and phone_key:
                local["both_channel_candidates"] += 1
            elif email_key:
                local["email_only_candidates"] += 1
            elif phone_key:
                local["phone_only_candidates"] += 1
            else:
                local["no_usable_channel_candidates"] += 1

            if email_key or phone_key:
                surname_value = row[last_name_index] if last_name_index is not None else None
                surname_status, _ = surname_readiness(item, surname_value)
                row_surname_ready[row_key] = surname_status != "unavailable"
                if surname_status == "source_confirmed":
                    local["source_confirmed_surname_candidates"] += 1
                elif surname_status == "placeholder_none":
                    local["surname_placeholder_candidates"] += 1
                else:
                    local["surname_policy_unavailable"] += 1

        local["logical_rows_including_header_and_blank"] = 1 + local["data_records"] + local["blank_records"]
        totals.update(local)
        per_source.append({
            "source_ordinal": ordinal,
            "declared_rows": int(item.get("declared_rows_from_spec", 0)),
            "header_columns": len(headers),
            "delimiter": DELIMITERS.get(dialect.delimiter, "other"),
            "utf8_bom": True,
            "email_mapping_selected": email_index is not None,
            "phone_mapping_selected": phone_index is not None,
            "last_name_mapping_selected": last_name_index is not None,
            "csv_field_values_read_as_text": True,
            **dict(local),
        })

    duplicate_candidate_rows: set[tuple[int, int]] = set()
    ambiguous_duplicate_rows: set[tuple[int, int]] = set()
    duplicate_groups = 0
    for groups in (email_groups, phone_groups):
        for refs in groups.values():
            if len(refs) < 2:
                continue
            duplicate_groups += 1
            duplicate_candidate_rows.update(refs)
            signatures = {row_channel_values[ref] for ref in refs}
            if len(signatures) > 1 or any(not row_mapping_complete[ref] for ref in refs):
                ambiguous_duplicate_rows.update(refs)

    normalization_collision_rows: set[tuple[int, int]] = set()
    for refs in phone_raw_groups.values():
        # Any repeated normalized key is held for review, including repeated
        # identical source text. Raw formatting remains available locally.
        if len(refs) > 1:
            normalization_collision_rows.update(refs)
    ambiguous_duplicate_rows.update(normalization_collision_rows)

    # Automatic creation eligibility is computed after the cross-source
    # collision pass. None is a required CRM field placeholder only; it never
    # participates in channel matching or deduplication.
    automatic_candidates = 0
    for ordinal, _, item in resolved_sources:
        local_ordinal = next(x for x in per_source if x["source_ordinal"] == ordinal)
        for key, channels in row_channel_values.items():
            if key[0] != ordinal or key in ambiguous_duplicate_rows:
                continue
            if not any(channels) or not row_surname_ready.get(key, False):
                continue
            automatic_candidates += 1
            local_ordinal["crm_contract_ready_candidates"] = int(local_ordinal.get("crm_contract_ready_candidates", 0)) + 1
            totals["crm_contract_ready_candidates"] += 1

    result = {
        "dry_run_kind": "source_only_mapped_read_only",
        "target_contract": "EspoCRM Contact; lastName required; emailAddress or phoneNumber is sufficient as a contact channel",
        "destination_lookup_performed": False,
        "destination_write_performed": False,
        "owner_source_changed": False,
        "per_source_ordinal_counts": per_source,
        "aggregate_counts": {
            **dict(totals),
            "rows_in_duplicate_candidate_groups": len(duplicate_candidate_rows),
            "rows_in_ambiguous_duplicate_groups": len(ambiguous_duplicate_rows),
            "rows_in_phone_normalization_collisions": len(normalization_collision_rows),
            "duplicate_candidate_groups": duplicate_groups,
            "automatic_import_candidates_after_ambiguous_exclusion": automatic_candidates,
        },
        "limitations": [
            "Header mapping remains heuristic and requires independent review; full-name columns are not split into first/last name.",
            "Workbook and sheet aliases remain unconfirmed and are not inferred from file names.",
            "Email syntax is a local shape check; no deliverability or consent is established.",
            "Phone normalization uses approved +7 default for unmarked supported national shapes; output is syntactic and does not establish country, reachability, or ownership.",
            "Duplicate candidates are not merged. Destination CRM was not queried.",
            "When no explicit surname is mapped, the approved literal None fallback is recorded as placeholder_none and excluded from deduplication.",
            "Manager Import was denied in the synthetic check; blind Create Only replay duplicated a record. Unknown create effects require destination reconciliation before any retry.",
        ],
    }
    output_path = args.mapping.resolve().parent / "dry-run-summary.json"
    output_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.umask(0o077)
    try:
        descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        output_path.chmod(0o600)
    except OSError:
        return fail("private_dry_run_write_failed")

    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Exact-reference terminal-conflict recovery

This opt-in lane addresses terminal format-3 rows whose disposition is exactly `excluded` and reason exactly `destination_conflict_without_channel_match`. Normal import still skips checkpointed rows. Historical rows, migration history and event lines are never reset/deleted; new receipts append under `conflict_resume.rows[exact_reference]` in the same atomic private checkpoint and mirror into the existing private event log.

Implementation assignment qitem-20261110191255-e426d189e9bcae70 permits synthetic/CI work only. This document is an executable interface description, not authority to run against the owner CRM. Lead owns independent acceptance and a later bounded consumer assignment. A historical no-match report is not a write authorization or historical cause attribution.

## Explicit selection

A separately authorized consumer prepares a mode-0600 JSON file under the existing Data Engineer PRIVATE_DIR (the directory declared in tools/contact_import.py). It contains exactly these fields:

```json
{
  "format": 1,
  "mapping_version": "<current approved mapping version>",
  "mapping_sha256": "<mapping_digest(current approved mapping)>",
  "phone_normalization_version": "e164-default-7-v1",
  "source_references": ["<exact source_reference(row)>"]
}
```

The digest is SHA256 of UTF-8 JSON using sorted keys, ensure_ascii=False and separators comma/colon, as implemented by mapping_digest. References bind source ordinal, source-byte revision, logical row and mapping version. They are private metadata: never include the selection or its contents in Git/shared proof/chat. The normal source loader still verifies the fixed CSV paths/BOM/revisions/headers/approved mapping and uses the accepted normalizer. Every selected reference is validated before any CRM call; unknown/duplicate/non-conflict/noncandidate/mismatched references fail closed, including references beyond the processing bound. Current checkpoint/row normalizer metadata must match.

Only under a subsequent authorized consumer assignment, the interface is:

```sh
python3 tools/contact_import.py --resume-conflicts-file /absolute/existing/private-contact-import/conflict-resume-selection.json --limit 10
```

The positive limit bounds selected references processed, including verification of prior results. It is not a new-contact quota and zero/unbounded is forbidden in this mode. Migration and rollback flags cannot be combined. CLI lanes share a nonblocking private checkpoint lock; busy state returns a static error. No reset/retry-all option exists.

## Effect and restart behavior

For a fresh selected reference, exact typed emailAddress/phoneNumber GETs use the accepted raw/normalized query adapter. One current match is retained without create; multiple matches/read failures remain excluded. For no match, an intent is fsynced into the atomic checkpoint (including directory fsync), then channels are read again immediately before any POST. A match appearing on that final read prevents the write.

A successful create must have a usable response ID and GET read-back with exact source marker, surname and normalized channels, plus a unique current channel reconciliation. Only then is created recorded. HTTP409 remains conflict;400/422 remains rejected. Neither is automatically retried on repeat. Other POST errors, malformed success or timeout record unknown and stop the batch; no next reference is posted.

Any unresolved intent, returned response, unknown effect or created record permanently removes that reference's create branch. Restart reads/reconciles the effect and verifies the exact marker/channels; absence or ambiguity requires review, never another POST. A crash before POST after intent is conservatively unknown too. Prior unique existing matches also never become new creates merely because the match later disappears. A successful repeated run verifies prior created markers/channels with zero additional POSTs.

Receipts are authoritative in the checkpoint; the event JSONL is a secondary append-only mirror. If persistence/mirroring fails, execution stops; an already persisted intent remains conservative on restart. Public output contains aggregate counts, POST-attempt count, stop reason and preservation booleans only. No records/channels/IDs/references/provider bodies are returned. The tool does not make the GET→POST interval transactional with EspoCRM; a concurrent collision must remain a409 rather than silently bypassing provider duplicate checks.

Existing normal-import dispositions and its rollback selection are unchanged. That legacy rollback does not target creations recorded solely in conflict_resume; any reversal of those effects needs a separately authorized operation using the preserved private marker/ID receipts. No owner execution or historical attribution is claimed by synthetic evidence.

## Verification

Focused synthetic regression command:

```sh
python3 -m unittest discover -s tests -p test_contact_conflict_resume.py -v
```

Coverage includes exact selection/lineage, final-read races, read failures/ambiguity, accepted phone normalization, create verification,409/validation, unknown effect/crashes, persistence/mirror failures, append history, private modes/locks, normal CLI skip behavior and exact repeat. The existing typed-query and normalizer/checkpoint suites remain in the shared Actions command. Tests use temporary fake CRM/state only; no owner sources, credentials or CRM are accessed.

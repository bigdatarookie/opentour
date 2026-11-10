# Contact duplicate identity for OpenTour imports

## Demonstrated defect and candidate

In isolated stock EspoCRM 10.0.11, effective Contact duplicate fields were `name` and `emailAddress`. The General builder's person-name condition compares firstName and lastName. The importer supplies the approved technical `lastName="None"` when a surname is unavailable and does not invent a first name. After one such Contact, unrelated phone-only and email-only Contacts with the same technical name received 409 `X-Status-Reason: duplicate`. Changing only the surname allowed the rejected new-phone/repeated-marker payload to create. Neither the shared phone nor marker alone explained that control.

The declarative override at `custom/Espo/Custom/Resources/metadata/scopes/Contact.json` selects **emailAddress and phoneNumber** as duplicate fields. Names, including technical None and coincident real names, are not stable channel identities. This aligns with the existing importer policy, which reconciles exact email/phone channels and preserves ambiguous matches instead of merging by name. Native channel duplicate checks stay enabled: this is not `X-Skip-Duplicate-Check`, `_skipDuplicateCheck`, or a validation bypass. No fields/records are invented or rewritten.

Only the exact allowlisted HTTP reason `duplicate` on status409 is retained by the importer as `crm_http_409_duplicate`. Structured allowlisted field/type handling still takes precedence; arbitrary response bodies, names, IDs, exception messages and unknown reasons remain suppressed. Existing 409 disposition/reconciliation paths match the prefix and are unchanged. This diagnostic does not establish which channel/record matched or why historical requests failed.

## Applying the candidate

This file is a **candidate profile**, not an automatic change to a running CRM. Merge only its `duplicateCheckFieldList` property into the target's existing `custom/Espo/Custom/Resources/metadata/scopes/Contact.json`, preserving unrelated custom properties and a private exact before-state. Clear Espo's metadata cache with its supported `php command.php clear-cache`, then verify effective membership. Do not modify a stock vendor file. Revert the previous custom-file bytes (or remove the new file if absent before), clear cache and verify the effective before-state when resetting an experiment.

The current assignment applied this only to the disposable DevOps fixture, verified both matrices/channel negative controls, and restored its original profile. Owner runtime at127.0.0.1:18082 was not inspected or changed. No schema/service redeployment is needed for the metadata override, but owner adoption and an authorized remaining-only pass must follow independent QA and the relevant operational assignment. Do not treat committing this JSON as an installed owner fix. Existing historical exclusions/checkpoints are not reclassified or edited.

## Synthetic reproduction

Use a freshly provisioned, empty, disposable EspoCRM fixture with its own loopback port, volumes/network and generated private runtime config. Runtime JSON: `api` naming its `/api/v1` base, `headers` containing only task-generated authentication, and `syntheticOnly:true`. Keep this config private; never use an owner credential file. The probe rejects owner port18082 and has no default target/credential fallback.

```sh
python3 tools/synthetic_contact_409_probe.py --runtime-file /absolute/private/synthetic-runtime.json
```

The probe uses the merged importer payload builder, request/normalization-query adapter and main loop with in-memory synthetic row/mapping seams. All private/checkpoint/event locations are temporary; no owner source loader, mapping, CSV or checkpoint is read. It does not prove CSV normalization. Cases are unique marker/phone, same phone/new marker, different phone/repeated marker, email-only importer create and exact source/checkpoint repeat. Output contains only status, allowlisted field/type/reason, active Contact counts and outcome; no channels, credentials, IDs, raw bodies or exports. Empty starting count is required. It does not change settings or auto-delete records.

With the channel profile: baseline200 count0→1; same phone409 count1; repeated marker/new phone200 count1→2; email-only importer200 `created_and_verified` count2→3; exact repeat performs zero POST and stays at3. A separate same-email/new-marker control returned409 and stayed at3. The recorded experiment first showed the stock all-name-conflict behavior and one surname-only discriminator. Before comparing profiles, only this matrix's synthetic rows were reset. Finally its rows were soft-deleted, original metadata restored/cache rebuilt and active count/readiness rechecked. DevOps retains the task-owned environment for independent QA/cleanup.

This establishes present fixture behavior only. Historical1,427 conflicts remain excluded/UNKNOWN until separately authorized consumer reconciliation; no historical per-request attribution is made.

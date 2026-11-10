# Synthetic Contact409 reproduction and candidate repair

Assignment `qitem-20261110114124-2d9854da1306361b`; return owner `orch-lead@opentour-rig`; retained outcome `qitem-opentour-current-outcome-20261109`. Base merged main `b55132d8b33446c222f98f109494ea3534f6ff7f`; isolated branch `fix/synthetic-contact-409`. Exact candidate/PR/Actions result are supplied in the native return. This is author evidence, not independent acceptance.

## Environment and method

DevOps supplied a dedicated empty EspoCRM fixture at127.0.0.1:18083, project `ot-synth409-devops-20261110`, separate task-owned DB/data volumes/network and generated private authentication. Docker inspection of only those containers confirms `espocrm/espocrm:10.0.11@sha256:8e1c7e97e0a1a08953a86af89c3808cb95410b6a5eb487d1e3475d2c7289357d` and `mariadb:11.4@sha256:d1891ede5a559f1086f55053bb8cc1569b0298338c4d72d71725a7f74f6ba620`. DevOps reported MariaDB11.4.13. Fixture admin/readiness/empty active Contact count were checked through only that endpoint. Owner18082 was never used.

The first three cases use the merged payload builder and real request adapter. Email-only and exact-repeat cases execute the merged import loop with in-memory synthetic row/mapping seams and temporary private/checkpoint/event paths. No owner input loader, CSV, mapping, checkpoint/event, DB, credential or historical log is read. This does not prove CSV normalization. Shared results contain only statuses, allowlisted reason/category, active persisted Contact counts and outcomes; no contact/channel/ID, credential or raw response is emitted.

## Stock result and discriminator

Effective stock Contact duplicate fields: name=true, emailAddress=true, phoneNumber=false (firstName/lastName are not separate configured fields).

| Case | HTTP/result | Active Contacts |
| --- | --- | --- |
| Technical surname None + unique marker/phone | 200 created | 0→1 |
| Same phone, different marker | 409, reason duplicate; old diagnostic only crm_http_409 | 1→1 |
| Different phone, repeated marker | 409, duplicate | 1→1 |
| Email-only through importer, different marker | 409; excluded destination_conflict_without_channel_match | 1→1 |
| Exact same source/checkpoint repeat | Zero POST; replays exclusion, **not** successful import | 1→1 |

Because both identity discriminators failed, one next probe changed **only the surname** in the rejected repeated-marker/new-phone payload. It returned200, active count1→2. Task-fixture source `application/Espo/Classes/DuplicateWhereBuilders/General.php:61–75,110–141` reads the configured fields and builds a person-name comparison of firstName and lastName. Stock `Modules/Crm/Resources/metadata/scopes/Contact.json` selects name/email. Thus technical None was used as a false shared name identity in this present fixture. Marker uniqueness or shared phone alone does not explain that surname-only control.

## Candidate and actual consumer result

The declarative custom Contact profile selects emailAddress + phoneNumber. It excludes names as stable channel identities, preserving native duplicate/validation checks rather than using a skip flag. This matches the existing importer channel reconciliation and technical-placeholder exclusion policy. It does not merge/overwrite records or fabricate a personal name. The importer additionally preserves only the observed exact409 reason `duplicate` as `crm_http_409_duplicate`; unknown reasons/raw duplicate records stay suppressed. Existing409 prefix-based disposition/reconciliation behavior is unchanged.

Preserved the fixture's before-state (no custom Contact scope file), merged only the profile property, cleared its metadata cache and observed effective name=false/email=true/phone=true. Reset only this matrix's two synthetic Contacts before the profile comparison.

| Case under candidate profile | HTTP/result | Active Contacts |
| --- | --- | --- |
| Same technical surname + unique marker/phone | 200 created | 0→1 |
| Same phone, different marker | 409 crm_http_409_duplicate | 1→1 |
| Different phone, repeated marker | 200 created | 1→2 |
| Email-only through importer | 200, created_and_verified | 2→3 |
| Exact same source/checkpoint repeat | Zero POST; verified checkpoint retained | 3→3 |
| Same email, new marker negative control | 409 crm_http_409_duplicate | 3→3 |

The server does not make the marker unique: that case deliberately tests the server directly. Importer checkpoint/source reconciliation provides its own repeat behavior; no generic server idempotency guarantee is inferred.

## Regression and restoration

A new diagnostic regression failed before editing (`crm_http_409` instead of `crm_http_409_duplicate`), then passed. Three new tests cover recognized-reason privacy, unknown/other-status refusal and the channel-only profile without a skip flag. Two existing structured-classification checks were reused and passed. Shared Actions is the primary full synthetic test check; no duplicate local full suite is required. `git diff --check` and portable probe parsing/help pass. `tools/synthetic_contact_409_probe.py` is the portable version of the one-shot experiment runner; it requires an explicit private synthetic runtime and refuses owner18082. Application/config details and scoped adoption steps are in `local/crm/CONTACT_DUPLICATES.md`.

Only matrix-created active rows were soft-deleted:2 before comparing profiles, then3 after the corrected cases. Restored the prior custom-file absence, cleared cache, verified original effective name=true/email=true/phone=false, admin readiness200 and active Contact count0. No physical owner DB/reset was used. DevOps retains the restored task-owned environment for independent QA; temporary synthetic importer checkpoint/events were removed. Raw fixture responses/authentication and before-state bytes were not committed.

## Limits and next owner

The JSON is a candidate profile, **not installed owner configuration**. Independent Code/System QA must review policy scope and reproduce relevant current behavior before any separately assigned owner adoption or authorized remaining-only pass. No real import/retry, owner config, manager/native human action, campaign, deployment or external prototype. This demonstrates current fixture behavior and a working channel-based correction, not the cause of any historical request. All historical1,427 conflict dispositions remain excluded/UNKNOWN until authorized consumer reconciliation. Return the exact candidate/CI result to Lead; do not close the retained mission outcome.

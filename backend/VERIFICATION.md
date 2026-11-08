# Read backend verification — 2026-11-09

Scope: local read backend for CRM clients and native board data. This does not accept a manager login, dialogue, human decision, campaign or deployed application.

The first implementation was independently Code-QA-reviewed at `e591adf3e2da55d83f148c8610cd3f8c6e543797`. The final candidate repairs the EspoCRM query encoding in `backend/adapters.py`, adds a wire-level regression and strengthens the masked live probe's search/filter assertions. It also documents the authorized upstream ACL boundary. Run instructions and API contracts are in [README](README.md).

## Independent code evidence

Code QA independently ran 19 backend tests and the native-board HTTP probe on `e591adf`, with no defects found. Report: `docs/review/backend-read-candidate/01-review-platform.qa-code.md` in the local project workspace. The report is a preliminary verdict on that candidate, not acceptance of the subsequent query repair or real CRM integration. The existing five import regression tests had also passed in the builder's earlier full run. No tests against owner CSVs, mappings or checkpoints were run for this backend.

## Search defect found and repaired

The first real probe checked search HTTP status only. Strengthening it to require an unmatched synthetic term to produce zero rows exposed a defect: the old query returned HTTP 200 with the one current record. The installed EspoCRM `application/Espo/Core/Record/SearchParamsFetcher.php` drops `where` when its query value is a string. Sending a JSON string in that parameter therefore silently discarded both search and channel filters.

Controlled, read-only boundary probes observed untyped JSON-string `where` returning one record and a correctly typed JSON `searchParams` envelope returning zero for the same unmatched synthetic term. The repaired adapter sends arrays for `where` and `select`, integers for pagination, and uppercase order inside that envelope. A new synthetic HTTP-boundary test failed on the previous encoding and passed after the fix. The full affected backend suite now passes 20 tests. The strengthened real public HTTP probe then passed, including the zero-result search assertion and filter content assertions. No provider data values or raw errors were emitted during diagnosis.

These observations replace any earlier status-only suggestion that search/filter semantics had been proven. Independent Code QA must review the narrow query/probe change, and System QA must assess the actual read integration.

## Actual CRM and native HTTP observations

After Lead selected the existing backend's fixed GET-only boundary, DevOps provisioned an API-only non-admin service identity and supplied its private runtime reference under `qitem-20261108201904-50149096`. Developer passed that reference directly to the masked probe, without displaying or copying credential contents:

```sh
python3 tools/backend_read_probe.py --crm-credential-file /Users/garry/Documents/git/opentour/local/crm/secrets/backend-espo-api.json
```

The probe starts an ephemeral loopback backend, exercises the public HTTP routes with a process-local diagnostic read grant, discards returned values, prints aggregates, then stops its own server. It does not create a human identity or persist an app user/token.

| Check | Observation |
| --- | --- |
| Unauthenticated board | HTTP 401 |
| Real native board | HTTP 200, five slice cards, complete bounded queue window |
| Native detail | HTTP 200, same card identity |
| Unchanged native conditional read | HTTP 304 |
| Real CRM persons list | HTTP 200, total 1 |
| Real CRM organization list | HTTP 200, total 0 |
| CRM person detail | HTTP 200, same ID and content version as list |
| CRM provenance | Version-2 source marker present; technical `None` metadata present |
| Combined entity list | HTTP 200; combined total equals entity totals |
| Email filter | HTTP 200; returned items have email and filtered total does not exceed person total |
| Deliberately unmatched synthetic search | HTTP 200; zero results, empty items |

The live organization route was exercised as an empty result. Populated organization behavior, pagination across entity boundaries, role/project denials, closed mutations for both roles, source-path isolation and update/restart semantics have synthetic test coverage. A populated real organization and a real manager browser journey were not exercised. Native snapshot reads do not prove a live status transition occurred during this episode.

The probe emitted no contact values, real IDs, source marker contents, credentials or raw provider errors. It performed only source GETs. It did not retry any import, modify a CRM record or use owner CSV/private mapping/checkpoint files. The 59 unmatched import conflicts remain unresolved and excluded; this read path does not accept them.

## Credential and action boundary

DevOps reports effective Contact/Account read-all with create/edit/delete/stream denied; Import/User/Role access denied. The upstream identity still has mandatory unrelated own-scope privileges and Portal/other mandatory reads, as documented in README. The reviewed backend's fixed GET operations and app project-read authorization are the exposed boundary. No shared CRM ACL was modified. Do not describe this as a globally read-only CRM credential.

DevOps independently reported missing and invalid keys returning 503, unauthenticated backend read 401 and backend POST 403 before contacting CRM. Developer inspected that handoff evidence; those additional real-runtime negative checks were not duplicated. The code suite separately covers closed action paths.

Manager identity remains absent. Both roles' native replies, clarifications and free dialogue stay disabled. Independent System QA and final Code QA disposition are pending; no merge, deployment or full slice acceptance is claimed by this note.

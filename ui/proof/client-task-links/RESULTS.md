# Scoped client-to-task relation — developer evidence

Assignment qitem-20261109202012-e73120ca; retained outcome qitem-opentour-current-outcome-20261109; return owner orch-lead@opentour-rig. Base main f7624a7bcd1f2be81192d4ac952d47423b50dc3e. Branch feat/client-task-links; exact candidate is in the PR/native QA handoff. This is author evidence, not independent acceptance or CI.

## Result

An optional typed Contact/Account reference is stored in the app DB, without copied CRM fields. Schema v2 adds the indexed relation transactionally; v1 tasks, messages, outbox and replay keys remain unchanged and unlinked. New HTTP task creation checks the current referenced record through the existing fixed source adapter. Related-work projection filters project/task scope before its 100-result bound, and client versions include the authorized relation. Missing board access withholds relationship metadata; direct task reads recheck current grants.

Person/organization detail now opens the same persisted task discussion. Returning rereads the original client and restores modal scroll/focus while list filter, page and row context remain. Revoked stale links render no task discussion and still permit a return to the client. No CRM edit, native send or business action follows from the link/reply.

## Focused local verification

- New `test_client_task_links.py`: **6 pass**. Contact/Account persistence and typed-only schema/context; v1 migration preserving all existing conversation/outbox/request rows and old replay; scope filtering before a window containing 100+ inaccessible rows; project/object denial; invalid references/user creation refusal; atomic link/task/message/outbox rollback; HTTP current-client validation, role/object denial, scoped ETag change and navigation endpoints. The final HTTP case was rechecked after adding Account endpoint assertions.
- Existing selected checks only: `StoreTests.test_private_storage_and_schema_version` and `StoreTests.test_restart_exact_idempotency_and_linkage`: **2 pass**. Future-schema refusal now uses version3; full component suites were not rerun.
- `python3 tools/client_task_link_probe.py`: **13 synthetic browser checks pass**. Scoped related work; same Contact task identity/history; forward focus; same-task linked answer save; client modal/focus return; filter and page2 retention; close to original client row; Account link; mobile dialog/Close fit with a wrapped title; scroll restoration; current grant denial of stale task link; hidden revoked relation on return. DB task/answer parent linkage was also checked, and all outbox rows stayed pending.
- `node --check ui/app.js` and `git diff --check`: pass.

The initial new relation regression failed on the base with `invalid_board_fields`, matching the missing feature. During probe construction its search-count expectation was corrected for the existing matching synthetic email, and close focus was synchronized with the native dialog close event using a real client-row click. These were probe corrections; prior unrelated timing reports are not claimed resolved. The final focused journey passed without debugger instrumentation.

## Boundaries

Only synthetic clients/tasks/grants and temporary private app DB/server/browser profile were used; cleaned on exit. No owner records, credential inspection, live CRM calls/writes, native task sends/replies/resolves, manager binding, campaign send, deployment or external prototype. Old tasks gain no inferred relationship. Administrator creation/linking remains the existing API; there is no relation-edit UI or copied CRM cache. Related list/history bounds are explicit. Independent Code QA and affected System QA remain required; broader manager journey/slice acceptance is open.

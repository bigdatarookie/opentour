# Populated Organization detail consumer evidence

2026-11-09. Branch test/organization-detail-consumer, base main 77e8b50f9801050fdb8187871f5f2ab24233411c. Exact candidate commit/PR is in the native QA handoff. Return owner orch-lead@opentour-rig; retained outcome qitem-opentour-current-outcome-20261109.

## Existing behavior and actual gap

Current main already implements Account list/detail via Service.client/client_card and the existing /api/clients route. ui/app.js renders organizations, contacts/category, unknown values and a bounded Account deep link. Prior independent backend/contrast reviews explicitly left populated Account detail unproven because the live Account list was empty, and the existing synthetic browser workflow only filtered organizations without opening their detail.

A new focused synthetic-only command exercises that missing consumer path instead of adding a duplicate data implementation. It also reproduced a real layout defect for a long organization name at 390×844: Close bottom 867.92 versus dialog bottom 818.67. Page width itself was 390, so the failure was the footer escaping the dialog, not horizontal page overflow. The existing flex layout covered task/campaign detail but omitted client detail grids. The smallest correction extends those same rules to .detail-grid; task and campaign behavior keep the same layout properties. No backend projection, route, auth, write or application JavaScript change.

## Verification by Developer

python3 tools/ui_browser_probe.py --organization-detail: 19 checks pass after the repair. Before the repair it passed the Account HTTP/data/auth checks and failed the long-name mobile footer assertion. Final checks cover populated organization list; same-ID/version/category Account detail; unauthorized 401, other project 403 and missing Account 404; no clients before access; explicit synthetic mode; Organization name/contact/category display; safe Account deep-link target/rel; read-only rendering without person placeholder notes; Escape focus return; long-name mobile layout/visible Close; internal scroll reaching the source link; source error distinct from empty; retry of the same record; missing values not invented; untrusted text inert; disconnect cleanup; no live-service network requests.

python3 tools/ui_browser_probe.py: existing 19 synthetic task/client checks pass after the shared client-grid CSS change. This affected regression rerun covers person/client navigation, filter/paging, source failure/retry, text safety, mobile dialog/focus, native card refresh and disconnect. The unchanged backend/native/campaign suites were not repeated; earlier accepted contracts remain evidence within their original scope.

The focused CLI rejects --live before source setup or browser launch. It also forbids credential files, native source modes and screenshots. Candidate diff whitespace check passes. The fixture is an in-memory CRM implementation behind the real existing local backend HTTP/auth/projection and browser UI, not a real EspoCRM server or production fixture.

## Scope and cleanup

No owner/private CRM rows or credentials, source files, actual native API, manager binding, business writes, replies, campaign action or deployment were accessed. No source link was followed; observed browser HTTP requests all went to the task backend's own loopback origin. No screenshots were generated or shared. The existing harness closes its browser/server and removes its temporary task-owned profile; no persistent fixture or external principal was created.

The consumer now has reproducible populated Organization contract evidence plus the repaired long-title mobile Close behavior. Real upstream populated Account behavior and owner data in the current installation remain unobserved; an empty live list is still not that proof. No full manager journey or slice acceptance is claimed. Independent review/affected visible verification must judge this exact candidate; after the applicable QA/merge workflow, return result/limitations to Lead with the retained outcome ID.

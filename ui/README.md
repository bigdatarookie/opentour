# Atlas local workspace

The UI is served by the existing Python backend. No Node dependency, separate frontend server, build step, account provisioning or deployment is needed.

From the repository root, use the **already authorized** private references:

```sh
python3 -m backend.server --auth-file /absolute/private/read-grants.json --crm-credential-file /absolute/private/espo-service-api.json
```

Open `http://127.0.0.1:18083/` and enter an existing OpenTour application read grant. This is not the EspoCRM API key or an admin password. The shell can load without authentication; every data request still goes through the backend's existing authorization. The screen cannot issue access or create an account. With no issued app grant, it shows the access form rather than CRM or work data. No current manager is designated by this implementation.

The application token lives only in the current tab's memory; it is not put in a URL, cookie, local/session storage or generated asset. Reload requires re-entry. Disconnect clears the token, rendered data, selected detail, search and filters. The private CRM credential remains inside the backend. The service identity's inherited EspoCRM permissions remain as documented in [backend README](../backend/README.md); the UI adds no source operations.

## Selected Atlas integration

The user-selected V3 source is preserved in [prototypes/opentour-v3](../prototypes/opentour-v3/README.md). Its historical demo-only instructions are superseded by assignment qitem-opentour-v3-integration-20261111. Product UI loads only ui/app.js and the existing authenticated APIs, never the prototype fixture/controller. Local Prata and Commissioner fonts retain their OFL notices. Archived photography remains attributed in the prototype and is not presented as a real offer.

The project intro is removed, including its spacing. Clients use separate equal-width rounded filter/table regions with the actual API count and CRM source between them. The right panel shows only actual scoped OpenTour task history and delivery state; free dialogue is explicitly unavailable. Replies/comments use existing authorized task modals, retained drafts, idempotency and app DB/outbox. Native cards follow source changes with vertical collapse/expand, skip motion for reduced-motion, and retain one stable card. Roles come from the backend; there is no demo role switch or simulated event control.

For a standalone synthetic preview with a temporary DB, no real CRM/daemon and no native delivery:

```sh
python3 tools/atlas_preview.py --port 18085 --access-file /private/tmp/opentour-atlas-preview-access.json
```

Open the printed loopback URL. The new mode-0600 access file contains synthetic administrator/user keys for this process only; do not paste them into chat or Git. Ctrl-C closes the server and removes its keys/temporary DB. An existing access file is refused and preserved. This preview does not grant access to real project data.

For the real local backend use existing authorized private references with --board-db as appropriate. In an isolated worktree, add --work-root /Users/garry/Documents/git/opentour/opentour-rig to read the registered native root. No importer/profile/runtime binding is changed.

Focused synthetic integration verification:

```sh
python3 tools/atlas_browser_probe.py --proof-dir /private/tmp/opentour-atlas-proof
```

The proof directory contains synthetic-only screenshots. It exercises requested layout edits, source card movement, client-to-task reply/save/read-back, actual stored delivery, mobile panel/focus, server roles and unsent campaign labels. Existing read and conversation probes cover search/filter/paging/error/retry, unknown-save replay, restart and revocation. Full Python regressions run in the existing Actions workflow.

## Existing data behavior

- Default Tasks view: native aggregate cards, source-derived columns, owner role, last authored result, blockers, stage filter and task detail dialog. No per-qitem tracker, drag-and-drop or manual status control.
- Clients: the existing CRM list/search/type/channel filters, paging, person/organization details, technical-surname explanation, provenance and a validated local CRM deep link. Unknown values stay unknown; no enrichment or editing.
- Loading, empty results, retryable source errors, and an explicit stale-data notice when native refresh fails after a successful read. Counts stay unknown until loaded; errors are not zero-result successes.
- Shared native dialog supports Escape, focus return, scroll and responsive detail layout. A native-board refresh can update the open task detail without creating a second card. Client filters stay in memory when switching sections. Narrow screens stack board columns at readable widths.
- CRM/native source operations remain read-only; separately scoped application task replies save in OpenTour DB. Campaigns projects the pinned existing r01 local FIXTURE package with HTML/text/manifest views, sources and caveats; it is PREVIEW-ONLY, NOT CONTENT-APPROVED and NOT SENT. No free dialogue, application Operator, native human-decision action, credential provisioning or campaign send is fabricated.

Native board polling uses the existing ETag/version/cursor contract every 15 seconds while the document is visible. Manual Refresh is also available. Duplicate content does not rebuild the board. Backend source updates remain authoritative. Continuous source changes collapse the existing card vertically in its old column, then expand that same node in the new column. One stable ID/button is retained; the collapsing wrapper is inert. Reduced motion, initial/reconnected reads, a changed source epoch, return from a hidden document and filter changes render current state directly. Source errors break continuity rather than replaying a backlog. Open details/drafts, newer user focus and current scroll positions are preserved; interrupted refresh/filter/disconnect cannot finish an obsolete move. Motion describes a received source update and never proves completion. Real manager/native-business journey acceptance remains separate.

## Verification

```sh
node --check ui/app.js
python3 -m unittest discover -s tests -p test_backend.py -v
python3 tools/ui_browser_probe.py --proof-dir /private/tmp/opentour-ui-proof
python3 tools/ui_browser_probe.py --live --crm-credential-file /absolute/private/espo-service-api.json
```

Browser checks use installed `agent-browser` and a task-owned Chrome profile/session, closed and removed afterward. Default browser executable is macOS Google Chrome; pass `--browser /absolute/path/to/chrome` for another host. No owner profile is opened. `agent-browser` must already be installed; a missing browser is a verification limitation, not a reason to alter an authenticated owner environment.

The synthetic run uses in-memory adapters and displays a visible **ДЕМОНСТРАЦИЯ · Синтетические данные** banner. Only this run permits screenshots. The live run reuses the authorized CRM file reference, exercises actual backend/native/CRM reads through the browser, emits only check names and outcomes, and refuses a screenshot directory. Both use an ephemeral process-local diagnostic read grant, not a persisted person or new production credential. Their HTTP servers stop at completion.

Builder observations on 2026-11-09: the 21 backend HTTP/unit checks pass. Synthetic browser checks pass task/client details, Escape/focus, paging, organization filter, empty search, error/retry, untrusted CRM text, mobile sizing, open-detail refresh, memory-only token handling and disconnect cleanup. The real browser run exercises five native cards, current CRM person detail, empty organization result, search, keyboard return and mobile details with no screenshots or record values emitted. Populated real organization detail, an authenticated human manager, native replies/decisions/resume and overall slice acceptance remain unproven. Synthetic screenshot artifacts are under [proof](proof/).

The browser harness uses explicit `scrollintoview` before clicks so task cards inside a native board's horizontal/vertical scroll area are reached without a forced click. Shared proof images are synthetic only; do not record real CRM pages. Independent QA is required for this candidate.


## Existing campaign fixture preview

The existing backend serves GET /api/campaigns, its fixed draft-r01 detail and five allowlisted source materials through the same project read authorization. No CRM credential or mailer connection is needed for this package. The normal server can run with only its already authorized --auth-file; clients will remain unavailable without their separate CRM reference. No person or write grant is created by this change.

The five original files under opentour-rig/missions/01-local-information-layer/slices/04-campaign-draft/artifacts are included unchanged at their canonical paths. backend/campaign_preview.py pins each SHA-256, bounds file reads and fails closed for absent or changed content. This is a presentation of an existing source package, not a campaign database or provider draft. Audience is unselected, recipient count unavailable, sender unset, provider ID absent. Retaining r01 is not content approval or send authorization. Source terms remain historical October snapshots; no live availability or price validation occurred. The original manifest is shown as historical source, with no edits to its old checkout observations.

The HTML representation removes embedded external links and moves the exact original style block into a fixed same-origin presentation stylesheet. Original files and text alternatives stay unchanged. The frame has an empty sandbox and no-referrer policy; no scripts, origin permission, forms, navigation or popups are enabled. Parent CSP retains its no-inline policy; the child policy denies other resource types. Source URLs are explicit links outside the frame; they are not prefetched by the preview. Public campaign-email.css contains only pinned presentation CSS; campaign content/material endpoints require the existing app grant. There is no recipient selection, approval, reply, persistence or sending action.

Fixture-only verification (no CRM, native service, private credentials or owner records):

```sh
python3 -m unittest discover -s tests -p test_campaign_preview.py -v
python3 tools/campaign_preview_probe.py --proof-dir /private/tmp/opentour-campaign-proof
```

The browser probe uses a process-local synthetic grant and empty synthetic board solely to open the existing shell, plus a task-owned temporary Chrome profile/session. It closes both browser and HTTP server. The opaque srcdoc frame is inaccessible to the installed agent-browser frame selector: internal DOM/style/mobile overflow checks are NOT RUN. Screenshots verify visible rendering; source checks cover the pinned inert transformation, and browser checks cover sandbox opacity, shell layout, text/manifest alternatives, focus, cleanup and no external requests. See proof/campaign/RESULTS.md. Independent QA and full slice acceptance remain separate.


## Native observations in task detail

The existing task modal shows read-only observations for up to 20 current scoped native source references. It displays original/current ask state, bounded audit entries and actual linked reply observations. No matching entries means unconfirmed; missing current references, incomplete windows and source errors have distinct text. Source IDs remain available under provenance. An observed audit/reply is explicitly not verified manager identity, accepted content or resumed owner work. No reply/decision/resume/chat or mutation control is added.

Selection, focus and detail scroll survive board updates. Native observations refresh on the existing board read even with an unchanged board ETag, plus an explicit read-only refresh button. In-flight same-original reads are coalesced; session/modal/selection guards discard late responses. Access revocation clears the workspace through the existing auth handling. No additional polling controller, storage or task tracker is introduced. Campaign routes and fixture files stay unchanged.

Use the existing browser harness for synthetic observations, including source errors, delayed responses and auth revocation:

```sh
python3 tools/ui_browser_probe.py --native-observations --proof-dir /private/tmp/opentour-observation-ui-proof
```

For the actual native read consumer, supply the existing specification root and a currently active assigned qitem in slice 03-operator-board. A completed handoff's old qitem is not a current source reference. This mode uses no CRM, private credential file or screenshots; it creates only the existing process-local diagnostic read grant and closes its task-owned browser/server:

```sh
python3 tools/ui_browser_probe.py --native-observations --native-work-root /absolute/existing/opentour-rig --native-original-id <current-active-scoped-qitem>
```

Builder evidence: 19 targeted synthetic browser checks, 19 existing synthetic task/client checks, and 8 native-only live browser checks passed. Backend/native/campaign tests passed (21/10/8). Visible matching audit/reply cases are synthetic; real positive human decision/reply/resume and full slice acceptance remain unproven. Independent Code QA then scoped System QA must review the same candidate before integration. Detailed evidence: proof/native-observations/RESULTS.md.


## Populated Organization detail proof

Account list/detail projection and Organization rendering already existed. The focused probe now verifies the populated Organization path through the existing authenticated backend HTTP and UI, using one in-memory synthetic Account and no live CRM/native source:

```sh
python3 tools/ui_browser_probe.py --organization-detail
```

This mode refuses live/credential/native-source flags and screenshot output. It checks Account identity/version/category, authorization/project boundaries, Organization fields and Account deep link (without navigating it), source error/retry, unknown values, untrusted text, focus, mobile scrolling/Close and cleanup. The network observation permits only its own loopback backend. Existing task-owned browser/profile/grant/server lifecycle is reused.

A long organization name reproduced a clipped mobile footer: the Close button extended below the dialog at 390×844. The existing flex dialog layout now also covers client detail grids, keeping the footer visible and body scrollable. Task/campaign flex behavior stays as before. The focused 19 checks and the 19 existing synthetic task/client browser checks pass. Backend/data projection/authorization and campaign/native routes were not changed, so their accepted evidence is retained rather than repeated. See proof/organization-detail/RESULTS.md.

This is a populated synthetic internal HTTP/UI contract proof. It does not prove populated owner Account data or a real upstream Espo Account read in the current installation; no private CRM reference or record was accessed. No manager identity, write, conversation, campaign or deployment is enabled.


## Focused board transition verification

Run python3 tools/board_transition_probe.py from the repository root. It starts only a temporary synthetic backend/browser and seeds one temporary app task; it does not contact CRM/native daemon, send an app reply, or read owner sources/credentials. Paused Web Animations let it inspect actual intermediate vertical geometry and old/new column membership, then exercise modal status, unsent input/caret, reduced motion, superseding source refresh, filter/scroll/focus, reconnect/source epoch, synthetic visibility events and disconnect cleanup. The product contains no synthetic event/status control. Evidence: proof/board-transition/RESULTS.md.


## v0.12 addressed answer delivery

The existing app discussion now distinguishes saved/delivered/received/accepted/continued, needs clarification/rejection and failed/unknown. Its card follows the current addressed request rather than closing it when any comment is saved. Immutable request version and server actor are bound in the outbox; the browser sends replyVersion explicitly. Draft text remains when a stale/already accepted request returns409. Agent results/reasons are plain text; no unrestricted chat or native human action is enabled.

The worker is an operational service, not a developer drain. See backend/BOARD_CONVERSATIONS.md for service identity, supervisor/DB contract and actual-recipient receive/report commands. A reported substantive continuation is distinct from a transport ACK; real agent verification belongs to independent System QA.

A boardOnly:true test grant uses one exact task ID and cannot read CRM/native/campaign sources. Atlas keeps its discussion usable and explains unavailable source sections. This is a synthetic application identity, not a named manager; omit CRM credentials in that runtime and revoke the grant after QA. Existing source-enabled grants are unchanged.

Default root-local hosting remains unchanged. --public-base-url https://existing-host/opentour enables a configured HTTPS proxy prefix, including local styles/fonts/API and email preview links. Host/Origin acceptance is explicit; no forwarded-header trust or public raw backend/daemon/CRM. This support is not evidence of publication.

Focused builder browser: python3 tools/board_continuation_probe.py (also --prefix). It uses a fake native transport/recipient and temporary synthetic task, with no actual agent/CRM/native queue calls. Independent System QA must replace that fixture step with a real addressed agent and observe useful original-obligation continuation, stage timings and unresolved backlog on the exact accepted candidate.

## Static UI with an explicit protected API

Default `python3 -m backend.server ...` and same-origin prefix hosting are unchanged.
The static export is a separate deployment artifact; it neither enables Pages nor
starts/upgrades any service. Generate it from the reviewed source, into a **new**
output directory outside the checkout:

```sh
python3 tools/build_static_ui.py --output /private/tmp/opentour-public-ui --base-path /opentour --api-base-url "$OPENTOUR_PROTECTED_API_BASE"
```

`OPENTOUR_PROTECTED_API_BASE` is an operator-supplied protected **HTTPS** base,
including any forwarding prefix, without `/api`, userinfo, query, fragment or
credentials. No production host is supplied by this repository. Literal
`http://127.0.0.1:PORT` / `http://localhost:PORT` are accepted only for disposable
local validation; the browser permits these only when the UI is also loopback.
Never publish a loopback target as a production artifact. The Pages artifact root
is the output directory, served at the agreed `/opentour/` project path. Only the
allowlisted shell, scripts, styles, fonts and fixed campaign presentation CSS are
copied. No records, credentials, grant files, DB, source exports or source maps
are included.

The exporter writes deployment-owned API metadata and a CSP meta policy allowing
connections only to self and the configured API origin. The UI uses that base for
all API calls and its static base for assets/email preview styles; neither URL
parameters, fragments nor browser storage can select the API. Bearer access is
entered separately, stays in memory and is sent in the Authorization header;
fetch omits cookies and referrers and rejects redirects. Do not put tokens in a
URL, HTML, build argument or public config. The static host's response headers
must not add a conflicting self-only `connect-src` policy (multiple CSPs intersect).
A static meta CSP cannot set `frame-ancestors`; host-level framing protection is a
separate hosting capability, not a claim of this exporter.

For the corresponding reviewed backend configuration, preserve its existing
private auth/DB/source references and add:

```sh
python3 -m backend.server --auth-file "$OPENTOUR_AUTH_FILE" --board-db "$OPENTOUR_BOARD_DB" --public-base-url "$OPENTOUR_PROTECTED_API_BASE" --allowed-ui-origin https://bigdatarookie.github.io
```

This is a configuration contract, **not** an instruction to replace an existing
service or omit its existing source options. `--allowed-ui-origin` can be repeated
for individually trusted origins, without trailing slash/path. No wildcard,
`null`, non-loopback HTTP, credential-bearing or caller-selected origin is
accepted. CORS applies to `/api/` only; preflight permits GET/POST and
Authorization, Content-Type and If-None-Match, without credential cookies. Actual
requests still require the existing bearer grant and project/object scope.
Readable 401/403 responses do not grant access; ETag is exposed for conditional
reads. Origin allowlisting is a browser control, not authentication. The backend
remains loopback; a forwarding layer must preserve the configured public Host
and browser Origin, pass OPTIONS/Authorization/ETag, avoid redirects and shared
API caching, and expose neither the raw backend, CRM nor OpenRig daemon.

Publication-resource owner still owes: the exact protected HTTPS API base and
forwarding prefix; who can access that forwarding route; its TLS/Host/Origin and
preflight/header behavior; the authorized Pages artifact publication mechanism;
and separately issued/revocable private app access. The known UI origin is
`https://bigdatarookie.github.io`, base `/opentour/`. GitHub's Origin covers the
whole host, not a project path: assess trusted sibling Pages content before
adding it. No new real-user grant or production-readiness claim is made here.

Affected synthetic validation, with disposable local origins/profile/DB/grant,
no CRM/native consumer/worker/canonical runtime:

```sh
python3 -m unittest discover -s tests -p 'test_static_api.py' -v
python3 tools/static_api_probe.py
```

The browser probe uses the existing `agent-browser` invocation and task-owned
Chrome profile. It checks configured API rendering, server-authored synthetic
comment, foreign-task denial, unauthorized read, ETag/304, CSP refusal, unlisted
UI origin refusal and same-origin root/prefix regressions. Its isolated app
writes never run an outbox worker and do not deliver native context. These checks
do not prove the unprovisioned external forwarding/Pages route or repeat the
accepted ticket-to-agent journey.

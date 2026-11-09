# Local read-only workspace

The UI is served by the existing Python backend. No Node dependency, separate frontend server, build step, account provisioning or deployment is needed.

From the repository root, use the **already authorized** private references:

```sh
python3 -m backend.server --auth-file /absolute/private/read-grants.json --crm-credential-file /absolute/private/espo-service-api.json
```

Open `http://127.0.0.1:18083/` and enter an existing OpenTour application read grant. This is not the EspoCRM API key or an admin password. The shell can load without authentication; every data request still goes through the backend's existing authorization. The screen cannot issue access or create an account. With no issued app grant, it shows the access form rather than CRM or work data. No current manager is designated by this implementation.

The application token lives only in the current tab's memory; it is not put in a URL, cookie, local/session storage or generated asset. Reload requires re-entry. Disconnect clears the token, rendered data, selected detail, search and filters. The private CRM credential remains inside the backend. The service identity's inherited EspoCRM permissions remain as documented in [backend README](../backend/README.md); the UI adds no source operations.

## Delivered surface

- Default Tasks view: native aggregate cards, source-derived columns, owner role, last authored result, blockers, stage filter and task detail dialog. No per-qitem tracker, drag-and-drop or manual status control.
- Clients: the existing CRM list/search/type/channel filters, paging, person/organization details, technical-surname explanation, provenance and a validated local CRM deep link. Unknown values stay unknown; no enrichment or editing.
- Loading, empty results, retryable source errors, and an explicit stale-data notice when native refresh fails after a successful read. Counts stay unknown until loaded; errors are not zero-result successes.
- Shared native dialog supports Escape, focus return, scroll and responsive detail layout. A native-board refresh can update the open task detail without creating a second card. Client filters stay in memory when switching sections. Narrow screens stack board columns at readable widths.
- Read-only status throughout. Campaigns projects the pinned existing r01 local FIXTURE package with HTML/text/manifest views, sources and caveats; it is PREVIEW-ONLY, NOT CONTENT-APPROVED and NOT SENT. No chat/history, application Operator, reply field, human-decision action, credential provisioning or campaign send is fabricated.

Native board polling uses the existing ETag/version/cursor contract every 15 seconds while the document is visible. Manual Refresh is also available. Duplicate content does not rebuild the board. Backend source updates remain authoritative. The first read UI does not implement the full collapse/expand transition choreography from UI_FLOW; the actual live transition journey remains outside acceptance here. Reduced motion disables decorative animation.

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

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
- Read-only status throughout. Campaigns is explicitly unavailable. No chat/history, application Operator, reply field, human-decision action, credential provisioning or campaign send is fabricated.

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

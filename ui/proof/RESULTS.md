# Local read UI — builder evidence

Date: 2026-11-09. Base: merged backend `d1b1fb25766562a24fccf4a156921108f5f17629`. This note is builder evidence, not independent acceptance or deployment.

## Checks executed

- `node --check ui/app.js`: passed.
- `python3 -m unittest discover -s tests -p test_backend.py -v`: 21 tests passed. The added HTTP test confirms public fixed shell/assets have no embedded record/token data, appropriate MIME/CSP/no-store headers, API data still requires authorization, and arbitrary file paths are not served. Existing provider/auth/write-denial tests remain passing.
- `python3 tools/ui_browser_probe.py --proof-dir /private/tmp/opentour-ui-proof`: 19 synthetic browser checks passed.
- `python3 tools/ui_browser_probe.py --live --crm-credential-file /Users/garry/Documents/git/opentour/local/crm/secrets/backend-espo-api.json`: 14 real-source browser checks passed; no screenshots or record/credential values emitted.

The browser runner used installed agent-browser and Google Chrome in isolated task-owned temporary profiles and mode-specific sessions. It closed its own browser/server after each run. It did not use an owner browser profile, create a persistent login or app grant, or change CRM/native records. The pre-existing CRM API reference was passed only to the backend process; it was never opened for display.

## Synthetic browser result

Passed: empty public shell before access; authorized five-card board; visible synthetic label; read-only work details; Escape/focus return; client list/details and validated CRM link; client focus return; pagination; organization filter; empty search; source-error state and retry preserving the filter; untrusted CRM text rendered without execution; mobile page width and dialog fit; simulated native refresh preserving open detail and a single card per ID; no token in local/session storage; disconnect clears data/search/detail title.

The initial refresh test had a malformed selector in the harness assertion; correction made the check pass. A real-data harness click initially targeted a card outside the current scroll viewport; the supported explicit scroll-into-view action then succeeded. No forced clicks or production UI bypasses were used.

## Real-source browser result

Passed: public shell contains no records before authorization; actual native five-card board; live mode has no synthetic-data badge; existing work detail route; Escape/focus return; actual CRM list/detail and validated source link; empty organization filter; unmatched synthetic search criterion through the real client route; mobile viewport/dialog fit; memory-only application token; disconnect cleanup. The current live organization list is empty, so a populated real organization detail was not exercised.

This browser run used an ephemeral in-memory diagnostic **read grant**, not a real manager identity. It retained no page snapshots, source values, screenshots or credentials. No client data was used in the shared images below.

## Visual evidence

All images show the visible synthetic-data banner and `.invalid` example contacts. Builder inspected desktop task/client views and the mobile task viewport for readability and overflow.

- [Task board, desktop](tasks-desktop.png)
- [Client list, desktop](clients-desktop.png)
- [Task board, mobile viewport](tasks-mobile.png)

## Focused contrast repair after independent review

Code QA returned four informative text selectors below 4.5:1. `python3 tools/ui_contrast_check.py` reproduced the failure before the repair and passes afterward. Only four CSS foreground declarations were darkened; no layout, JavaScript, API or authorization changed. The check covers declared foreground/background pairs in the current CSS, including client-row hover and the actual transparent empty-column canvas. It is not a general cascade analyzer or full accessibility audit.

| Text | New foreground | Measured ratio |
| --- | --- | --- |
| Task result | `#586b55` | 5.75:1 on white |
| Client contact | `#52664d` | 6.24:1 on white; 5.88:1 on hover |
| Client type | `#5b6e52` | 5.53:1 on white; 5.21:1 on hover |
| Empty-column message | `#64715a` | 4.78:1 on the `#f5f6f2` canvas |

Existing screenshots above document the initial candidate before this contrast repair; they were not silently replaced. Functional and live-data checks were not repeated for a foreground-color-only change. This repair is returned for the affected independent re-review and does not broaden the scoped acceptance.

## Limits

No manager identity, authenticated-human browser acceptance, dialogue/history, reply/decision/resume, real live status transition, populated real organization detail or campaign section is accepted. This first UI does not implement the complete collapse/expand transition animation. Synthetic refresh demonstrates read-state preservation only. All mutation endpoints remain denied by the existing backend. No new external account/API credential, native controller, writable tracker, CRM import/write, campaign send or deployment was introduced. Overall slice acceptance is not claimed. Run and access prerequisites: [UI README](../README.md).

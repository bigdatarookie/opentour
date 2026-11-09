# Native observation UI consumer evidence

2026-11-09. Branch feat/native-observation-ui; base main 1a08180b35d14bd928764a37ffef906765461244. Exact candidate commit/PR is supplied in the native QA handoff. This evidence is included in that candidate.

The existing task modal consumes the merged native-observation API. It presents original/current ask state, audit/reply observations, unconfirmed results, incomplete windows and failures without inferring manager identity, accepted decision content or resumed owner work. Source IDs are tied to existing work references, never a second task board. Reply/decision/resume/chat/write controls remain unavailable. The API adds only bounded enum state and current-ask ID metadata from already scoped snapshots. No new source reads or personal fields.

## Verification by Developer

- node --check ui/app.js: pass.
- tests/test_native_observations.py: 10 pass, including unknown source-state words becoming null and never entering shared output.
- tests/test_backend.py: 21 pass.
- tests/test_campaign_preview.py: 8 pass; campaign routes and pinned fixture remain unchanged.
- Targeted synthetic browser mode: 19 checks pass. Before-access absence; fixture label; unconfirmed/current-ask state; no write controls; audit/actual linked-reply display; authority/continuation caveat; incomplete windows; source failure distinct from empty; retry; wrong-scope response refusal; mobile fit/Close; board refresh preserving focus/scroll/modal/selection; unchanged-board refresh reading new observations; late old-selection response discarded; Escape focus; no-current-original display; revoked access clearing observations.
- Existing synthetic task/client browser mode: 19 checks pass, including task/client details, filters/paging, safe text, source error/retry, mobile layout, detail refresh, memory-only grant and disconnect.
- Native-only live browser mode: 8 checks pass on the current Developer assignment qitem-20261109085156-3c4482ac. The actual source read display, read refresh, desktop/mobile fit, Escape focus and disconnect work. No actual human decision/reply/resume was generated or accepted. Live mode emitted only check names/outcomes, used no CRM or private credential file, and refused screenshots.
- New observation text color pairs were calculated against their declared surfaces: ratios 5.892–7.829, above 4.5:1. This is a bounded new-text check, not a page-wide accessibility acceptance.
- Desktop/mobile synthetic screenshots inspected. Long task details keep the Close footer reachable, with internal scrolling and readable wrap. These screenshots contain synthetic values only.
- Candidate diff whitespace check passes; original campaign artifact bytes and inherited whitespace are unchanged.

## Runtime and limits

Both browser modes reuse tools/ui_browser_probe.py, task-owned temporary Chrome profiles, an in-memory diagnostic project read grant and the existing HTTP server. Browser/server resources are closed by the harness. The native-only mode requires an active scoped qitem; when the author's task is handed off, QA should use its own active assignment in slice 03, not the now-closed author qitem. Synthetic mode's source mutations affect only in-memory fixtures. There are no new persistent credentials, owner browser profiles, native business writes, CRM/mail calls, owner-row access, external prototype integration, or deployment.

Matching audit/reply display is synthetic evidence only; native live evidence covers the current read, without positive human binding/content acceptance/owner continuation. Historical asks outside the current blocker/window remain unsearched. Queue/audit/reply completeness notices do not assert full-history completeness. No manager identity, real decision/action or full slice acceptance is claimed.

Required next stages: independent Code QA, then scoped System QA of this exact same candidate's visible read-only display before any merge. Author verification is not independent acceptance.

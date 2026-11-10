# OpenTour v01 / V3 / Атлас

Current status: delivered r2; independent QA2 main PASS and extra A PASS; extra B and part of narrow coverage NOT RUN. Readiness is NOT established by the builder. Direct URL: http://127.0.0.1:9013/ . Browser title: opentour-v01 / V3 / Атлас. Lead owns the static server; keep it running. Only this variant directory was edited. No backend, real agents, CRM, authentication, sending or bookings.

Default and reset: Tasks / Администратор / dialogue open / t02 В работе. Mobile dialogue is an initially open drawer: Закрыть reveals the readable horizontally scrolling board. #reset clears only in-memory variant comments, drafts, messages, event, filters and role, restoring fixture defaults. Reload persistence is not promised.

Public journey controls:
- [data-task="t02"] opens the task. #task-reply and #task-submit save the clarification with author and confirmation. #task-event, «Показать обновление команды», applies the confirmed fixture event once. The same card DOM node vertically collapses180ms, then expands220ms in Выполнено. Modal status/result updates; textarea/draft/focus remain. Repeating produces an already-applied notice. Reduced motion applies immediately. A comment itself does not complete work.
- #task-close / Escape restores original card focus and board scroll. Task drafts survive closing. Human tasks t03/t06 accept answers in BOTH roles; blank text gives a visible correction.
- [data-section="clients"], #client-search «Маяк», [data-client="c03"] opens the organization dossier, known need/contact and correct related work. Missing contact is «Не указано». #crm-info is a local not-connected explanation. Search/type filter alone does not retarget context.
- [data-section="campaigns"], #campaign-select=camp01. #audience-button reveals exactly Анна/c01 and Илья/c02. [data-material="email"|"sms"|"call"] switches actual material. #email-cta opens t03, never sends. camp02 shows two organizations c03/c06 and an unfinished concept.
- #chat-text / #chat-send use section+agent+object drafts/history and deterministic local acknowledgment. Tasks: Оператор OpenRig / Проект OpenTour. Clients: Creative / База клиентов, or explicitly selected client. Campaigns: Оператор кампаний / selected campaign. #dialog-toggle retains history/draft on collapse/reopen. #role=user disables direct compose/send with explanation; task text remains enabled. Admin draft is retained, not cross-posted.

Anchors: Kanban/modal = native HTML/CSS interactive control; card/reply/event actions have actual visible outcomes. Dossiers = typographic content. Email = licensed winter photography plus two narrative offers, exact synthetic39900/52900 prices, durations, uncertainty and local CTA. See ASSETS.md. No SVG visual elements are used; SVG cycles N/A, no invented refinements. No icon package: actions have text labels.

Author evidence: checks/01-entry.png1440 entry;02-email.png actual editorial letter;03-narrow-dialog.png;04-narrow-board.png;05-narrow-task.png. Actual task reply/event retained modal, unsent draft and event-button focus; exactly one t02 node moved to Done. Context draft stayed in Creative/Clients and did not transfer to Campaigns. User direct compose/send disabled while t03 answer saved. At390 document width390, dedicated board scrollWidth1290/client343; close/reopen t03 preserved draft, card focus and boardX523. Reduced motion: immediate Done, no active animations, one node after repeated event. Browser error list empty. Prata/Commissioner faces loaded, Russian phrase checks true; all66 Russian alphabet letters includingЁ/ё present in both local cmap tables. Optional fontTools import was unavailable; a built-in cmap read supplied the glyph check, no package installed.

Times: first rendered desktop draft evidence08:05:06Z09Nov2026; email/event evidence08:06:07Z; first exercisable notices to lead/QA2/creative followed those captures, before creative08:08Z response. r2 role-scroll/drawer-focus fix08:09:36Z; QA2 notified affected scope only. Author narrow and reduced-motion checks completed by08:15Z. Creative's single bounded response08:08 found no concrete visible defect in sampled board/letter/narrow; it is not journey acceptance. Actual first-notice receipt and independent QA start/deadline/result remain their owners' records.

r2 affected scope: role change retains dialogue history scroll; narrow dialogue has inert background, dialog semantics, focus containment/Tab wrap and initial Close focus. Main task/event/campaign content and context keys unchanged. These are already served in app.js?v=2/style.css?v=2.

Known limits: synthetic local prototype, no reload persistence, no real dispatch/send/CRM/booking. Untested secondary combinations are NOT RUN, not claims. Independent QA2 coverage is recorded below; missing named extra/narrow checks remain explicit, no self-declared ready. No unit-test suite, source/hash audit or sibling implementation inspection. Only task-owned browser session opentour-v3-build was closed; lead preview server stays alive.

Native JSONL (thread ID verified from CODEX_THREAD_ID): /Users/garry/.codex/sessions/2026/11/06/rollout-2026-11-06T16-13-47-01a1b022-b82e-75c2-8b35-3c29b48a7c9a.jsonl .


## Independent QA2 return —09Nov2026 08:24Z

Read ../.. / qa/qa2/coverage.md (run-root qa/qa2/coverage.md), actual current app.js?v=2. QA clock08:08:12Z–08:18:12Z, deadline honored; report returned08:24Z. No extra allowance or further QA continuation was authorized on that item.

- Main journey PASS: t02 clarification saved without completion; explicit team update maintained open modal/result and moved one card with correct counts; c03 search/open; camp01 two-person audience, substantive email/two offers, SMS/call; one Admin campaign message/ack; reset returned Tasks/t02working.
- Extra A role boundary PASS: User direct dialogue input/send disabled with explanation; t03 task answer saved without changing status.
- Extra B draft isolation/persistence across sections and collapse/reopen NOT RUN. Author self-check is retained separately and is not independent coverage.
- Narrow390×844 partial: readable native task dialog, body/document390 with no horizontal overflow, visible close and internal content scroll; prior submitted answer visible. A distinct narrow text submission and ordinary-scroll continuity NOT RUN. The required narrow text-action smoke is therefore not independently complete.
- No objective product defect was reproduced. Creative's earlier aesthetic sample found no concrete visible defect, separate from journey coverage. Missing required coverage prevents builder-ready claim; lead owns final scoped disposition, no automatic rerun/new budget.

QA evidence: run-root qa/qa2/v3-entry.png, v3-reset-main.png, v3-narrow-user-task.png and coverage.md. QA2 closed task-owned contexts and left preview server running. Builder's opentour-v3-build browser was already closed. Source remained r2, unchanged after08:09:36Z. Keep http://127.0.0.1:9013/ available for observation.

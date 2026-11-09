# Board conversation candidate — developer evidence

Assignment: qitem-20261109190910-488446dc40a06c17. Retained outcome: qitem-opentour-current-outcome-20261109. User correction: qitem-opentour-board-data-ownership-20261110. Base: main df05df9c063119e362a66b5c030196175ff1a265. Branch: feat/board-conversations. Candidate commit is supplied in the PR/native QA handoff; this is author evidence, not independent acceptance.

## Observed implementation

Private SQLite stores canonical OpenTour tasks, request/answer/comment links and transactional outbox state. Explicit application grants default off; both roles may answer only within server-granted task scope. Native execution/CRM/free dialogue remain protected. Fixed-seat context delivery is opt-in local tooling, never an HTTP action. Exact stable native-ID reconciliation distinguishes pending/delivered/failed/unknown and does not resend an ambiguous create. Recipient access receipts remain separate from processing/completion. The browser reads/saves linked discussions and retains an uncertain application-save intent for safe same-key replay.

## Checks run

- `python3 -m unittest discover -s tests -p test_board_conversations.py -v`: **11 pass**. Includes transaction rollback, durable restart/replay, explicit links, scope/role and cross-task refusal, private permissions/schema, concurrent duplicate submissions/workers, committed-response loss, absent unknown result without replay, reference conflict, pre-send refusal and recipient scoping. A task-owned HTTP fake exercises the native adapter wire shape and lost committed response; no real native call.
- Shared HTTP/auth regression checks: `test_backend.py` **21 pass**, `test_native_observations.py` **10 pass**, `test_campaign_preview.py` **8 pass**. Existing PR4+ behavior retained. Unrelated import/CRM suites were not run.
- `python3 tools/board_conversation_probe.py`: **15 synthetic browser checks pass**. No data before access; existing native board retained; request and scoped answer visible; draft survives modal close; validation allows correction; committed HTTP response loss keeps the exact frozen intent; retry leaves exactly two DB messages with correct parent link; text is inert; saved/pending are distinct; backend restart preserves history; synthetic delivery is distinct from agent processing; mobile page fits at 390×844; correct reply-mode label; footer remains reachable; revocation clears private DOM/drafts. Real DB content was checked for a single answer, not just a UI count.
- `node --check ui/app.js` and `git diff --check`: pass.
- Synthetic mobile screenshot viewed locally: task title, discussion, saved/delivery notices and reachable Close visible; inert HTML-like input rendered as text. Screenshot is not committed. Task-owned DB/server/browser profile were cleaned; screenshot removed after review.

## Limits

No production CRM/owner sources, credentials, manager binding, native human answer/resolve, campaign action, external prototype, deployment or real native context delivery. Native wire behavior is simulated with the real adapter; live acceptance/agent consumption remain NOT RUN. New app grants were synthetic only. The worker is explicitly drained locally, with scheduling/first real use left for the retained outcome; failed/unknown entries remain durable for scoped investigation. No new container/MariaDB/infra dependency was found. Administrator task creation is API-only; task list and detail history expose bounds rather than claiming complete history.

Independent Code QA and affected System QA must review this exact candidate before merge. No author self-acceptance or merge.

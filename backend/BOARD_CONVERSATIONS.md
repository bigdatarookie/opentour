# OpenTour board conversations

User correction `qitem-opentour-board-data-ownership-20261110` makes OpenTour the business-conversation source of truth. Task records, requests, answers/comments, their links and delivery/receipt state live in SQLite. They are not rebuilt from native ask/reply history. Existing CRM/native board/campaign read integrations are preserved separately.

## Private storage and start

`python3 -m backend.server --auth-file /absolute/private/project-grants.json --board-db /absolute/private/opentour-board/board.sqlite3` starts the existing loopback service with its application store. Default DB: `~/.local/share/opentour/board/board.sqlite3`. A CRM reference remains optional and unchanged. No container, MariaDB change, new service or package is needed.

DB paths inside the checkout, its original shared checkout (when running a worktree), or `.artifacts` are rejected. The immediate directory must be owned by this OS user and mode 700; newly created directories/files use 700/600. Non-private files/directories and symlink DB files are refused rather than changing owner permissions. Keep backups equally private, outside Git. Use SQLite's backup API for a consistent backup; do not copy a database during writes. The store uses foreign keys, `BEGIN IMMEDIATE` transactions, 5-second busy timeout, explicit connection closure and `PRAGMA user_version=2` migration (v1 tasks/messages/outbox are preserved); newer schemas fail closed. Host-local single-user storage is selected, not network-filesystem or multi-host deployment.

## Explicit application permissions

The existing hashed bearer grant still supplies subject/role/project. Add an optional server-owned `board` object:

```json
{"read":true,"respond":true,"create":false,"tasks":["task_example_id"]}
```

`tasks` is the exact object allowlist. `"*"` is explicit project-wide board scope, not an implied role right. Creating a task requires `administrator`, `create:true`, `read:true` and wildcard scope. Both roles may answer/comment only with `read:true`, `respond:true` and the task ID/wildcard grant. Only administrator can author a request. Subject and role come from the grant, never the body. Project membership and the current grant are checked on every read/write. Old grants default to no board access. This application principal is not a verified native human or manager binding. No grants/accounts were provisioned in this change.

## API

| Route | Effect |
| --- | --- |
| `GET /api/board-tasks` | At most 100 scoped tasks, newest first, `complete` indicates truncation |
| `POST /api/board-tasks` | Administrator creates task + initial request/comment + outbox + idempotency record in one transaction |
| `GET /api/board-tasks/<id>` | Task and latest 100 messages, explicit `reply_to`, delivery/receipt state and `historyComplete` |
| `POST /api/board-tasks/<id>/messages` | Save request/answer/comment + delivery intent + idempotency record atomically |

Create body: `requestId`, `title` (240 chars), `description` (4000), `section` (`tasks`, `clients`, `campaigns`), optional `requestText` (4000). Without requestText, the initial description is a comment. Message body: `requestId`, `kind`, `text` (4000), and `replyTo` for `answer` only. The referenced parent must be an actual request in that same task. No arbitrary actor, command, URL, destination or native decision fields are admitted. JSON body size is bounded to 32 KiB. `project` query may only be `opentour`; other queries are rejected.

Use a stable `requestId` (8–128 URL-safe letters/digits/underscore/hyphen) for one create/save intent. Its namespace is subject + operation/task, and its normalized content digest is stored transactionally. Same key/content returns the original task/message; changed content returns 409. Concurrent submission and lost HTTP responses do not duplicate a task/message/outbox. On uncertain application save, repeat that exact request, not a fresh key. This is safe application persistence, not permission to replay a native effect.

The UI shows separately granted app tasks alongside existing native execution cards. Both roles can open discussions and save linked replies/comments. Text is rendered inertly. Draft and unknown-save intent survive closing/reopening a modal in the current authenticated tab; credentials and drafts are memory-only and cleared on disconnect/revocation. A full tab reload clears unsaved drafts; committed history survives backend restart. The UI labels persistence and delivery separately and does not mark work complete when someone replies.

## Transactional outbox and delivery

Each message owns exactly one outbox row. Its stable delivery ID and native qitem ID are persisted **before** any send. The immutable payload contains only project/task/message/parent IDs, task title, this message, and its parent request where relevant; it does not dump the conversation, CRM, owner sources, credentials or terminal history. Request↔answer relationships remain in OpenTour even if delivery is unavailable.

Fixed destinations (stored from task section, never accepted from a message/browser destination field):

| Task section | Agent destination |
| --- | --- |
| tasks | `operator-agent@kernel` |
| clients | `campaign-creative@opentour-rig` |
| campaigns | `campaign-operator@opentour-rig` |

The sender is the verified existing Developer seat `platform-developer@opentour-rig`; the local worker checks `rig whoami`. No sender or manager is invented. Run only when context delivery is authorized:

```sh
python3 -m backend.context_delivery --board-db /absolute/private/opentour-board/board.sqlite3 --deliver --limit 20
```

This is an explicit finite drain, not an auto-started loop or a second workflow controller. It uses local native queue create to deliver context, never human answer/resolve or a business action. No daemon credential/config file is read. Native endpoint is fixed loopback; redirects/proxies and arbitrary targets are disabled. Worker installation/scheduling and first real delivery remain operational follow-up; no live delivery was performed for the candidate.

States are distinct: message `persistence=saved`; outbox `pending`, `delivered`, `failed`, `unknown`. `delivered` means the exact native context row was observed/accepted, not that an agent acted. Before network I/O the worker commits `unknown`; any concurrent/restarted worker performs only exact-ID reconciliation. It validates source, fixed destination, full persisted payload and delivery/project tags. A committed send followed by lost response reconciles to delivered without another send. An absent row after an unknown attempt stays unknown, because the original request may still commit. No queue/person-wide search or new task on retry. Proven local rejection before the first send is failed; remote errors/ambiguous responses are unknown. Failed rows and unresolved unknowns are retained for scoped technical investigation, never automatically rekeyed or blindly resent. If the process dies after marking unknown but before sending, this conservatively retains unknown; native execution is not claimed exactly once.

A recipient can use its own verified seat to access **only** its delivered context and record a durable `processing=received` receipt:

```sh
python3 -m backend.context_delivery --board-db /absolute/private/opentour-board/board.sqlite3 --receive context_delivery_id
```

The delivery ID is in the native `delivery:` tag. This prints the minimal task/message JSON and records recipient access; it is not completion, approval, or proof of useful continuation. Other seats/undelivered IDs are refused. It is a same-host trusted agent tool, not a browser identity service. Native execution reference is linked from the outbox; the business conversation is still read from this DB.

## Validation and remaining scope

Use `python3 -m unittest discover -s tests -p test_board_conversations.py -v` and `python3 tools/board_conversation_probe.py`. All provider/native delivery checks are synthetic, including a real local HTTP fake with commit followed by response loss. The browser probe uses a private task-owned DB/server/profile, verifies restart/retry/linkage/mobile/revocation and cleans them up. It writes a synthetic-only screenshot to `/tmp/opentour-board-conversation-synthetic.png` for local review; remove after viewing.

No real manager binding, native human decision, live agent consumption, CRM write, campaign send, external prototype or deployment is proven. Administrator task creation is API-only in this finite slice. The list/history bounds are explicit; deeper history pagination and broader task lifecycle UI are follow-up, not inferred completion. Independent Code QA and affected System QA are required before merge. No infrastructure dependency beyond a private local directory and the existing Python/SQLite runtime was found.


## Typed client-to-task relation

A task may carry one optional `clientRef`: `{"entity":"Contact","externalId":"provider-id"}` (or `Account`). Only these two fields/types are admitted; no CRM name, contacts, provider body or PII is copied into the relation. The explicit administrator create API accepts this field and verifies the record through the existing fixed CRM detail read before creating a new task. Missing/inaccessible source fails without creating a task/link/outbox. A same-key committed replay returns the existing task, even if the provider later becomes unavailable. This relation does not edit the CRM or authorize business actions.

Schema v2 adds `task_clients` and its typed-reference index transactionally. Existing v1 tasks remain unlinked; their messages, outbox and request digests/replay remain unchanged. No relationship is inferred or backfilled. New message context may include this typed reference, never copied CRM fields. There is no relation edit API in this finite change.

Client detail joins only app tasks allowed by the current project/board/object grant, with filtering before the 100-result bound. It exposes IDs/titles plus explicit completeness. Clients remain readable for old CRM-read grants; related-work metadata is withheld with `board_access_not_granted`, never a claim that no relation exists. Direct task navigation rechecks its current grant. The client-detail version includes the scoped relation, so an old CRM-only ETag cannot mask relation/grant changes. Task detail includes its typed reference; references do not assert that a deleted/offline CRM record still exists.

From either person or organization detail, related work opens the same persisted discussion in the existing dialog. Return to client rereads the client and restores its modal scroll and link focus; list filters, page and originating row remain in place. Stale links cannot bypass revoked task grants, and the error still offers return to client. Drafts remain keyed by the original app task. No manager identity, native action, provider write or live integration is implied.

Focused verification: `python3 -m unittest discover -s tests -p test_client_task_links.py -v` and `python3 tools/client_task_link_probe.py`. These use temporary synthetic records/grants/DB/browser only. The full component suites are not required to repeat unchanged behavior; independent affected Code/System QA remains the next step.

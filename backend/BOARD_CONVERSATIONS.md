# OpenTour board conversations

User correction `qitem-opentour-board-data-ownership-20261110` makes OpenTour the business-conversation source of truth. Task records, requests, answers/comments, their links and delivery/receipt state live in SQLite. They are not rebuilt from native ask/reply history. Existing CRM/native board/campaign read integrations are preserved separately.

## Private storage and start

`python3 -m backend.server --auth-file /absolute/private/project-grants.json --board-db /absolute/private/opentour-board/board.sqlite3` starts the existing loopback service with its application store. Default DB: `~/.local/share/opentour/board/board.sqlite3`. A CRM reference remains optional and unchanged. No container, MariaDB change, new service or package is needed.

DB paths inside the checkout, its original shared checkout (when running a worktree), or `.artifacts` are rejected. The immediate directory must be owned by this OS user and mode 700; newly created directories/files use 700/600. Non-private files/directories and symlink DB files are refused rather than changing owner permissions. Keep backups equally private, outside Git. Use SQLite's backup API for a consistent backup; do not copy a database during writes. The store uses foreign keys, `BEGIN IMMEDIATE` transactions, 5-second busy timeout, explicit connection closure and `PRAGMA user_version=4` migration (v1/v2/v3 messages/outbox, receipt state and request digests are preserved); newer schemas fail closed. Host-local single-user storage is selected, not network-filesystem or multi-host deployment.

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

Legacy/default destinations for tasks without a validated original-obligation binding (never accepted from a browser destination field):

| Task section | Agent destination |
| --- | --- |
| tasks | `operator-agent@kernel` |
| clients | `campaign-creative@opentour-rig` |
| campaigns | `campaign-operator@opentour-rig` |

The operational worker has an explicit declared local service mode:

```sh
python3 -m backend.context_delivery --board-db /absolute/private/opentour-board/board.sqlite3 --serve --service
python3 -m backend.context_delivery --board-db /absolute/private/opentour-board/board.sqlite3 --status
```

It declares opentour-board-service@opentour-rig through the daemon's supported body-only sourceSession route (CLI equivalent: queue create --source outside a managed seat). There is no X-OpenRig-Session header. Provenance is claimed:v1 attribution, **not authentication**, a real seat, a manager or native human authority. Service mode refuses managed-seat identity variables and seat headers. OS process ownership/private DB/grants plus loopback-only daemon access form the runtime trust boundary. DevOps owns the supervisor, persistent storage, restart/recovery and deployment. No arbitrary process is labelled Developer. Default seat mode still verifies actual Developer/DevOps identity for bounded diagnostics; --deliver is not the operational design.

The worker drains the existing outbox with bounded batches, restart-safe exact-ID reconciliation and backoff on actual lookup/worker errors. It records heartbeat and aggregate pending/delivered/failed/unknown plus processing backlog via --status; heartbeat readiness is separate from publication or manager activation. It creates fixed-role context work only, never native answer/resolve or business actions. No daemon credential/config is read. Fixed loopback transport disables redirects/proxies. Pending rows bind the actual sender and generated native body before any possible POST. The body includes trusted operational receive/report instructions and the immutable app payload as data. Keep the worker's installed source path available while its context commands are outstanding.

States are distinct: saved message, pending/delivered/failed/unknown transport, received/accepted/needs_clarification/rejected/continued recipient processing. Delivered means the exact queue row was observed, not that an agent acted. Unknown effects reconcile sender, destination, full pinned body and delivery/project tags before any retry; absence after uncertainty never authorizes another POST. A failed GET before any send safely remains pending. A crash after intent but before send is conservatively unknown. No queue/person-wide lookup or new task key is invented on retry. The service does not own agent judgment or replace native execution custody.

A recipient can use its own verified seat to access **only** its delivered context and record a durable `processing=received` receipt:

```sh
python3 -m backend.context_delivery --board-db /absolute/private/opentour-board/board.sqlite3 --receive context_delivery_id
```

The delivery ID is in the native `delivery:` tag. This prints the minimal task/message JSON (including current processing state) and records recipient access; it is not completion, approval, or proof of useful continuation. Other seats/undelivered IDs are refused. It is a same-host trusted agent tool, not a browser identity service. Native execution reference is linked from the outbox; the business conversation is still read from this DB.

## Validation and remaining scope

Use `python3 -m unittest discover -s tests -p test_board_conversations.py -v` and `python3 tools/board_conversation_probe.py`. All provider/native delivery checks are synthetic, including a real local HTTP fake with commit followed by response loss. The browser probe uses a private task-owned DB/server/profile, verifies restart/retry/linkage/mobile/revocation and cleans them up. It writes a synthetic-only screenshot to `/tmp/opentour-board-conversation-synthetic.png` for local review; remove after viewing.

Synthetic tests do not prove real manager binding, native human decisions, actual agent continuation, CRM writes, send or publication. Actual agent continuation requires independent System QA on the exact candidate; publication is separately owned by DevOps. Administrator task creation is API-only in this finite slice. The list/history bounds are explicit; deeper history pagination and broader task lifecycle UI are follow-up, not inferred completion. Independent Code QA and affected System QA are required before merge. No infrastructure dependency beyond a private local directory and the existing Python/SQLite runtime was found.


## Typed client-to-task relation

A task may carry one optional `clientRef`: `{"entity":"Contact","externalId":"provider-id"}` (or `Account`). Only these two fields/types are admitted; no CRM name, contacts, provider body or PII is copied into the relation. The explicit administrator create API accepts this field and verifies the record through the existing fixed CRM detail read before creating a new task. Missing/inaccessible source fails without creating a task/link/outbox. A same-key committed replay returns the existing task, even if the provider later becomes unavailable. This relation does not edit the CRM or authorize business actions.

Schema v2 adds `task_clients` and its typed-reference index transactionally. Existing v1 tasks remain unlinked; their messages, outbox and request digests/replay remain unchanged. No relationship is inferred or backfilled. New message context may include this typed reference, never copied CRM fields. There is no relation edit API in this finite change.

Client detail joins only app tasks allowed by the current project/board/object grant, with filtering before the 100-result bound. It exposes IDs/titles plus explicit completeness. Clients remain readable for old CRM-read grants; related-work metadata is withheld with `board_access_not_granted`, never a claim that no relation exists. Direct task navigation rechecks its current grant. The client-detail version includes the scoped relation, so an old CRM-only ETag cannot mask relation/grant changes. Task detail includes its typed reference; references do not assert that a deleted/offline CRM record still exists.

From either person or organization detail, related work opens the same persisted discussion in the existing dialog. Return to client rereads the client and restores its modal scroll and link focus; list filters, page and originating row remain in place. Stale links cannot bypass revoked task grants, and the error still offers return to client. Drafts remain keyed by the original app task. No manager identity, native action, provider write or live integration is implied.

Focused verification: `python3 -m unittest discover -s tests -p test_client_task_links.py -v` and `python3 tools/client_task_link_probe.py`. These use temporary synthetic records/grants/DB/browser only. The full component suites are not required to repeat unchanged behavior; independent affected Code/System QA remains the next step.


## v0.12 versioned answer and substantive continuation

Administrator task creation accepts optional continuationRef naming the original native qitem; it never accepts arbitrary agent destinations. A new reference must now be resolved server-side using the validated binding contract below; task creation cannot silently use a section default for an unverified new reference. The recipient must actually own that original obligation in project:opentour before accepting/continuing an answer. This reference is execution linkage, not a second execution tracker, a gate resolver, or business authority. Existing tasks are not assigned guessed obligations.

Message projection includes a stable version over immutable server-authored message identity/content/actor/time. Answers may submit replyVersion alongside replyTo; a supplied stale version fails409. Even compatibility clients that omit it are server-bound to the exact immutable request version in their outbox payload; the browser now supplies it explicitly. Actor/role come from server grants, never a body claim. Exact request-key replay remains stable after restart. Only one answer per request can be accepted; a comment cannot close a request. Insufficient input gets a precise needs_clarification receipt, not a guessed decision.

After --receive, the actual addressed seat can report:

```sh
python3 -m backend.context_delivery --board-db /absolute/private/opentour-board/board.sqlite3 --report context_delivery_id --state accepted --reason 'The answer is sufficient for the original synthetic obligation.'
python3 -m backend.context_delivery --board-db /absolute/private/opentour-board/board.sqlite3 --report context_delivery_id --state continued --reason 'Continued the original obligation.' --result-file /absolute/private/substantive-result.txt --evidence-ref qitem-original-obligation
```

Or report needs_clarification/rejected with a specific reason. Reporting verifies actual rig whoami, fixed destination, delivered/received state, request version and original project/owner. Service mode cannot report recipient processing. Continued requires accepted answer, substantive result and the original execution reference, currently in-progress/done. It records the recipient's substantive return; it is not inferred from ACK, queue delivery, comment save, an animation or native business completion. The agent continues work through its existing native custody and closes the delivery qitem after processing. Reports are transactional/idempotent; conflicting repeats409 and receipt timestamps survive restart. Re-receive never downgrades accepted/continued. Stage timestamps are actual saved/delivered/received/accepted/continued facts, not predicted timings.

Atlas cards/history/panel project these receipts and reasons/results on refresh. Open drafts survive pending delivery/errors. Native decisions remain on the separate unavailable route. Legacy tasks without continuationRef can still save/read discussions but cannot falsely claim a linked original continuation.

## Board-only test identity and prefix hosting

For the reversible published QA task use boardOnly:true with one exact board.tasks ID, read/respond true, create false. Wildcard/empty boardOnly scopes are refused. Such grants cannot reach CRM, native projection or campaign adapters, even when a provider is configured. Atlas shows the scoped discussion and a clear restricted-source explanation. Existing read grants keep their previous behavior. Also omit --crm-credential-file from the isolated synthetic runtime. No real manager is provisioned; removing the test grant revokes it on the next request.

The root-local default is unchanged. An explicit --public-base-url https://existing-host/opentour supports a prefix behind DevOps' HTTPS proxy: shell/style/API/preview paths share the configured prefix, Host and Origin are checked against explicit configuration plus loopback. No wildcard origins or forwarded-header trust; the backend still binds loopback. This does not authorize proxy credential use or prove publication. The raw daemon/CRM/backend must not be exposed directly.


## Exact original-obligation assignee routing

The native obligation's current assigned agent overrides the section default only after server-side validation. There is no new destination/session input and no global arbitrary-recipient allowlist. The default API resolver reads only GET /api/queue/<exact-id>, requires the returned qitemId to match, exact sole project:opentour and mission:01-local-information-layer tags, and pending/in-progress/blocked state. It validates the canonical local destination against the registered agent seat through the supported read-only rig ps --nodes --rig <rig> --session <exact-session> --fields canonicalSessionName,rigName,logicalId,lifecycleState,runtime --json --no-cleanup projection. Registry observation pins OPENRIG_URL to the local daemon; there is no remote host selection, catalog cleanup or native write. Allowed scope is registered OpenTour agent seats and the existing kernel Operator, not humans/services/unregistered or foreign-rig recipients. The runtime must have the actual installed rig CLI on PATH, not a borrowed managed-seat wrapper.

Schema4 appends task_execution.destination and outbox.routing_ref as nullable fields. It does not rewrite historical bodies/digests/IDs or infer destinations for existing rows. New validated tasks persist the derived owner/ref before any outbox effect, and new messages preserve that binding. A new save re-reads the original scope/state/expected owner before creating its intent. Ownership changes reject rather than retarget. Exact-key committed replays return their prior result without requiring a still-open native obligation and create no duplicate messages/deliveries.

The HTTP API supplies NativeObligation.resolve automatically. Trusted local seeding/tools that create a new continuationRef must pass resolve_obligation=NativeObligation().resolve to BoardStore.create/append; omitting the resolver for a new binding fails closed. Callers still cannot set a destination. Native lookup/registration failure creates no new task/message/outbox intent. Scope/state/owner errors are explicit; no installed OpenRig changes or guessed identities.

Before a first possible send, the worker revalidates the exact original reference and pinned owner. A read outage stays pending; a closed/foreign/reassigned reference fails before POST. An already-unknown send performs only exact delivery-key/body/sender/destination reconciliation, even if the original has since moved or closed; it never chooses a new recipient or POSTs again. Actual recipient acceptance/continuation rechecks scoped ownership. Native read and send are not a distributed transaction; a change after the pre-send read is handled by the recipient check, not a claim of atomic native custody. Existing no-binding rows keep their fixed section behavior, including the previously accepted Operator path.

Deploy backend and worker from the same reviewed release, with the worker stopped during schema/source upgrade; an older static-list worker must not consume new assignee-bound rows. DevOps owns private DB backup/restart and rollback. The implementation task performs no deployment, owner DB edit or real native queue write.

The supported local staging, SQLite backup, coordinated LaunchAgent activation and pre-traffic rollback procedure is documented in [Local board release and rollback](../docs/operations/local-board-release.md). That runbook does not authorize activation; the separate local-runtime-upgrade gate still controls it.

Focused synthetic coverage: python3 -m unittest discover -s tests -p test_board_obligation_routing.py -v. It includes QA-System-owned routing through HTTP/store/outbox, forged/foreign/closed/wrong-owner rejection, registered-seat projection, pending preflight, unknown-send reconciliation, receipt ownership, replay and migration/default preservation. After independent Code QA/merge, the remaining consumer check is one reversible QA-System-owned native obligation with exact project/mission tags, using the merged backend/worker together and observing actual delivery/receipt/continuation. Do not repeat the already accepted Operator consumer or infer real delivery from fixture results.

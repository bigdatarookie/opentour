# Local OpenTour backend

Python 3.9+ standard library, no package install. CRM/native execution remain scoped read projections. OpenTour now owns durable board tasks, requests, answers/comments and a transactional context outbox in private SQLite, with a task discussion UI. See [BOARD_CONVERSATIONS.md](BOARD_CONVERSATIONS.md). Saving conversation data does not authorize a native decision or business action. An explicitly invoked local worker can deliver fixed-seat task context; it is not run by the web server.

## Run

From the repository root:

```sh
python3 -m backend.server --auth-file /absolute/private/read-grants.json --crm-credential-file /absolute/private/espo-read-api.json
```

It binds only `127.0.0.1:18083`. `--port` can select a different local port. Configuration paths are safe references, never credentials in argv. The read-grants file and CRM credential file must be private regular files with no group/other permissions (typically mode `600` inside a mode `700` directory). Do not put either in Git, `.artifacts`, screenshots or chat.

The existing CRM remains at `http://127.0.0.1:18082`. The adapter requires an already authorized EspoCRM API key in a private JSON object with an `apiKey` field. Keep the key inside this backend boundary: its fixed CRM adapter makes GET requests only, but an EspoCRM API user's effective ACL may retain unrelated mandatory permissions even when the assigned role denies them. Backend code does not create a principal, read an admin-password file, retry imports or inspect owner CSV/mapping/checkpoint files. No key configured means CRM endpoints return HTTP 503; board reads continue.

The installed EspoCRM mandatory ACL overrides narrower Roles with unrelated own-scope create/edit/delete permissions and Portal read-all. Lead decision `qitem-20261108195859-3f40e4d0` therefore authorizes a dedicated non-admin API service identity with Contact/Account read-all **confined to this reviewed backend**, without changing the shared ACL or creating another proxy. The upstream principal is not intrinsically read-only; the fixed GET adapter and application authorization enforce the exposed read boundary. DevOps owns provisioning, the private reference, actual inherited-scope verification and revocation. This does not designate a human manager or authorize use of any additional upstream privilege. Never use the API credential directly from a browser, grant it to an app user, or widen the fixed provider methods/routes.

Read grants are a server-controlled JSON object with a `principals` array. Each entry has `subject`, `role` (`user` or `administrator`), `projects` (must include `opentour`) and `tokenSha256` (SHA-256 of a high-entropy bearer token). A request uses `Authorization: Bearer …`. The grant is checked on every request. Roles or project names sent by the browser do not grant access. A grant authorizes reading this isolated project's CRM and work projection; it is not a native human identity. No real manager is currently designated. Do not issue an access grant to an inferred person. The diagnostic probe uses only a short-lived process-local read grant and does not create a human account.

Native mutation/free dialogue routes still return HTTP 403 for both roles with `manager_identity_and_native_action_authorization_unavailable`. Separately, `/api/board-tasks` supports OpenTour DB writes only when a server-owned application grant explicitly enables board permissions and object scope. Old read grants gain no write capability. This replaces the obsolete blanket prohibition on a writable board database under the user correction `qitem-opentour-board-data-ownership-20261110`; no native human binding is required merely to save an application response. No UI acknowledgement is presented as a saved native decision.

The server provides no permissive CORS. It rejects foreign Host and Origin values and disables response caching and request logging. It is a local development server, not a public deployment or a production identity provider. Browser integration should use same-origin routing and keep server credentials off the browser. No owner daemon token is read or exposed. Native reads use the existing local trusted control plane.

## Read contract

| Route | Result |
| --- | --- |
| `GET /healthz` | Process liveness, explicitly not integration readiness; no auth required |
| `GET /api/capabilities` | Server-observed read role and closed action/dialogue boundary |
| `GET /api/clients` | Real EspoCRM records; `kind=person|organization|all`, `q`, `hasEmail=true|false`, `hasPhone=true|false`, `offset`, `limit` (1–100) |
| `GET /api/clients/crm:Contact:<id>` | Person short card; Account ID shape is `crm:Account:<id>` |
| `GET /api/board` | One card per native slice in mission `01-local-information-layer`, aggregated routine qitems |
| `GET /api/board/work:opentour:01-local-information-layer:<slice>` | Same stable card/detail, authorized through current source membership |

`project` can be omitted or equal `opentour`; other projects are refused. No arbitrary upstream URLs, entity types, filesystem paths, shell commands or native session targets are accepted. HTTP errors are bounded codes without provider bodies or contact values. Source failure returns an error rather than an empty success. Unknown counts are not converted to zero.

Client ordering is Contact first, then Account, each ordered by native ID; `total`, `nextOffset` and per-entity totals reflect the same search/channel criteria. This is offset pagination over the live provider, not a transaction snapshot: concurrent CRM edits can change page boundaries. A CRM record remains authoritative and deep editing uses its `sourceLink`. Related-work relationships are explicitly unavailable, never invented. Organization type is preserved in `attributes.crmType`; more CRM-specific filters can be added when their field contract is selected.

EspoCRM queries use a typed JSON `searchParams` envelope. A JSON string in the plain `where` parameter is silently ignored by the installed provider and must not be used. The regression test and masked live probe assert unmatched-search content, not just an HTTP success status. Current local observations and remaining acceptance limits are recorded in [VERIFICATION.md](VERIFICATION.md).

Version-2 import markers already present on CRM Contacts supply source ordinal, content revision, logical row and mapping revision. Raw CRM descriptions and private source paths are not returned. For a source-marked Contact whose lastName is the literal `None`, display name excludes that technical value; `surname.technicalValue` and `deduplicationKey=false` preserve its meaning. Status is `technical_placeholder_observed`, not a claim to have verified the private mapping. Unmarked literal surnames are not silently rewritten. The known 59 unmatched import conflicts are not retried or represented as accepted contacts by this service.

## Native board and refresh

The native CLI enumerates slices with explicit `--workspace` and `--mission`. Each detail request uses `project` and `mission`, and its returned source path must match membership. This avoids the installed OpenRig 0.7.7 global slice-list route, which was observed ignoring its project query. Queue records must have matching project, mission and slice tags. A finite queue window is labelled `queueWindowComplete=false` at its bound; incomplete facts cannot establish completion.

The adapter reads only shared authored `PROGRESS.md` current-state/latest-outcome text plus selected native fields. Queue bodies, terminal captures, raw story events and private evidence files are not exposed. Sensitive-pattern redaction is defense in depth for shared text; source authors must continue keeping PII and secrets out of shared progress. Title translations for the five initial slices are presentation labels, not work state. Owners are native seat references/roles; a human request is not authenticated-human proof.

Columns derive in order: active human request → Требуется человек; active QA custody → На проверке; active work → В работе; explicit authored completion **and** native proof readiness `ready` with a complete queue window → Выполнено. Otherwise native active/blocked/planned evidence determines the column or it is unknown. Closing a handoff or a synthetic test qitem cannot complete a business card. Native blockers remain visible alongside any column. `lastResult` comes from the last authored outcome; `requiredNextAction` uses an active row's request summary or is null. Freeform historical progress text is source context, not a newly inferred decision.

Poll `/api/board` with `If-None-Match` from its ETag; unchanged content returns 304. Each card and snapshot has a content version. `cursor.epoch` identifies the process and `cursor.sequence` increases only when board content changes. Discard older responses in the same epoch; on a process restart replace the snapshot for the new epoch. Keep modal/input/filter state keyed by stable card ID. These are read projections, not a second workflow engine or persisted event log. Polling rather than SSE is the first transport; animation remains UI work.

## Verify

```sh
python3 -m unittest discover -s tests -p test_backend.py -v
python3 tools/backend_read_probe.py
```

The tests use synthetic in-memory source adapters and a real local HTTP server. The probe uses real native work with an ephemeral in-memory diagnostic grant; without a CRM key it explicitly reports CRM integration NOT RUN. With an authorized runtime reference, run `python3 tools/backend_read_probe.py --crm-credential-file /absolute/private/espo-read-api.json` for real CRM list/detail/filter/search reads. It prints only HTTP statuses, counts and boolean provenance observations. It never prints record values, source markers, tokens or credentials; its server is shut down at the end. A passing probe is not a manager conversation/human-decision acceptance.

EspoCRM query fields and paging follow the vendor [search parameter contract](https://docs.espocrm.com/development/api-search-params/) and [CRUD API](https://docs.espocrm.com/development/api/crud/). Local behavior must still be checked against the installed CRM.


Read-only native action observation metadata is available for a known scoped original task through the existing board authorization. See [NATIVE_OBSERVATIONS.md](NATIVE_OBSERVATIONS.md) for the fixed route, source bounds, privacy projection and explicit unconfirmed identity/action semantics. This does not enable native writes or turn an audit entry into an accepted human decision.

# Reconcile an existing client conversation anchor

Use the existing client conversation, BoardStore, server-owned ClientControls and
request audit. This maintenance command creates no app message, outbox delivery,
native queue work, proposal or business action. It does not reopen terminal work.

First reconcile the original uncertain event read-only: exact request identity,
persisted messages, outbox receipts and actual native recipient state. A 409 alone
is not proof that an earlier attempt had no effect. Resolve pending or unknown
app/native deliveries before considering any routing change.

The business owner identifies a distinct current same-purpose Creative anchor.
Keep the prior completed obligation closed. The deployment owner coordinates the
existing private server controls entry for the same client; a browser cannot
choose the replacement anchor. Source acceptance and the bounded adoption remain
separate from actual original ProductQA delivery acceptance.

Run as the actual registered Engineering Platform or Infrastructure seat. The
command obtains its actor from the inherited native CLI; no actor flag or HTTP
route exists. Default mode opens the existing private database read-only and
validates both anchors against the real GET-only native adapter, including scope,
recipient and registered seat. It refuses unresolved outboxes or a previously
saved original event.

```
umask 077
python3 -m tools.reconcile_client_binding \
  --board-db /private/app-data/board.sqlite3 \
  --client-controls-file /private/auth/client-controls.json \
  --task-id task_0123456789abcdef0123456789abcdef \
  --previous-ref qitem-existing-completed-anchor \
  --event-request-id original-preserved-request > /private/rebind-plan.json
```

The plan contains only opaque identities and hashes, never conversation or
proposal bodies. Review its task/client fingerprint, exact prior/current anchor
and original event identity. Apply the same saved plan with all the same arguments
plus:

```
  --apply-plan /private/rebind-plan.json \
  --expected-plan-sha256 PLAN_HASH_FROM_READ_ONLY_OUTPUT \
  --request-id stable-maintenance-request
```

Apply revalidates the current controls/native state and full same-task snapshot.
A single existing SQLite transaction compares and updates only
`task_execution.native_ref` and inserts one idempotency audit in `requests`.
A changed snapshot fails without routing mutation. Exact retries return the saved
maintenance outcome; conflicting content under that key is rejected. Existing
messages, proposals and historical outbox payloads/routing stay unchanged. The
original event request key is not consumed by maintenance.

No schema migration or service restart is required by this compatible data-only
operation. The running app still validates actual eligibility for every new
event. After accepted source and scoped adoption, return readiness to the original
ProductQA lineage for its one reconciled event and actual Creative consume/reply;
maintenance success alone does not establish that consumer result.

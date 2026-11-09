# Native action preparation contract

Scope: the next bounded step for slice 03 under SPEC/UI_FLOW. This is **preparation only**. No action route, human binding, transport, persistence, queue write, reply or decision is enabled. Actual native action integration is **NOT RUN**. Existing administrator/user write denials remain in force.

`native_action_contract.py` contains pure request validation, reviewable native-shaped payload drafts, receipt interpretation and snapshot-refresh rules. It is deliberately not imported by `server.py`; `Intent.execution_enabled` is always false. It does not provide an executor, identity verifier, retry worker, new ledger, queue or controller. Synthetic tests supply all authority and native observations in memory.

## Installed capability inspected

Observed CLI: OpenRig `0.7.7 (f3d8bac4)`. Source root on this installation is `/Users/garry/.local/node-v24.22.1-darwin-arm64/lib/node_modules/@openrig/cli`. These references are inspection evidence, not proof of exercised effects:

| Source | Relevant behavior |
| --- | --- |
| `daemon/dist/routes/mission-control.js`, `/action` | Accepts `verb`, `qitemId`, decision or question/option, plus `auditNotes`. Headerless body actors retain `claimed:v1`; `primary-user` is the trusted terminal convention. This is not a verified OpenTour manager login. |
| `daemon/dist/domain/mission-control/mission-control-write-contract.js`, `answerAsk` | Only answers the addressed person's ask. A partial choice leaves the ask pending; completed answers return a native reply and close the ask. A committed earlier return wins over later words. A retry may record another audit entry while reusing the original reply. |
| Same file, `resolveParked` | Requires a human/typed-gate park, records the decision and changes the **same** task to `in-progress` with blocker cleared. Nudge is best effort after recording, not owner-work proof. |
| `daemon/dist/domain/queue-repository.js`, `getHumanAnswer`/`createHumanAnswer` | Native return lookup is by ask, answering actor and asker. Creation uses the ask-derived stable reply identity. The application must read that native return, never invent a provider reply ID. |
| `daemon/dist/domain/mission-control/mission-control-action-log.d.ts`; route `/audit` | Native audit exposes action ID, verb, task, actor/provenance, before/after state, reason and audit notes. Filter names include `qitem_id`, `action_verb`, `actor_session`. |

The inspected action route does **not** admit/enforce an expected-revision compare-and-swap or unique client-request key. Audit correlation can be recorded but is not an atomic deduplication constraint. Native answer reuse and duplicate-resolve rejection do not establish general exactly-once execution. No live native mutation endpoint was called to investigate this.

## Inputs and object authorization

The future server must obtain a verified native human binding and an explicit allowed-original-task set from a trusted resolver. The current read `Principal` has neither and is insufficient. `Authority` is a typed preparation input, **not evidence that authentication occurred**; no browser-supplied role, `actorSession`, `authority`, human address or boolean can establish it. A `transport:v1` provenance label alone is also insufficient human authentication.

Before projecting a writable action descriptor, the consumer must read authoritative task facts inside the selected project and object scope. The aggregate board-card ID is not an ask ID. Never answer an arbitrary qitem just because it appears on the same slice. A valid `answer` binds the allowed original task → its current ask blocker → the addressed person → the original owner/asker, with matching project/mission/slice tags. `resolve` is narrower than native capabilities: only that person's direct park on the same original task is modeled. Typed external/auth/fold gates and administrator overrides are excluded.

Request fields are exactly:

```json
{
  "requestId": "stable-draft-request-id",
  "action": "answer",
  "originalTaskId": "synthetic-original",
  "targetTaskId": "synthetic-ask",
  "expectedRevision": "64 lowercase hexadecimal characters",
  "decision": "Synthetic words, not automatically approval"
}
```

Alternatively, `questionId` plus `optionId` replaces `decision`. Choices must exist and be unanswered in the native snapshot; mixed, empty, oversized or control-character decisions are rejected. Clarification on agent work remains an explicit unsupported seam; `clarify`, `send`, arbitrary destinations, actor claims and extra routing fields are rejected. Do not repurpose native `annotate` as a comment-to-Operator delivery receipt.

## Revision and request identity

`native_revision` hashes the target task's relevant native fields, question/options/answers and observation revision. It is separate from the board card/content version and refresh cursor. Preparation rejects a known stale revision, but cannot close a race between this read and a future native write. No current draft is executable until a supported concurrency/authorization boundary is selected.

The request key is stable for `(project, application subject, binding revision, requestId)`. The content digest separately binds action, original/target IDs, expected revision and canonical decision/choice. Repeated delivery preserves both. Reusing a request identity with different content is a conflict rather than a new decision. Draft previews place hashes and original-task/binding references in proposed `auditNotes.opentour`, not raw personal data. These are correlation proposals using a supported metadata field; they are not currently being submitted or enforced by OpenRig.

After an indeterminate effect, read matching native audit, ask, reply and original-task facts before considering another action. The pure `reconcile` function consumes a previously validated intent and those trusted observations. It does not reconstruct authority, search an audit log, save application receipts or retry anything. If a future session cannot recover the intent/correlation safely from native facts and authenticated scope, return unconfirmed rather than create an application decision database.

## Receipt and refresh meanings

| Observed facts | Prepared interpretation |
| --- | --- |
| No matching native audit | `unconfirmed`; no action retry allowed |
| Same request key, different content/binding/original reference | Conflict; preserve draft and original task, no resend |
| Wrong actor, target, provenance or current custody | Refused; no receipt accepted |
| Audit correlation matches but committed words differ | `decision_content_unconfirmed`; new notes cannot overwrite the original committed answer |
| A choice without a matching value read from native `humanAnswers` | `decision_content_unconfirmed` |
| Native choice stored, ask still pending | `partial_answer_recorded`; no resumed-work claim |
| Ask closed but linked native return not observed | `answer_return_unconfirmed` |
| Completed ask plus native return to the same original owner | `answer_returned`; original task ID remains unchanged |
| Resolve audit for the same original task, state `in-progress`, blocker cleared | `decision_recorded` |

`nativeReadyToContinue` is derived separately from the current original task's pending/in-progress state with blocker cleared and unchanged owner. `ownerActionObserved` stays false: a later owner action/result must be independently observed at the real consumer. A denial, condition or clarification retains its text/meaning; recording it is not consent to send, deploy or perform another reserved business action.

Snapshot read policy is independent of submission: same epoch/sequence/version is unchanged; a lower sequence is ignored; conflicting content at the same sequence requires resync. An unfamiliar epoch requires an authoritative reconnect snapshot rather than guessing epoch order. After that resync, replace current state without replaying transitions or actions. The helper does not schedule polling or drive the UI; existing read paths continue unchanged. Synthetic refresh/resume tests retain the same original task and never manufacture a replacement work item.

## Verified preparation and next consumer action

Run from the candidate checkout:

```sh
python3 -m unittest discover -s tests -p test_native_action_contract.py -v
```

Sixteen targeted synthetic tests pass: stable duplicate identity, conflicting reuse, stale/invalid decisions/options, role/project/object/ask-custody restrictions, arbitrary-message and actor-field rejection, receipt/reply identity and committed-content checks, partial/unknown outcomes, same-original-task continuation, stale/duplicate/restart snapshot rules, and current HTTP write denial for both roles. The HTTP check uses synthetic adapters; no live daemon or CRM action was used. This result is preparation evidence, not actual native integration or independent acceptance.

Next consumer is Developer with the kernel capability owner, under Lead's selected scope: establish a supported authenticated-human/object binding and conditional/idempotent native action boundary; verify authoritative audit/ask/return/original reads within that scope; then adapt these validators and receipt states behind the existing closed API only after explicit live-write authority. Preserve the native ledger as source of truth. QA reviews this candidate now; the future authorized live episode must prove an actual persisted response, duplicate/unknown-effect reconciliation and the same original owner doing resumed work. Clarification-to-Operator remains a separate exact capability gap. No current preparation warrants enabling reply fields, free chat or native writes.

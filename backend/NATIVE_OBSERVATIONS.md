# Read-only native decision observations

This extends the existing backend's board reads. It does not enable a decision, reply, comment, retry or manager login. No UI or external prototype change is included.

GET /api/board/work:opentour:01-local-information-layer:<slice>/native-decisions/<original-qitem-id> uses the existing application read grant and project checks. The original must be in that slice's current native catalog/queue snapshot, with project, mission and slice tags. Unknown IDs and slices are refused before full-row or audit reads. Source project/mission configuration must match the service. Browser-supplied audit filters, actors, upstream URLs, original/ask authority or decision content are not accepted. Mutations remain HTTP 403 for both roles.

The reader obtains the original row, verifies its scope/current custody, then reads only its resolve audit and, if the current blocker is an in-scope ask from that original's owner to an external person address, the ask's answer audit. The spelling of a person address is a routing check, never authentication. Linked replies are looked up only among the existing scoped queue's human-answer candidates with the same native sender/owner and verified by their actual replyTo. A native reply ID is returned only after reading the stored row; no ID is manufactured. Historical asks that are no longer current blockers, legacy untagged returns and primary-user overrides are outside this bounded lookup.

Audit pages are limited to 20 per known target and candidate replies to 20; overflow/window completeness is explicit. These are source read bounds, not a claim of full history. A missing match means unconfirmed. Native source errors or changed original/ask custody return an error rather than an empty success. The original/ask is re-read after audit/reply reads; this detects observed changes but is not a transactional snapshot or compare-and-swap guarantee.

Only fixed status names, action/task IDs, verbs and validated before/after state enums leave the boundary. Full queue bodies, summaries, audit reasons/annotations/notes, actors and human answers are transient source inputs and are never forwarded, logged or persisted. The reader uses existing NativeWork/JsonGET and only loopback GET routes. It creates no receipt ledger, retry controller or task tracker.

The output deliberately keeps humanIdentityVerified, decisionAccepted, ownerActionObserved, executionEnabled and retryAllowed false. Native audit/reply presence does not establish the current app user's binding, validated intent, accepted content or consumer action. The merged pure native_action_contract.py still requires a real trusted Authority before its reconcile function can be used as an action receipt. This reader does not invent that Authority or turn transport provenance into a human login. Real manager/reply/resume acceptance remains open.

## Source contract inspected

Installed OpenRig 0.7.7: daemon/dist/routes/mission-control.js GET /audit under /api/mission-control supports qitem_id, action_verb and limit. domain/mission-control/audit-browse.js returns rows/hasMore/nextBeforeId. domain/mission-control/mission-control-write-contract.js snapshotQitem supplies IDs/states; answerAsk writes actual linked native return rows via QueueRepository.createHumanAnswer. routes/queue.js GET /:qitemId returns the stored row. The source paths are relative to the installed @openrig/cli package; no write endpoint was exercised.

## Developer verification — 2026-11-09

- 9 targeted tests in tests/test_native_observations.py pass: bounded source metadata, privacy filtering, source and slice membership before lookup, misconfigured source project, source/custody change, invalid audit, incomplete/absent observations, actual stored ask/reply correlation, unrelated owner refusal, authenticated HTTP scope and mutation denial.
- Existing 21 backend tests and 16 native action contract tests pass. Tests are synthetic and include local HTTP servers; they make no live source mutations.
- The native-only HTTP probe uses a temporary in-memory diagnostic read grant and stops its own HTTP server. It reads the existing specification/native queue; no CRM object, credentials file, owner source or browser profile is used.

```sh
python3 -m unittest discover -s tests -p test_native_observations.py -v
python3 tools/native_observation_probe.py --work-root /absolute/existing/opentour-rig --original-id <existing-scoped-qitem>
```

Actual native read of the Developer's current scoped assignment qitem-20261109081714-6c7fcd91 returned authenticated HTTP 200, unauthenticated 401, zero audit entries and zero linked replies, complete bounded queue/audit windows and status unconfirmed. All identity/acceptance/owner-action/execution/retry flags remained false. This proves the negative source read integration, not a live recorded answer or resumed work. No raw source values, actors, decision words or credentials were emitted. Independent QA pending; no full slice acceptance or deployment.

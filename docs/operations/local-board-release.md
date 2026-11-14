# Local OpenTour board release and rollback

This is the versioned local release procedure for the persistent loopback board backend and delivery worker. It is intentionally separate from external publication. The release from PR20 is `1ed7c1f79e9441c338fa4ac3ecfbdaf75e9dec6e` (tree `3fb29ac7dc55c0c7ad294ed29be9e69f483e279c`).

## Boundaries and state

The existing OpenTour app database is `~/Library/Application Support/OpenTour/state/board/board.sqlite3`. The app grant file is referenced by path at `~/Library/Application Support/OpenTour/auth/system-qa-grants.json`; keep that reference and its contents unchanged. The OpenRig daemon owns queue and conversation state separately. This app release does not migrate those records. The OpenTour outbox is in the SQLite database and must remain with it; starting the worker may deliver pending rows.

PR20's `BoardStore` upgrades schema 3 to schema 4 inside its SQLite transaction by adding nullable `task_execution.destination` and `outbox.routing_ref`. It preserves existing rows and IDs. The 68131ed application rejects schema 4. Therefore an old release can only be restored with its matching schema-3 database, and the worker must be stopped before source/schema change. A newer static-list worker must never overlap with PR20 routing.

Run activation only after the separate `auth:local-runtime-upgrade` gate is resolved and the exact merged release is selected. This document and its helper do not resolve that gate. Do not use the procedure for the CRM database, owner inputs, or public deployment.

## Prepare and rehearse

1. Stage the exact merged commit into a new version directory. The helper removes write bits from staged files and directories after archive verification (preserving executable bits); do not copy a dirty checkout:

   ```sh
   python3 tools/local_board_release.py stage \
     --repo /Users/garry/Documents/git/opentour \
     --revision 1ed7c1f79e9441c338fa4ac3ecfbdaf75e9dec6e \
     --release-root "/Users/garry/Library/Application Support/OpenTour/releases"
   ```

   Confirm the returned commit and tree are the accepted values above. The helper rejects an existing version directory and unsafe archive entries.

2. Render the two version-pinned LaunchAgents to the new release's private `launch-agents` directory. Rendering parses both plist files and reports `loaded:false`; it never calls `launchctl`:

   ```sh
   python3 tools/local_board_release.py render-agents \
     --release-dir "/Users/garry/Library/Application Support/OpenTour/releases/1ed7c1f" \
     --app-root "/Users/garry/Library/Application Support/OpenTour" \
     --python /Users/garry/.local/bin/python3.11 \
     --auth-file "/Users/garry/Library/Application Support/OpenTour/auth/system-qa-grants.json" \
     --database "/Users/garry/Library/Application Support/OpenTour/state/board/board.sqlite3" \
     --output-dir "/Users/garry/Library/Application Support/OpenTour/staged-agents/1ed7c1f"
   ```

   The server and worker must name the same release and database. The worker uses the declared service actor, no managed-seat identity, and the installed unwrapped `rig` from its PATH. No CRM credential argument is generated.

3. Run the focused synthetic rehearsal below before any production activation. The real database is not a test fixture. Immediately before an authorized upgrade, create a private online snapshot with SQLite's backup API; do not copy a live database file:

   ```sh
   python3 tools/local_board_release.py backup \
     --database "/Users/garry/Library/Application Support/OpenTour/state/board/board.sqlite3" \
     --backup-dir "/Users/garry/Library/Application Support/OpenTour/backups"
   ```

   Keep both the mode-0600 database snapshot and mode-0600 JSON sidecar in the mode-0700 backup directory. The sidecar records schema, aggregate table counts, and private logical/file digests; the helper never prints row contents. Check the snapshot reports schema 3 and `integrity: ok`. If the backup fails, is not schema 3, or integrity is not `ok`, stop before activation.

## Activation sequence (not run by this change)

Schedule a short local maintenance window. Close or save all open task forms. The UI holds its bearer token and unsaved drafts in page memory; it has no persistent browser-session store. Keeping the same page open can retain that in-memory state through a brief server restart, but a refresh/reload loses the token and draft and requires reconnecting. In-flight requests can fail during downtime. No exact zero-interruption browser-session guarantee is made.

1. Record aggregate DB state with `inspect`; do not inspect board contents. Review any pending or unknown outbox work before allowing a worker to run. Pending rows can create native qitems; unknown rows must be reconciled by exact existing delivery identity, never blindly resent.
2. Stop the old worker LaunchAgent first, then the old server LaunchAgent, using `launchctl bootout gui/<uid> <existing-plist-path>`. Verify both old labels are absent from `launchctl list`, no listener remains on `127.0.0.1:18083`, and both old processes exited. Do not kill a PID while its `KeepAlive` job remains loaded.
3. Keep the old plist files and old release directory intact. Install the two rendered new plist files atomically under `~/Library/LaunchAgents`, retaining their versioned labels. Validate the installed files with `plutil -lint`; do not edit their generated arguments by hand.
4. Bootstrap the new server LaunchAgent first with `launchctl bootstrap gui/<uid> <new-server-plist>`. Its `BoardStore` performs the transactional schema 3→4 migration. Confirm the listener is the new release, `GET /healthz` is `ok`, and `inspect` reports schema 4 and `integrity: ok`. Health is liveness only.
5. Recheck aggregate outbox state and reconcile any unexpected pending/unknown difference before starting delivery. Then bootstrap the new worker LaunchAgent. This is the point at which pending application deliveries can create native qitems. Verify the worker label/process and the supported application receipts; do not infer consumer continuation from worker health.
6. Reconnect the existing UI page if its requests failed. Keep the existing auth grant reference and origin. Verify the approved user path separately; this release operation itself makes no claim of QA-System delivery or product acceptance.

The versioned LaunchAgents have `RunAtLoad` and `KeepAlive`; a `kill` alone is not a stop or upgrade. `bootout` unloads the job before its replacement is bootstrapped. Never bootstrap old and new labels for the same port/database at once.

## Rollback

The helper supports only the safe pre-traffic rollback: schema 4 differs from the schema-3 backup solely by PR20's two nullable columns, and both must still be empty. It compares a private fingerprint of all pre-existing table rows and refuses restoration if any application/outbox row changed after backup or either new routing field became non-null. Thus rollback cannot silently erase new answers, receipts, assignments, or delivery effects.

1. Stop/unload the new worker first and then the new server. Verify both jobs and processes are gone and no SQLite `-wal`/`-shm` sidecars remain.
2. Restore the recorded schema-3 snapshot while services are stopped:

   ```sh
   python3 tools/local_board_release.py restore \
     --database "/Users/garry/Library/Application Support/OpenTour/state/board/board.sqlite3" \
     --backup "/Users/garry/Library/Application Support/OpenTour/backups/<recorded-schema3-snapshot>.sqlite3" \
     --assert-services-stopped
   ```

   The helper first verifies no versioned OpenTour LaunchAgent is loaded, no listener remains on port 18083, and neither backend nor worker module is running. It then refuses a non-schema-3 backup, non-schema-4 target, changed logical rows, invalid integrity, or SQLite sidecars. It restores through a same-directory temporary database and atomic replace. Never force past a refusal.

3. Bootstrap the retained 68131ed server and worker plists only after restore reports schema 3 and integrity `ok`. Verify the old server opens the restored DB and the expected loopback health route returns. Keep the PR20 release and backup until the new release is accepted.

If the worker has run or users have saved new app data, the fingerprint check will refuse snapshot restoration. Stop and preserve the current DB, reconcile exact outbox/native effects, and make a separate recovery plan that preserves those newer records. Restoring the pre-upgrade snapshot after delivery can erase receipt IDs while leaving native qitems, causing inconsistent history or duplicates. The old 68131ed binary cannot open schema 4; a forced old-code launch is not rollback. There is no schema-4 downgrade or data-loss override in this helper.

## Synthetic verification

Run only disposable synthetic databases and plist fixtures:

```sh
PYTHONDONTWRITEBYTECODE=1 \
OPENTOUR_LEGACY_RELEASE="/Users/garry/Library/Application Support/OpenTour/releases/68131ed" \
  python3 -m unittest discover -s tests -p test_local_board_release.py -v
```

The tests verify a private schema-3 snapshot, PR20's real `BoardStore` 3→4 migration with sample task/outbox rows preserved, integrity, guarded restoration, refusal when app/outbox rows change, a schema-3 open by the installed legacy source when available, exact-commit archive staging, and parse/validation of temporary LaunchAgents. No test loads a plist with `launchctl`, opens a service, reads the production DB, or contacts OpenRig.

## Schema 5 client conversations: reviewed local adoption contract

This is source preparation, not permission to operate the live DB or services
while authoring. After independent reviewed merge, DevOps stages that exact
release and preserves the current live schema4/2fd09e2 process and receipt
history until the authorized integration window. The current schema3 backup is
not current and must not replace schema4 receipts.

Take a **fresh** private SQLite online backup/manifest with the existing `backup`
command; record integrity, schema4 and fingerprints/counts without row values.
Inspect pending/unknown deliveries by exact IDs and reconcile before worker
restart. Stop worker then server, confirm process exit, stage reviewed source,
and open BoardStore once for the transactional4→5 migration. It adds only
`client_conversations` and `proposal_revisions`; no existing messages/outbox rows
are rewritten. Opening the same schema5 DB again is idempotent. Older binaries
refuse schema5, so do not point the old release at that migrated DB.

Preserve existing private source/auth references. Add only the reviewed exact
client grant and `--client-controls-file` binding described in backend/README.md;
use a separately authorized synthetic CRM record/Creative obligation. Existing
GET-only CRM credentials never gain writes. Verify source/process working dir,
schema5, integrity and pre-migration legacy row fingerprints, then server health
and exact scoped access. Start worker only after native-effect reconciliation.
Independent QA owns actual first/second agent replies and persistence checks.

A bounded **pre-traffic** rollback is now available, tested on disposable DBs:

```sh
python3 tools/local_board_release.py restore-v4 --database "$OPENTOUR_BOARD_DB" --backup "$OPENTOUR_FRESH_SCHEMA4_BACKUP" --assert-services-stopped
```

The CLI checks both LaunchAgents are stopped. It requires the fresh verified
schema4 snapshot, schema5 current DB, exactly the two empty new tables, every
pre-existing table/row/receipt/worker heartbeat unchanged, and no SQLite sidecar.
Any new contextual row, reply, proposal, message, receipt/native effect or changed
worker state refuses replacement. If an effect occurred or remains unknown,
preserve schema5 and reconcile/forward-fix; never restore over it or run schema4
code. The old schema3→4 restore remains its separately bounded historical path.
These helpers do not install/load agents or change grants; no author activation
is performed by this PR.

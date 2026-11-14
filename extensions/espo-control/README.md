# Confined synthetic Contact.title capability (source only)

This is a reviewed-source candidate for a narrow EspoCRM custom API action and
OS-operator bootstrap command. It does not install itself, create an API user,
change Roles/mandatory ACL, access existing records, or turn the current GET
identity into a writer. No native CRM integration or effective deployed ACL is
claimed by the synthetic checks.

## Boundary

An ordinary non-admin Role cannot prove the required confinement in the observed
Espo10.0.11 setup. This module instead recognizes a separate random capability
only in three fixed custom routes: GET/POST `OpenTourControlTitle`, and GET
`OpenTourControlTitle/status/<operation>`. No arbitrary entity/ID/field/host is
accepted. The server-owned binding pins one Contact, verifies its exact synthetic
marker, and permits only caller-selected `title` (string, at most100 Unicode
characters, no control characters). CRM's ordinary created/modified metadata is
maintained. Control saves explicitly skip business hooks, using the inspected
supported save option, so custom workflow/notification hooks are not requested.
There is no public create/delete/Stream endpoint.

The route uses Espo's supported `noAuth` custom Action seam and performs its own
constant-time capability check before DB access. Espo runs noAuth actions under
its local system user; **the action's checks, not that system user's broad
rights, are the confinement**. No global authentication method is registered.
The capability is not an Espo API-key/token and cannot establish a normal native
API user. The action rejects normal Espo auth headers even when combined with
the capability. Broader native API rights and existing GET credentials are
unchanged. After installation, independent QA must observe denial of ordinary
Contact/Account/Note/Attachment/EmailAccount/Stream routes using this capability,
not infer it from Role labels or this source-only report.

The app adds another check: existing bearer Auth must identify an application
`administrator` with explicit `crmControlTitle: ["crm:Contact:<pinned-id>"]`.
That application role is **not** a CRM administrator credential. An ordinary
app user, wrong record/entity, missing scope or extra field is denied. Technical
capability possession is service attribution, never a named human identity.
Backend control requests use only `X-OpenTour-Control` with the separate private
writer reference; never X-Api-Key, a password or a browser/URL secret.

## Exact source seam inspected

Implementation targets upstream EspoCRM tag10.0.11, source commit
`32d559ba86d3be607599d1325c359668c1178850`, matching the documented installed
version. Relevant official sources:

- [Custom Actions/routes](https://docs.espocrm.com/development/api-action/)
- [10.0.11 noAuth/system-user dispatch](https://github.com/espocrm/espocrm/blob/32d559ba86d3be607599d1325c359668c1178850/application/Espo/Core/Api/RouteProcessor.php)
- [ORM transaction manager](https://github.com/espocrm/espocrm/blob/32d559ba86d3be607599d1325c359668c1178850/application/Espo/ORM/TransactionManager.php)
- [Repository save/hook options](https://github.com/espocrm/espocrm/blob/32d559ba86d3be607599d1325c359668c1178850/application/Espo/Core/Repositories/Database.php)

The existing internal `UniqueId` entity stores namespaced idempotency receipts
in the **same DB transaction** as title changes or bootstrap creation. No new
CRM or BoardStore schema/table, task queue or API user is introduced. Its null
terminateAt prevents ordinary expiry cleanup; retain these receipts while
requests can be retried. The short native primary ID is accompanied by the full
namespace/operation name; collisions refuse rather than overwrite an unrelated
row. CAS locks the exact Contact row, checks the opaque current field/version,
then stores title and receipt atomically. Same operation/input returns the
original receipt; changed content or stale version is409. A receipt-write failure
rolls back the title. Concurrent same-key inserts rely on the native unique
primary key plus the CRM transaction rollback, not a Python mock guarantee.

The backend looks up the exact operation before a POST. A transport-loss response
leaves the browser's payload/key frozen; explicit retry looks up that receipt
and returns the saved result without another POST. If the lookup itself fails,
there is no POST. A not-yet-visible receipt can still have an in-flight first
request: an explicit same-key retry remains protected by native row lock and
atomic receipt uniqueness. There is no automatic blind second POST. Receipts
return only this control field/version and claimed app actor, not customer data.

## Non-circular reviewed bootstrap/adoption

All steps below require the later authorized local integration owner; none was
run against the live CRM during source work.

1. Review this module and backend/UI together, including independent affected
   Code/PHP boundary review. Test actual Espo routing/ORM behavior first on a
   task-owned disposable instance of the pinned10.0.11 image. Synthetic PHP stubs
   do not prove real SQL locks/atomicity, routing, hooks or token rejection.
2. An authorized OS operator can install only this module directory under the
   existing `custom/Espo/Modules/OpenTourControl` namespace without replacing
   other custom files, and clear/rebuild Espo cache through its supported CLI.
   No admin password/API key or native user/Role change is needed. Directory and
   private file ownership must match the runtime PHP user (normally www-data),
   not an accidental root-owned CLI invocation. No public hosting is needed.
3. Generate a fresh bootstrap nonce and separate capability using a local
   cryptographic generator, each at least32 URL-safe characters. Write
   `data/opentour-control-bootstrap.json` as mode0600 with exactly
   `{nonce,token}`. Do not print/paste/store these live values in Git or chat.
   Keep the same nonce/token on retries. Installation and OS CLI access to the
   existing app/DB are the remaining privileged capability; the app writer does
   not get them.
4. Run `bin/command open-tour-control-bootstrap` as that authorized runtime OS
   user. It takes no caller fields/IDs/options. It creates one visibly fictional
   Contact with fixed synthetic names, empty title and a nonce-derived marker,
   and atomically saves its receipt. It then publishes private binding/hash and
   writer-reference files. A response/file failure after DB commit reuses that
   same bootstrap receipt/Contact on retry. A changed nonce while control files
   already exist refuses before another Contact is created. Failure publishing
   either private file is an incomplete bootstrap; rerun the same input, never
   invent a new ID or repeat with a new nonce. Raw capability is never stdout.
5. Inspect the returned synthetic Contact ID and the exact marker using bounded
   local checks. Copy only the mode0600 writer reference from
   `data/opentour-control-writer.json` into the app's existing private runtime
   area. The upstream binding `data/opentour-control.json` contains only the
   pinned ID, marker and token hash. It is not a generic endpoint config.
6. Enable backend `--crm-control-credential-file <private-writer-reference>` and
   a separate exact app bearer grant extension `crmControlTitle` for that same
   typed Contact. Keep the old GET-only credential unchanged and separately
   supplied for CRM card reads. Only the reviewed local adoption owner changes
   runtime/grants; this source task does not do so. Pinning happens **after**
   the authorized CLI creates the synthetic record, so there is no record-ID/
   writer-creation circular dependency and no persistent app administrator key.
7. Independent integration verifies native denial with this capability alone,
   edit/readback/reload of title, forbidden records/entities/fields/roles, CAS,
   same-key concurrency and committed-response-loss reconciliation. Confirm no
   unrelated business field/record/Stream/account changed. Keep PR23's separate
   conversation/proposal integration and control binding; do not relabel these
   tests as its actual-agent outcome. No send, booking or payment follows.

To revoke, the authorized operator disables/removes the upstream control binding
and app grant/reference, preserving records/receipts for unknown-operation
reconciliation. Missing binding fails closed. Disabling the module/cache route
also removes its surface. Do not delete the control Contact or receipts while an
operation is unknown. Any later cleanup is a separately verified exact-ID/marker
operation on the created synthetic Contact only; no generic delete capability
is supplied to the app. Replacing the capability requires an explicit lifecycle
operation, not rerunning bootstrap with another nonce.

## Validation commands

```sh
python3 -m unittest discover -s tests -p 'test_crm_control.py' -v
python3 tools/crm_control_probe.py
```

CI also runs PHP syntax and the actual extension classes with synthetic Espo
interface/ORM stubs in the digest-pinned Espo image, read-only/no-network/without
CRM/config/credentials. The browser uses only a disposable profile and a
synthetic denied-by-default upstream. These are affected source checks, not
live Espo ACL/ORM integration or deployment acceptance.

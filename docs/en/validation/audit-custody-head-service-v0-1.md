# Audit Custody Append-only Head Service v0.1

**Status: opt-in local custody publisher + read-only TLS service. NOT a deployed independently administered production custodian.** PR #2452 builds a concrete producer/retention side for the previously merged #2451 HTTPS read-only client.

## What is implemented

The new `audit_custody_head_store_v0_1.py` maintains one custodian-owned SQLite database separate from `VERITAS_DATABASE_URL` and its PostgreSQL archive. The only publishing API is an **offline local CLI**, not an HTTP mutation route.

On a publish request, the custodian takes a SQLite `BEGIN IMMEDIATE` writer lock, validates the **pre-approved Ed25519 signer key** and signed full checkpoint via the existing #2450 verifier, re-checks all retained receipts and signatures, and requires **exact sequence +1** and the **exact previous receipt SHA-256**. Conflicting parallel proposals and rewound sequence numbers are rejected, and exact retries are idempotent. SQLite transactions use `synchronous=FULL`, exclusive initial creation and rollback journal. SQL triggers reject ordinary `UPDATE`/`DELETE` against head history and pinned key metadata. The database holds at most 4,096 receipts in v0.1; exceeding this capacity fails closed rather than truncating.

**Not WORM:** a privileged owner can delete/recreate/modify the database, remove its SQL triggers, or restore an old backup. The independent verifier must therefore preserve a **separate minimum accepted head sequence** and signer trust as specified in #2451. Neither a hash chain nor a SQL trigger is sufficient to prevent a privileged whole-store rollback.

The read-only server exposes **only** `GET /v1/audit/checkpoints/latest`, in exactly the v0.1 JSON format already accepted by #2451. It rechecks all stored signatures and the full chain before returning HTTP 200. Empty, corrupt, oversized or unavailable custody history returns HTTP 503. HTTP `POST`, `PUT`, and `DELETE` return 405. The server uses TLS with an operator-provisioned certificate and key; no default self-signed key, privileged write token or publishing endpoint is created at runtime.

## Trust-domain model

```text
Audited / PostgreSQL domain                  Custody domain (different administrator)
--------------------------------            ------------------------------------
Local observer --> checkpoint export ------> Offline reviewing custodian + signed receipt
PostgreSQL history                                   |
  (no custody key / write access)            Publisher CLI (SQLite BEGIN IMMEDIATE CAS)
                                                     |
                                            Custodian-owned SQLite head history
                                                     |
                                            Read-only HTTPS service (GET only)
                                                     |
Independent verifier <--- verified HTTPS TLS cert + pinned public key + minimum sequence
       |
       +---- #2450 signature and #2449 PostgreSQL inventory comparison
```

The **production separation is a deployment requirement, not a fact proven by this PR**. For meaningful protection, install publisher and retention on another host/account with different administrative privileges, independently provisioned signing and TLS keys, protected backup/retention policies, and a verifier-controlled minimum head. A malicious root on the *single CI host* can impersonate all its Unix users.

### Offline owner commands

Preprovision a secure custody directory owned by the publisher, not by the audited DB administrator. Supply an independently authenticated raw Ed25519 public key in lowercase hex:

```sh
python -m scripts.validation.audit_custody_head_store_cli_v0_1 init \
  --db /custody-owned/store/head.sqlite \
  --signer-public-key-hex YOUR_VERIFIED_64_HEX_SIGNER_PUBLIC_KEY
```

After offline review of a checkpoint and its #2450 signed receipt:

```sh
python -m scripts.validation.audit_custody_head_store_cli_v0_1 publish \
  --db /custody-owned/store/head.sqlite \
  --reference /reviewed/reference.json \
  --receipt /reviewed/signed-receipt.json
```

The publisher creates no signing keys, never signs on behalf of an agent, and does not query PostgreSQL. Receipt issuance is performed separately by the independently managed signing process. The newest history head can be inspected:

```sh
python -m scripts.validation.audit_custody_head_store_cli_v0_1 head \
  --db /custody-owned/store/head.sqlite
```

### Read-only custodian HTTPS role

Use a **different unprivileged OS user** with read/traverse permissions on the SQLite store, but no write access and no signing keys. Provide separate TLS certificate and key files available only to the HTTP service account.

```sh
python -m scripts.validation.audit_custody_head_store_cli_v0_1 serve \
  --db /custody-owned/store/head.sqlite \
  --certificate /https-owned/tls.pem \
  --private-key /https-owned/tls.key \
  --listen-host 127.0.0.1 --port 8443
```

The listener binds to loopback by default. No production exposure, deployment automation, firewalls, reverse proxy, TLS renewal, rate limit or HA mechanism is supplied. Operators must provide those independently. Never run the publisher or server under the audited PostgreSQL administrator account.

The existing #2451 verifier authenticates the HTTPS endpoint through an independently provisioned CA bundle and exact hostname, compares against a separate pinned signer public key and minimum head sequence, validates #2450 signature and receipt binding, then compares with the currently observed #2449 PostgreSQL registry. A response from the service itself does **not** authorize an action or authenticate an audit packet's original source.

## Real tests vs unproven operations

The dedicated CI exercises:
- Two PostgreSQL local archive packets, independently stored signed custody head, actual TLS validation, privileged PostgreSQL row deletion and `HISTORY_DIVERGED` result.
- Concurrent CAS to exactly one new SQLite head; exact retries; conflicting forks; invalid signers, changed content, and restart-equivalent fresh connections.
- SQLite write-blocking triggers, deliberately simulated privileged modifications, and fail-closed history verification.
- Separate **three Linux identities on one GitHub Actions runner**: custody publisher, read-only HTTPS account, and audited-DB-admin identity. File permission checks deny the DB admin access to custody storage and deny the HTTP identity custody writes. The real local TLS listener responds to GET but refuses POST.
- #2451, #2450, and #2449 tests remain green. The service has **no runtime Bind/effect integration** and no real provider call.

**Remaining assurance gaps:** actual distinct host/administrator control, externally verifiable monotonic head or WORM storage, power-loss/physical storage crash recovery, historical receipt backfill, robust independent minimum-sequence persistence, signer/TLS key rotation and revocation, independent trusted time, production traffic testing, independent third-party certification, remote backup policy, and authenticated provenance of audit source packets. A custodian who controls both service and verifier's external pins can still substitute a coherent history. The system does not establish that every expected audit event is present.

## Merge gate

Keep Draft until *final HEAD* dedicated real PostgreSQL + HTTPS + OS-account rehearsal, full CI, Security Gates and CodeQL pass. The single-host rehearsal must **not** be described as cross-organization custody or production-WORM evidence.

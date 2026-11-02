# Independent cross-host custody rehearsal v0.1 (NOT yet executed)

## Objective and claims

This is a **two-host operator-run evidence protocol**, not a claim that a real two-host run has occurred. Host A holds the audited PostgreSQL registry; Host B is a separately administered custody publisher + read-only HTTPS server from PR #2452. A verifier on A holds an independently authenticated CA certificate, expected DNS hostname, pinned Ed25519 public key, and a minimum acceptable head sequence. The verifier does not fetch these pins from the audited DB, custody response, or receipt.

**Do not use the same root/VM snapshot or a shared administrator** for A and B when asserting administrative independence. Never send signing private keys to A or put them in GitHub Actions artifacts.

## Before execution: record evidence

Record the two hosts' machine IDs (redacted/pseudonymous), OS/kernel, distinct owner/UID and administrative group boundaries, separate credential custody, repo commit, TLS cert fingerprint, CA origin, signer key fingerprint, verifier-controlled minimum sequence, network topology, and time of observation. Independently validate that A's admin cannot SSH into B, read B's custody DB, edit its TLS key or issue a signed receipt. A local VM or single CI runner does not meet this standard.

## Phase 1: independent custodian bootstrap (Host B)

1. Provision a separately owned directory with owner-only write access and a separate read-only service account. Provision trusted signing public key and TLS server certificate/key *out of band*. Sign checkpoint receipts offline; do not enable a public mutation endpoint.
2. Run `python -m scripts.validation.audit_custody_head_store_cli_v0_1 init --db /custody-owned/store/head.sqlite --signer-public-key-hex <independently-verified-public-key>`.
3. Review the exported checkpoint and signed receipt against approved scope; then `python -m scripts.validation.audit_custody_head_store_cli_v0_1 publish --db /custody-owned/store/head.sqlite --reference /reviewed/reference.json --receipt /reviewed/signed-receipt.json`.
4. Under a different read-only account, run `python -m scripts.validation.audit_custody_head_store_cli_v0_1 serve --db /custody-owned/store/head.sqlite --certificate /https-owned/tls.pem --private-key /https-owned/tls.key --listen-host <restricted-B-interface> --port 8443`. Restrict ingress to the verifier. This server does not implement HTTP writes.

## Phase 2: independent verification (Host A)

Provision CA, signer public key, and minimum sequence outside PostgreSQL. Set `VERITAS_DATABASE_URL` to A's audited PostgreSQL registry. Then run:

```sh
python -m scripts.validation.audit_cross_host_rehearsal_v0_1 \
  --reference /verified-input/reference.json \
  --receipt /verified-input/signed-receipt.json \
  --endpoint https://custody.example.test:8443/v1/audit/checkpoints/latest \
  --expected-hostname custody.example.test \
  --ca-bundle /verifier-owned/ca.pem \
  --trusted-signer-public-key-hex <64-hex-key> \
  --minimum-sequence <independently-recorded-floor>
```

The example hostname is a placeholder, not a deployed endpoint. Expected clean result: `{"verdict":"HISTORY_UNCHANGED_UNAUTHENTICATED","verified":true}`. This is a local audit-history continuity observation only; it does **not** authenticate original source events or approve execution.

## Phase 3: attacks and recovery

Use synthetic non-production packets and isolated databases. Run each test with the same independently held pins and record both raw outputs and exit status.

| Attack / event | Expected fail-closed evidence |
| --- | --- |
| A PostgreSQL admin deletes an archived packet or reverts the registry to a prior snapshot | `HISTORY_DIVERGED` or another non-success verdict |
| A admin substitutes signed receipt or public key | `CUSTODY_HEAD_MISMATCH` or `SIGNER_PIN_MISMATCH` |
| B server presents a different CA/hostname | `REMOTE_ANCHOR_UNAVAILABLE` / `REMOTE_ENDPOINT_INVALID` |
| B server returns an older signed head below verifier's floor | `REMOTE_HEAD_SEQUENCE_ROLLBACK` |
| B server unavailable | `REMOTE_ANCHOR_UNAVAILABLE`, exit code 2 |
| B publisher/service restarts, no new receipt | Same pinned head and successful clean verification |
| B custody owner replaces its entire database with a prior valid state | Reject only if verifier independently retains a higher floor; otherwise this remains a known limitation |
| A admin attempts to mutate B's custody database or TLS/signing key | OS/network access denied, independently evidenced |

Never claim successful rollback detection if the signed baseline is from the restored epoch or the verifier's independent floor is lost. Stop and report any unexpected PASS, network fallback, secret exposure, or cross-admin access.

## Evidence manifest and stop gate

For each test, retain sanitized: test ID, command/arguments with secrets removed, repo SHA, host roles, pre/post minimum sequence, expected/actual verdict, exit code, TLS peer certificate fingerprint, receipt SHA-256, signed reference SHA-256, DB registry snapshot digest, and separately signed custody operator acknowledgement. Do not publish real IPs, private keys, DB credentials, or personal data.

**GO:** two genuinely separate administrative domains, clean success, all expected fail-closed attacks, independently held floor, reproducible evidence and independent reviewer.

**NO-GO:** any unverified admin separation, unpinned trust root, missing proof of rollback rejection, unexplained results, or failed CI.

The repository CI tests only local verifier input validation and existing #2451/#2452 synthetic rehearsals. The real cross-host experiment requires user-provisioned Host B and operator participation and cannot be claimed from GitHub Actions.

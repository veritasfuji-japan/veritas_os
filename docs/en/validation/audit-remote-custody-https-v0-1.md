# Audit Remote Custody HTTPS v0.1 — external latest-head lookup

**Status: opt-in read-only transport integration.** This change builds on the merged #2449 local registry checkpoint and #2450 Ed25519 signed custody receipt. It does **not** deploy a remotely administered custody service, manage production signing keys, establish globally complete audit coverage or grant execution authority.

## Trust boundary

A verifier should retrieve the *latest expected custody head* from a service whose administration and persistent storage are separated from the PostgreSQL audit database owner. This module accepts a single, operator-configured HTTPS URL:

`https://custody.example.org/v1/audit/checkpoints/latest`

The response must be UTF-8 JSON, `application/json`, at most 2,048 bytes, with exactly these fields:

```json
{
  "format_version": "veritas.audit-custody-remote-head/0.1",
  "scope": "LOCAL_AUDIT_OBSERVATION_ONLY",
  "signer_public_key_hex": "<64 lowercase hex digits>",
  "latest_receipt_sha256": "<64 lowercase hex digits>",
  "sequence": 1
}
```

A publisher must place this record in a **separate trust domain** under authenticated, monotonic head-update control. The repository does not implement that publisher or its durable backing store. The JSON fields are a transport record, **not a proof that the external operator is honest or that the server cannot roll back**.

The verifier independently supplies:

- A trusted CA certificate bundle that authenticates the **expected hostname**; never fetch this bundle from the audited database or receipt.
- The exact expected server hostname; the URL must be HTTPS with no username, password, query, fragment or unexpected path.
- The **trusted Ed25519 signer public key** previously approved out of band. A key supplied by the remote service cannot silently replace it.
- A **minimum acceptable head sequence** previously retained by the verifier outside the monitored database. This detects remote rollback *below that independently retained floor*, not rollback to another acceptable sequence.

The network client uses Python `http.client.HTTPSConnection` with TLS certificate and hostname verification. It does not use environment proxies or follow redirects. It rejects non-200 responses, wrong content type, compression, duplicate JSON keys, nonfinite values, oversized payloads and unknown trust fields. Network errors, invalid pins, stale sequence and malformed data never fall back to local or embedded values.

After remote validation, the existing signed custody validator checks the signature, checkpoint binding, latest receipt digest and current PostgreSQL history. All successful history statuses remain suffixed with `_UNAUTHENTICATED` because source packet metadata is self-declared.

## Operator CLI

```sh
python -m scripts.validation.audit_remote_custody_https_cli_v0_1 \
  --reference ./audited-registry-checkpoint.json \
  --receipt ./signed-custody-receipt.json \
  --anchor-endpoint https://custody.example.org/v1/audit/checkpoints/latest \
  --expected-hostname custody.example.org \
  --ca-bundle /independently-provisioned/trust/custody-ca.pem \
  --trusted-signer-public-key-hex YOUR_INDEPENDENTLY_PINNED_64_HEX_PUBLIC_KEY \
  --minimum-sequence 1
```

Only `HISTORY_UNCHANGED_UNAUTHENTICATED` and `HISTORY_EXTENDED_UNAUTHENTICATED` cause exit code 0. All other outcomes exit 2. This command does not modify a remote endpoint, database, policy or authorization state.

## Bounded, fail-closed statuses

| Status | Meaning |
| --- | --- |
| `REMOTE_ENDPOINT_INVALID` | URL, expected hostname, CA input type or timeout violates the operator-only contract |
| `EXTERNAL_TRUST_REQUIRED` | Independently pinned signer public key or minimum sequence is absent/invalid |
| `REMOTE_ANCHOR_UNAVAILABLE` | TLS, DNS, network, timeout, HTTP status or transport failed |
| `REMOTE_ANCHOR_INVALID` | Remote JSON content is malformed or violates the strict record contract |
| `REMOTE_SIGNER_PIN_MISMATCH` | Transport-provided public key differs from independently trusted key |
| `REMOTE_HEAD_SEQUENCE_ROLLBACK` | Latest remote sequence is below independently retained minimum |
| `REMOTE_RECEIPT_SEQUENCE_MISMATCH` | Local signed receipt and independently hosted head report different sequence |
| `CUSTODY_HEAD_MISMATCH` | Receipt hash differs from latest externally delivered head |
| `SIGNATURE_INVALID` | Existing Ed25519 verification rejects the signed receipt |
| `HISTORY_DIVERGED` / `INCOMPLETE` | Existing retrospective PostgreSQL comparison reports missing/changed or invalid local history |
| `REGISTRY_UNAVAILABLE` | Audited PostgreSQL cannot be read consistently |

## Scope and assurance

This PR adds a **client for an external custodian**, not a custody server or a production deployment. Its CI creates a synthetic TLS server on loopback using an ephemeral test CA and a real PostgreSQL 16 container; that proves TLS hostname/CA rejection and the check pipeline, **not independent hosts or owners**.

There is no ability for an attacker who controls only the audited database to choose the trusted CA, signer key, expected hostname or sequence floor *under the assumed split-control deployment*. This assumption is **not proven solely by this repository**, and root access to the test runner defeats the local separation.

Still pending: a separately administered real host/account, authenticated and monotonic head publishing, secure key custody, independent minimum-sequence persistence, key rotation/revocation, failure drills across hosts, real backup restore, third-party audit, trusted time, WORM or legal evidence retention, packet provenance authentication and comprehensive expected-input enumeration. A malicious external custodian (or compromise of its TLS/private keys), or a restored head that remains above the verifier's independently held floor, can still defeat the intended retrospective check.

## Merge gate

Keep Draft until final-HEAD TLS + PostgreSQL tests, existing signed-custody regression, CodeQL, Security Gates and full CI succeed. Do not report real independent remote custody until an out-of-repository test uses different physical/organizational trust domains.

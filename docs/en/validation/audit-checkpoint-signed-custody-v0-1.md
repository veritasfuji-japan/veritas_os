# Audit Checkpoint Signed Custody v0.1 — signed local evidence, externally pinned head

**Status:** opt-in, offline Ed25519 receipt for the already bounded and locally self-checked #2449 audit registry checkpoint. This is a *retrospective integrity mechanism*, **not** execution authorization, independently authenticated origin, WORM custody or universal history completeness.

## Why both a public-key pin and latest-head pin?

The #2449 comparison accepts a local reference whose full SHA-256 is saved outside the PostgreSQL database. That detects a later missing or altered archived packet relative to the pinned baseline, but has no cryptographic identity for whoever registered the baseline.

The new receipt binds **the full checkpoint SHA-256 and snapshot root** to an Ed25519 signature. The verifier refuses to check live PostgreSQL until the signed receipt validates using **both**:

1. The expected 32-byte **trusted public key** (hex, previously acquired through an independently verified channel), never copied from or trusted based on the receipt.
2. The full **expected latest receipt digest**, independently recorded by the relying operator. This is a critical rollback pin: a *valid old receipt* must not replace the latest expected receipt.

The receipt includes a numbered sequence and signed preceding receipt hash. **v0.1 does not verify complete sequence continuity, maintain an atomic distributed head, lock a real remote store, or authenticate an approval to advance the head**. The head pin is the actual rollback safeguard. An operator must advance it via an independently authenticated process that cannot be changed by the DB administrator.

## Explicit separation

The **observer** captures and exports the local DB checkpoint; the **custodian** holds the signing key and signs a reviewed, supplied JSON checkpoint without any need to connect to PostgreSQL; the **relying verifier** checks the externally pinned key/head and then queries current PostgreSQL. In the controlled CI these are isolated OS accounts on the *same runner*, which proves a basic Unix file-permission boundary only. The workflow is **not** evidence of remote service independence, HSM custody, real organizational segregation or a malicious-root threat model.

The signing process rejects symlink keys, non-regular key files, wrong ownership, group/other-readable keys and any key other than 32 raw bytes. The signing key is **not created or copied by the application**. Privileged operators must provision it securely and keep it out of source control, database backups, audit packet directories and app runtime environments.

## Example manual sequence (trusted operator environment)

First capture the existing bounded snapshot and move a *reviewed copy* into an independently controlled custody environment:

```sh
python -m scripts.validation.audit_registry_checkpoint_cli_v0_1 capture \
  --output ./audit-registry-baseline.json
```

Provision a unique Ed25519 private key as **32 raw bytes** in a file owned only by the custody signer (mode 0600). Provision its corresponding 32-byte public key through a verified trust channel, **not through the receipt or the reference JSON**. This PR deliberately does not automatically generate or provision key material.

In a separately controlled signing session (with no database access), run:

```sh
python -m scripts.validation.audit_checkpoint_signed_custody_cli_v0_1 attest \
  --reference ./audit-registry-baseline.json \
  --private-key /separately-provisioned-custody/signing-key.raw \
  --output ./signed-custody-receipt.json \
  --sequence 1 \
  --previous-receipt-sha256 0000000000000000000000000000000000000000000000000000000000000000
```

The signer writes the output exclusively and will **not overwrite** an existing receipt. It prints a receipt-head SHA-256: the relying operator must register and protect that exact head digest in an *independently controlled* authority. Incrementing a sequence is an operator claim in v0.1; do not claim proven chain continuity.

After an outage or suspected restore, the relying verifier supplies the trusted public-key hex and independently approved latest head digest:

```sh
python -m scripts.validation.audit_checkpoint_signed_custody_cli_v0_1 verify \
  --reference ./audit-registry-baseline.json \
  --receipt ./signed-custody-receipt.json \
  --trusted-public-key-hex YOUR_PINNED_RAW_ED25519_PUBLIC_KEY_HEX \
  --expected-head-sha256 YOUR_INDEPENDENT_LATEST_RECEIPT_SHA256
```

The CLI returns 0 only for `HISTORY_UNCHANGED_UNAUTHENTICATED` and `HISTORY_EXTENDED_UNAUTHENTICATED`. Every trust failure, data divergence, unavailable DB, malformed file or corruption returns nonzero.

## Statuses

| Status | Meaning |
| --- | --- |
| `EXTERNAL_PINS_REQUIRED` | No valid externally supplied public key and/or receipt-head digest |
| `RECEIPT_INVALID` | Malformed receipt, invalid sequence/fields or its self-digest mismatch |
| `CUSTODY_HEAD_MISMATCH` | Receipt is not the independently pinned latest receipt (including a valid old signature) |
| `SIGNER_PIN_MISMATCH` | Receipt signer fingerprint differs from the independently supplied public key |
| `SIGNATURE_INVALID` | Ed25519 verification failed for the domain-separated signed statement |
| `REFERENCE_INVALID` | Checkpoint does not satisfy the existing #2449 local contract |
| `SIGNED_BASELINE_MISMATCH` | Signed full checkpoint digest or root differs from supplied JSON |
| `SIGNED_LOCAL_BASELINE_VERIFIED` | Offline signature, key and latest-head digest match; **not an external origin guarantee** |
| `HISTORY_DIVERGED` | A pinned packet has disappeared or differs in the currently observed database |
| `INCOMPLETE` | Current registry contains corrupt, orphaned or over-limit local observations |
| `REGISTRY_UNAVAILABLE` | Storage state indeterminate; no clean-history claim |

Unchanged and extended statuses retain the #2449 `_UNAUTHENTICATED` suffix. Signing local evidence does not retroactively authenticate its self-declared packet origins.

## Validation and remaining limitations

- Pure negative tests: tampered statement with recomputed self-hash, forged signature, substituted trusted key, missing/incorrect external pins, old valid signed receipt replacing newer expected head, invalid predecessor, false trust scope, symlink or world-readable private key, and exclusive-output non-overwrite.
- Dedicated PostgreSQL CI: new locally observed packets, pool close/reopen, signed head advancement, simulated privileged row deletion and in-place JSON corruption, independent head comparison, and prior #2449/#2448 regressions.
- Single-runner rehearsal checks that a second Linux identity cannot read the custodian private key and that a complete CLI flow works. Root and CI orchestration control both identities: **not an independent remote custody or adversarial-root proof**.
- No new migrations. No changes to live Bind Authorization, single-use consumption, policy, provider adapter, runtime trust root, or real external effects.
- No automatic external publication, HSM, timestamp service, key rotation, certificate revocation, external audit-log transport, recovery time objective, retention SLA, full chain proof or guarantee of global archive coverage.
- **Commit and WORM trust boundary:** a separately held latest head is necessary; a public key plus a locally mutable receipt alone cannot prevent rollback. If both independent pins can be changed by the DB administrator, this verification loses its trust basis.

## Merge gate

Keep Draft until final-head dedicated real PostgreSQL / cross-identity checks, broad CI, CodeQL and Security Gates pass, and the independent public-key + latest-head responsibilities are explicitly reviewed. No claim of production-grade independent custody should be made from a single-runner rehearsal.

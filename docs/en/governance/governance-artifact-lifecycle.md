# Governance Artifact Lifecycle

## Overview

VERITAS OS treats governance artifacts as **signed, verifiable control-plane
assets** rather than optional configuration.  Every governance change is
attributed, digested, and recorded so that operators, auditors, and replay
surfaces can always determine which governance was in force for any given
decision.

## Lifecycle Stages

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Author     │────▶│   Approve    │────▶│    Sign      │
│   (propose)  │     │   (4-eyes)   │     │  (Ed25519)   │
└──────────────┘     └──────────────┘     └──────────────┘
                                                │
       ┌────────────────────────────────────────┘
       ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Verify     │────▶│   Activate   │────▶│  Thread into │
│  (posture)   │     │  (hot-reload)│     │  decisions   │
└──────────────┘     └──────────────┘     └──────────────┘
                                                │
       ┌────────────────────────────────────────┘
       ▼
┌──────────────┐     ┌──────────────┐
│   Audit      │────▶│  Rollback    │
│  (history)   │     │  (governed)  │
└──────────────┘     └──────────────┘
```

### 1. Author (Propose)

A governance policy change is proposed via `PUT /v1/governance/policy`.
The proposer identity is captured in the `updated_by` field and recorded
in the audit history as `proposer`.

### 2. Approve (4-Eyes)

By default, governance updates require two distinct approvals (4-eyes
principle).  Each approval includes a `reviewer` identity and `signature`.
Approver identities are recorded in the audit trail.

### 3. Sign (Ed25519)

Policy bundles are signed with Ed25519 during compilation:

```bash
python -m veritas_os.scripts.compile_policy \
  policies/my_policy.yaml \
  --output-dir artifacts/ \
  --signing-key keys/policy_signing.pem
```

The signature covers the canonical `manifest.json` and provides
cryptographic authenticity verification.

### 4. Verify (Posture-Aware)

Verification behavior depends on the runtime posture:

| Posture     | Ed25519 Signed | SHA-256 Only | Missing Signature |
|-------------|----------------|--------------|-------------------|
| **dev**     | ✅ Accept      | ⚠️ Accept    | ⚠️ Accept         |
| **staging** | ✅ Accept      | ⚠️ Accept    | ⚠️ Accept         |
| **secure**  | ✅ Accept      | ❌ Reject    | ❌ Reject         |
| **prod**    | ✅ Accept      | ❌ Reject    | ❌ Reject         |

In secure/prod posture, only Ed25519-signed bundles are accepted.  SHA-256
integrity-only bundles are rejected because they do not provide authenticity
verification.

### 5. Activate (Hot-Reload)

After verification, the governance policy is activated.  Registered
callbacks (e.g., FUJI hot-reload) are notified so that enforcement
components pick up the new policy without process restart.

### 6. Thread into Decisions

Every decision includes a `governance_identity` field:

```json
{
  "governance_identity": {
    "policy_version": "governance_v1",
    "digest": "a3f5c7...sha256hex",
    "signature_verified": true,
    "signer_id": "key-fingerprint-abc",
    "verified_at": "2026-04-10T08:00:00Z"
  }
}
```

This allows audit and replay surfaces to determine exactly which
governance artifact was in force for any decision.

### 7. Audit (History)

Every governance change is appended to `governance_history.jsonl` with:

- `changed_at` — ISO-8601 timestamp
- `proposer` — who proposed the change
- `approvers` — list of approver identities
- `previous_digest` — SHA-256 of previous governance policy
- `new_digest` — SHA-256 of new governance policy
- `event_type` — `update` or `rollback`
- Full previous and new policy snapshots

### 8. Rollback (Governed)

Rollback is a governed operation with the same requirements as updates:

- 4-eyes approval required (unless disabled in dev)
- Recorded as `event_type: "rollback"` in audit history
- Full provenance tracking (proposer, approvers, digests)
- Attributable and auditable

## Key Management

### Generating Keys

```bash
python -c "
from veritas_os.policy.signing import generate_keypair
priv, pub = generate_keypair()
open('policy_signing.pem', 'wb').write(priv)
open('policy_verify.pem', 'wb').write(pub)
print('Keys generated: policy_signing.pem (KEEP SECRET), policy_verify.pem')
"
```

### Environment Variables

| Variable                         | Description                              |
|----------------------------------|------------------------------------------|
| `VERITAS_POLICY_VERIFY_KEY`      | Path to Ed25519 public key PEM           |
| `VERITAS_POLICY_REQUIRE_ED25519` | When `true`, reject SHA-256 fallback     |
| `VERITAS_POLICY_RUNTIME_ENFORCE` | Enable compiled policy enforcement       |
| `VERITAS_POSTURE`                | Runtime posture (`dev`/`staging`/`secure`/`prod`) |

### Key Rotation

1. Generate a new Ed25519 key pair
2. Re-compile all policy bundles with the new signing key
3. Deploy the new public key via `VERITAS_POLICY_VERIFY_KEY`
4. Verify bundles load correctly in staging
5. Promote to production

### Failure Handling

- **Missing public key in prod**: Startup validation warns; bundle loading
  falls back to SHA-256 but will be rejected in strict posture
- **Invalid signature**: Bundle loading fails with `ValueError`
- **Corrupt manifest**: Bundle loading fails with `ValueError`
- **Missing manifest.sig**:
  - `dev` / `staging`: warning + accept (migration compatibility)
  - `secure` / `prod`: reject (fail-closed)

## Migration Notes

### From Unsigned to Signed Governance

1. **No breaking changes in dev/staging**: Unsigned artifacts continue to
   work.  Warnings are logged to encourage migration.

2. **Secure/prod requires Ed25519**: Before promoting to secure or prod
   posture, ensure all policy bundles are Ed25519-signed.

3. **Governance history is backward-compatible**: New `proposer`,
   `approvers`, `previous_digest`, `new_digest`, and `event_type` fields
   are additive.  Existing history records without these fields continue
   to be readable.

4. **DecideResponse `governance_identity` is additive**: The new field
   defaults to `null` when not populated.  Existing API consumers are
   unaffected.

---

## ガバナンスアーティファクトのライフサイクル（日本語）

VERITAS OS はガバナンスアーティファクトを**署名付きで検証可能な制御プレーン資産**
として扱い、オプション設定ではなく必須の管理対象とします。

### ポスチャによる検証の違い

| ポスチャ     | Ed25519署名 | SHA-256のみ | 署名なし |
|-------------|-------------|-------------|---------|
| **dev**     | ✅ 許可     | ⚠️ 許可     | ⚠️ 許可  |
| **staging** | ✅ 許可     | ⚠️ 許可     | ⚠️ 許可  |
| **secure**  | ✅ 許可     | ❌ 拒否     | ❌ 拒否  |
| **prod**    | ✅ 許可     | ❌ 拒否     | ❌ 拒否  |

### 決定アーティファクトへのスレッディング

すべての決定に `governance_identity` フィールドが含まれ、どのガバナンスポリシーが
有効だったかを追跡可能です。

### ロールバック

ロールバックは通常の更新と同じ承認フローが適用されます（4-eyes承認）。
監査履歴には `event_type: "rollback"` として記録されます。

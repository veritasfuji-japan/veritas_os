# Governance Artifact Signing Operations

## Scope

This runbook defines operator actions for governance artifact signature
verification, key rotation, and failure handling across runtime posture levels.

## Posture-specific behavior

- `dev` / `staging`
  - Ed25519 signatures are verified when available.
  - SHA-256-only and missing-signature bundles are accepted with warnings.
- `secure` / `prod`
  - Only Ed25519-signed governance bundles are accepted.
  - Missing signatures, invalid signatures, and SHA-256-only artifacts are rejected.

## Signer verification

1. Set `VERITAS_POLICY_VERIFY_KEY` to the current Ed25519 public key PEM path.
2. Compile policy bundles with signing metadata (`signing.algorithm=ed25519`).
3. Confirm `/v1/decide` output includes `governance_identity.signature_verified=true`.
4. Confirm `governance_identity.signer_id` is populated when `manifest.signing.key_id`
   is present.

## Key rotation procedure

1. Generate a new Ed25519 key pair.
2. Re-sign bundles using the new private key.
3. Deploy the new public key through `VERITAS_POLICY_VERIFY_KEY`.
4. Verify staged rollout in `staging` posture.
5. Promote to `secure`/`prod` only after successful verification.

## Failure handling

### Invalid signature

- Runtime behavior: bundle load fails.
- Operator response:
  1. Stop rollout.
  2. Rebuild bundle from trusted source.
  3. Re-sign and re-verify.

### Missing signature

- Runtime behavior:
  - `dev` / `staging`: warning and accept.
  - `secure` / `prod`: fail-closed rejection.
- Operator response:
  1. Treat as release blocker for `secure`/`prod`.
  2. Sign bundle and redeploy.

### Missing verification key

- Runtime behavior:
  - Ed25519 authenticity cannot be verified without `VERITAS_POLICY_VERIFY_KEY`.
  - In strict posture this should be treated as a misconfiguration and fixed before
    promotion.
- Operator response:
  1. Restore public key path and file permissions.
  2. Re-run bundle verification checks.

## Migration note for legacy unsigned flows

- Legacy SHA-256/missing-signature bundles may continue in `dev`/`staging` for migration.
- Before `secure`/`prod` promotion, all governance bundles must be Ed25519 signed.

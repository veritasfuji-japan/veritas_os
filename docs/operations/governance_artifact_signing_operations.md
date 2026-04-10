# Governance Artifact Signing Operations

## Scope

This runbook defines operator actions for governance artifact signature
verification, key rotation, and failure handling across runtime posture levels.

## Posture-specific behavior

- `dev` / `staging`
  - Ed25519 signatures are verified when available.
  - SHA-256-only and missing-signature bundles are accepted with warnings.
- TrustLog signer backend:
  - `file` signer is allowed for local workflows only.
  - `aws_kms` signer is recommended for pre-production parity testing.
- `secure` / `prod`
  - Only Ed25519-signed governance bundles are accepted.
  - Missing signatures, invalid signatures, and SHA-256-only artifacts are rejected.
  - TrustLog signer backend must be `aws_kms` with an AWS KMS Ed25519 key.
  - `file` signer startup is refused unless break-glass override is explicitly set.

## TrustLog signer hardening policy

### Why file signer is dev-only

- The file signer stores private key material on the application host.
- Even with restrictive filesystem permissions, host-level compromise, backup
  exposure, or misconfiguration can leak key material.
- Leaked signing keys allow forged TrustLog entries, weakening non-repudiation
  and reducing external audit credibility.

### Required secure/prod configuration (AWS KMS Ed25519)

Set:

1. `VERITAS_TRUSTLOG_SIGNER_BACKEND=aws_kms`
2. `VERITAS_TRUSTLOG_KMS_KEY_ID=<kms-key-id-or-arn>`

Operational notes:

- Use an asymmetric AWS KMS key with Ed25519 signing support (`EDDSA`).
- Scope IAM permissions to the specific key and required KMS actions only.
- Validate startup logs show the KMS signer backend and key id metadata.

### Emergency break-glass (unsupported)

- Env: `VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD=1`
- Effect: allows startup to continue with `file` signer in `secure`/`prod`.
- Security warning: this mode is unsupported for enterprise deployments and
  should be used only for short-lived emergency recovery.
- Exit criteria: remove override, restore `aws_kms` signer, and document
  incident timeline in governance/audit records.

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

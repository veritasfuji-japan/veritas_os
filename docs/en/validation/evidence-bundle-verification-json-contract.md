# Evidence Bundle Verification JSON Contract

This page documents the reviewer-facing JSON result contract emitted by:

```bash
veritas-evidence-bundle verify \
  --bundle-dir <bundle_dir> \
  --public-key <trusted_ed25519_public_key> \
  --require-signature \
  --json
```

This JSON contract supports reviewer-facing verification and UI integration. It
is not regulatory certification. It is not completed third-party audit approval.
Trusted public keys must come from an out-of-band reviewer/operator trust
channel; a public key copied only from the Evidence Bundle is not trusted by
itself.

## Contract scope

The contract separates two reviewer decisions that external UI and audit tooling
must not collapse:

1. **File/hash integrity**: whether hash-covered files match `manifest.json`.
2. **Manifest authenticity**: whether the manifest signature verifies under the
   trusted Ed25519 public key supplied by the reviewer/operator trust channel.

Strict reviewer verification requires both checks to pass in the same
`--require-signature` run. `hash_integrity_ok: true` alone is not an
authenticity decision.

## Stable top-level fields

| Field | Type | Reviewer-facing meaning |
|---|---|---|
| `ok` | boolean | Overall CLI verification result. In strict mode, `true` requires file/hash integrity to pass and required signature verification to pass under the supplied trusted public key. |
| `tampered` | boolean | `true` means the verifier detected a condition that invalidates the bundle verification result, such as a hash mismatch, missing required content, manifest hash failure, required signature failure, or missing required signature. Use `hash_integrity_ok` and `authenticity_ok` to distinguish integrity from authenticity. |
| `hash_integrity_ok` | boolean | `true` means all hash-covered files match the hashes recorded in `manifest.json` and the manifest hash check did not fail. It does not prove who authored or signed the manifest. |
| `signature_status` | string | Reviewer-facing manifest signature state. Expected values are `pass`, `fail`, `missing`, and `not_verified`. |
| `signature_verified` | boolean | `true` means the manifest signature cryptographically verified under the trusted Ed25519 public key supplied to `--public-key`. |
| `authenticity_ok` | boolean | `true` means reviewer-facing manifest authenticity was established by signature verification under the trusted public key. `false` means reviewer-facing authenticity was not established. |
| `authenticity_failure` | string or null | Machine-readable authenticity failure reason. `null` is expected only when `authenticity_ok` is `true`. Current failure values include `signature_not_verified`, `signature_verification_failed`, `signature_verification_error`, and `signature_missing`. |
| `errors` | array of strings | Blocking diagnostics. If this array is non-empty, `ok` is `false`. UI consumers may display these as rejection/blocker reasons. |
| `warnings` | array of strings | Non-blocking diagnostics for the current posture/mode. Warnings can still require reviewer attention, but they do not by themselves make `ok` false. |

Additional diagnostic fields, such as `manifest` and `file_hash_results`, may be
present for reviewer inspection. Consumers should depend on the stable fields
above for summary decisions.

## Strict success JSON

Conditions:

- correct trusted Ed25519 public key supplied with `--public-key`
- `--require-signature` enabled
- hash-covered files match `manifest.json`
- manifest signature verifies under the trusted public key

Illustrative JSON shape:

```json
{
  "ok": true,
  "tampered": false,
  "hash_integrity_ok": true,
  "signature_status": "pass",
  "signature_verified": true,
  "authenticity_ok": true,
  "authenticity_failure": null,
  "errors": [],
  "warnings": []
}
```

Reviewer/UI interpretation: the bundle passed strict reviewer-facing
verification for file/hash integrity and manifest authenticity. This is still
not regulatory certification or completed third-party audit approval.

## Failure JSON shapes

### Missing public key with `--require-signature`

Conditions:

- `--require-signature` enabled
- no trusted public key supplied to `--public-key`
- manifest signature may be present, but cannot be verified

Illustrative JSON shape:

```json
{
  "ok": false,
  "tampered": true,
  "hash_integrity_ok": true,
  "signature_status": "not_verified",
  "signature_verified": false,
  "authenticity_ok": false,
  "authenticity_failure": "signature_not_verified",
  "errors": [
    "Manifest signature present but no signature verifier was provided; manifest authenticity was not verified",
    "No trusted public key supplied; manifest signature authenticity cannot be verified"
  ],
  "warnings": []
}
```

Reviewer/UI interpretation: file/hash integrity may pass, but authenticity was
not established. Do not accept this as strict reviewer-facing verification.

### Wrong public key

Conditions:

- trusted-key input does not correspond to the signing key for the manifest
- `--require-signature` enabled

Illustrative JSON shape:

```json
{
  "ok": false,
  "tampered": true,
  "hash_integrity_ok": true,
  "signature_status": "fail",
  "signature_verified": false,
  "authenticity_ok": false,
  "authenticity_failure": "signature_verification_failed",
  "errors": [
    "Manifest signature verification failed"
  ],
  "warnings": []
}
```

Reviewer/UI interpretation: the hash-covered files can still match the manifest,
but the supplied public key did not verify the manifest signature. Authenticity
failed.

### Malformed signature

Conditions:

- `manifest_signature` cannot be parsed or checked as a valid signature input
- `--require-signature` enabled

Illustrative JSON shape:

```json
{
  "ok": false,
  "tampered": true,
  "hash_integrity_ok": true,
  "signature_status": "fail",
  "signature_verified": false,
  "authenticity_ok": false,
  "authenticity_failure": "signature_verification_error",
  "errors": [
    "Manifest signature verification error: <parse-or-verifier-error>"
  ],
  "warnings": []
}
```

Reviewer/UI interpretation: the signature input could not be processed as a
successful Ed25519 verification. Treat this as a failed authenticity result.

### Unsigned bundle under secure/prod posture

Conditions:

- `VERITAS_POSTURE=secure` or `VERITAS_POSTURE=prod`, or strict mode otherwise
  requires a manifest signature
- `manifest_signature` is absent

Illustrative JSON shape:

```json
{
  "ok": false,
  "tampered": true,
  "hash_integrity_ok": true,
  "signature_status": "missing",
  "signature_verified": false,
  "authenticity_ok": false,
  "authenticity_failure": "signature_missing",
  "errors": [
    "Manifest signature missing"
  ],
  "warnings": []
}
```

Reviewer/UI interpretation: file/hash integrity may pass, but required manifest
authenticity is absent. Do not accept unsigned secure/prod bundles as
reviewer-facing verified evidence.

## Consumer guidance

- Show `hash_integrity_ok` and `authenticity_ok` separately.
- Treat `ok: true` in strict mode as requiring both integrity and authenticity.
- Treat `authenticity_ok: false` as “authenticity not established,” even when
  `hash_integrity_ok: true`.
- Display `errors` as blocking reviewer actions and `warnings` as review notes.
- Record trusted public key provenance outside the bundle before relying on
  `signature_verified: true`.

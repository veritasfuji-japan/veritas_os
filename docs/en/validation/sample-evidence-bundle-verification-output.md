# Sample Evidence Bundle Verification Output

This page is a reviewer-facing sample transcript for Evidence Bundle strict
verification. All command output below is **illustrative output** for external
auditors and design partners to preview the expected CLI shape before handling a
real bundle. Use it with the one-page
[Evidence Bundle Reviewer Checklist](evidence-bundle-reviewer-checklist.md) and the
[Evidence Bundle Verification JSON Contract](evidence-bundle-verification-json-contract.md).

## Safety boundary

- This sample does not include any private key, real signing key, real bundle,
  customer data, production witness ledger, or production signature material.
- Placeholder paths such as `<bundle_dir>` and
  `<trusted_ed25519_public_key>` must be replaced by reviewer-specific handoff
  paths.
- A trusted Ed25519 public key must come from an out-of-band
  reviewer/operator trust channel, not from a key copied only from the Evidence
  Bundle.

## Strict verification command

Reviewers should use strict mode for reviewer-facing verification:

```bash
veritas-evidence-bundle verify \
  --bundle-dir <bundle_dir> \
  --public-key <trusted_ed25519_public_key> \
  --require-signature
```

Strict verification is complete only when the CLI reports both file/hash
integrity and manifest signature success. JSON consumers should use the stable
contract fields documented in
[Evidence Bundle Verification JSON Contract](evidence-bundle-verification-json-contract.md).

## Successful strict verification

Illustrative output:

```text
Evidence bundle verification: PASS
File/hash integrity: PASS
Manifest signature: PASS
```

Illustrative `--json` summary fields:

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

Reviewer interpretation:

- `File/hash integrity: PASS` means every hash-covered file still matches the
  hashes recorded in `manifest.json`.
- `Manifest signature: PASS` means the manifest signature verifies under the
  trusted Ed25519 public key supplied by the reviewer.
- The bundle is reviewer-facing verified only when both lines are `PASS` in the
  same strict verification run.

## Missing public key failure

Illustrative command shape:

```bash
veritas-evidence-bundle verify \
  --bundle-dir <bundle_dir> \
  --require-signature
```

Illustrative output:

```text
Evidence bundle verification: FAIL
File/hash integrity: PASS
Manifest signature: NOT VERIFIED
  error: Manifest signature present but no signature verifier was provided; manifest authenticity was not verified
  error: No trusted public key supplied; manifest signature authenticity cannot be verified
```

Illustrative `--json` summary fields:

```json
{
  "ok": false,
  "tampered": true,
  "hash_integrity_ok": true,
  "signature_status": "not_verified",
  "signature_verified": false,
  "authenticity_ok": false,
  "authenticity_failure": "signature_not_verified"
}
```

Reviewer interpretation:

- The files may still match the manifest, so file/hash integrity can report
  `PASS`.
- Authenticity is not established because no trusted public key was supplied.
- Do not accept this as reviewer-facing Evidence Bundle verification.

## Wrong public key failure

Illustrative command shape:

```bash
veritas-evidence-bundle verify \
  --bundle-dir <bundle_dir> \
  --public-key <wrong_ed25519_public_key> \
  --require-signature
```

Illustrative output:

```text
Evidence bundle verification: FAIL
File/hash integrity: PASS
Manifest signature: FAIL
  error: Manifest signature verification failed
```

Illustrative `--json` summary fields:

```json
{
  "ok": false,
  "tampered": true,
  "hash_integrity_ok": true,
  "signature_status": "fail",
  "signature_verified": false,
  "authenticity_ok": false,
  "authenticity_failure": "signature_verification_failed"
}
```

Reviewer interpretation:

- Hash-covered files still match `manifest.json`, so file/hash integrity can
  pass.
- The supplied public key did not verify the manifest signature, so manifest
  authenticity failed.
- Treat this as a failed reviewer verification even if the bundle content has
  not been hash-tampered.

## Why file/hash integrity PASS alone is insufficient

`File/hash integrity: PASS` only proves that the current files match the hashes
recorded inside the current `manifest.json`. It does not prove who authored that
manifest, whether the signer is trusted, or whether the manifest was replaced
alongside the files.

Manifest authenticity requires `Manifest signature: PASS` under a trusted
Ed25519 public key that the reviewer received out-of-band through the approved
trust channel. A bundle with only `File/hash integrity: PASS` must remain
unaccepted for external reviewer purposes until manifest authenticity is also
verified.


## Malformed signature failure

Illustrative `--json` summary fields:

```json
{
  "ok": false,
  "tampered": true,
  "hash_integrity_ok": true,
  "signature_status": "fail",
  "signature_verified": false,
  "authenticity_ok": false,
  "authenticity_failure": "signature_verification_error"
}
```

Reviewer interpretation:

- The signature input could not be parsed or processed as a successful Ed25519
  manifest signature verification.
- Treat this as a failed authenticity result even when file/hash integrity is
  still `PASS`.

## Unsigned secure/prod bundle failure

Under `VERITAS_POSTURE=secure` or `VERITAS_POSTURE=prod`, unsigned bundles fail
closed because manifest authenticity is required.

Illustrative `--json` summary fields:

```json
{
  "ok": false,
  "tampered": true,
  "hash_integrity_ok": true,
  "signature_status": "missing",
  "signature_verified": false,
  "authenticity_ok": false,
  "authenticity_failure": "signature_missing"
}
```

Reviewer interpretation:

- The bundle is not reviewer-facing verified evidence because required manifest
  authenticity is absent.
- Do not accept unsigned secure/prod bundles even if `hash_integrity_ok` is
  `true`.

# Sample Evidence Bundle Verification Output

These examples should be read with the
[Trusted Public Key Provenance Receipt](trusted-public-key-provenance.md).
Strict verification requires reviewer/operator provenance for the public key;
`public_key_fingerprint_sha256` records key material evidence, not trust
proof. Matching fingerprints support correlation and do not certify the
bundle or complete a third-party audit.

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
- `public_key_fingerprint_sha256` records which public key file bytes were used
  for verification. It is key-provenance evidence, not a trust proof; matching a
  fingerprint copied from the bundle must never replace the out-of-band trust
  channel.

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

## Saving the JSON result

When reviewers need a durable evidence artifact, add `--json --output <path>`:

```bash
veritas-evidence-bundle verify \
  --bundle-dir <bundle_dir> \
  --public-key <trusted_ed25519_public_key> \
  --require-signature \
  --json \
  --output evidence-bundle-verification-result.json
```

The CLI writes the same JSON result to stdout and to the UTF-8 output file. The
saved verification result is reviewer evidence, including for failed
verification attempts such as missing public keys or wrong public keys. It is
not regulatory certification and is not completed third-party audit approval.
Reviewers must interpret the file with out-of-band trusted public key
provenance, preserved in a Trusted Public Key Provenance Receipt;
`public_key_fingerprint_sha256` helps correlate the saved result with the
key handoff receipt, but does not make the key trustworthy on its own. A
public key copied only from the Evidence Bundle must not be trusted by
itself.

## Validating a saved JSON result shape

A saved verification result can be checked later against the JSON Schema:

```bash
veritas-evidence-bundle validate-result \
  --result evidence-bundle-verification-result.json
```

Illustrative success output:

```text
Evidence bundle verification result schema: PASS
```

Illustrative failure output:

```text
Evidence bundle verification result schema: FAIL
  error at $['signature_status']: 'verified' is not one of ['pass', 'fail', 'missing', 'not_verified']
```

For machine-readable saved-result Schema validation, add `--json`:

```bash
veritas-evidence-bundle validate-result \
  --result evidence-bundle-verification-result.json \
  --json
```

To preserve that validation report as audit evidence, add `--output <path>` with
`--json`:

```bash
veritas-evidence-bundle validate-result \
  --result evidence-bundle-verification-result.json \
  --json \
  --output evidence-bundle-verification-result-validation.json
```

The stdout JSON and saved UTF-8 JSON file are byte-for-byte identical. Failure
reports for schema-invalid or malformed saved results are also written so CI,
UI, and external audit tools can retain the failed validation outcome. The
validation report is self-describing: `report_schema_id` identifies the
validation report schema, `validated_schema_id` identifies the verification
result schema used for saved result validation, and `validator` identifies the
emitting CLI command. The validation report shape is documented by
[`schemas/evidence_bundle_validation_report.schema.json`](../../../schemas/evidence_bundle_validation_report.schema.json).
`validate-result --output` without `--json` fails clearly.

Illustrative `validate-result --json` success output:

```json
{
  "ok": true,
  "schema_valid": true,
  "result_path": "evidence-bundle-verification-result.json",
  "report_schema_id": "https://veritas-os.example/schemas/evidence_bundle_validation_report.schema.json",
  "validated_schema_id": "https://veritas-os.example/schemas/evidence_bundle_verification_result.schema.json",
  "validator": "veritas-evidence-bundle validate-result",
  "errors": []
}
```

Illustrative `validate-result --json` failure output:

```json
{
  "ok": false,
  "schema_valid": false,
  "result_path": "evidence-bundle-verification-result.json",
  "report_schema_id": "https://veritas-os.example/schemas/evidence_bundle_validation_report.schema.json",
  "validated_schema_id": "https://veritas-os.example/schemas/evidence_bundle_verification_result.schema.json",
  "validator": "veritas-evidence-bundle validate-result",
  "errors": [
    {
      "path": "$['signature_status']",
      "message": "'verified' is not one of ['pass', 'fail', 'missing', 'not_verified']"
    }
  ]
}
```

Malformed JSON is also returned as structured JSON with `path` set to `$` and a
message beginning with `malformed JSON:`.

The saved-result schema validation confirms saved verification result shape
only. The separate validation report schema validates only the
`validate-result --json` report shape. Its `report_schema_id`,
`validated_schema_id`, and `validator` fields are metadata for interpretation;
they do not prove authenticity or trust. Neither schema validates the original
Evidence Bundle, re-runs file/hash integrity checks, re-runs Ed25519 signature
verification, establishes out-of-band trusted key provenance, or provides
regulatory certification or completed third-party audit approval. A saved
`validate-result --json --output` report is evidence of the schema-validation
report for an existing result file, not evidence of a new Evidence Bundle
verification run.

## Validating trusted public key provenance correlation

After strict verification and receipt preservation, reviewers can validate the
receipt shape and correlate its fingerprint with the saved verification result:

```bash
veritas-evidence-bundle validate-key-provenance \
  --receipt trusted-public-key-provenance.json \
  --verification-result verification-result.json
```

Illustrative success output:

```text
Trusted public key provenance validation: PASS
Receipt schema: PASS
Verification result schema: PASS
Fingerprint correlation: PASS
Bundle-internal key used: PASS
Strict authenticity result: PASS
```

Illustrative failure output:

```text
Trusted public key provenance validation: FAIL
Receipt schema: PASS
Verification result schema: PASS
Fingerprint correlation: FAIL
Bundle-internal key used: PASS
Strict authenticity result: PASS
  error [fingerprint_correlation_ok] at $['public_key_fingerprint_sha256']: receipt and verification result public key fingerprints do not match
```

For machine-readable output and saved audit evidence, use `--json --output`:

```bash
veritas-evidence-bundle validate-key-provenance \
  --receipt trusted-public-key-provenance.json \
  --verification-result verification-result.json \
  --json \
  --output key-provenance-validation.json
```

The stdout JSON and saved UTF-8 JSON file are byte-for-byte identical, including
failure reports. `--output` without `--json` fails clearly. The report does not
echo raw fingerprint values; raw fingerprints remain in the source receipt and
verification-result artifacts. This command validates receipt shape, validates
saved verification-result shape, checks exact fingerprint correlation, rejects
`bundle_internal_key_used: true`, and confirms strict authenticity success. It
does not create trust by itself, does not re-run cryptographic verification,
does not prove regulatory certification, and does not complete third-party
audit approval. Matching fingerprints support correlation, not standalone
trust.

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
  "public_key_fingerprint_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "errors": [],
  "warnings": []
}
```

Reviewer interpretation:

- `File/hash integrity: PASS` means every hash-covered file still matches the
  hashes recorded in `manifest.json`.
- `Manifest signature: PASS` means the manifest signature verifies under the
  trusted Ed25519 public key supplied by the reviewer.
- `public_key_fingerprint_sha256` should match the fingerprint the reviewer
  recorded from the out-of-band trusted-key handoff.
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
  "authenticity_failure": "signature_not_verified",
  "public_key_fingerprint_sha256": null
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
  "authenticity_failure": "signature_verification_failed",
  "public_key_fingerprint_sha256": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
}
```

Reviewer interpretation:

- Hash-covered files still match `manifest.json`, so file/hash integrity can
  pass.
- The supplied public key did not verify the manifest signature, so manifest
  authenticity failed. The fingerprint records the supplied wrong key for later
  evidence review; it does not make that key trustworthy.
- Treat this as a failed reviewer verification even if the bundle content has
  not been hash-tampered.

## Why file/hash integrity PASS alone is insufficient

`File/hash integrity: PASS` only proves that the current files match the hashes
recorded inside the current `manifest.json`. It does not prove who authored that
manifest, whether the signer is trusted, or whether the manifest was replaced
alongside the files.

Manifest authenticity requires `Manifest signature: PASS` under a trusted
Ed25519 public key that the reviewer received out-of-band through the approved
trust channel. The reviewer should record that trusted key fingerprint and
compare it with `public_key_fingerprint_sha256`; a bundle-internal key or
fingerprint is not sufficient. A bundle with only `File/hash integrity: PASS`
must remain unaccepted for external reviewer purposes until manifest
authenticity is also verified.


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
  "authenticity_failure": "signature_verification_error",
  "public_key_fingerprint_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
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
  "authenticity_failure": "signature_missing",
  "public_key_fingerprint_sha256": null
}
```

Reviewer interpretation:

- The bundle is not reviewer-facing verified evidence because required manifest
  authenticity is absent.
- Do not accept unsigned secure/prod bundles even if `hash_integrity_ok` is
  `true`.

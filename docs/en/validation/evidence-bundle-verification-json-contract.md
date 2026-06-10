# Evidence Bundle Verification JSON Contract

For reviewer/operator key trust records, pair this contract with the
[Trusted Public Key Provenance Receipt](trusted-public-key-provenance.md).
Strict verification requires trusted public key provenance before reviewers
rely on authenticity. The `public_key_fingerprint_sha256` field records key
material evidence; it is not trust proof. Matching fingerprints support
correlation between `verification-result.json` and the provenance receipt,
not regulatory certification or completed third-party audit approval.

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

Machine-readable verification result validation is pinned in the JSON Schema at
[`schemas/evidence_bundle_verification_result.schema.json`](../../../schemas/evidence_bundle_verification_result.schema.json).
`validate-result --json` validation reports are self-describing and have
their own machine-readable JSON Schema at
[`schemas/evidence_bundle_validation_report.schema.json`](../../../schemas/evidence_bundle_validation_report.schema.json).
The `report_schema_id` field identifies the validation report schema,
`validated_schema_id` identifies the saved verification result schema used for
saved result validation, and `validator` identifies the CLI command that
emitted the report. These metadata fields help CI, UI, and external audit
tools interpret the report later; they do not prove authenticity, establish
trusted key provenance, re-run cryptographic verification, or provide
certification.

## Saving reviewer evidence to a file

Use `--output <path>` with `--json` to save the exact JSON verification result
as UTF-8 reviewer evidence while still emitting the same JSON to stdout:

```bash
veritas-evidence-bundle verify \
  --bundle-dir <bundle_dir> \
  --public-key <trusted_ed25519_public_key> \
  --require-signature \
  --json \
  --output evidence-bundle-verification-result.json
```

The saved file is evidence of the verification result observed by the reviewer.
It is not regulatory certification and is not completed third-party audit
approval. Failed verification results are also written when `--output` is used,
because failure JSON is important audit evidence for missing keys, wrong keys,
tampering, or other verification blockers.

`--output` is reserved for the machine-readable JSON result and therefore
requires `--json`; human-oriented CLI output remains unchanged when `--json` is
not selected. If the result file cannot be written, the CLI exits non-zero and
prints a clear write-failure diagnostic.

Saved results must be interpreted together with out-of-band trusted public key
provenance. `public_key_fingerprint_sha256` helps correlate the saved result
with the reviewer/operator key handoff record, but the fingerprint does not by
itself establish trust and a key copied only from the bundle must not be used as
a trust source.

## Validating a saved result against the schema

Use `validate-result --result <path>` to check later that a saved verification
result JSON file still conforms to the machine-readable schema:

```bash
veritas-evidence-bundle validate-result \
  --result evidence-bundle-verification-result.json
```

A schema-valid saved result prints:

```text
Evidence bundle verification result schema: PASS
```

A malformed or schema-invalid saved result exits non-zero, prints
`Evidence bundle verification result schema: FAIL`, and includes diagnostics for
missing required fields, invalid field types, invalid enum values such as
`signature_status`, and invalid patterns such as
`public_key_fingerprint_sha256` values that are not `null` or 64-character
lowercase hexadecimal strings.

For CI, UI, or external audit-tool integrations, add `--json` to make the saved
result Schema validation outcome machine-readable on stdout:

```bash
veritas-evidence-bundle validate-result \
  --result evidence-bundle-verification-result.json \
  --json
```

Add `--output <path>` with `--json` to save the exact same Schema validation
report as UTF-8 audit evidence while still emitting the JSON to stdout:

```bash
veritas-evidence-bundle validate-result \
  --result evidence-bundle-verification-result.json \
  --json \
  --output evidence-bundle-verification-result-validation.json
```

`validate-result --output` requires `--json`. Parent directories are created
when needed. Schema-invalid and malformed-result failure reports are also saved,
because failure reports are part of the audit trail. If the report cannot be
written, the CLI exits non-zero and prints a clear write-failure diagnostic on
stderr.

A schema-valid saved result emits only JSON on stdout and exits `0`:

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

Schema-invalid or malformed JSON inputs emit only JSON on stdout and exit `1`.
Each error contains a JSONPath-like `path` and reviewer/tooling-safe `message`.
For malformed JSON, the path is `$` because the document cannot be parsed before
schema validation.

The validation report schema validates only the shape of the
`validate-result --json` report (`ok`, `schema_valid`, `result_path`,
`report_schema_id`, `validated_schema_id`, `validator`, and `errors[]`
diagnostics with `path` and `message`). The report is self-describing:
`report_schema_id` identifies the validation report schema,
`validated_schema_id` identifies the verification result schema used by
`validate-result`, and `validator` identifies the emitting CLI command. These
fields are metadata for interpretation only. They do not validate the original
Evidence Bundle, do not validate the saved verification result beyond recording
this command outcome, do not prove authenticity, do not re-run Evidence Bundle
file/hash checks, do not re-run Ed25519 manifest signature verification, do
not establish trusted key provenance, and are not regulatory certification or
completed third-party audit approval. Saving a
`validate-result --json --output` report records the schema-validation outcome
for the already-saved result file; it is not a new cryptographic verification
run. Reviewers must still preserve out-of-band trusted public key provenance for
the key represented by `public_key_fingerprint_sha256` before relying on any
saved strict verification result.

Use `validate-key-provenance` when tooling needs one command to validate the
Trusted Public Key Provenance Receipt shape and correlate it with this saved
verification-result contract:

```bash
veritas-evidence-bundle validate-key-provenance \
  --receipt trusted-public-key-provenance.json \
  --verification-result verification-result.json \
  --json
```

The JSON report includes stable booleans for receipt schema validity,
verification-result schema validity, fingerprint presence, fingerprint
correlation, `bundle_internal_key_used: false`, and strict authenticity success.
It does not echo raw fingerprint values, raw file paths, raw schema validator
messages, or raw exception text; the raw fingerprints remain in the source
receipt and verification-result artifacts. `--output <path>` is allowed only
with `--json`; the saved JSON is byte-for-byte the same as stdout JSON, and
failure reports are saved as audit evidence. This correlation report has a
dedicated Draft 2020-12 schema at
[`schemas/trusted_public_key_provenance_validation_report.schema.json`](../../../schemas/trusted_public_key_provenance_validation_report.schema.json).
The schema validates the report shape only; it does not re-run cryptographic
verification, create trust, prove regulatory certification, or complete
third-party audit approval. The report does not expose raw fingerprints or raw
paths. Matching fingerprints support correlation, not standalone trust.

Use `validate-key-provenance-result` to validate a saved
`validate-key-provenance --json` report against that report schema:

```bash
veritas-evidence-bundle validate-key-provenance-result \
  --result key-provenance-validation.json
```

The command validates saved report shape only. It does not re-run key
provenance validation, does not re-run cryptographic verification, does not
create trust, is not regulatory certification, and is not completed third-party
audit approval. Its JSON output uses `result_schema_valid`,
`validated_schema_id`, `validator`, and fixed `errors`; it does not expose raw
fingerprints, raw paths, raw exception text, raw schema validator messages, or
raw JSON values from the saved report. Add `--json --output <path>` to save a
byte-for-byte copy of stdout JSON; parent directories are created, and
`--output` without `--json` is rejected.

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
| `public_key_fingerprint_sha256` | string or null | SHA-256 hex fingerprint of the public key file bytes supplied with `--public-key`, or `null` when no public key was supplied. This records which key material was used for verification; it does not by itself establish trust. Reviewers must still use an out-of-band reviewer/operator trust channel. |
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
  "public_key_fingerprint_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "errors": [],
  "warnings": []
}
```

Reviewer/UI interpretation: the bundle passed strict reviewer-facing
verification for file/hash integrity and manifest authenticity. The
`public_key_fingerprint_sha256` value is supporting key-provenance evidence for
which out-of-band key material was used; it is not a trust proof. This result is
still not regulatory certification or completed third-party audit approval.

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
  "public_key_fingerprint_sha256": null,
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
  "public_key_fingerprint_sha256": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
  "errors": [
    "Manifest signature verification failed"
  ],
  "warnings": []
}
```

Reviewer/UI interpretation: the hash-covered files can still match the manifest,
but the supplied public key did not verify the manifest signature. The
fingerprint records the wrong supplied key material for later review; matching a
fingerprint alone must not make a bundle-trusted key trustworthy. Authenticity
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
  "public_key_fingerprint_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
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
  "public_key_fingerprint_sha256": null,
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
- Record `public_key_fingerprint_sha256` with the reviewer/operator Trusted
  Public Key Provenance Receipt as key-material evidence.
- Never trust a key because its fingerprint matches a value copied from the
  bundle or its adjacent artifacts; fingerprint matching is only useful after the
  reviewer obtained the key through an out-of-band trust channel.
- Record trusted public key provenance outside the bundle before relying on
  `signature_verified: true`, preferably using the
  [Trusted Public Key Provenance Receipt](trusted-public-key-provenance.md).

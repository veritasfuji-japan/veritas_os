# Trusted Public Key Provenance Receipt

The Trusted Public Key Provenance Receipt records why a reviewer or operator
trusted the Ed25519 public key used during strict Evidence Bundle verification.
For the end-to-end Reviewer Evidence Packet sequence, see the
[Reviewer Key Provenance Walkthrough](reviewer-key-provenance-walkthrough.md) and the
[Reviewer Handoff Guide](reviewer-handoff-guide.md).
It complements `verification-result.json`; it is not generated from the
Evidence Bundle alone and it does not replace cryptographic verification.

Receipt schema:
[`schemas/trusted_public_key_provenance_receipt.schema.json`](../../../schemas/trusted_public_key_provenance_receipt.schema.json)

`validate-key-provenance --json` report schema:
[`schemas/trusted_public_key_provenance_validation_report.schema.json`](../../../schemas/trusted_public_key_provenance_validation_report.schema.json)

## Illustrative sample artifacts

Reviewers who want to see the expected artifact relationships can inspect the
illustrative sample set at
[`samples/evidence_bundle/key_provenance_review/`](../../../samples/evidence_bundle/key_provenance_review/).
The sample set links `verification-result.json`,
`trusted-public-key-provenance.json`, `key-provenance-validation.json`,
`key-provenance-result-validation.json`, and `reviewer-evidence-packet.json`.
It is illustrative only: it does not create trust, replace out-of-band public
key trust, prove regulatory certification, or represent completed third-party
audit approval. Matching fingerprints support correlation only.

## Why public key provenance matters

Strict Evidence Bundle verification separates two questions:

1. **Which key material was used?** The verifier records this as
   `public_key_fingerprint_sha256`.
2. **Why was that key trusted?** The reviewer must establish this through an
   out-of-band reviewer/operator process such as an operator handoff,
   reviewer vault, signed release, KMS/certificate process, or offline key
   ceremony.

A matching signature under an untrusted key does not establish reviewer-facing
authenticity. A public key copied only from the Evidence Bundle, or from
bundle-adjacent material without an independent trust process, is not trusted by
itself.

## Public key fingerprint versus trust

`public_key_fingerprint_sha256` is key-material evidence. It records the
SHA-256 lowercase hexadecimal fingerprint of the public key bytes supplied to
strict verification.

The fingerprint is not a trust proof. It helps reviewers correlate the saved
verification result with an independent provenance receipt. Trust comes from the
reviewer/operator trust channel recorded in the receipt, not from the bundle or
fingerprint alone.

## How reviewers should use the receipt

Reviewers should preserve a Trusted Public Key Provenance Receipt next to the
strict verification artifacts when relying on Evidence Bundle authenticity:

1. Obtain the Ed25519 public key outside the Evidence Bundle through an
   approved reviewer/operator trust channel.
2. Record a receipt with the key fingerprint, trust channel, received timestamp,
   approving identity, approval reference, and reviewer notes.
3. Run strict verification with the trusted public key and save JSON output:
   `veritas-evidence-bundle verify --require-signature --json --output
   verification-result.json`.
4. Compare the fingerprint in `verification-result.json` with the fingerprint in
   the Trusted Public Key Provenance Receipt.
5. Preserve both files as review evidence.

A matching fingerprint supports correlation between the cryptographic
verification run and the out-of-band trust record. It is not regulatory
certification and is not completed third-party audit approval. It is not
standalone proof that the original Evidence Bundle is authentic.

## CLI validation

Use `validate-key-provenance` to validate the receipt shape, validate the saved
Evidence Bundle verification result shape, and correlate the two saved
fingerprints:

```bash
veritas-evidence-bundle validate-key-provenance \
  --receipt trusted-public-key-provenance.json \
  --verification-result verification-result.json
```

Successful human-readable output reports each check explicitly:

```text
Trusted public key provenance validation: PASS
Receipt schema: PASS
Verification result schema: PASS
Fingerprint correlation: PASS
Bundle-internal key used: PASS
Strict authenticity result: PASS
```

For CI, UI, or audit-tool ingestion, add `--json`. The JSON report has a
dedicated Draft 2020-12 schema at
[`schemas/trusted_public_key_provenance_validation_report.schema.json`](../../../schemas/trusted_public_key_provenance_validation_report.schema.json).
That schema validates the report shape only; it does not re-run cryptographic
verification, create trust, prove regulatory certification, or complete
third-party audit approval. Add `--output <path>` with `--json` to save the
exact same JSON report that is emitted to stdout; failure reports are saved too,
and parent directories are created when needed.
`--output` without `--json` is rejected. To avoid echoing externally supplied
key material or local environment details in logs, the public CLI report exposes
only booleans and fixed diagnostics. It does not print raw fingerprint values,
raw file paths, raw schema validator messages, or raw exception text; it only
reports whether receipt and verification-result fingerprints are present and
whether correlation passed. The raw fingerprints remain preserved in the source
receipt and verification-result artifacts.

```bash
veritas-evidence-bundle validate-key-provenance \
  --receipt trusted-public-key-provenance.json \
  --verification-result verification-result.json \
  --json \
  --output key-provenance-validation.json
```

Saved `validate-key-provenance --json` reports can be checked later with
`validate-key-provenance-result`:

```bash
veritas-evidence-bundle validate-key-provenance-result \
  --result key-provenance-validation.json
```

Successful human-readable output is:

```text
Trusted public key provenance validation report schema: PASS
```

Add `--json` for a stable machine-readable report, and add `--output <path>`
with `--json` to save byte-for-byte the same JSON emitted to stdout. Parent
directories are created when needed, and `--output` without `--json` is
rejected. The JSON output has a dedicated Draft 2020-12 schema at
[`schemas/trusted_public_key_provenance_result_validation_report.schema.json`](../../../schemas/trusted_public_key_provenance_result_validation_report.schema.json).
That schema validates the validator result shape only. It does not re-run key
provenance validation, does not re-run cryptographic verification, does not
create trust, is not regulatory certification, and is not completed third-party
audit approval. Its public output uses fixed diagnostics and does not expose
raw fingerprints, raw file paths, raw exception text, raw schema validator
messages, or raw JSON values from the saved report.

The command checks that:

- `--receipt` conforms to
  `schemas/trusted_public_key_provenance_receipt.schema.json`;
- `--verification-result` conforms to
  `schemas/evidence_bundle_verification_result.schema.json`;
- both `public_key_fingerprint_sha256` values match exactly;
- the receipt has `bundle_internal_key_used: false`; and
- the saved result reports strict authenticity success: `signature_status:
  "pass"`, `signature_verified: true`, and `authenticity_ok: true`.

This command validates receipt shape and fingerprint correlation only. The CLI
report intentionally does not echo raw fingerprint values, raw file paths, raw
schema validator messages, or raw exception text; use the original receipt and
verification-result artifacts when a reviewer must inspect exact fingerprints.
It does not create trust by itself, does not re-run cryptographic verification,
does not prove regulatory certification, and does not complete third-party
audit approval. Matching fingerprints support correlation between a saved
strict verification result and a reviewer/operator provenance record; they are
not standalone trust.

## Fingerprint comparison

Compare these fields exactly:

- `verification-result.json.public_key_fingerprint_sha256`
- `trusted_public_key_provenance_receipt.public_key_fingerprint_sha256`

Both values must be 64-character lowercase hexadecimal SHA-256 fingerprints.
If the values differ, the verification result used different key material than
the trusted provenance receipt records. Treat that as a reject condition until a
corrected handoff or corrected verification result is available.

## Bundle-internal keys are not enough

A key stored only inside the Evidence Bundle can help identify what the bundle
claims, but it cannot establish why a reviewer should trust the bundle. The
provenance receipt therefore requires `bundle_internal_key_used` to be `false`.
If the only available key material came from inside the bundle, do not accept the
bundle as reviewer-facing verified evidence.

## Example valid receipt

```json
{
  "receipt_type": "trusted_public_key_provenance",
  "algorithm": "Ed25519",
  "public_key_fingerprint_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "trust_channel": "operator_handoff",
  "received_at": "2026-06-09T00:00:00Z",
  "approved_by": "reviewer@example.com",
  "approval_reference": "ticket-or-vault-reference",
  "notes": "Public key received from out-of-band reviewer/operator trust channel.",
  "bundle_internal_key_used": false
}
```

## Example reject conditions

Reject or request a corrected handoff when any of the following occur:

- The public key is copied only from the Evidence Bundle.
- `bundle_internal_key_used` is `true` or missing.
- The receipt fingerprint does not match
  `verification-result.json.public_key_fingerprint_sha256`.
- `trust_channel` is unknown and not recorded as `other` with clear notes and an
  approval reference.
- The receipt is missing `approved_by`, `approval_reference`, or reviewer notes.
- Strict verification did not produce `signature_status: "pass"`,
  `signature_verified: true`, and `authenticity_ok: true` under the trusted key.

## Boundary

The receipt records reviewer/operator provenance for trusted Ed25519 public key
material. It does not re-run cryptographic verification, does not prove that the
original Evidence Bundle is authentic by itself. This receipt is not
regulatory certification. This receipt is not completed third-party audit
approval.

## Reviewer Evidence Packet key provenance references

Reviewer Evidence Packets may include an optional `key_provenance` metadata section that references the Trusted Public Key Provenance validation artifacts by fixed artifact name and schema identifier:

- `trusted-public-key-provenance.json`
- `key-provenance-validation.json`
- `key-provenance-result-validation.json`

These references help reviewers locate the artifacts used to check public key trust provenance for strict Evidence Bundle signature review. The packet does not create trust by itself, does not re-run cryptographic verification, and does not replace the out-of-band reviewer/operator trust channel. Matching fingerprints support correlation between the verification result and the Trusted Public Key Provenance Receipt; matching fingerprints are not standalone trust proof.

Reviewer Evidence Packet metadata must not embed raw public key fingerprints, raw local file paths, raw exception text, raw schema validator messages, or raw JSON values copied from externally supplied artifacts. It should reference only the stable artifact names and schema identifiers above. The packet is not regulatory certification and is not completed third-party audit approval.

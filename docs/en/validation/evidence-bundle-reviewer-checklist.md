# Evidence Bundle Reviewer Checklist

This checklist is the reviewer-facing entry point for evaluating a VERITAS OS
Evidence Bundle. It gives external auditors and design partners a single-page
verification order, acceptance criteria, and reference map before they inspect
bundle contents in detail.

Use it with the strict CLI path in
[Evidence Bundle Signature Verification Demo](evidence-bundle-signature-verification.md)
and the example transcripts in
[Sample Evidence Bundle Verification Output](sample-evidence-bundle-verification-output.md)
and the [Evidence Bundle Verification JSON Contract](evidence-bundle-verification-json-contract.md).
Use the [Trusted Public Key Provenance Receipt](trusted-public-key-provenance.md)
to preserve the reviewer/operator trust basis for the public key used in
strict verification.

## Scope and non-certification boundary

This checklist supports reviewer verification of one delivered Evidence Bundle.
It is not regulatory certification, legal approval, or completed
third-party audit approval. Reviewers remain responsible for their own audit scope,
evidence sampling, legal/regulatory conclusions, and sign-off process.

Security boundaries:

- Hash integrity is not authenticity.
- A public key included only inside the bundle is not trusted by itself.
- The `public_key_fingerprint_sha256` JSON field records which public key
  material was used for verification; it is key-provenance evidence, not a trust
  proof. Strict verification requires trusted public key provenance before a
  reviewer relies on authenticity.
- The trusted Ed25519 public key must be obtained outside the bundle through an
  approved out-of-band reviewer/operator trust channel, and reviewers should
  preserve a Trusted Public Key Provenance Receipt for that key. Matching
  `public_key_fingerprint_sha256` values support correlation between the
  verification result and the provenance receipt; they are not certification.
- The `--json` result contract supports reviewer-facing verification and UI
  integration, but it does not certify regulatory compliance or audit approval.
- Do not add private keys, real signing keys, production secrets, or unsanitized
  customer data to review notes or shared examples.

## Saving JSON reviewer evidence

Reviewers can preserve a machine-readable audit trail by adding
`--json --output <path>` to strict verification:

```bash
veritas-evidence-bundle verify \
  --bundle-dir <bundle_dir> \
  --public-key <trusted_ed25519_public_key> \
  --require-signature \
  --json \
  --output evidence-bundle-verification-result.json
```

The saved verification result is reviewer evidence, including when verification
fails. It is not regulatory certification and is not completed third-party audit
approval. Interpret the saved JSON with the out-of-band trusted public key
handoff record; `public_key_fingerprint_sha256` helps correlate the saved result
with that key provenance record, but does not itself establish trust.

To validate only the saved result shape later, run:

```bash
veritas-evidence-bundle validate-result \
  --result evidence-bundle-verification-result.json
```

`validate-result` checks JSON parsing and the saved result schema, including
required fields, `signature_status` enum values, and
`public_key_fingerprint_sha256` null-or-lowercase-hex shape. Add `--json` when
CI, UI, or external audit tooling must consume a machine-readable validation
report for the saved result file; that validation report has its own
machine-readable schema at
[`schemas/evidence_bundle_validation_report.schema.json`](../../../schemas/evidence_bundle_validation_report.schema.json).
The JSON validation report is self-describing: `report_schema_id` identifies
the validation report schema, `validated_schema_id` identifies the verification
result schema used for saved result validation, and `validator` identifies the
emitting CLI command. Add `--output <path>` together with `--json` to save the
exact stdout validation report as UTF-8 audit evidence, including failure
reports for schema-invalid or malformed saved results. The validation report
schema only validates the report shape, and its metadata fields do not prove
authenticity or trust. It does not validate the original bundle, re-run
file/hash integrity checks or Ed25519 signature verification, establish trusted
key provenance, or provide regulatory certification or completed third-party
audit approval. Preserve the out-of-band trusted-key provenance record even
when saved-result schema validation passes.

After preserving a Trusted Public Key Provenance Receipt, validate the receipt
and correlate it with the saved strict verification result:

```bash
veritas-evidence-bundle validate-key-provenance \
  --receipt trusted-public-key-provenance.json \
  --verification-result verification-result.json
```

This command validates the receipt schema, validates the saved verification
result schema, checks exact fingerprint correlation, rejects
`bundle_internal_key_used: true`, and confirms strict authenticity success
(`signature_status: "pass"`, `signature_verified: true`, and
`authenticity_ok: true`). Add `--json --output <path>` to emit and save the
exact same machine-readable report, including failure reports. The JSON report
has a dedicated Draft 2020-12 schema at
[`schemas/trusted_public_key_provenance_validation_report.schema.json`](../../../schemas/trusted_public_key_provenance_validation_report.schema.json).
That schema validates the report shape only; it does not re-run cryptographic
verification, create trust, prove regulatory certification, or complete
third-party audit approval. The public report exposes only booleans and fixed
diagnostics: it does not echo raw fingerprint values, raw file paths, raw schema
validator messages, or raw exception text. It only records fingerprint presence
and correlation status because the raw fingerprints remain in the source receipt
and verification-result artifacts. Matching fingerprints support correlation,
not standalone trust.

To validate the saved `validate-key-provenance --json` report shape later, run:

```bash
veritas-evidence-bundle validate-key-provenance-result \
  --result key-provenance-validation.json
```

This command validates saved report shape only. Its `--json` output has a
dedicated Draft 2020-12 schema at
[`schemas/trusted_public_key_provenance_result_validation_report.schema.json`](../../../schemas/trusted_public_key_provenance_result_validation_report.schema.json).
That schema validates the validator result shape only. It does not re-run key
provenance validation, does not re-run cryptographic verification, does not
create trust, is not regulatory certification, and is not completed third-party
audit approval. Add `--json --output <path>` to emit and save byte-for-byte the
same fixed-diagnostic JSON report; parent directories are created and
`--output` without `--json` is rejected. The output does not expose raw
fingerprints, raw file paths, raw exception text, raw schema validator messages,
or raw JSON values from the saved report.

## Verification order

| Step | Reviewer action | PASS criterion | FAIL / follow-up criterion |
|---|---|---|---|
| 1 | Confirm bundle origin and expected handoff channel. | The bundle source, transfer channel, bundle type, and review objective match the expected handoff. | The source or channel is unexpected, undocumented, or inconsistent with the review request. |
| 2 | Obtain the trusted Ed25519 public key out-of-band. | The reviewer obtains the public key from a trusted registry, signed operator note, KMS/certificate process, or other approved channel outside the bundle, and records the expected SHA-256 fingerprint. | The public key is missing, comes only from inside the bundle, its fingerprint is copied only from bundle-adjacent material, or its provenance cannot be established. |
| 3 | Run the strict verification command. | The reviewer runs `veritas-evidence-bundle verify --bundle-dir <bundle_dir> --public-key <trusted_ed25519_public_key> --require-signature`; add `--json --output <path>` when a saved JSON evidence file is required. | The command is not run, omits `--require-signature`, omits the trusted public key, or uses an untrusted key path. |
| 4 | Confirm `File/hash integrity: PASS`. | The CLI prints `File/hash integrity: PASS` in the strict verification run. | The CLI reports hash failure, manifest hash mismatch, missing files, malformed manifest data, or any file/hash error. |
| 5 | Confirm `Manifest signature: PASS`. | The CLI prints `Manifest signature: PASS` under the trusted Ed25519 public key obtained in Step 2. For `--json`, `authenticity_ok` is `true`, `signature_status` is `pass`, `signature_verified` is `true`, and `public_key_fingerprint_sha256` matches the out-of-band key fingerprint recorded by the reviewer. | The CLI reports missing public key, wrong key, malformed signature, unsigned secure/prod bundle, signature verification failure, or a fingerprint mismatch against the out-of-band reviewer record. For `--json`, `authenticity_ok` is `false`. |
| 6 | Inspect `acceptance_checklist.json`. | The checklist exists and has no blocking failures for the submitted bundle profile. | The checklist is missing, malformed, incomplete, or contains any blocking failure. |
| 7 | Inspect `verification_report.json`. | The report exists and is consistent with the strict verification result and expected bundle scope. | The report is missing, malformed, stale, inconsistent with CLI output, or reports unresolved errors. |
| 8 | Confirm no missing expected artifacts. | Required artifacts for the bundle type and review objective are present, including expected manifest, witness, report, acceptance, and profile-specific files. | Expected artifacts are absent, empty, renamed without explanation, or inconsistent with the handoff metadata. |
| 9 | Record reviewer result: `ACCEPT`, `REJECT`, or `NEEDS FOLLOW-UP`. | The final result records evidence reviewed, command output, key provenance, blockers, and reviewer rationale. | The result is ambiguous, lacks key provenance, lacks CLI evidence, or does not explain unresolved exceptions. |

## Required ACCEPT criteria

Record `ACCEPT` only when all of the following are true:

- `File/hash integrity: PASS` is present in the strict verification output.
- `Manifest signature: PASS` is present in the same strict verification output.
- The trusted Ed25519 public key was obtained outside the bundle, its
  provenance is documented by the reviewer in a Trusted Public Key
  Provenance Receipt, and its out-of-band SHA-256 fingerprint matches
  `public_key_fingerprint_sha256` in the strict `--json` result.
- `acceptance_checklist.json` has no blocking failures.
- Expected artifacts for the bundle type and review objective are present.
- Any non-blocking notes in `verification_report.json` have been reviewed and
  do not change the review conclusion.

## Required REJECT criteria

Record `REJECT` when any of the following conditions occur and cannot be
resolved by a corrected handoff:

- The public key is missing.
- The supplied public key is the wrong key for the manifest signature.
- The signature is malformed or cannot be parsed.
- The bundle is unsigned under `secure` or `prod` posture.
- The CLI reports a hash mismatch.
- The CLI reports a manifest hash mismatch.
- The reviewer cannot establish trusted key provenance.
- `acceptance_checklist.json` contains a blocking failure.
- Expected required artifacts are missing for the declared bundle type or review
  objective.

## NEEDS FOLLOW-UP criteria

Record `NEEDS FOLLOW-UP` when the reviewer cannot yet accept or reject the
bundle because clarification or replacement evidence is required. Typical cases:

- The handoff channel is unclear but may be confirmed by the operator.
- The public key is available but its provenance documentation is incomplete.
- `verification_report.json` contains notes requiring operator explanation.
- Expected artifacts are present but naming, scope, or profile metadata needs
  clarification.
- The reviewer needs a regenerated bundle to separate a procedural issue from a
  true integrity or authenticity failure.

Do not use `NEEDS FOLLOW-UP` to bypass a cryptographic failure. If strict
verification cannot produce both required PASS lines under a trusted out-of-band
key, the bundle is not reviewer-facing verified evidence.

## Reference map

- Signature semantics and strict command:
  [Evidence Bundle Signature Verification Demo](evidence-bundle-signature-verification.md)
- Sample success and failure transcripts:
  [Sample Evidence Bundle Verification Output](sample-evidence-bundle-verification-output.md)
- Stable `--json` field semantics for reviewer/UI consumers:
  [Evidence Bundle Verification JSON Contract](evidence-bundle-verification-json-contract.md)
- Trusted public key provenance receipt and fingerprint correlation:
  [Trusted Public Key Provenance Receipt](trusted-public-key-provenance.md)
- Bundle contents and delivery policy:
  [External Audit Readiness Pack](external-audit-readiness.md)

## Reviewer Evidence Packet key provenance references

Reviewer Evidence Packets may include an optional `key_provenance` metadata section that references the Trusted Public Key Provenance validation artifacts by fixed artifact name and schema identifier:

- `trusted-public-key-provenance.json`
- `key-provenance-validation.json`
- `key-provenance-result-validation.json`

These references help reviewers locate the artifacts used to check public key trust provenance for strict Evidence Bundle signature review. The packet does not create trust by itself, does not re-run cryptographic verification, and does not replace the out-of-band reviewer/operator trust channel. Matching fingerprints support correlation between the verification result and the Trusted Public Key Provenance Receipt; matching fingerprints are not standalone trust proof.

Reviewer Evidence Packet metadata must not embed raw public key fingerprints, raw local file paths, raw exception text, raw schema validator messages, or raw JSON values copied from externally supplied artifacts. It should reference only the stable artifact names and schema identifiers above. The packet is not regulatory certification and is not completed third-party audit approval.

# Reviewer Key Provenance Walkthrough

This walkthrough gives reviewers a single, copyable path for preserving and
checking Trusted Public Key Provenance artifacts in a Reviewer Evidence Packet.
It assumes the reviewer has already obtained the trusted Ed25519 public key
outside the Evidence Bundle through an approved reviewer/operator trust channel.

## Scope and boundaries

This process is reviewer-facing evidence handling. It does not create trust by
itself and does not replace out-of-band public key trust. The Reviewer Evidence
Packet references artifacts so reviewers can locate them; the packet does not
prove trust alone.

Important boundaries:

- This does not create trust by itself.
- This does not replace out-of-band public key trust.
- This does not re-run cryptographic verification unless the `verify` command
  is run.
- This is not regulatory certification.
- This is not completed third-party audit approval.
- Matching fingerprints support correlation, not standalone trust.
- Reviewer Evidence Packets reference artifacts; they do not prove trust alone.
- Reviewer Review Results record reviewer outcome only; decisions can be
  `ACCEPT`, `REJECT`, or `NEEDS_FOLLOW_UP` and depend on reviewer scope plus
  out-of-band public key trust context.

For reviewer handoff packaging, see the [Reviewer Handoff Guide](reviewer-handoff-guide.md). For the checked-in sample package flow, see the [Reviewer Handoff Sample Quickstart](reviewer-handoff-sample-quickstart.md).

Use placeholder artifact names only in examples. Do not paste real fingerprints,
real public keys, local file paths, exception text, schema validator messages,
private keys, production secrets, or unsanitized customer data into reviewer
examples or packet metadata.

## Illustrative sample artifacts

A schema-valid, illustrative sample chain is available at
[`samples/evidence_bundle/key_provenance_review/`](../../../samples/evidence_bundle/key_provenance_review/).
Use it only to see expected file names and relationships. The samples do not
create trust, do not replace out-of-band public key trust, do not prove
regulatory certification, and are not completed third-party audit approval.
Matching fingerprints in the samples support correlation only, not standalone
trust. The sample set now includes `sample-artifact-manifest.json` as an index
of expected artifact names, reviewer roles, schema identifiers, and SHA-256 file
digests. CI validates the illustrative sample chain and manifest for JSON Schema
conformance, fixed artifact references, artifact hashes, and forbidden
sensitive/raw diagnostic patterns only. The sample set also includes
`reviewer-handoff-review-result.json` as an illustrative Review Result /
Acceptance Record, plus `reviewer-review-result-validation.json` and
`reviewer-review-result-report-validation.json` as saved reviewer result
validation report artifacts, and `reviewer-handoff-package-validation.json` as
the saved package validation report artifact, and
`reviewer-handoff-quickstart-command-validation.json` as the checked-in
quickstart command validation report sample, and
`reviewer-handoff-quickstart-command-report-validation.json` as the saved
second-level validation report for that quickstart report. The quickstart sample shows the
expected machine-readable report shape, is CI-validated, and is not a trust
source by itself. These reports demonstrate validation output shape
and validation status only; they do not create trust, replace out-of-band public
key trust, prove regulatory certification, represent completed third-party
audit approval, or establish cryptographic truth by themselves. Hash matching
supports sample integrity, not standalone trust, and CI validation does not
create trust or replace out-of-band public key trust.

## Full reviewer sequence

1. Verify the Evidence Bundle strictly with a trusted public key.
2. Save `verification-result.json`.
3. Review `trusted-public-key-provenance.json`.
4. Run `validate-key-provenance`.
5. Save `key-provenance-validation.json`.
6. Run `validate-key-provenance-result`.
7. Save `key-provenance-result-validation.json`.
8. Confirm `reviewer-evidence-packet.json` references these artifacts by fixed
   artifact name and schema identifier.
9. Record or inspect `reviewer-handoff-review-result.json` with the reviewer
   decision: `ACCEPT`, `REJECT`, or `NEEDS_FOLLOW_UP`.
10. Run `validate-review-result` to validate the saved review result artifact
    shape and review-boundary acknowledgements.
11. Run `validate-review-result-report` to validate the saved
    `validate-review-result --json` validation report shape.
12. Run `validate-reviewer-handoff-package` against `sample-artifact-manifest.json`
    and the sample base directory to validate the whole sample package
    structure, hashes, schemas, relationships, and safety boundaries.
13. Run `validate-quickstart-command-report` to validate the saved
    quickstart command validation report shape without re-running the original
    quickstart command guard.

## 1. Verify the Evidence Bundle strictly

Run strict verification with the public key obtained through the reviewer or
operator trust channel, and save the JSON result:

```bash
veritas-evidence-bundle verify \
  --bundle evidence-bundle.json \
  --public-key trusted-public-key.pem \
  --require-signature \
  --json \
  --output verification-result.json
```

The saved `verification-result.json` records the verification result for this
run. It is the only command in this walkthrough that performs cryptographic
Evidence Bundle verification. Later schema and provenance-validation commands
inspect saved artifacts; they do not re-run the bundle signature verification.

## 2. Review the Trusted Public Key Provenance Receipt

Review `trusted-public-key-provenance.json` before relying on the saved
verification result. The receipt should document the reviewer/operator trust
basis for `trusted-public-key.pem`, such as the approved trust channel,
approving identity, approval reference, received timestamp, and reviewer notes.

The receipt is not generated from the Evidence Bundle alone. A public key copied
only from the Evidence Bundle, bundle-adjacent material, or packet metadata is
not trusted by itself.

## 3. Validate key provenance correlation

After strict verification and receipt review, validate the receipt shape,
validate the saved verification-result shape, and correlate the saved public-key
fingerprints:

```bash
veritas-evidence-bundle validate-key-provenance \
  --receipt trusted-public-key-provenance.json \
  --verification-result verification-result.json \
  --json \
  --output key-provenance-validation.json
```

A passing `key-provenance-validation.json` supports correlation between the
Trusted Public Key Provenance Receipt and the strict verification result. It
still does not create trust, replace the out-of-band trust channel, prove
regulatory certification, or complete third-party audit approval.

## 4. Validate the saved key provenance validation report

Validate the saved `validate-key-provenance --json` report shape:

```bash
veritas-evidence-bundle validate-key-provenance-result \
  --result key-provenance-validation.json \
  --json \
  --output key-provenance-result-validation.json
```

This command validates the saved provenance-validation report shape only. It
does not re-run key provenance validation and does not re-run cryptographic
Evidence Bundle verification.

## 5. Confirm Reviewer Evidence Packet references

Confirm `reviewer-evidence-packet.json` includes the expected key provenance
references, when the packet declares optional `key_provenance` metadata. The
packet should reference stable artifact names and schema identifiers for:

- `trusted-public-key-provenance.json`
- `key-provenance-validation.json`
- `key-provenance-result-validation.json`

Reviewer Evidence Packets reference artifacts; they do not prove trust alone.
Packet metadata must not embed raw public key fingerprints, raw local file
paths, raw exception text, raw schema validator messages, or raw JSON values
copied from externally supplied artifacts.

## 6. Record the Reviewer Review Result

Use `reviewer-handoff-review-result.json` when the reviewer needs a
machine-readable Review Result / Acceptance Record. The artifact records what
was checked, the reviewer, reviewer scope, limitation acknowledgements, and the
decision value: `ACCEPT`, `REJECT`, or `NEEDS_FOLLOW_UP`. Validate the saved
artifact with:

```bash
veritas-evidence-bundle validate-review-result \
  --result reviewer-handoff-review-result.json \
  --json \
  --output reviewer-review-result-validation.json
```

Validate the saved review-result validation report shape:

```bash
veritas-evidence-bundle validate-review-result-report \
  --result reviewer-review-result-validation.json \
  --json \
  --output reviewer-review-result-report-validation.json
```

`validate-review-result` validates schema conformance, acknowledgement
structure, required artifact references, and forbidden sensitive/raw diagnostic
patterns. Its `--json` output has a stable JSON Schema contract at
[`schemas/reviewer_handoff_review_result_validation_report.schema.json`](../../../schemas/reviewer_handoff_review_result_validation_report.schema.json),
which validates the validation report shape. The report records validation
status, not cryptographic truth by itself. It records and checks review-result
structure only: it does not create trust, does not replace out-of-band public key
trust, does not prove regulatory certification, and is not completed third-party
audit approval. A reviewer decision depends on the reviewer's scope and
out-of-band public key trust context.


## 7. Validate the full reviewer handoff sample package

```bash
veritas-evidence-bundle validate-reviewer-handoff-package \
  --manifest samples/evidence_bundle/key_provenance_review/sample-artifact-manifest.json \
  --base-dir samples/evidence_bundle/key_provenance_review \
  --json \
  --output reviewer-handoff-package-validation.json
```

The package validator checks the sample manifest, manifest schema, artifact
presence under the declared base directory, SHA-256 digests, applicable artifact
schemas, expected artifact names, expected roles, expected schema IDs, expected
validator fields, synthetic placeholder fingerprints, and forbidden sensitive or
raw diagnostic patterns. The checked-in `reviewer-handoff-package-validation.json`
sample demonstrates the output shape of `validate-reviewer-handoff-package --json`.
Its boolean-only validation report records validation status only. It does not create trust, does not replace out-of-band public key
trust, does not prove regulatory certification, is not completed third-party
audit approval, and does not establish cryptographic truth by itself. Sample
hashes support sample integrity only.

## Artifact map

| artifact | produced by | validated by | schema | reviewer purpose |
|---|---|---|---|---|
| `verification-result.json` | `veritas-evidence-bundle verify --require-signature --json --output verification-result.json` | `veritas-evidence-bundle validate-result` and `veritas-evidence-bundle validate-key-provenance --verification-result verification-result.json` | [`schemas/evidence_bundle_verification_result.schema.json`](../../../schemas/evidence_bundle_verification_result.schema.json) | Records the strict Evidence Bundle verification run under the reviewer-supplied trusted public key. |
| `trusted-public-key-provenance.json` | Reviewer/operator trust process outside the Evidence Bundle | `veritas-evidence-bundle validate-key-provenance --receipt trusted-public-key-provenance.json` | [`schemas/trusted_public_key_provenance_receipt.schema.json`](../../../schemas/trusted_public_key_provenance_receipt.schema.json) | Records why the reviewer or operator trusted the public key used for strict verification. |
| `key-provenance-validation.json` | `veritas-evidence-bundle validate-key-provenance --json --output key-provenance-validation.json` | `veritas-evidence-bundle validate-key-provenance-result --result key-provenance-validation.json` | [`schemas/trusted_public_key_provenance_validation_report.schema.json`](../../../schemas/trusted_public_key_provenance_validation_report.schema.json) | Records receipt schema validity, verification-result schema validity, strict-authenticity checks, and fingerprint correlation status. |
| `key-provenance-result-validation.json` | `veritas-evidence-bundle validate-key-provenance-result --json --output key-provenance-result-validation.json` | Reviewer packet review and schema-aware audit tooling | [`schemas/trusted_public_key_provenance_result_validation_report.schema.json`](../../../schemas/trusted_public_key_provenance_result_validation_report.schema.json) | Records that the saved key provenance validation report itself matches the expected result-validation report shape. |
| `reviewer-evidence-packet.json` | Reviewer Evidence Packet export or assembly process | Reviewer packet validation/report tooling and reviewer inspection | [`docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json`](../demo/schemas/reviewer-evidence-packet-v1.schema.json) | Points reviewers to the saved artifacts; it is a navigation and evidence-packet reference, not standalone trust proof. |
| `reviewer-handoff-review-result.json` | Reviewer review process | `veritas-evidence-bundle validate-review-result --result reviewer-handoff-review-result.json` and reviewer inspection | [`schemas/reviewer_handoff_review_result.schema.json`](../../../schemas/reviewer_handoff_review_result.schema.json) | Records artifacts checked, limitations acknowledged, reviewer scope, and decision (`ACCEPT`, `REJECT`, or `NEEDS_FOLLOW_UP`); it records outcome, not cryptographic truth by itself. |
| `reviewer-review-result-validation.json` | `veritas-evidence-bundle validate-review-result --json --output reviewer-review-result-validation.json` | `veritas-evidence-bundle validate-review-result-report --result reviewer-review-result-validation.json` | [`schemas/reviewer_handoff_review_result_validation_report.schema.json`](../../../schemas/reviewer_handoff_review_result_validation_report.schema.json) | Records saved review-result validation-report structure and validation status only; it does not re-run reviewer review, create trust, replace out-of-band public key trust, prove regulatory certification, or establish cryptographic truth. |
| `reviewer-review-result-report-validation.json` | `veritas-evidence-bundle validate-review-result-report --json --output reviewer-review-result-report-validation.json` | CI sample validation and reviewer inspection | [`schemas/reviewer_handoff_review_result_report_validation_report.schema.json`](../../../schemas/reviewer_handoff_review_result_report_validation_report.schema.json) | Records second-level validation-report shape only; it does not create trust, replace out-of-band public key trust, prove regulatory certification, indicate completed third-party audit approval, or establish cryptographic truth. |
| `sample-artifact-manifest.json` | Illustrative sample set maintenance | `veritas-evidence-bundle validate-reviewer-handoff-package --manifest samples/evidence_bundle/key_provenance_review/sample-artifact-manifest.json --base-dir samples/evidence_bundle/key_provenance_review` and CI sample validation | [`schemas/trusted_public_key_provenance_review_sample_manifest.schema.json`](../../../schemas/trusted_public_key_provenance_review_sample_manifest.schema.json) | Indexes expected sample artifacts, roles, schema identifiers, and SHA-256 digests; hash matching supports sample integrity, not standalone trust. |
| `reviewer-handoff-package-validation.json` | `veritas-evidence-bundle validate-reviewer-handoff-package --json --output reviewer-handoff-package-validation.json` | Reviewer/operator inspection and CI-style sample validation | [`schemas/reviewer_handoff_package_validation_report.schema.json`](../../../schemas/reviewer_handoff_package_validation_report.schema.json) | Records package validation status for manifest, hashes, schemas, relationships, and safety boundaries only; it does not create trust, replace out-of-band public key trust, prove regulatory certification, indicate completed third-party audit approval, or establish cryptographic truth. |
| `reviewer-handoff-quickstart-command-validation.json` | `scripts/quality/check_reviewer_handoff_quickstart_command.py --json --output reviewer-handoff-quickstart-command-validation.json` | Reviewer/operator inspection, CI sample validation, deterministic regeneration check, and `veritas-evidence-bundle validate-quickstart-command-report` | [`schemas/reviewer_handoff_quickstart_command_validation_report.schema.json`](../../../schemas/reviewer_handoff_quickstart_command_validation_report.schema.json) | Shows the expected machine-readable quickstart command guard report shape for command presence, command executability, and output-contract status only; it is CI-validated but is not a trust source by itself and does not create trust, replace out-of-band public key trust, prove regulatory certification, indicate completed third-party audit approval, or establish cryptographic truth. |
| `reviewer-handoff-quickstart-command-report-validation.json` | `veritas-evidence-bundle validate-quickstart-command-report --json --output reviewer-handoff-quickstart-command-report-validation.json` | Reviewer/operator inspection, CI sample validation, and deterministic regeneration check | [`schemas/reviewer_handoff_quickstart_command_report_validation_report.schema.json`](../../../schemas/reviewer_handoff_quickstart_command_report_validation_report.schema.json) | Records second-level validation of the saved quickstart command validation report shape and fixed metadata only; it records validation status only and does not re-run the guard, create trust, replace out-of-band public key trust, prove regulatory certification, indicate completed third-party audit approval, or establish cryptographic truth. |


The checked-in reviewer handoff sample validation reports are CI-validated and
regeneration-checked against CLI behavior. The regeneration check recreates
`reviewer-review-result-validation.json`,
`reviewer-review-result-report-validation.json`, and
`reviewer-handoff-package-validation.json` from the sample inputs and compares
normalized JSON with the checked-in files. This reduces drift between CLI output
and documented samples, but validates sample reproducibility only. It does not
create trust, replace out-of-band public key trust, prove regulatory
certification, indicate completed third-party audit approval, or establish
cryptographic truth. Sample hashes support sample integrity only, and validation
reports record validation status, not cryptographic truth by themselves.

# Reviewer Handoff Sample Quickstart

This quickstart is the reviewer-facing entry point for the complete illustrative
Reviewer Handoff sample flow in
[`samples/evidence_bundle/key_provenance_review/`](../../../samples/evidence_bundle/key_provenance_review/).
It explains what to inspect, what to run, and how to read the checked-in sample
validation reports. Use it for sample orientation only.

## 1. Inspect the sample directory

Open `samples/evidence_bundle/key_provenance_review/` and confirm that the
sample folder contains the artifact map below. These files are placeholders that
show the expected handoff shape for reviewers and operators.

## 2. Validate the whole package

Run the package-level validator from the repository root. The command validates
sample structure and validation status only.

veritas-evidence-bundle validate-reviewer-handoff-package --manifest samples/evidence_bundle/key_provenance_review/sample-artifact-manifest.json --base-dir samples/evidence_bundle/key_provenance_review --json --output reviewer-handoff-package-validation.json

## 3. Inspect `reviewer-handoff-package-validation.json`

Open `reviewer-handoff-package-validation.json` after running the command, or
inspect the checked-in sample report in the sample directory. It records whether
package-level checks passed for the manifest, artifact references, sample file
hashes, schema contracts, relationships, and safety boundaries. It records
validation status only; it does not create trust or establish cryptographic
truth by itself.

## 4. Understand `reviewer-review-result-validation.json`

`reviewer-review-result-validation.json` is the saved
`validate-review-result --json` report for
`reviewer-handoff-review-result.json`. It validates the reviewer decision record
shape, required artifact references, decision values, reviewer scope, and
required limitation acknowledgements. Its diagnostics are privacy-preserving,
fixed, and boolean-only.

## 5. Understand `reviewer-review-result-report-validation.json`

`reviewer-review-result-report-validation.json` is the saved
`validate-review-result-report --json` report for the previous validation
report. It validates validation-report shape and validation status only. It does
not re-run reviewer approval, public key provenance review, or Evidence Bundle
verification.

## 6. Understand `sample-artifact-manifest.json`

`sample-artifact-manifest.json` indexes the sample artifacts, their roles,
schema identifiers, and SHA-256 hashes. The manifest lets the package validator
confirm that the sample artifact references are present and that sample hashes
match. Sample hashes support sample integrity only.

## 7. Understand the deterministic regeneration check

The deterministic regeneration check runs in CI through
`scripts/quality/check_reviewer_handoff_sample_regeneration.py`. It regenerates
the checked-in sample validation reports with the current CLI, normalizes the
JSON, and compares the regenerated reports with the repository copies. This
keeps sample reports aligned with current CLI behavior and confirms that
privacy-preserving diagnostics remain fixed and boolean-only.

## 8. Understand trust boundaries

The reviewer handoff sample package validates sample structure and validation
status only. It does not create trust, does not replace out-of-band public key
trust, does not prove regulatory certification, is not completed third-party
audit approval, and does not establish cryptographic truth by itself. Matching
fingerprints support correlation only, not standalone trust. Validation reports
record validation status only.

## Artifact map

- `verification-result.json`: strict evidence bundle verification result
- `trusted-public-key-provenance.json`: out-of-band public key provenance receipt
- `key-provenance-validation.json`: validates correlation between verification result and trusted key provenance
- `key-provenance-result-validation.json`: validates saved key-provenance validation report shape
- `reviewer-evidence-packet.json`: reviewer-facing packet index
- `reviewer-handoff-review-result.json`: reviewer decision record
- `reviewer-review-result-validation.json`: validates reviewer decision record
- `reviewer-review-result-report-validation.json`: validates saved reviewer-result validation report
- `reviewer-handoff-package-validation.json`: validates package-level structure/status
- `sample-artifact-manifest.json`: indexes sample artifacts, roles, schemas, and hashes
- `README.md`: sample explanation

## What this proves

- The sample package structure is valid.
- The sample artifact references are present.
- The sample hashes match.
- The sample schemas validate.
- The sample validation reports match current CLI behavior.
- Privacy-preserving diagnostics remain fixed and boolean-only.

## What this does not prove

- It does not create trust.
- It does not replace out-of-band public key trust.
- It does not prove regulatory certification.
- It is not completed third-party audit approval.
- It does not establish cryptographic truth by itself.
- Sample hashes support sample integrity only.
- Matching fingerprints support correlation only, not standalone trust.
- Validation reports record validation status only.

# Trusted Public Key Provenance reviewer sample artifacts

This directory contains an illustrative sample artifact chain for the Trusted
Public Key Provenance reviewer walkthrough. Repository path:
`samples/evidence_bundle/key_provenance_review/`.

Reviewer-facing quickstart: [Reviewer Handoff Sample Quickstart](../../../docs/en/validation/reviewer-handoff-sample-quickstart.md). For the broader handoff context, see the [Reviewer Handoff Guide](../../../docs/en/validation/reviewer-handoff-guide.md).

> Illustrative sample only. Not production evidence, not regulatory
> certification, and not completed third-party audit approval.

## Artifact chain

```text
verification-result.json
→ trusted-public-key-provenance.json
→ key-provenance-validation.json
→ key-provenance-result-validation.json
→ reviewer-evidence-packet.json
→ reviewer-handoff-review-result.json
→ reviewer-review-result-validation.json
→ reviewer-review-result-report-validation.json
→ reviewer-handoff-package-validation.json
→ reviewer-handoff-quickstart-command-validation.json
→ reviewer-handoff-quickstart-command-report-validation.json
```

## Files

| file | purpose |
|---|---|
| `verification-result.json` | Illustrates the saved strict Evidence Bundle verification result under a reviewer-supplied trusted public key. |
| `trusted-public-key-provenance.json` | Illustrates the reviewer/operator trust-channel receipt that correlates to the saved verification result fingerprint. |
| `key-provenance-validation.json` | Illustrates the saved `validate-key-provenance --json` report showing schema and fingerprint-correlation checks. |
| `key-provenance-result-validation.json` | Illustrates the saved `validate-key-provenance-result --json` report for the provenance-validation report. |
| `reviewer-evidence-packet.json` | Illustrates Reviewer Evidence Packet references to the key provenance artifacts. |
| `reviewer-handoff-review-result.json` | Illustrates a reviewer-facing Review Result / Acceptance Record for what was checked and whether follow-up remains. |
| `reviewer-review-result-validation.json` | Illustrates saved `validate-review-result --json` output shape and validation status for the Review Result. |
| `reviewer-review-result-report-validation.json` | Illustrates saved `validate-review-result-report --json` output shape for the saved Review Result validation report. |
| `reviewer-handoff-package-validation.json` | Illustrates saved `validate-reviewer-handoff-package --json` output shape for manifest, hash, schema, relationship, and safety-boundary status only. |
| `reviewer-handoff-quickstart-command-validation.json` | Records the checked-in quickstart command guard result for command presence, command executability, and output-contract status only. |
| `reviewer-handoff-quickstart-command-report-validation.json` | Records second-level validation of the saved quickstart command validation report shape only. |
| `sample-artifact-manifest.json` | Indexes the illustrative sample artifacts, roles, schema identifiers, validators, and SHA-256 digests. |

## Sample Artifact Manifest

`sample-artifact-manifest.json` is an index for this illustrative sample set.
It lists the expected artifact names, reviewer roles, schema identifiers, and
SHA-256 digests for the files in this directory, including saved reviewer
result validation reports, the saved package validation report, the checked-in
quickstart command validation report, and its second-level report validation
artifact. The manifest checks sample structure and file
integrity only. It does not create trust, does not replace
out-of-band public key trust, is not regulatory certification, and is not
completed third-party audit approval.

## Package validation command

Reviewers and operators can validate the whole illustrative handoff package from
the manifest:

```bash
veritas-evidence-bundle validate-reviewer-handoff-package \
  --manifest samples/evidence_bundle/key_provenance_review/sample-artifact-manifest.json \
  --base-dir samples/evidence_bundle/key_provenance_review
```

For a machine-readable validation report, add `--json`; to save the exact same
JSON emitted on stdout, add `--output reviewer-handoff-package-validation.json`.
This sample pack checks in `reviewer-handoff-package-validation.json` as a safe
placeholder artifact demonstrating the output shape of
`validate-reviewer-handoff-package --json`.
The command validates the manifest, manifest schema, artifact presence under
`--base-dir`, SHA-256 digests, applicable artifact schemas, expected roles,
expected schema identifiers, expected validator names, synthetic placeholder
fingerprints, and safety boundaries. Its report records validation status only;
it does not create trust, does not replace out-of-band public key trust, does
not prove regulatory certification, does not indicate completed third-party
audit approval, and does not establish cryptographic truth by itself. Sample
hashes support sample integrity only.

## Quickstart command guard JSON report

The reviewer handoff quickstart command guard
(`scripts/quality/check_reviewer_handoff_quickstart_command.py`) supports
`--json` and optional `--output reviewer-handoff-quickstart-command-validation.json`
for CI-safe machine-readable status. The report validates command presence,
command executability, and the package-validation output contract only, using
[`schemas/reviewer_handoff_quickstart_command_validation_report.schema.json`](../../../schemas/reviewer_handoff_quickstart_command_validation_report.schema.json).
The checked-in sample report
`reviewer-handoff-quickstart-command-validation.json` shows the expected
machine-readable report shape and is CI-validated as part of this sample
package. It records validation status only and is not a trust source by itself;
it does not create trust, does not replace out-of-band public key trust, does
not prove regulatory certification, is not completed third-party audit approval,
and does not establish cryptographic truth by itself.

The saved quickstart command validation report can also be independently
validated without re-running the original quickstart command guard:

```bash
veritas-evidence-bundle validate-quickstart-command-report \
  --result samples/evidence_bundle/key_provenance_review/reviewer-handoff-quickstart-command-validation.json \
  --json \
  --output samples/evidence_bundle/key_provenance_review/reviewer-handoff-quickstart-command-report-validation.json
```

The second-level report validates the saved report shape and fixed metadata
only. It records validation status only; it does not create trust, does not
replace out-of-band public key trust, does not prove regulatory certification,
is not completed third-party audit approval, and does not establish
cryptographic truth by itself.

## Regeneration check

CI validates the checked-in reviewer handoff sample reports for schema and
sample-pack structure, and also regeneration-checks them against current CLI
behavior with `scripts/quality/check_reviewer_handoff_sample_regeneration.py`.
The checker regenerates `reviewer-review-result-validation.json`,
`reviewer-review-result-report-validation.json`,
`reviewer-handoff-package-validation.json`,
`reviewer-handoff-quickstart-command-validation.json`, and
`reviewer-handoff-quickstart-command-report-validation.json` in a temporary
directory and compares
normalized JSON with the checked-in files. This reduces drift between CLI output
and documented samples. It validates sample reproducibility only; it does not
create trust, replace out-of-band public key trust, prove regulatory
certification, indicate completed third-party audit approval, or establish
cryptographic truth. Sample hashes support sample integrity only, and validation
reports record validation status, not cryptographic truth by themselves.

## Boundaries

- These samples are illustrative only.
- These samples do not create trust.
- These samples do not replace out-of-band public key trust.
- These samples do not prove regulatory certification.
- These samples are not completed third-party audit approval.
- Saved reviewer result validation reports demonstrate validation output shape
  only.
- The saved package validation report demonstrates validation output shape only.
- The saved quickstart command validation report demonstrates expected
  machine-readable guard output shape only.
- The saved quickstart command report validation report validates the saved
  quickstart report shape only.
- Validation reports record validation status, not cryptographic truth by
  themselves.
- Sample hashes support sample integrity only.
- Matching fingerprints support correlation, not standalone trust.
- Placeholder fingerprints and hashes are synthetic-looking values used only to
  satisfy schemas and show relationships.
- The samples intentionally avoid real keys, real fingerprints, customer data,
  secrets, absolute local paths, exception text, and raw schema validator
  messages.

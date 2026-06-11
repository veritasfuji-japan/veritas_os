# Reviewer Handoff Guide for Trusted Public Key Provenance

This guide explains what to send to a reviewer for the Trusted Public Key
Provenance sample pack and Evidence Bundle review flow, what the reviewer can
verify, and what the artifacts do not prove. It is a reviewer-facing handoff
map, not a trust source. The checked-in illustrative sample pack lives at
`samples/evidence_bundle/key_provenance_review/` and now includes saved reviewer
result validation report artifacts.

For a concise runbook for this checked-in sample package, see the
[Reviewer Handoff Sample Quickstart](reviewer-handoff-sample-quickstart.md).

Use placeholder artifact names only. Do not add real keys, real fingerprints,
real secrets, local absolute paths, customer data, exception text, raw schema
validator messages, or externally supplied raw JSON values to examples,
Reviewer Evidence Packet metadata, or review notes.

## Review package contents

Send the reviewer a folder or archive containing these placeholder-named
artifacts:

| Artifact | Purpose |
| --- | --- |
| `evidence-bundle.json` | Evidence Bundle under review. |
| `verification-result.json` | Saved strict Evidence Bundle verification result. |
| `trusted-public-key-provenance.json` | Trusted Public Key Provenance Receipt documenting the out-of-band trust channel for the public key used during strict verification. |
| `key-provenance-validation.json` | Saved `validate-key-provenance` report for receipt shape, verification-result shape, and fingerprint correlation. |
| `key-provenance-result-validation.json` | Saved `validate-key-provenance-result` report confirming the saved validation report schema shape. |
| `reviewer-evidence-packet.json` | Reviewer Evidence Packet that references the key provenance artifacts by stable artifact name and schema identifier. |
| `sample-artifact-manifest.json` | Sample artifact manifest listing expected sample artifacts and SHA-256 digests for sample integrity checks. |
| `reviewer-handoff-review-result.json` | Reviewer Review Result / Acceptance Record that records what was checked and the reviewer decision (`ACCEPT`, `REJECT`, or `NEEDS_FOLLOW_UP`). |
| `reviewer-review-result-validation.json` | Saved `validate-review-result --json` output demonstrating validation output shape and validation status only. |
| `reviewer-review-result-report-validation.json` | Saved `validate-review-result-report --json` output demonstrating second-level validation report shape only. |

The reviewer must obtain `trusted-public-key.pem` through an approved
out-of-band reviewer/operator trust channel before relying on manifest signature
verification. Do not treat a public key copied from the Evidence Bundle or from
bundle-adjacent files as trusted by itself.

## Copyable command examples

Run strict Evidence Bundle verification with the reviewer-supplied trusted
public key and save the JSON result:

```bash
veritas-evidence-bundle verify \
  --bundle evidence-bundle.json \
  --public-key trusted-public-key.pem \
  --require-signature \
  --json \
  --output verification-result.json
```

Validate the Trusted Public Key Provenance Receipt against the saved strict
verification result:

```bash
veritas-evidence-bundle validate-key-provenance \
  --receipt trusted-public-key-provenance.json \
  --verification-result verification-result.json \
  --json \
  --output key-provenance-validation.json
```

Validate the saved key provenance validation report schema:

```bash
veritas-evidence-bundle validate-key-provenance-result \
  --result key-provenance-validation.json \
  --json \
  --output key-provenance-result-validation.json
```

Validate the saved Reviewer Review Result artifact:

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

`validate-review-result` checks the saved review result artifact against
[`schemas/reviewer_handoff_review_result.schema.json`](../../../schemas/reviewer_handoff_review_result.schema.json)
and verifies the decision enum, required artifact references, required boolean
limitation acknowledgements, and forbidden sensitive/raw diagnostic patterns.
It records and checks review-result structure only: it does not create trust,
does not replace out-of-band public key trust, does not prove regulatory
certification, is not completed third-party audit approval, and does not
establish cryptographic truth by itself. The `--json` output has a stable JSON
Schema contract at
[`schemas/reviewer_handoff_review_result_validation_report.schema.json`](../../../schemas/reviewer_handoff_review_result_validation_report.schema.json).
That schema validates the validation report shape and records validation status;
it does not create trust, replace out-of-band public key trust, prove regulatory
certification, indicate completed third-party audit approval, or establish
cryptographic truth by itself. JSON output uses booleans, fixed schema
identifiers, and fixed diagnostics only.

`validate-review-result-report` validates the saved validation report emitted by
`validate-review-result --json` against
[`schemas/reviewer_handoff_review_result_validation_report.schema.json`](../../../schemas/reviewer_handoff_review_result_validation_report.schema.json).
It validates report shape only; it does not re-run reviewer review, create
trust, replace out-of-band public key trust, prove regulatory certification,
indicate completed third-party audit approval, or establish cryptographic truth.
It records validation-report structure, not cryptographic truth by itself. Its
own `--json` output has a schema at
[`schemas/reviewer_handoff_review_result_report_validation_report.schema.json`](../../../schemas/reviewer_handoff_review_result_report_validation_report.schema.json)
and remains boolean-only with fixed diagnostics.

## What the reviewer can verify

The package supports these reviewer checks:

- Evidence Bundle file/hash integrity.
- Manifest signature verification when a trusted public key is provided through
  an out-of-band reviewer/operator trust channel.
- Public key provenance receipt shape.
- Correlation between `verification-result.json` and
  `trusted-public-key-provenance.json` through matching public key fingerprint
  fields.
- Saved validation report schema conformance for
  `key-provenance-validation.json`,
  `key-provenance-result-validation.json`,
  `reviewer-review-result-validation.json`, and
  `reviewer-review-result-report-validation.json`.
- Reviewer Evidence Packet references to the expected key provenance artifacts
  by stable artifact name and schema identifier.
- Reviewer Review Result / Acceptance Record contents, including checked
  artifacts, decision (`ACCEPT`, `REJECT`, or `NEEDS_FOLLOW_UP`), limitations,
  reviewer scope, and out-of-band trust context.
- Sample artifact manifest SHA-256 consistency for the illustrative sample set.
- Whole-package sample validation through `veritas-evidence-bundle validate-reviewer-handoff-package`, covering manifest, hashes, schemas, relationships, and safety boundaries.
- CI regeneration checking for the saved reviewer handoff sample validation reports, confirming they can be regenerated from the CLI and still match the checked-in sample outputs.
- Machine-readable quickstart command guard reporting through `scripts/quality/check_reviewer_handoff_quickstart_command.py --json`, validating command presence, command executability, and output-contract status only.

## CI regeneration check for saved sample reports

The checked-in sample reports (`reviewer-review-result-validation.json`,
`reviewer-review-result-report-validation.json`, and
`reviewer-handoff-package-validation.json`) are CI-validated for sample-pack
structure and are also regeneration-checked against CLI behavior. The
regeneration check reduces drift between CLI output and documented samples by
recreating the reports in a temporary directory and comparing normalized JSON
with the repository copies. This validates sample reproducibility only. It does
not create trust, replace out-of-band public key trust, prove regulatory
certification, indicate completed third-party audit approval, or establish
cryptographic truth. Sample hashes support sample integrity only, and validation
reports record validation status rather than cryptographic truth by themselves.

## What the reviewer cannot infer from these artifacts alone

Keep these boundaries explicit in reviewer communications:

- These artifacts do not create trust by themselves.
- They do not replace out-of-band public key trust.
- They do not prove regulatory certification.
- They are not completed third-party audit approval.
- Matching fingerprints support correlation, not standalone trust.
- Saved reviewer result validation reports demonstrate validation output shape
  only and record validation status, not cryptographic truth by themselves.
- The saved `reviewer-handoff-package-validation.json` artifact demonstrates
  `validate-reviewer-handoff-package --json` output shape and package
  validation status only.
- Sample artifact hashes prove sample integrity only, not production evidence
  authenticity.
- Reviewer Evidence Packets reference artifacts; they do not prove trust alone.
- Reviewer Review Results record review outcome only; they are not
  cryptographic truth by themselves and reviewer decisions depend on reviewer
  scope and out-of-band public key trust context.

## Reviewer checklist

| Step | Artifact | Command or check | Expected result | Boundary |
| --- | --- | --- | --- | --- |
| Verify Evidence Bundle | `evidence-bundle.json` | Run `veritas-evidence-bundle verify --require-signature --json --output verification-result.json` with the reviewer-supplied trusted public key. | File/hash checks pass and the manifest signature verifies under the trusted public key. | Hash integrity is not authenticity without out-of-band public key trust. |
| Validate `verification-result.json` | `verification-result.json` | Confirm the saved result reports strict verification success and includes the public key fingerprint field expected by the schema. | The saved result is suitable input for key provenance validation. | The result records which key was used; it does not establish why the key is trusted. |
| Review `trusted-public-key-provenance.json` | `trusted-public-key-provenance.json` | Review receipt shape, trust-channel fields, reviewer/operator approval fields, and notes. | The receipt records the out-of-band trust rationale for the public key. | The receipt does not re-run cryptographic verification and does not create trust by itself. |
| Run `validate-key-provenance` | `trusted-public-key-provenance.json`, `verification-result.json` | Run the copyable `validate-key-provenance` command above. | Receipt shape, verification-result shape, strict authenticity flags, and fingerprint correlation pass. | Matching fingerprints support correlation, not standalone trust. |
| Run `validate-key-provenance-result` | `key-provenance-validation.json` | Run the copyable `validate-key-provenance-result` command above. | The saved validation report conforms to its schema. | Schema conformance does not prove regulatory certification or third-party audit approval. |
| Run `validate-review-result` | `reviewer-handoff-review-result.json` | Run the copyable `validate-review-result` command above. | The saved review result conforms to its schema and emits `reviewer-review-result-validation.json`. | The report demonstrates validation output shape and status only; it does not create trust, replace out-of-band public key trust, prove regulatory certification, indicate completed third-party audit approval, or establish cryptographic truth. |
| Run `validate-review-result-report` | `reviewer-review-result-validation.json` | Run the copyable `validate-review-result-report` command above. | The saved review-result validation report conforms to its schema and emits `reviewer-review-result-report-validation.json`. | Schema conformance records validation-report structure only; it does not re-run reviewer review, create trust, replace out-of-band public key trust, prove regulatory certification, indicate completed third-party audit approval, or establish cryptographic truth. |
| Review `reviewer-evidence-packet.json` | `reviewer-evidence-packet.json` | Confirm key provenance references use only expected artifact names and schema identifiers. | The packet points reviewers to `trusted-public-key-provenance.json`, `key-provenance-validation.json`, and `key-provenance-result-validation.json`. | Reviewer Evidence Packets reference artifacts; they do not prove trust alone. |
| Review `sample-artifact-manifest.json` | `sample-artifact-manifest.json` | Confirm listed sample artifacts and SHA-256 digests match the provided sample pack. | Sample artifact manifest SHA-256 consistency is preserved. | Sample artifact hashes prove sample integrity only, not production evidence authenticity. |
| Validate reviewer handoff package | `sample-artifact-manifest.json` and sample directory | Run `veritas-evidence-bundle validate-reviewer-handoff-package --manifest samples/evidence_bundle/key_provenance_review/sample-artifact-manifest.json --base-dir samples/evidence_bundle/key_provenance_review --json --output reviewer-handoff-package-validation.json`. | Manifest, hashes, schemas, expected relationships, validator names, synthetic placeholders, and safety boundaries pass. | Package validation records sample validation status only; it does not create trust, replace out-of-band public key trust, prove regulatory certification, indicate completed third-party audit approval, or establish cryptographic truth. |
| Record `reviewer-handoff-review-result.json` | `reviewer-handoff-review-result.json` | Record the artifacts checked, reviewer scope, limitation acknowledgements, and decision (`ACCEPT`, `REJECT`, or `NEEDS_FOLLOW_UP`). | The review outcome is machine-readable and tied to the reviewer's stated scope and out-of-band trust context. | The record is not certification, regulatory approval, completed third-party audit approval, or cryptographic truth by itself. |
| Confirm CI sample validation status | CI sample validation logs or status checks | Confirm the sample validation check completed successfully for the submitted commit. | CI checked sample schema conformance, fixed references, manifest entries, and sample hashes. | CI sample validation does not create trust, replace out-of-band public key trust, prove regulatory certification, or indicate completed third-party audit approval. |
| Inspect quickstart command guard JSON | `scripts/quality/check_reviewer_handoff_quickstart_command.py --json` output | Optionally run `scripts/quality/check_reviewer_handoff_quickstart_command.py --json --output reviewer-handoff-quickstart-command-validation.json`. | The guard reports command presence, command executability, and output-contract validation status under `schemas/reviewer_handoff_quickstart_command_validation_report.schema.json`. | The report records validation status only; it does not create trust, replace out-of-band public key trust, prove regulatory certification, indicate completed third-party audit approval, or establish cryptographic truth. |


## Reviewer handoff package validation CLI

`veritas-evidence-bundle validate-reviewer-handoff-package` validates the
illustrative sample handoff package structure from `sample-artifact-manifest.json`
and `--base-dir`. It checks manifest parsing, the manifest schema, artifact
containment, artifact presence, SHA-256 digests, applicable artifact schemas,
expected artifact names, expected roles, expected schema IDs, expected validator
fields, synthetic placeholder fingerprints, and forbidden sensitive/raw text
patterns. Add `--json` for a boolean-only report and `--output` to persist the
same JSON report emitted on stdout. The sample pack now includes the saved
placeholder artifact `reviewer-handoff-package-validation.json` to demonstrate
that output shape.

This command validates sample package integrity and safety boundaries only. It
does not create trust, does not replace out-of-band public key trust, does not
prove regulatory certification, does not represent completed third-party audit
approval, and does not establish cryptographic truth by itself. Sample hashes
support sample integrity only; validation reports record validation status only.

The reviewer handoff quickstart command guard also supports a machine-readable
JSON mode: run `scripts/quality/check_reviewer_handoff_quickstart_command.py --json`
or add `--output reviewer-handoff-quickstart-command-validation.json` to save the
same normalized report. Its schema is
[`schemas/reviewer_handoff_quickstart_command_validation_report.schema.json`](../../../schemas/reviewer_handoff_quickstart_command_validation_report.schema.json).
The guard report validates command presence, command executability, and output
contract status only. It does not create trust, does not replace out-of-band
public key trust, does not prove regulatory certification, is not completed
third-party audit approval, and does not establish cryptographic truth by itself.

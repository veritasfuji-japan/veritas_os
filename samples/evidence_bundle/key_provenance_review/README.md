# Trusted Public Key Provenance reviewer sample artifacts

This directory contains an illustrative sample artifact chain for the Trusted
Public Key Provenance reviewer walkthrough. Repository path:
`samples/evidence_bundle/key_provenance_review/`.

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
| `sample-artifact-manifest.json` | Indexes the illustrative sample artifacts, roles, schema identifiers, and SHA-256 digests. |

## Sample Artifact Manifest

`sample-artifact-manifest.json` is an index for this illustrative sample set.
It lists the expected artifact names, reviewer roles, schema identifiers, and
SHA-256 digests for the files in this directory, including saved reviewer
result validation reports. The manifest checks sample structure and file
integrity only. It does not create trust, does not replace
out-of-band public key trust, is not regulatory certification, and is not
completed third-party audit approval.

## Boundaries

- These samples are illustrative only.
- These samples do not create trust.
- These samples do not replace out-of-band public key trust.
- These samples do not prove regulatory certification.
- These samples are not completed third-party audit approval.
- Saved reviewer result validation reports demonstrate validation output shape
  only.
- Validation reports record validation status, not cryptographic truth by
  themselves.
- Sample hashes support sample integrity only.
- Matching fingerprints support correlation, not standalone trust.
- Placeholder fingerprints and hashes are synthetic-looking values used only to
  satisfy schemas and show relationships.
- The samples intentionally avoid real keys, real fingerprints, customer data,
  secrets, absolute local paths, exception text, and raw schema validator
  messages.

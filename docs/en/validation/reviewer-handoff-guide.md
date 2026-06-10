# Reviewer Handoff Guide for Trusted Public Key Provenance

This guide explains what to send to a reviewer for the Trusted Public Key
Provenance sample pack and Evidence Bundle review flow, what the reviewer can
verify, and what the artifacts do not prove. It is a reviewer-facing handoff
map, not a trust source.

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

`validate-review-result` checks the saved review result artifact against
[`schemas/reviewer_handoff_review_result.schema.json`](../../../schemas/reviewer_handoff_review_result.schema.json)
and verifies the decision enum, required artifact references, required boolean
limitation acknowledgements, and forbidden sensitive/raw diagnostic patterns.
It records and checks review-result structure only: it does not create trust,
does not replace out-of-band public key trust, does not prove regulatory
certification, is not completed third-party audit approval, and does not
establish cryptographic truth by itself. JSON output uses booleans, fixed schema
identifiers, and fixed diagnostics only.

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
  `key-provenance-validation.json` and
  `key-provenance-result-validation.json`.
- Reviewer Evidence Packet references to the expected key provenance artifacts
  by stable artifact name and schema identifier.
- Reviewer Review Result / Acceptance Record contents, including checked
  artifacts, decision (`ACCEPT`, `REJECT`, or `NEEDS_FOLLOW_UP`), limitations,
  reviewer scope, and out-of-band trust context.
- Sample artifact manifest SHA-256 consistency for the illustrative sample set.

## What the reviewer cannot infer from these artifacts alone

Keep these boundaries explicit in reviewer communications:

- These artifacts do not create trust by themselves.
- They do not replace out-of-band public key trust.
- They do not prove regulatory certification.
- They are not completed third-party audit approval.
- Matching fingerprints support correlation, not standalone trust.
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
| Review `reviewer-evidence-packet.json` | `reviewer-evidence-packet.json` | Confirm key provenance references use only expected artifact names and schema identifiers. | The packet points reviewers to `trusted-public-key-provenance.json`, `key-provenance-validation.json`, and `key-provenance-result-validation.json`. | Reviewer Evidence Packets reference artifacts; they do not prove trust alone. |
| Review `sample-artifact-manifest.json` | `sample-artifact-manifest.json` | Confirm listed sample artifacts and SHA-256 digests match the provided sample pack. | Sample artifact manifest SHA-256 consistency is preserved. | Sample artifact hashes prove sample integrity only, not production evidence authenticity. |
| Record `reviewer-handoff-review-result.json` | `reviewer-handoff-review-result.json` | Record the artifacts checked, reviewer scope, limitation acknowledgements, and decision (`ACCEPT`, `REJECT`, or `NEEDS_FOLLOW_UP`). | The review outcome is machine-readable and tied to the reviewer's stated scope and out-of-band trust context. | The record is not certification, regulatory approval, completed third-party audit approval, or cryptographic truth by itself. |
| Confirm CI sample validation status | CI sample validation logs or status checks | Confirm the sample validation check completed successfully for the submitted commit. | CI checked sample schema conformance, fixed references, manifest entries, and sample hashes. | CI sample validation does not create trust, replace out-of-band public key trust, prove regulatory certification, or indicate completed third-party audit approval. |

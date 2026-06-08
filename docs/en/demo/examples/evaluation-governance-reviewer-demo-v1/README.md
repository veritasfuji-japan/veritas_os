# Evaluation Governance Reviewer Demo v1

This directory contains a synthetic end-to-end offline reviewer demo for the
Evaluation Governance helper chain. It generates the Evaluation Governance
offline chain and then generates a Reviewer Evidence Packet from that chain.

The demo is intentionally narrow in v1:

- It is non-runtime and non-enforcing.
- It does not call `/v1/decide`.
- It does not change runtime admissibility behavior.
- It does not prove legitimacy.
- It does not certify regulatory compliance.
- It does not dereference external artifact references.
- It does not require network access.
- It does not include secrets or PII.

## Generate to a temporary output directory

```bash
python scripts/demo/run_evaluation_governance_reviewer_demo.py \
  --input-dir docs/en/demo/examples/evaluation-governance-offline-chain-v1 \
  --output-dir /tmp/evaluation-governance-reviewer-demo
```

## Regenerate checked-in example outputs intentionally

```bash
python scripts/demo/run_evaluation_governance_reviewer_demo.py \
  --input-dir docs/en/demo/examples/evaluation-governance-offline-chain-v1 \
  --write-example-output
```

## Run the full demo suite

```bash
python scripts/demo/run_evaluation_governance_reviewer_demo_suite.py \
  --input-dir docs/en/demo/examples/evaluation-governance-offline-chain-v1 \
  --write-example-output
```

This regenerates the checked-in generated examples, validates them, and writes
`generated/reviewer-demo-report.generated.example.md`.

## Validate checked-in generated examples

```bash
python scripts/demo/validate_evaluation_governance_reviewer_demo.py \
  --demo-dir docs/en/demo/examples/evaluation-governance-reviewer-demo-v1/generated
```

The validator checks expected files, schema shape where schemas exist,
non-runtime / non-enforcing boundaries, and Reviewer Evidence Packet
attachments. It does not establish legitimacy, certify compliance, or call
`/v1/decide`.

## Generate the checked-in reviewer report example

```bash
python scripts/demo/generate_evaluation_governance_reviewer_demo_report.py \
  --demo-dir docs/en/demo/examples/evaluation-governance-reviewer-demo-v1/generated \
  --output docs/en/demo/examples/evaluation-governance-reviewer-demo-v1/generated/reviewer-demo-report.generated.example.md
```

This report is a human-readable Markdown summary for reviewers. It does not
establish legitimacy, certify compliance, or call `/v1/decide`.

## Checked-in generated examples

The files under [`generated/`](generated/) are checked in for reviewer
readability. They show the full reviewer-facing output directory produced from
synthetic local inputs:

- Evaluation Governance offline chain artifacts
- `chain-manifest.generated.example.json`
- `reviewer-evidence-packet.generated.example.json`
- `demo-summary.generated.example.json`

The helper validates schema shape through the underlying helper chain where
validation is available. The helper does not establish present legitimacy and
does not enforce runtime decisions.

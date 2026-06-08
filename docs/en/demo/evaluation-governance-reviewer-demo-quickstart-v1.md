# Evaluation Governance Reviewer Demo Quickstart v1

## 1. Purpose

This quickstart shows how to run the synthetic, offline Evaluation Governance reviewer demo.

The demo generates reviewer-facing artifacts for:

- Outcome Delta Attribution
- Evaluation Drift Detection
- Trajectory-Level Admissibility Monitor
- Legitimacy Impact Review
- Chain Manifest
- Reviewer Evidence Packet
- Demo Summary

## 2. What this demo demonstrates

The demo follows this end-to-end reviewer path:

```text
Evaluation Receipt
-> Outcome Delta Attribution
-> Evaluation Drift Detection
-> Trajectory-Level Admissibility Monitor
-> Legitimacy Impact Review
-> Reviewer Evidence Packet
```

This helps reviewers inspect how VERITAS represents:

- authority and evaluator evidence
- outcome changes
- drift signals
- trajectory-level admissibility movement
- legitimacy-impacting changes
- reviewer evidence attachments

## 3. Important boundary

This demo is synthetic.
This demo is offline.
This demo is non-runtime.
This demo is non-enforcing in v1.
It does not call `/v1/decide`.
It does not change runtime admissibility.
It does not establish legitimacy.
It does not certify regulatory compliance.
It does not dereference external artifact refs.
It does not require network access.
It does not contain secrets or PII.

## 4. Run the demo

Run the reviewer demo with a temporary output directory:

```bash
python scripts/demo/run_evaluation_governance_reviewer_demo.py \
  --input-dir docs/en/demo/examples/evaluation-governance-offline-chain-v1 \
  --output-dir /tmp/evaluation-governance-reviewer-demo
```

This writes generated reviewer-facing artifacts to:

```text
/tmp/evaluation-governance-reviewer-demo
```

## 5. Validate the generated demo output

```bash
python scripts/demo/validate_evaluation_governance_reviewer_demo.py \
  --demo-dir /tmp/evaluation-governance-reviewer-demo
```

This local validator checks expected files, schema shape where schemas exist,
non-runtime / non-enforcing boundaries, and Reviewer Evidence Packet
attachments. It does not establish legitimacy, does not certify compliance, and
does not call `/v1/decide`.

## 6. Generate a reviewer report

```bash
python scripts/demo/generate_evaluation_governance_reviewer_demo_report.py \
  --demo-dir /tmp/evaluation-governance-reviewer-demo \
  --output /tmp/evaluation-governance-reviewer-demo/reviewer-demo-report.md
```

This creates a human-readable Markdown summary of the chain manifest,
Reviewer Evidence Packet, trajectory monitor, and legitimacy impact review.
It does not establish legitimacy, does not certify compliance, and does not
call `/v1/decide`.

## 7. Run the full demo suite

Recommended reviewer command:

```bash
python scripts/demo/run_evaluation_governance_reviewer_demo_suite.py \
  --input-dir docs/en/demo/examples/evaluation-governance-offline-chain-v1 \
  --output-dir /tmp/evaluation-governance-reviewer-demo
```

This runs generation, validation, and Markdown report generation in one
synthetic offline workflow. It is non-runtime and non-enforcing, does not call
`/v1/decide`, does not establish legitimacy, and does not certify compliance.

Maintainers can intentionally refresh checked-in generated examples with:

```bash
python scripts/demo/run_evaluation_governance_reviewer_demo_suite.py \
  --input-dir docs/en/demo/examples/evaluation-governance-offline-chain-v1 \
  --write-example-output
```

`--write-example-output` intentionally updates checked-in generated examples.
Normal reviewers should prefer `--output-dir`.

## 8. Expected outputs

The output directory should contain:

```text
outcome-delta-attribution-1.generated.example.json
outcome-delta-attribution-2.generated.example.json
evaluation-drift-detection-1.generated.example.json
evaluation-drift-detection-2.generated.example.json
trajectory-admissibility-monitor.generated.example.json
legitimacy-impact-review.generated.example.json
chain-manifest.generated.example.json
reviewer-evidence-packet.generated.example.json
demo-summary.generated.example.json
```

## 9. What reviewers should inspect first

Recommended inspection order:

1. `demo-summary.generated.example.json`
   - confirms non-runtime and non-enforcing demo boundaries
2. `chain-manifest.generated.example.json`
   - lists generated chain artifacts
3. `reviewer-evidence-packet.generated.example.json`
   - shows Evaluation Governance artifacts attached as reviewer evidence
4. `trajectory-admissibility-monitor.generated.example.json`
   - shows trajectory-level admissibility movement
5. `legitimacy-impact-review.generated.example.json`
   - shows legitimacy-impacting change signals

## 10. Regenerate checked-in examples intentionally

Maintainers can intentionally regenerate checked-in example outputs with:

```bash
python scripts/demo/run_evaluation_governance_reviewer_demo.py \
  --input-dir docs/en/demo/examples/evaluation-governance-offline-chain-v1 \
  --write-example-output
```

This intentionally updates checked-in example outputs.
Normal reviewers should prefer `--output-dir`.
This mode exists for maintainers.

## 11. Relationship to Reviewer Evidence Packet

The Reviewer Evidence Packet can include optional `evaluation_governance_artifacts`.
The generated packet attaches the Evaluation Governance chain artifacts for review.
These attachments are optional reviewer evidence in v1.
They are not mandatory runtime outputs.

See:

- [Reviewer Evidence Packet v1](reviewer-evidence-packet.md)
- [Evaluation Governance offline-chain Reviewer Evidence Packet example](examples/evaluation-governance-chain-reviewer-packet-v1/README.md)

## 12. Relationship to Evaluation Governance overview

The Evaluation Governance overview explains the artifact chain.
This quickstart explains how to run the synthetic reviewer demo.

See:

- [Evaluation Governance Overview v1](../architecture/evaluation-governance-overview-v1.md)

## 13. Troubleshooting

- If Python cannot import dependencies, run the repository's normal development setup first.
- If output files are not created, confirm `--output-dir` is provided.
- If trying to write checked-in examples, use `--write-example-output`.
- The demo should not require network access.

## 14. Non-goals

- This quickstart does not claim regulatory compliance.
- This quickstart does not claim automatic legitimacy determination.
- This quickstart does not change runtime behavior.
- This quickstart does not certify governance correctness.
- This quickstart does not replace human, legal, compliance, or audit review.

# Evaluation Governance Sample Bundle v1

This directory contains a synthetic, non-enforcing sample bundle for external reviewers who want to inspect how Evaluation Governance artifacts can be represented together.

The bundle demonstrates a complete artifact chain for a fictional scenario: a high-risk internal approval workflow where a delegated authority scope changes, an evaluator version changes, and the trajectory monitor flags potential admissibility expansion.

## What this bundle is

- A reviewer-facing example of Evaluation Governance JSON artifacts.
- A synthetic, offline documentation fixture.
- A compact way to understand references between governance artifacts.
- A sample that contains deterministic placeholder hashes shaped like SHA-256 values.
- A bundle intended for external reviewer understanding.

## What this bundle is not

- It does not prove runtime enforcement.
- It does not automatically establish legitimacy.
- It does not certify regulatory compliance.
- It does not introduce live receipt generation.
- It does not modify production governance configuration.
- It does not contain secrets or personally identifiable information (PII).

## Validate the sample bundle

Run:

```bash
python scripts/demo/validate_evaluation_governance_sample_bundle.py
```

This helper validates schema shape only. It does not prove runtime enforcement, establish legitimacy, certify regulatory compliance, verify cryptographic hash correctness in v1 beyond schema shape, dereference artifact references, or require network access.

## Compact artifact flow

```text
Root Authority Manifest
→ Evaluation Function Manifest
→ Manifest Change Receipt
→ Evaluation Receipt
→ Outcome Delta Attribution
→ Evaluation Drift Detection
→ Trajectory-Level Admissibility Monitor
→ Legitimacy Impact Review
```

## Included artifacts

| Artifact | Example file | Purpose |
| --- | --- | --- |
| Root Authority Manifest | `root-authority-manifest.example.json` | Defines the synthetic root trust anchor and authority sources. |
| Evaluation Function Manifest | `evaluation-function-manifest.example.json` | Describes the governed evaluator and references the root authority manifest. |
| Manifest Change Receipt | `manifest-change-receipt.example.json` | Records a synthetic evaluator manifest change. |
| Evaluation Receipt | `evaluation-receipt.example.json` | Records a synthetic admissibility evaluation using the evaluator manifest. |
| Outcome Delta Attribution | `outcome-delta-attribution.example.json` | Attributes a synthetic outcome change to evaluator and authority-scope changes. |
| Evaluation Drift Detection | `evaluation-drift-detection.example.json` | Marks evaluator drift as suspected based on the attribution artifact. |
| Trajectory-Level Admissibility Monitor | `trajectory-admissibility-monitor.example.json` | Flags possible admissibility expansion across the synthetic trajectory. |
| Legitimacy Impact Review | `legitimacy-impact-review.example.json` | Reviews legitimacy-relevant impact from the manifest change. |

All examples are documentation fixtures only and validate against their corresponding schemas in `docs/en/demo/schemas/`.

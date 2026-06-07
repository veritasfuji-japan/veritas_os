# Evaluation Drift Detection Helper v1 Example

This directory contains a synthetic, offline example for the Evaluation Drift
Detection helper v1.

The helper reads a local Outcome Delta Attribution v1 JSON artifact and produces
a draft Evaluation Drift Detection v1 JSON artifact. The generated artifact is
schema-shaped review material only.

## Scope and non-goals

This v1 helper:

- is non-enforcing;
- does not change runtime admissibility;
- does not change `/v1/decide` behavior;
- does not prove legitimacy;
- does not certify compliance;
- does not mutate production governance configuration;
- does not dereference artifact references;
- does not require network access;
- does not require secrets, environment variables, or external services.

## Example command

```bash
python scripts/demo/generate_evaluation_drift_detection.py \
  --attribution docs/en/demo/examples/evaluation-drift-detection-helper-v1/outcome-delta-attribution.example.json \
  --output /tmp/evaluation-drift-detection.json
```

If `--output` is omitted, the generated Evaluation Drift Detection JSON is
printed to stdout.

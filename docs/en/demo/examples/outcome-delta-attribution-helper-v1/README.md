# Outcome Delta Attribution Helper v1 Example

This directory contains a synthetic offline helper example for Evaluation
Governance. The helper compares two Evaluation Receipt v1 JSON files and
produces a draft Outcome Delta Attribution v1 JSON artifact.

The example is intentionally limited:

- It is non-enforcing in v1.
- It does not change runtime admissibility behavior.
- It does not prove legitimacy.
- It does not certify compliance.
- It does not dereference artifact references.
- It does not require network access.
- It uses synthetic data only, with no secrets, PII, customer data, or real
  organization data.

## Example command

```bash
python scripts/demo/generate_outcome_delta_attribution.py \
  --prior docs/en/demo/examples/outcome-delta-attribution-helper-v1/prior-evaluation-receipt.example.json \
  --current docs/en/demo/examples/outcome-delta-attribution-helper-v1/current-evaluation-receipt.example.json \
  --output /tmp/outcome-delta-attribution.json
```

When `--output` is omitted, the generated JSON is printed to stdout instead.

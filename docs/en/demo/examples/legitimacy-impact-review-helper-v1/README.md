# Legitimacy Impact Review helper v1 example

This directory contains a synthetic offline helper example for generating a draft Legitimacy Impact Review v1 artifact.

The helper reads:

- a Manifest Change Receipt v1 JSON file; and
- optionally, a Trajectory-Level Admissibility Monitor v1 JSON file.

It produces a draft Legitimacy Impact Review that surfaces legitimacy-impacting signals as reviewable evidence.

Important boundaries:

- It is non-enforcing in v1.
- It does not change runtime admissibility or `/v1/decide` behavior.
- It does not prove legitimacy.
- It does not certify regulatory compliance.
- It does not dereference artifact refs.
- It does not require network access.
- It does not require secrets, environment variables, or external services.

Example command:

```bash
python scripts/demo/generate_legitimacy_impact_review.py \
  --manifest-change docs/en/demo/examples/legitimacy-impact-review-helper-v1/manifest-change-receipt.example.json \
  --trajectory-monitor docs/en/demo/examples/legitimacy-impact-review-helper-v1/trajectory-admissibility-monitor.example.json \
  --output /tmp/legitimacy-impact-review.json
```

If `--output` is omitted, the helper prints the generated JSON to stdout.

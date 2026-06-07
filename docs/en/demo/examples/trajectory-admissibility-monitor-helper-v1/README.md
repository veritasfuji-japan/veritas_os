# Trajectory-Level Admissibility Monitor Helper v1 Example

This directory contains a synthetic offline helper example for generating a
Draft Trajectory-Level Admissibility Monitor v1 artifact.

The helper reads local Evaluation Governance artifacts:

- Evaluation Receipts
- Outcome Delta Attributions
- Evaluation Drift Detections

It then produces a draft Trajectory-Level Admissibility Monitor JSON object for
review. In v1 this helper is non-enforcing: it does not change runtime
admissibility, does not prove legitimacy, and does not certify compliance.

The helper also does not dereference artifact refs, does not require network
access, does not require environment variables, and does not require secrets.
All data in this example is synthetic and intentionally avoids real
organization, customer, or person data.

## Example command

```bash
python scripts/demo/generate_trajectory_admissibility_monitor.py \
  --evaluation-receipts \
    docs/en/demo/examples/trajectory-admissibility-monitor-helper-v1/evaluation-receipt-1.example.json \
    docs/en/demo/examples/trajectory-admissibility-monitor-helper-v1/evaluation-receipt-2.example.json \
    docs/en/demo/examples/trajectory-admissibility-monitor-helper-v1/evaluation-receipt-3.example.json \
  --attributions \
    docs/en/demo/examples/trajectory-admissibility-monitor-helper-v1/outcome-delta-attribution-1.example.json \
    docs/en/demo/examples/trajectory-admissibility-monitor-helper-v1/outcome-delta-attribution-2.example.json \
  --drift-detections \
    docs/en/demo/examples/trajectory-admissibility-monitor-helper-v1/evaluation-drift-detection-1.example.json \
    docs/en/demo/examples/trajectory-admissibility-monitor-helper-v1/evaluation-drift-detection-2.example.json \
  --output /tmp/trajectory-admissibility-monitor.json
```

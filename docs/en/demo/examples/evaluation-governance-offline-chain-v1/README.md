# Evaluation Governance Offline Chain v1 Example

This directory contains a synthetic offline Evaluation Governance chain example.
It demonstrates how the existing reviewer-facing helper sequence can be run over
local example inputs:

Evaluation Receipt -> Outcome Delta Attribution -> Evaluation Drift Detection ->
Trajectory-Level Admissibility Monitor -> Legitimacy Impact Review.

The example is non-runtime and non-enforcing in v1. It does not change runtime
admissibility, does not call `/v1/decide`, does not prove legitimacy, does not
certify compliance, does not dereference artifact refs, does not require network
access, and does not include secrets or PII.

## Generate into a temporary output directory

```bash
python scripts/demo/run_evaluation_governance_offline_chain.py \
  --input-dir docs/en/demo/examples/evaluation-governance-offline-chain-v1 \
  --output-dir /tmp/evaluation-governance-offline-chain-output
```

## Regenerate checked-in example outputs intentionally

```bash
python scripts/demo/run_evaluation_governance_offline_chain.py \
  --input-dir docs/en/demo/examples/evaluation-governance-offline-chain-v1 \
  --write-example-output
```

The checked-in generated examples are included only for reviewer readability.
The helper validates schema shape when `jsonschema` is available locally. It does
not verify present legitimacy, does not enforce runtime decisions, does not
verify external artifact hashes, and does not require artifact refs to resolve.

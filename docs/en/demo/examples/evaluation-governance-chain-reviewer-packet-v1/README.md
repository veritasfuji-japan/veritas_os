# Evaluation Governance chain Reviewer Evidence Packet v1

This directory contains a synthetic, reviewer-facing Reviewer Evidence Packet
example generated from the Evaluation Governance offline chain manifest.

The generated packet attaches Evaluation Governance artifacts as optional
reviewer evidence. It is intended for local architecture/demo review only.

## Boundary

This v1 example is:

- synthetic and local/offline only;
- generated from
  `docs/en/demo/examples/evaluation-governance-offline-chain-v1/generated/chain-manifest.generated.example.json`;
- populated with Evaluation Governance artifact attachments from the offline
  chain manifest;
- non-runtime and non-enforcing;
- not connected to `/v1/decide`;
- not a change to runtime admissibility or production governance
  configuration;
- not proof of legitimacy;
- not regulatory, audit, legal, or compliance certification;
- not a workflow that dereferences external artifact references;
- not dependent on network access; and
- not a container for secrets, PII, customer data, or live external service
  data.

## Generate the packet

```bash
python scripts/demo/generate_reviewer_evidence_packet_from_evaluation_governance_chain.py \
  --chain-manifest docs/en/demo/examples/evaluation-governance-offline-chain-v1/generated/chain-manifest.generated.example.json \
  --artifact-base-dir docs/en/demo/examples/evaluation-governance-offline-chain-v1 \
  --output /tmp/reviewer-evidence-packet.json
```

When `--output` is omitted, the helper prints the generated Reviewer Evidence
Packet JSON to stdout. When `--output` is provided, it writes the JSON to that
path and prints a short local/offline summary.

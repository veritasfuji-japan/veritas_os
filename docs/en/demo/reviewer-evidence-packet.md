# Reviewer Evidence Packet v1

Reviewer Evidence Packet v1 is a deterministic local/offline JSON-friendly export for the SaaS permission-change governed execution demo.

It packages the existing demo output into one reviewer-facing artifact so external reviewers, investors, and enterprise stakeholders can inspect the main governance evidence without opening every internal artifact separately.

## What it includes

The packet is built from `run_saas_permission_change_governed_demo()` and includes:

- case outcomes for the SaaS permission-change governed execution demo
- compact AuthorityEvidence and HumanApproval summaries
- OutcomeReceipt summaries for each case
- EvidenceChainManifest summaries for each case
- EvidenceChainVerification summaries for each case
- aggregate counts for blocked, committed, and verified cases
- deterministic reviewer notes
- a deterministic packet hash that excludes `packet_hash` itself from the hash payload

## Local/offline boundary

Reviewer Evidence Packet v1 is a local/offline fixture export only.

It does not connect to live SaaS, IAM, IdP, SSO, customer directories, banks, sanctions systems, production approval workflows, or live audit stores.

It demonstrates bind-time governance and evidence-chain verification using deterministic artifacts. It is not legal advice, regulatory approval, third-party certification, production audit certification, or proof of live deployment.

## Usage

Run the export locally:

```bash
python3 scripts/demo/export_reviewer_evidence_packet.py
```

The command prints deterministic JSON to stdout with sorted keys and indentation. It performs no network calls and requires no credentials.

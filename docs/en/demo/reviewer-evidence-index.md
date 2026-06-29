# Reviewer Evidence Index

This page is the landing page for local/offline Reviewer Evidence documentation. It groups the reviewer-facing overview, packet contract, generated examples, schemas, and validation references so reviewers can follow the evidence model without jumping between unrelated docs.

See also: [Reviewer Evidence Assurance Overview](reviewer-evidence-assurance-overview.md) and [Reviewer Evidence Packet v1](reviewer-evidence-packet.md).

## Overview

Reviewer Evidence documentation explains how deterministic demo artifacts help reviewers inspect governed outcomes, evidence-chain continuity, packet validation, and catalog-backed failure explanations.

The reviewer evidence layer is documentation and validation only. It does not change runtime admissibility, governance policy behavior, FUJI fail-closed behavior, TrustLog persistence, schemas, validators, or generated artifacts.

## Quick architecture summary

```text
Reviewer Evidence
  ↓
Evidence Chain
  ↓
Packet Validation
  ↓
Failure Reason Catalog
  ↓
Validation Report
```

## Reviewer Evidence Assurance Overview

Start with the [Reviewer Evidence Assurance Overview](reviewer-evidence-assurance-overview.md) to understand the assurance boundary, layered model, component mapping, tamper coverage, and non-goals for reviewer evidence.

## Reviewer Evidence Packet

Use [Reviewer Evidence Packet v1](reviewer-evidence-packet.md) for the packet purpose, included evidence summaries, optional Evaluation Governance attachments, approval proof continuity rules, local/offline boundary, usage, and golden fixture guidance.

## Failure Reason Catalog

Failure reasons are stable machine-readable strings with reviewer-facing metadata. Use these catalog docs and examples when explaining validation failures:

- [Generated failure reason catalog Markdown](examples/reviewer-failure-reason-catalog-v1/reviewer-failure-reason-catalog.generated.example.md)
- [Generated failure reason catalog JSON](examples/reviewer-failure-reason-catalog-v1/reviewer-failure-reason-catalog.generated.example.json)
- [Failure reason catalog schema](schemas/reviewer-failure-reason-catalog-v1.schema.json)

## Validation

Reviewer validation references are:

- [Reviewer Evidence Packet Validation Report](reviewer-evidence-packet-validation-report.md)
- [Reviewer Evidence Packet schema](schemas/reviewer-evidence-packet-v1.schema.json)
- [Failure reason catalog schema](schemas/reviewer-failure-reason-catalog-v1.schema.json)

## Generated Examples

Generated examples are checked in for review and deterministic validation. This navigation PR does not regenerate them.

- [Reviewer Evidence Packet generated example](examples/evaluation-governance-chain-reviewer-packet-v1/reviewer-evidence-packet.generated.example.json)
- [Failure reason catalog Markdown example](examples/reviewer-failure-reason-catalog-v1/reviewer-failure-reason-catalog.generated.example.md)
- [Failure reason catalog JSON example](examples/reviewer-failure-reason-catalog-v1/reviewer-failure-reason-catalog.generated.example.json)

## Schemas

Schema references for reviewer evidence artifacts are:

- [Reviewer Evidence Packet v1 schema](schemas/reviewer-evidence-packet-v1.schema.json)
- [Reviewer Failure Reason Catalog v1 schema](schemas/reviewer-failure-reason-catalog-v1.schema.json)

## Suggested reading order

1. [Reviewer Evidence Assurance Overview](reviewer-evidence-assurance-overview.md)
2. [Reviewer Evidence Packet v1](reviewer-evidence-packet.md)
3. [Reviewer failure reason catalog Markdown example](examples/reviewer-failure-reason-catalog-v1/reviewer-failure-reason-catalog.generated.example.md)
4. [Reviewer failure reason catalog JSON example](examples/reviewer-failure-reason-catalog-v1/reviewer-failure-reason-catalog.generated.example.json)
5. [Reviewer Evidence Packet generated example](examples/evaluation-governance-chain-reviewer-packet-v1/reviewer-evidence-packet.generated.example.json)
6. [Reviewer Evidence Packet v1 schema](schemas/reviewer-evidence-packet-v1.schema.json)
7. [Reviewer Failure Reason Catalog v1 schema](schemas/reviewer-failure-reason-catalog-v1.schema.json)
8. [Reviewer Evidence Packet Validation Report](reviewer-evidence-packet-validation-report.md)

## Related reviewer docs

- [Reviewer Evidence Bundle v1](reviewer-evidence-bundle.md)
- [External Reviewer Artifact Index v1](external-reviewer-artifact-index.md)
- [External Reviewer Quickstart](external-reviewer-quickstart.md)

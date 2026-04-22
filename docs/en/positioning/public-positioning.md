# VERITAS OS Public Positioning Guide (EN)

## Official public positioning

**VERITAS OS = Decision Governance and Bind-Boundary Control Plane for AI Agents**

Core promise:

- AI decisions are **reviewable, traceable, replayable, auditable, and enforceable before real-world effect**.
- VERITAS OS functions as a governance layer from **decision adjudication through bind-boundary enforcement**, not only an execution runtime.
- Current implemented bind-boundary lineage is:
  `decision artifact -> execution intent -> bind receipt` (TrustLog-integrated).
- Operator-facing bind public contract includes `bind_outcome`, `bind_failure_reason`, `bind_reason_code`, `execution_intent_id`, and `bind_receipt_id`.
- The contract now also exposes additive `bind_summary` objects so mutation/export responses share one compact bind vocabulary while preserving legacy flat fields.

## What VERITAS OS is / is not

- **Is:** a governance-first operating layer for AI agent decisions in enterprise and regulated workflows.
- **Is not:** a blanket replacement for all orchestration/runtimes, or a speculative AGI narrative product.

## Current fact vs future direction

### Current fact (implemented)

- Bind-boundary is implemented on at least three operator-governed effect paths:
  1. `PUT /v1/governance/policy` (governance policy update path)
  2. `POST /v1/governance/policy-bundles/promote` (policy bundle promotion path)
  3. `PUT /v1/compliance/config` (runtime compliance config mutation path)
- Bind artifacts are exposed through list/export/detail operator surfaces:
  `/v1/governance/bind-receipts`, `/v1/governance/bind-receipts/export`,
  and `/v1/governance/bind-receipts/{bind_receipt_id}`.
- `BindReceipt` is the full artifact contract (including canonical target metadata), while `bind_summary` is the shared compact bind vocabulary reused across bind-governed mutation/export responses.
- Replay/revalidation helpers exist and move receipts toward replayable governance artifacts.

### Future direction (not yet complete)

- Expand bind-boundary coverage across additional effect paths.
- Converge toward a standardized governance framework that governs multiple effect paths consistently.
- Keep this framed as direction; do not claim all effect paths are complete today.

## Recommended language

- Decision Governance OS
- governance layer before execution
- decision-to-bind governance boundary
- reviewable / traceable / replayable / auditable / enforceable
- fail-closed safety gate
- tamper-evident TrustLog lineage
- decision -> execution_intent -> bind_receipt lineage
- operator-facing governance surface
- bind outcome public contract

## Caution / restricted language

Use only in historical or research context with explicit qualifier:

- Proto-AGI
- AGI framework
- self-improvement OS

Avoid unqualified use in titles, subtitles, and opening product summary paragraphs.

## Technical Maturity Snapshot (internal self-assessment)

> This section is an **internal re-evaluation (self-assessment)** and is not third-party certification; treat it as the current published internal snapshot.

| Category | 2026-03-15 | 2026-04-15 | Delta |
|---|---|---|---|
| Architecture | 82 | 85 | +3 |
| Code Quality | 83 | 84 | +1 |
| Security | 80 | 86 | +6 |
| Testing | 88 | 89 | +1 |
| Production Readiness | 80 | 85 | +5 |
| Governance | 82 | 86 | +4 |
| Docs | 80 | 83 | +3 |
| Differentiation | 84 | 86 | +2 |
| **Overall** | **82** | **85 / 100** | **+3** |

Reference baseline review document:
- `docs/ja/reviews/technical_dd_review_ja_20260315.md`

## README summary policy

In README opening sections (first 3–5 screens), prioritize this order:

1. What the product is
2. What problem it solves
3. Difference from runtime/orchestration tools
4. Why it fits enterprise/regulated contexts
5. Fact boundary vs roadmap boundary

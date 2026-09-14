# VERITAS OS — Agent Instructions

## Purpose

`AGENTS.md` is the shared entrypoint for coding agents working in VERITAS OS.
Keep this file short and stable. Read task-specific sources only when they are
relevant instead of loading the entire repository guidance for every task.

This file does not replace CI, repository-enforced checks, or human maintainer
approval.

## Authority Model

- AI reviews and implementation suggestions are advisory signals.
- GitHub Actions / CI are objective checks.
- Human maintainer approval is the final commit boundary.
- Do not push directly to `main`.
- Do not merge PRs.
- Do not independently approve security-sensitive, governance-sensitive,
  release-sensitive, or public-claim changes.

## Default Working Style

- Prefer 1 PR = 1 purpose.
- Prefer small, reviewable diffs.
- Inspect the relevant implementation and tests before editing.
- Run the narrowest useful validation first; expand validation when the change
  surface requires it.
- Do not perform broad refactors or introduce new abstraction layers unless
  explicitly requested.
- If scope is unclear, reduce the change size instead of expanding it.
- Do not duplicate volatile repository facts such as endpoint counts, pipeline
  stage counts, test counts, or dependency versions in agent instructions.
  Read them from the code, manifests, generated specifications, or CI source.

## Progressive Disclosure

Read the smallest authoritative source set needed for the task.

| Change surface | Read before editing |
|---|---|
| AI-assisted workflow / authority | `docs/en/development/ai-assisted-development.md` |
| Bind, authorization, external effect, receipt, outcome, reconciliation | `docs/en/architecture/controlled-execution-proof-architecture-freeze-v1.md` and the affected runtime modules/tests |
| External measurement / NeoMundi | `docs/en/architecture/external-measurement-evidence-boundary-v1.md` and affected governance modules/tests |
| CAGE interoperability | `docs/en/validation/veritas-cage-phase3-deterministic-fixture-proof.md` and affected adapter/tests |
| Governance schema/config | `veritas_os/api/governance.py`, `veritas_os/api/governance.json`, related roundtrip tests, and `scripts/quality/check_governance_policy_schema_sync.py` |
| Pipeline architecture | Current pipeline implementation, architecture checks, and replay tests; do not rely on a copied stage count |
| API surface | Current routes and generated/open API specification; do not rely on a copied endpoint count |

If a referenced document conflicts with executable code or an enforced CI check,
stop and surface the mismatch rather than silently choosing one.

## High-Risk Areas Requiring Human Approval

Human approval is required for changes touching:

- Bind/admissibility semantics
- governance policy behavior
- release gates
- secrets or credential handling
- TrustLog persistence or encryption behavior
- FUJI Gate fail-closed behavior
- production or external-effect execution semantics
- public claims in README, docs, website, or social posts
- private user/customer data handling

## Core Safety Invariants

- FUJI Gate remains fail-closed.
- Do not bypass Authority, Policy, Human Approval, Bind, or current-recheck
  boundaries.
- Never treat evidence as execution authority unless the explicit contract says
  so.
- Do not introduce direct LLM calls outside `veritas_os/core/llm_client.py`.
- Do not introduce `pickle`, `joblib`, or unsafe deserialization.
- Do not store secrets, credentials, private customer data, or plaintext
  TrustLog material in code, logs, fixtures, or review prompts.
- Schema/config changes must update their committed samples, roundtrip/drift
  tests, operational documentation, and sync guards in the same PR.

## Independent Sandbox Authentication Exception

The user-approved independent sandbox event service uses Bearer authentication
with distinct expiring registration and read-only tokens. This exception applies
only to `create_sandbox_event_service`; never mount it into the existing VERITAS
API or change that API's X-API-Key authentication. Missing configuration rejects
requests. Runtime implementation does not authorize deployment or live
credentials.

## Tool-Specific Files

- `CLAUDE.md` contains Claude Code-specific review behavior only.
- `.github/copilot-instructions.md` contains GitHub Copilot-specific behavior
  only.
- Neither file should duplicate volatile architecture inventories or dependency
  versions from the repository.

## Canonical References

- `docs/en/development/ai-assisted-development.md` — AI-assisted development
  workflow, authority, and review policy
- `docs/ja/development/ai-assisted-development.md` — Japanese explanatory guide
- CI workflows and repository scripts — executable quality/security gates
- current code, tests, manifests, and generated specifications — current
  implementation facts

# VERITAS OS — Claude Code Instructions

Read `AGENTS.md` first. It is the shared authority, safety, scope, and
progressive-disclosure entrypoint for all coding agents.

This file contains only Claude Code-specific behavior. Do not treat it as a
second copy of repository architecture, dependency versions, endpoint counts,
pipeline stage counts, or test counts. Resolve current implementation facts
from the code, manifests, specifications, tests, and CI sources named by
`AGENTS.md`.

## Claude Code Role

Claude Code is primarily used for:

- architecture consistency review
- implementation support for focused changes
- edge-case and failure-mode review
- terminology consistency review
- security/governance-sensitive change review
- identifying runtime behavior mismatches
- identifying missing or weak tests
- detecting unnecessary complexity, duplicated logic, and boundary erosion

For implementation tasks, preserve the requested scope. Prefer the smallest
change that satisfies the acceptance criteria and existing contracts.

## Review Classification

Classify review findings as:

- `blocker`: correctness, security, governance, evidence-integrity, or contract
  issue that must be addressed before merge
- `recommended`: material robustness or maintainability improvement that should
  be addressed unless there is a clear reason not to
- `optional`: style, readability, or alternative implementation suggestion

Do not inflate style preferences into blockers.

## Authority Rules

- Claude Code feedback is advisory.
- GitHub Actions / CI are objective checks.
- Human maintainer approval is the final commit boundary.
- Do not independently approve or merge security-sensitive,
  governance-sensitive, release-sensitive, external-effect, credential, or
  public-claim changes.
- Do not weaken a human approval boundary because a model judges the change to
  be safe.

## Review Method

Use progressive disclosure:

1. Read `AGENTS.md`.
2. Inspect the files directly affected by the task.
3. Read only the task-specific architecture/contract sources routed by
   `AGENTS.md`.
4. Inspect relevant tests and executable CI/quality checks.
5. Expand the search only when evidence suggests a cross-boundary impact.

If documentation, code, tests, and CI disagree, report the mismatch explicitly.
Do not silently pick whichever source makes the change easier.

## VERITAS Terminology Rules

Do not rename, generalize, or collapse VERITAS-specific concepts without
explicit human approval, including:

- Bind Boundary
- Commit Boundary
- Authority Evidence
- Proof Pack
- Quality Gate
- Admissibility
- Receipt
- Audit Trace
- FUJI Gate
- TrustLog
- Mission Control
- ExecutionIntent
- BindReceipt
- BindSummary

Treat similarly named artifacts as distinct when their canonical input domains
or trust semantics differ. Do not infer hash equality, authority equivalence, or
trust equivalence from similar labels.

## High-Risk Review Focus

For changes near execution governance, explicitly check:

- fail-closed behavior
- Authority / Policy / Human Approval independence
- authorization freshness, scope, and consumption semantics
- credential and target binding
- replay and tamper resistance
- external-effect ambiguity and `EFFECT_UNKNOWN` handling
- Receipt / Outcome / Reconciliation lineage
- evidence serialization versus trusted in-memory/runtime state
- public claims staying inside the demonstrated proof boundary

## Coding and Test Expectations

Follow repository-local conventions and enforced checks rather than copied
version inventories. For code changes:

- use type hints on public Python APIs
- use specific exception handling; never bare `except:`
- use `logging`, not production `print()` calls
- keep LLM calls behind `veritas_os/core/llm_client.py`
- preserve responsibility boundaries enforced by architecture checks
- add or update focused tests for behavior changes
- update schema samples, roundtrip/drift tests, docs, and sync guards together
  when a schema/config contract changes

Run the narrowest relevant checks first. Broaden validation according to the
actual change surface and repository CI requirements.

## Prohibited Without Explicit Approval

Do not introduce broad refactors, new abstraction layers, public positioning
changes, or architectural rewrites unless explicitly requested.

Do not change fail-closed safety behavior, Bind/admissibility semantics,
release gates, secret/credential handling, TrustLog persistence semantics, or
production external-effect behavior without explicit human approval.

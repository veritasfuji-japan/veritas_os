# AI-Assisted Development Guardrails

## Purpose

VERITAS OS may use multiple AI tools to accelerate implementation, review, documentation, and release preparation.

This guide defines an auditable AI-assisted development workflow. It does not introduce autonomous development, automatic merging, or replacement of human maintainers.

## Principle

AI tools may propose, implement, review, and summarize changes.

Only a human maintainer may approve:

- security-sensitive changes
- governance-boundary changes
- release decisions
- public claims
- changes involving private user or customer data

## Authority Model

- AI reviews are advisory signals.
- GitHub Actions / CI are objective checks.
- Human maintainer approval is the final commit boundary.

## Agent Instruction Hierarchy

`AGENTS.md` is the shared entrypoint for coding agents.

Tool-specific instruction files must contain only role-specific deltas:

- `CLAUDE.md` — Claude Code review and implementation behavior
- `.github/copilot-instructions.md` — GitHub Copilot-specific behavior

Do not maintain parallel copies of volatile repository facts in agent instruction files. In particular, do not duplicate changing endpoint counts, pipeline stage counts, test counts, or dependency versions. Read current facts from code, manifests, generated specifications, tests, and CI only when the task needs them.

When sources disagree, agents must surface the mismatch instead of silently selecting the most convenient source.

## Progressive Disclosure

Agents should load the smallest authoritative source set that is sufficient for the task.

Recommended sequence:

1. Read `AGENTS.md`.
2. Inspect the files directly affected by the task.
3. Read only the architecture, contract, or validation documents routed by `AGENTS.md` for that change surface.
4. Inspect relevant tests and executable CI/quality checks.
5. Expand to adjacent subsystems only when there is evidence of cross-boundary impact.

This keeps model reasoning autonomous where appropriate without weakening execution, governance, security, or human-approval boundaries.

## Tool Roles

| Tool | Primary role |
|---|---|
| ChatGPT | PR intent, scope, risk framing, architecture reasoning, market/value review |
| Codex | Primary implementation, focused PR patching, test updates, CI failure fixes |
| Claude Code | Architecture review, edge-case review, implementation support, terminology consistency |
| GitHub Copilot | GitHub-native PR review, local coding assistance, small bug suggestions |
| Gemini | External clarity review, documentation readability, product explanation review |
| Grok | Adversarial review, unnecessary-complexity detection, market/message skepticism |
| Meta AI | Lightweight secondary review, terminology clarity, readability review |
| GitHub Actions | Objective CI checks, tests, quality gates, release gates |
| Human maintainer | Final approval, merge decision, security/governance/release/public-claim authority |

## Recommended Workflow

1. ChatGPT defines PR intent, scope, risk, and non-goals.
2. Codex implements the focused change.
3. Claude Code reviews architecture, edge cases, terminology, and consistency.
4. GitHub Actions verifies tests and quality gates.
5. External AI tools may provide advisory review using non-sensitive excerpts.
6. Human maintainer approves, rejects, or requests changes.

## Prohibited Automation

AI must not automatically merge or independently approve:

- bind/admissibility logic changes
- governance policy changes
- release gate changes
- secret handling changes
- TrustLog persistence or encryption behavior changes
- FUJI Gate fail-closed behavior changes
- production or external-effect execution behavior changes
- public claim changes
- website positioning changes
- changes involving private user or customer data

## External AI Review Safety

External/free-tier AI review may use only non-sensitive excerpts.

Do not paste:

- secrets
- credentials
- API keys
- `.env` content
- private customer data
- unpublished internal strategy
- non-public security details

Use only:

- public docs
- sanitized diffs
- limited file excerpts
- error messages without secrets
- abstracted design questions

External AI feedback must not become a merge blocker by itself.

## Review Priority

1. CI/test failures
2. Security or data exposure
3. Governance or execution-boundary violations
4. Runtime behavior mismatch
5. Evidence-integrity, replay, or tamper-resistance weaknesses
6. Public documentation mismatch
7. Missing tests for code changes
8. Refactor or style suggestions

## Governance Schema Drift Guardrail

- Baseline governance log retention must remain **180 days**.
- High-risk governance log retention must remain **365 days**.
- Any governance schema change must update, in the same PR:
  - `veritas_os/api/governance.py` Pydantic schema,
  - `veritas_os/api/governance.json` committed policy sample,
  - governance roundtrip/drift regression tests,
  - `scripts/quality/check_governance_policy_schema_sync.py` validation guard.

## Non-Goals

This guide does not introduce:

- autonomous development
- automatic PR approval
- automatic merging
- replacement of human maintainers
- changes to runtime governance behavior
- changes to CI/release gates
- model confidence as a substitute for execution authority

## VERITAS Development Statement

VERITAS OS is developed through an auditable AI-assisted workflow:

- Coding agents may reason, explore, implement, and test within the requested scope.
- Tool-specific instructions remain minimal and task-routed.
- GitHub Actions verifies executable checks.
- External models may provide advisory review.
- Human maintainer approval remains the final commit boundary.

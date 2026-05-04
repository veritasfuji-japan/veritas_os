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
3. Runtime behavior mismatch
4. Public documentation mismatch
5. Missing tests for code changes
6. Refactor or style suggestions

## Non-Goals

This guide does not introduce:

- autonomous development
- automatic PR approval
- automatic merging
- replacement of human maintainers
- changes to runtime governance behavior
- changes to CI/release gates

## VERITAS Development Statement

VERITAS OS is developed through an auditable AI-assisted workflow:

- Codex may implement.
- Claude Code may review.
- GitHub Actions verifies.
- External models may provide advisory review.
- Human maintainer approval remains the final commit boundary.

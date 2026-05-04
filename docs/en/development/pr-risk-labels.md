# PR Risk Label Guidance

## Purpose

This document defines recommended PR risk labels for VERITAS OS development.

It supports the auditable AI-assisted development workflow defined in:

- `docs/en/development/ai-assisted-development.md`
- `docs/en/development/ai-review-matrix.md`

Risk labels are triage aids. They do not replace CI, review, or human maintainer approval.

## Authority Model

- AI reviews are advisory signals.
- GitHub Actions / CI are objective checks.
- Human maintainer approval is the final commit boundary.
- Risk labels do not authorize merge.
- Risk labels do not downgrade security, governance, release, or public-claim review requirements.

## Recommended Labels

| Label | Meaning | Typical examples | Human approval |
|---|---|---|---|
| `risk:low` | Small, low-impact change | typo fix, docs-only clarification, non-public wording cleanup | normal review |
| `risk:medium` | Meaningful change with limited blast radius | focused runtime fix, focused test update, localized frontend behavior, non-sensitive docs restructure | maintainer review required |
| `risk:high` | Change may affect governance, security, release, or public claims | bind/admissibility behavior, FUJI Gate behavior, TrustLog persistence, release gates, public claims | explicit human approval required |
| `docs-only` | Documentation-only change | docs page, guide, review matrix, explanation page | normal review unless public claims change |
| `tests-only` | Test-only change | unit test coverage, fixture update, regression test | maintainer review required if expectations change |
| `runtime-change` | Runtime code behavior may change | backend logic, frontend behavior, API response behavior | maintainer review required |
| `governance-sensitive` | Governance behavior or policy boundary may change | policy behavior, bind/admissibility logic, approval flow, enforcement behavior | explicit human approval required |
| `security-sensitive` | Security posture may change | secrets handling, auth, RBAC, encryption, PII masking, CORS, deserialization | explicit human approval required |
| `release-gate-change` | Release or CI gate behavior may change | GitHub Actions, quality gate scripts, release workflow, coverage gate | explicit human approval required |
| `public-claim-change` | Public positioning or external claims may change | README, README_JP, website copy, investor/customer-facing docs, social-post source text | explicit human approval required |
| `needs-human-approval` | Human approval is explicitly required before merge | any high-risk or authority-sensitive change | explicit human approval required |
| `ai-assisted` | AI tools contributed to planning, implementation, review, or drafting | ChatGPT planning, Codex implementation, Claude Code review, external AI advisory review | does not change approval rules |

## Risk Classification Rules

Use the highest applicable risk level.

A PR is `risk:high` if it touches any of the following:

- bind/admissibility logic
- governance policy behavior
- FUJI Gate fail-closed behavior
- TrustLog persistence or encryption behavior
- release gates
- secrets or credential handling
- public claims
- website positioning
- private user/customer data handling

A docs-only PR can still be `risk:high` if it changes public claims, regulatory positioning, production-readiness statements, or external-review evidence claims.

A tests-only PR can still be `risk:medium` or `risk:high` if it changes expected behavior, removes coverage, weakens assertions, or changes governance/release gate assumptions.

## Suggested Review Routing

| Risk | Recommended review |
|---|---|
| `risk:low` | normal maintainer review |
| `risk:medium` | maintainer review + relevant AI advisory review |
| `risk:high` | explicit human approval + CI success + targeted architecture/security/governance review |

## AI Review Use

AI tools may suggest labels, but humans decide final labels.

Codex may identify likely risk categories during implementation.
Claude Code may review whether the assigned labels match the diff.
External AI tools may provide advisory feedback only from non-sensitive excerpts.

## Non-Goals

This document does not introduce:

- automatic label application
- automatic merge approval
- automatic release approval
- bypass of CI
- replacement of human maintainer judgment

## Minimal PR Labeling Example

For a docs-only typo fix:

- `risk:low`
- `docs-only`

For a bind/admissibility behavior change:

- `risk:high`
- `runtime-change`
- `governance-sensitive`
- `needs-human-approval`

For README positioning updates:

- `risk:high`
- `docs-only`
- `public-claim-change`
- `needs-human-approval`

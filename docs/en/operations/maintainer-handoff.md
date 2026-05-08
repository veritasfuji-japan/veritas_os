# Maintainer Handoff and Support Continuity Runbook

## 1. Purpose

This runbook documents a minimum handoff path so a new maintainer can continue VERITAS OS technical operations and reviewer-facing support artifacts with lower onboarding friction.

This runbook reduces handoff friction but does not eliminate bus-factor risk.

## 2. Scope

This runbook covers:

- Maintainer onboarding references
- Local setup and baseline checks
- Quality gates used in repository operations
- PR and release review checkpoints
- One-Day PoC reviewer packet continuity checks
- Security, incident triage, and responsibility boundaries

This runbook does not change runtime semantics, API contracts, provider tiers, evidence schema shape, benchmark schema shape, or CI workflow contracts.

## 3. What this runbook does not solve

It is not a substitute for a staffed support organization, 24/7 operations team, legal counsel, security operations center, or formal vendor support agreement.

It does not claim:

- Bus-factor risk elimination
- Formal support SLA coverage
- Legal compliance certification
- Security certification
- Production operations staffing guarantees

## 4. First 60 minutes for a new maintainer

Read first:

- `README.md`
- `docs/en/operations/provider-support-matrix.md`
- `docs/en/operations/type-safety-baseline.md`
- `docs/en/poc/one-day-poc-reviewer-pack.md`
- `docs/en/poc/one-day-poc-performance-report.md`

Then execute baseline commands:

    python -m pytest -q veritas_os/tests/test_one_day_poc_smoke.py
    python -m pytest -q veritas_os/tests/test_one_day_poc_benchmark.py
    python -m scripts.quality.check_type_baseline
    python -m scripts.quality.check_bilingual_docs

Then verify current operational state:

- Review open PRs/issues for release blockers and security-relevant regressions.
- Confirm no secrets or raw API keys are committed in active branches.
- Confirm CI status for `main` is green for required checks.

## 5. Repository orientation

Primary entrypoints:

- Repository overview: `README.md`
- Documentation hub: `docs/INDEX.md`
- Bilingual mapping: `docs/DOCUMENTATION_MAP.md`
- AI-assisted development guardrails: `docs/en/development/ai-assisted-development.md`

Core operations references:

- Provider support boundaries: `docs/en/operations/provider-support-matrix.md`
- Type safety baseline: `docs/en/operations/type-safety-baseline.md`
- One-Day PoC reviewer handoff: `docs/en/poc/one-day-poc-reviewer-pack.md`
- One-Day PoC benchmark report path: `docs/en/poc/one-day-poc-performance-report.md`

## 6. Local setup checklist

- Use supported Python version from repository configuration.
- Install dependencies according to project standard setup.
- Ensure test commands execute from repository root.
- Verify local environment does not embed customer secrets in shell history, scripts, or checked-in files.
- Confirm local changes remain scoped to the intended PR purpose.

## 7. Quality gates checklist

Minimum gates to run/check:

- CI (main workflow)
- Security Gates
- CodeQL custom checks
- Runtime Pickle Guard checks
- requirements sync checks
- bilingual docs check
- one-day PoC smoke tests
- one-day PoC benchmark tests
- provider support matrix docs test
- compliance positioning docs test
- type safety baseline test

Passing these gates does not certify production readiness, legal compliance, security certification, or SLA readiness.

## 8. PR review checklist

For each PR, check:

- Does it change runtime governance semantics?
- Does it change bind/RBAC/TrustLog behavior?
- Does it change evidence packet shape?
- Does it change benchmark packet shape?
- Does it change provider tier?
- Does it make stronger compliance claims?
- Does it add runtime dependencies?
- Does it expose secrets?
- Does it require EN/JA docs synchronization?
- Does it require One-Day PoC reviewer pack updates?
- Does it affect One-Day PoC execution paths?
- Does it affect CI/security gate expectations?

## 9. Release readiness checklist

Before release tagging or release handoff:

- `main` branch CI is green.
- release gate is green when applicable.
- docs updates are merged for changed behavior/positioning.
- provider support matrix is current.
- compliance positioning docs are current.
- benchmark path remains runnable.
- no unreviewed provider tier change exists.
- no stronger legal/compliance claim was introduced.
- no new runtime dependency exists without explicit justification.
- no secret-handling or sensitive logging regression exists.

## 10. One-Day PoC reviewer packet checklist

For external reviewer/investor handoff packets, confirm:

- reviewer pack doc is current
- evidence JSON is present and sanitized
- evidence Markdown is present and sanitized
- benchmark JSON is present when required
- benchmark Markdown is present when required
- provider support matrix link is included
- EU AI Act positioning docs link is included
- type safety baseline docs link is included
- known limitations are explicitly stated

## 11. Security and secret-handling rules

- Do not commit API keys.
- Do not paste raw secrets into issues, PRs, docs, or benchmark packets.
- Do not include raw request/response bodies when they may contain secrets.
- Use sanitized outputs for reviewer-facing artifacts.
- Treat customer data as sensitive by default.
- Evidence packets must remain secret-safe.
- Logs should avoid raw provider payloads where unnecessary.

## 12. Incident triage checklist

Initial triage only:

- Identify failing gate or failing path.
- Link the failing CI run/job or local command output.
- Reproduce with a targeted command.
- Isolate whether runtime behavior changed or only docs/tooling changed.
- Avoid broad refactor in incident fix PR.
- Document root cause and mitigation in the PR description.

Incident classes to cover:

- CI failure
- security gate failure
- evidence validation failure
- benchmark failure
- provider failure
- TrustLog/RBAC/bind behavior regression
- docs compliance-claim regression

## 13. Governance subsystem map

| Area | Primary docs/tests | Maintainer concern |
|---|---|---|
| Bind / admissibility | `docs/en/architecture/bind_time_admissibility_evaluator.md`, `docs/en/architecture/bind-boundary-governance-artifacts.md` | Do not weaken fail-closed behavior. |
| RBAC | `docs/en/architecture/decision-semantics.md`, `veritas_os/tests/test_role_guard_escalation.py` | Preserve denial visibility and escalation boundaries. |
| TrustLog | `docs/en/architecture/authority-evidence-vs-audit-log.md`, `veritas_os/tests/test_audit_log_writer.py` | Preserve append/audit semantics. |
| Evidence packets | `docs/en/poc/one-day-poc-reviewer-pack.md`, `veritas_os/tests/test_docs_poc_samples.py` | Preserve schema shape and sanitization guarantees. |
| Provider support | `docs/en/operations/provider-support-matrix.md`, `veritas_os/tests/test_provider_support_matrix_docs.py` | Do not overstate non-production providers. |
| Compliance positioning | `docs/en/positioning/public-positioning.md`, `veritas_os/tests/test_compliance_positioning_docs.py` | Do not claim legal certification. |
| Type safety | `docs/en/operations/type-safety-baseline.md`, `veritas_os/tests/test_type_safety_baseline.py` | Baseline is incremental, not strict full-repo typing. |

## 14. Provider dependency boundary

Provider tiers are documented, and production support claims must remain aligned with `docs/en/operations/provider-support-matrix.md`.

Do not imply provider-neutral production equivalence if not documented and tested.
Anthropic contract coverage is offline-only and does not change provider tier.

## 15. Compliance positioning boundary

Compliance positioning documents communicate technical supportability and evidence boundaries. They must not be rewritten into legal guarantees, regulatory approval claims, or certification claims.

## 16. Type safety baseline

Type safety is maintained as a baseline strategy with incremental expansion. Passing baseline checks indicates maintained baseline quality, not universal strict typing across all modules.

## 17. Escalation and handoff packet

When handing off to another maintainer, package at minimum:

- Current branch and PR status summary
- Latest CI run links and unresolved failures
- Open incident list and temporary mitigations
- Reviewer-facing packet links used in current diligence cycle
- Known risky areas touched in active work

## 18. Current known continuity risks

- Single primary maintainer risk remains.
- No staffed 24/7 support organization is claimed.
- No formal support SLA is claimed.
- Some operational knowledge may still be implicit.
- External legal/security review remains outside this repository.
- Production deployment ownership remains customer/operator responsibility.

## 19. Roadmap for reducing bus factor

- Add maintainer onboarding issue template.
- Add release manager checklist template.
- Add incident report template.
- Expand type baseline coverage for core modules.
- Add provider contract tests where practical.
- Add architecture decision records for major subsystems.
- Add deployment profile separation for dev/full/runtime dependencies.
- Add support SLA only if an actual support organization exists.

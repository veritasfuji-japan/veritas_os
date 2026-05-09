# One-Day PoC Operator Runbook

- This is an operator-facing runbook for conducting a One-Day PoC.
- It explains how to prepare, run, collect, package, and hand off reviewer-facing PoC evidence.
- It complements the One-Day PoC Evidence Pack.
- It is not a production deployment guide.
- It is not a production SLA.
- It is not third-party certified.
- It is not a customer environment measurement.
- It does not certify EU AI Act compliance.
- External LLM/provider latency and cost are not measured unless providers are intentionally enabled and separately recorded.

## Purpose

- Give operators a repeatable procedure for running a One-Day PoC.
- Make the output reviewable by customers, investors, and technical reviewers.
- Keep PoC claims bounded to local/configured evidence.

## Operator responsibilities

- Record commit SHA, date/time, operator name or role, and environment notes.
- Avoid editing generated evidence after collection except for explicitly documented redaction.
- Keep raw and sanitized artifacts separate when applicable.
- State non-claim boundaries clearly during review.

## Pre-flight checklist

- [ ] Repository checked out at intended commit.
- [ ] Dependencies installed according to existing setup docs.
- [ ] VERITAS API server available if running HTTP PoC flow.
- [ ] `VERITAS_API_KEY` configured where required.
- [ ] Output directory created.
- [ ] No production SLA / certification / customer-environment claim will be made.
- [ ] If external providers are enabled, provider configuration and measurement scope are recorded separately.

## Recommended evidence folder layout

```text
poc-evidence/
  README.md
  environment.md
  commands.md
  screenshots/
  json/
  markdown/
  logs/
  redactions.md
  reviewer-notes.md
```

- `environment.md`: date, commit SHA, local/configured environment notes.
- `commands.md`: exact commands run.
- `screenshots/`: block/allow decision path screenshots.
- `json/`: machine-readable outputs.
- `markdown/`: human-readable reports.
- `logs/`: optional local logs.
- `redactions.md`: what was redacted and why.
- `reviewer-notes.md`: summary for handoff.

## Run sequence

1. Capture environment and commit SHA.
2. Start or confirm VERITAS API server if required.
3. Run One-Day PoC walkthrough or smoke flow using existing docs/scripts.
4. Optionally run One-Day PoC benchmark if local/configured HTTP benchmark is in scope.
5. Collect JSON / Markdown / screenshots.
6. Record failures and exceptions.
7. Redact sensitive data if needed.
8. Package reviewer handoff.

For concrete commands, follow the existing walkthrough and benchmark documents rather than inventing new commands in this runbook.

## Evidence collection checklist

| Evidence | Required? | Where to save | Notes |
|---|---|---|---|
| Commit SHA and environment notes | Yes | `environment.md` | Include timestamp and local/configured scope. |
| Commands run | Yes | `commands.md` | Keep command list exact and ordered. |
| Blocked decision screenshot | Yes | `screenshots/` | Show scenario context and resulting decision. |
| Allowed decision screenshot if scenario exists | Conditional | `screenshots/` | Include only when allow path is part of the run. |
| JSON evidence packet if generated | Conditional | `json/` | Preserve raw generated output. |
| Markdown evidence report if generated | Conditional | `markdown/` | Keep reviewer-readable output adjacent to JSON. |
| Local deterministic metrics artifact reference | Recommended | `reviewer-notes.md` | Link deterministic local metrics artifact used in review. |
| One-Day PoC benchmark output if run | Conditional | `markdown/` or `json/` | Record if benchmark scope is included. |
| Redaction notes | Conditional | `redactions.md` | Describe what was redacted and why. |
| Reviewer notes | Yes | `reviewer-notes.md` | Summarize outcomes, boundaries, and follow-up. |

## What to record for each run

- Date/time.
- Commit SHA.
- Operator role.
- Environment type: local / configured / customer-managed if applicable.
- Whether external providers were enabled.
- Commands run.
- Scenario names.
- Result: pass / fail / inconclusive.
- Exceptions or known limitations.

## Review handoff package

- One short README for the reviewer.
- Evidence Pack link.
- Operator Runbook link.
- Evidence folder.
- Known limitations.
- Explicit non-claim boundaries.
- Open questions / follow-up items.

## Common failure modes

- Required API server not running.
- `VERITAS_API_KEY` missing.
- Evidence generated but not linked in handoff.
- Local deterministic metrics mistaken for production latency.
- Provider cost/latency implied without provider measurement.
- Screenshots lack context.
- Redaction not documented.
- Reviewer cannot identify why action was blocked or allowed.

## Non-claim boundaries

- Do not claim production SLA from local/configured PoC output.
- Do not claim third-party certification.
- Do not claim customer-environment measurement unless actually run and documented in that environment.
- Do not claim EU AI Act compliance certification.
- Do not claim provider cost/latency unless providers are explicitly enabled and separately measured.
- Do not present demo screenshots as production audit evidence.

## Related documents

- [`docs/en/poc/one-day-poc-evidence-pack.md`](one-day-poc-evidence-pack.md)
- [`docs/en/poc/one-day-poc-reviewer-pack.md`](one-day-poc-reviewer-pack.md)
- [`docs/en/poc/one-day-poc-walkthrough.md`](one-day-poc-walkthrough.md)
- [`docs/en/poc/one-day-poc-performance-report.md`](one-day-poc-performance-report.md)
- [`docs/en/benchmarks/local-performance-metrics.latest.md`](../benchmarks/local-performance-metrics.latest.md)
- [`docs/en/benchmarks/performance-metrics.md`](../benchmarks/performance-metrics.md)
- [`docs/INDEX.md`](../../INDEX.md)
- [`docs/DOCUMENTATION_MAP.md`](../../DOCUMENTATION_MAP.md)

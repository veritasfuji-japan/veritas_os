# AML/KYC Customer Handoff Path (pilot -> review)

## Goal

Define a practical handoff sequence so customer evaluator, operator, and
internal sponsor can review the same bounded evidence package.

## Handoff artifact set

1. Pilot run summary JSON (dry-run + live-run)
2. Acceptance criteria summary (PASS/WARNING/FAIL with gate rationale)
3. Synthetic case matrix (representative + failure scenarios)
4. Evidence bundle example mapping (decision/incident/release examples)
5. Security/privacy boundary statement

## Sequence

### Stage A: Internal sponsor checkpoint

- Confirm pilot scope is AML/KYC only.
- Confirm all artifacts are synthetic-only.
- Confirm unresolved failures are documented.

### Stage B: Customer evaluator package delivery

Provide:

- `aml_kyc_pilot_cases.json`
- `aml_kyc_failure_scenarios.json`
- live-run report JSON
- acceptance summary
- example evidence bundle mapping file

Evaluator should be able to trace each representative case to an implemented,
machine-checkable expected semantics contract.

### Stage C: Security / compliance review

- Confirm no PII in fixtures or report examples.
- Confirm endpoint security posture (localhost HTTP only for rehearsal).
- Confirm fail-closed semantics in documented boundary scenarios.

### Stage D: Pilot exit decision

Possible outcomes:

- **Ready for controlled pilot continuation**
- **Conditionally ready with named gaps**
- **Not ready (critical fail-closed regressions present)**

## Not-in-scope statement

This package does not claim:

- legal advice or legal determination automation
- production-data readiness
- expanded domains beyond AML/KYC beachhead

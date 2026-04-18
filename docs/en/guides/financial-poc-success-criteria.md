# Financial PoC Success Criteria (quantitative)

## Objective

Define a machine-checkable success contract for the AML/KYC pilot package.

---

## Acceptance criteria summary

Pilot acceptance is judged on four gates:

- **Gate A: reproducibility**
- **Gate B: operational stability**
- **Gate C: AML/KYC anchor integrity**
- **Gate D: representative scenario contract coverage**

Any gate failure is a pilot `FAIL`.

---

## Metrics and thresholds

For one run report:

- `total`: total pilot questions executed
- `pass_count`: cases with zero semantic mismatches
- `fail_count`: cases with one or more semantic mismatches
- `warning_count`: cases not evaluated or warning-state runtime outcomes
- `evaluated_count = total - warning_count`
- `pass_rate = pass_count / evaluated_count`
- `warning_rate = warning_count / total`

### Target thresholds

- **Gate A (minimum reproducibility)**
  - `evaluated_count >= 5`
  - `pass_rate >= 0.90`
- **Gate B (pilot-ready quality)**
  - `fail_count = 0`
  - `warning_count = 0`
- **Gate C (beachhead consistency)**
  - AML/KYC anchor case status is `pass`
- **Gate D (representative scenario contract)**
  - sanctions partial match is **not** `proceed`
  - source of funds missing is **not** `APPROVE`
  - policy definition missing is `POLICY_DEFINITION_REQUIRED` family
  - sufficient evidence low-risk case is `proceed/APPROVE` family
  - secure/prod controls missing is fail-closed `block`

---

## Outcome bands

- **PASS**
  - Gate A + Gate B + Gate C + Gate D satisfied.
- **WARNING**
  - Gate A + Gate C + Gate D satisfied, but warnings exist and no fails.
- **FAIL**
  - Any gate violation.

---

## Evaluator interpretation notes

- Warning-only runs are not sign-off quality for customer pilot review.
- Failure scenarios must be disclosed, not hidden, in handoff artifacts.
- Success does not imply legal determination automation.

---

## Security and privacy constraints

- Keep fixtures synthetic and deterministic.
- Never include production customer data, account identifiers, or raw watchlist
  extracts in pilot artifacts.
- Keep `http://` endpoint usage restricted to localhost rehearsal only.

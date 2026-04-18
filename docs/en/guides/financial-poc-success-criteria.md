# Financial PoC Success Criteria (quantitative)

## Objective

Define a machine-checkable success contract for the financial PoC runner.

---

## Metrics and thresholds

For one run report:

- `total`: total PoC questions executed
- `pass_count`: cases with zero semantic mismatches
- `fail_count`: cases with one or more semantic mismatches
- `warning_count`: cases not evaluated due to runtime issues (HTTP errors/timeouts)
- `evaluated_count = total - warning_count`
- `pass_rate = pass_count / evaluated_count`
- `warning_rate = warning_count / total`

### Target thresholds

- **Gate A (minimum reproducibility)**
  - `evaluated_count >= 5`
  - `pass_rate >= 0.90`
- **Gate B (demo-ready quality)**
  - `fail_count = 0`
  - `warning_count = 0`
- **Gate C (beachhead consistency)**
  - `aml_kyc` anchor case status is `pass`
- **Gate D (representative scenario contract)**
  - sanctions partial match case is **not** `proceed`
  - source of funds missing case is **not** `APPROVE`
  - approval boundary unknown is `human_review_required` or `hold`
  - high-risk ambiguity uses human-review path
  - sufficient evidence case is `proceed/APPROVE` family
  - policy definition missing is `POLICY_DEFINITION_REQUIRED` family
  - secure/prod controls missing is fail-closed `block`

---

## Outcome bands

- **PASS**
  - Gate A + Gate B + Gate C + Gate D satisfied.
- **WARNING**
  - Gate A + Gate C + Gate D satisfied, but warnings exist (`warning_count > 0`) and no fails.
- **FAIL**
  - Any gate violation; for example `fail_count > 0`, `pass_rate < 0.90`, `evaluated_count < 5`, or representative-case contract failure.

---

## Operational notes

- Keep the fixture synthetic and deterministic.
- Treat warning-only runs as operational instability, not semantics correctness.
- Track mismatch deltas over time as a regression signal.
- For live run security, keep `http://` endpoints limited to localhost and avoid production customer data in PoC payloads.

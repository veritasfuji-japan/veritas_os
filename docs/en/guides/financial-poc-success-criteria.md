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

### Target thresholds

- **Gate A (minimum reproducibility)**
  - `evaluated_count >= 5`
  - `pass_rate >= 0.90`
- **Gate B (demo-ready quality)**
  - `fail_count = 0`
  - `warning_count = 0`
- **Gate C (beachhead consistency)**
  - `aml_kyc` anchor case status is `pass`

---

## Outcome bands

- **PASS**
  - Gate A + Gate B + Gate C satisfied.
- **WARNING**
  - Gate A satisfied, but warnings exist (`warning_count > 0`) and no fails.
- **FAIL**
  - `fail_count > 0`, or `pass_rate < 0.90`, or `evaluated_count < 5`.

---

## Operational notes

- Keep the fixture synthetic and deterministic.
- Treat warning-only runs as operational instability, not semantics correctness.
- Track mismatch deltas over time as a regression signal.

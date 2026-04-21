# AML/KYC Operator Runbook (pilot package)

## Scope

Operational runbook for AML/KYC pilot execution using synthetic fixtures.
No production customer data is allowed.

## Inputs

- Runner CLI: `scripts/run_financial_poc.py`
- Runtime: `veritas_os/scripts/financial_poc_runner.py`
- Pilot cases:
  `veritas_os/sample_data/governance/aml_kyc_pilot_cases.json`
- Failure scenarios:
  `veritas_os/sample_data/governance/aml_kyc_failure_scenarios.json`

## Step-by-step execution

### 1) Environment sanity checks

```bash
curl -s http://localhost:8000/health
```

```bash
test -f veritas_os/sample_data/governance/aml_kyc_pilot_cases.json && echo "pilot_fixture_ok"
```

### 2) Dry-run (fixture and comparator plumbing)

```bash
python scripts/run_financial_poc.py \
  --input veritas_os/sample_data/governance/aml_kyc_pilot_cases.json \
  --dry-run \
  --output-json veritas_os/scripts/logs/aml_kyc_pilot_dry_run_report.json
```

Expected: `outcome=pass`, no warnings, no mismatches.

### 3) Live-run (strict required evidence)

```bash
VERITAS_API_KEY=demo-key \
python scripts/run_financial_poc.py \
  --input veritas_os/sample_data/governance/aml_kyc_pilot_cases.json \
  --api-url http://localhost:8000/v1/decide \
  --required-evidence-mode strict \
  --output-json veritas_os/scripts/logs/aml_kyc_pilot_live_report.json
```

### 4) Acceptance readout

Pilot pass requires:

- `summary.outcome` is `pass`
- `summary.counts.fail == 0`
- `summary.counts.warning == 0`
- `summary.pass_rate >= 0.90`
- `summary.evaluated >= 5`

Additionally, confirm bind-boundary lineage visibility on sampled decisions:

- `bind_outcome` is present when bind adjudication ran.
- `execution_intent_id` and `bind_receipt_id` are present for bind-tracked cases.
- `bind_outcome` is interpreted separately from decision approval status.

### 5) Failure-path validation

Use the failure scenario file to ensure evaluator has bounded expectations:

- run scenarios that should hold/block/review, not auto-proceed
- document each scenario result in pilot readout
- if runtime behavior diverges, mark as explicit gap (not hidden backlog)

### 6) Bind receipt spot-check (operator API)

```bash
curl -s "http://localhost:8000/v1/governance/bind-receipts?limit=5"
```

```bash
curl -s "http://localhost:8000/v1/governance/bind-receipts/<bind_receipt_id>"
```

Expected: receipt includes authority/constraint/drift/risk/admissibility
payloads and a terminal bind outcome (`COMMITTED`/`BLOCKED`/`ESCALATED`/`ROLLED_BACK`).

## Operator triage rubric

- **PASS**: all representative scenario contracts hold.
- **WARNING**: runtime/connectivity instability, semantics otherwise stable.
- **FAIL**: any semantic mismatch on required contract fields.

Treat any unexpected `proceed/APPROVE` in AML/KYC ambiguity as critical.

## Security reminders

- Do not persist API keys in shell history for shared environments.
- Do not copy raw reports containing request payloads into public channels.
- Keep all pilot artifacts labeled `synthetic-only`.

# One-Day VERITAS PoC Walkthrough

## Purpose

This walkthrough provides a one-day, external-reviewer-friendly PoC flow for demonstrating VERITAS value through existing capabilities, without changing runtime semantics.

## Target audience

- HPAN reviewers
- Enterprise stakeholders and solution owners
- Audit and assurance reviewers
- Investors and technical due-diligence reviewers

## What this PoC demonstrates

- Observability capability reporting via `GET /v1/observability/capabilities`
- RBAC denial audit append visibility (as exposed by current observability/reporting surfaces)
- Human Approval Workbench path for governance policy changes (review path and evidence)
- Bind Boundary outcomes and receipts
- Trace and span-chain continuity for governance-related flow
- Existing TrustLog and auditability signals as implemented today

## What this PoC does not demonstrate

- Full production deployment hardening and operations
- Deployment of Jaeger, Grafana, Tempo, or OTLP collector
- Cryptographic human approval signatures
- Any stronger TrustLog append durability guarantee beyond the current implementation
- Final enterprise packaging, commercial SLA, or complete security certification

This PoC is intended to show enforceable boundaries and auditable behavior, not final production packaging. The sanitized evidence packet is the recommended deliverable for external review.

Before running the smoke script, reviewers can preview the final deliverable format using the sample packet fixtures: `docs/en/poc/sample-one-day-poc-evidence.json`, `docs/en/poc/sample-one-day-poc-evidence.md`, and `docs/ja/poc/sample-one-day-poc-evidence.md`. These samples are dummy/sanitized/fixture-based and are not live environment evidence.
The evidence JSON follows the repo-local schema at `schemas/poc/one_day_poc_evidence.v1.schema.json`.
`python scripts/demo/one_day_poc_smoke.py --print-schema-path` prints the repo-local schema path without requiring an API key or network access.
`python scripts/demo/one_day_poc_smoke.py --validate-evidence PATH` validates a generated evidence JSON offline without requiring an API key or network access.
This validation mode is a lightweight stdlib contract check aligned with the v1 schema, not a full external jsonschema engine.
`generated_at` uses fixed UTC Z format: `YYYY-MM-DDTHH:MM:SSZ`.
`--validate-generated-evidence` validates the generated JSON evidence packet during the same smoke run when used with `--evidence-json`.

## Prerequisites

1. Running VERITAS API server.
2. API key with read permissions for observability endpoints.
   - The API key must map to a role with `governance_read` permission, such as `auditor` or `admin`.
3. Local environment variables:
   - `VERITAS_BASE_URL` (optional, default `http://127.0.0.1:8000`)
   - `VERITAS_API_KEY` (required)
   - `VERITAS_DEMO_ALLOW_MUTATION` (optional, default `false`)
4. Python runtime for the smoke script.

## Scenario A: Observability capability check

1. Run:
   - `python scripts/demo/one_day_poc_smoke.py --json`
   - `python scripts/demo/one_day_poc_smoke.py --json --evidence-json /tmp/veritas_poc_evidence.json`
   - `python scripts/demo/one_day_poc_smoke.py --evidence-md /tmp/veritas_poc_evidence.md`
   - With `--json`, stdout stays parseable JSON and status lines are emitted to stderr.
2. Confirm `capabilities_ok: true`.
3. Confirm summary includes:
   - structured logging format
   - OpenTelemetry importability signal
   - exporter configured signal
   - governance span chain signal
   - RBAC denial audit append visibility signal

## Scenario B: RBAC denial audit visibility

1. Produce or retrieve an RBAC-denied event through your standard test flow.
2. Show that denial evidence is visible through the existing audit/observability path.
3. Cross-check summary output and operational logs for the same trace context when possible.

## Scenario C: Governance policy update with human approval

1. Walk through governance policy update process in Human Approval Workbench.
2. Demonstrate that a 4-eyes approval path is required by current implementation.
3. Show evidence trail (approval record + audit entries).
4. Demonstrate post-approval edit invalidation behavior as currently implemented.

## Scenario D: Bind Boundary outcome and receipt

1. Execute a policy-governed action sample.
2. Show Bind Boundary outcome (`allow` or `deny`) and produced receipt/evidence.
3. Link outcome to policy context and audit entries.

## Scenario E: Trace/span verification

1. Select one end-to-end request from Scenarios B–D.
2. Show `trace_id` propagation across request/audit logs.
3. Show governance span chain continuity from decision to emitted evidence.

## Evidence checklist

- [ ] `GET /v1/observability/capabilities` response captured.
- [ ] Smoke script JSON summary captured.
- [ ] Sanitized evidence packet (`--evidence-json` / `--evidence-md`) generated for external reviewers.
- [ ] RBAC denial example with audit visibility.
- [ ] Human approval evidence for governance update path.
- [ ] Bind Boundary outcome + receipt sample.
- [ ] Trace ID and governance span chain continuity proof.
- [ ] Notes about limitations and non-goals included in reviewer packet.

## Success criteria

- External reviewers can follow the sequence without internal tribal knowledge.
- Reviewers can independently verify observability capability signals.
- Reviewers can inspect evidence for RBAC, human approval, bind boundary, and trace continuity.
- No runtime governance/bind/RBAC/TrustLog semantics are changed for the demo.

## Known limitations

- Not a production deployment reference architecture.
- No bundled Jaeger/Grafana/Tempo/OTLP collector deployment in this walkthrough.
- No cryptographic human approval signatures.
- TrustLog durability characteristics remain exactly as implemented today.
- Optional mutation path is disabled by default in smoke tooling.
- Evidence packet is PoC evidence only, not production certification.

## Evidence packet contents and exclusions

The one-day smoke script can generate a sanitized evidence packet for external sharing:

- `--evidence-json PATH`: writes a structured JSON evidence packet.
- `--evidence-md PATH`: writes a reviewer-friendly Markdown packet.

Included in the packet:

- Allowlisted summary signals for observability capabilities.
- Read-only check status for observability and governance policy read.
- Documentation links and explicit PoC non-goals.

Not included in the packet:

- API keys or any `X-API-Key` values.
- Raw exporter endpoint URLs.
- Raw environment values.
- Raw request/response payload bodies.
- Tokens, cookies, passwords, secrets, or authorization headers.

## Suggested talk track for external reviewers

1. "We are demonstrating enforceable governance boundaries and auditable outcomes, not a full production rollout."
2. "First, we show capability surfaces and logging/trace controls as currently implemented."
3. "Second, we show RBAC denial visibility and governance approval controls (including 4-eyes and post-approval edit invalidation)."
4. "Third, we show bind outcomes and receipts tied to trace-linked evidence."
5. "Finally, we highlight what is intentionally out-of-scope for this one-day PoC."

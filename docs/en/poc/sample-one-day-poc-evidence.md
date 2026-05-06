# VERITAS One-Day PoC Evidence Packet — Sample

> This is a fully dummy, sanitized sample packet for format preview only. It is not evidence from any live or production environment.

Generated at: 2026-01-01T00:00:00Z
Read-only: true
Mutation allowed: false

## Summary

- Packet type: `veritas_one_day_poc_evidence`
- Schema version: `one_day_poc_evidence.v1`
- Observability capabilities check result: PASS
- Governance policy read check status: 200

## Checks

### Observability Capabilities

- Status: 200
- Result: PASS
- Structured logging format: `json`
- OpenTelemetry importable: `true`
- Exporter configured: `false`
- Governance span chain: `true`
- RBAC denial audit append visibility: `true`

### Governance Policy Read

- Status: 200
- Required: `false`

## Evidence Links

- One-day walkthrough EN: `docs/en/poc/one-day-poc-walkthrough.md`
- One-day walkthrough JA: `docs/ja/poc/one-day-poc-walkthrough.md`
- Governance trace span chain EN: `docs/en/operations/governance-trace-span-chain.md`
- Governance trace span chain JA: `docs/ja/operations/governance-trace-span-chain.md`

## Non-goals / limitations

- `not_a_production_deployment_reference`
- `no_jaeger_grafana_tempo_otlp_deployment`
- `no_cryptographic_human_approval_signature`
- `no_new_trustlog_durability_guarantee`

## Security boundary

This sample contains no API keys, raw endpoints, tokens, cookies, passwords, secrets, or raw request/response bodies.


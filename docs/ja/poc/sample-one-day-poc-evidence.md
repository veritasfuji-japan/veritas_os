# VERITAS One-Day PoC Evidence Packet — Sample（日本語版）

> この文書は英語版サンプル `docs/en/poc/sample-one-day-poc-evidence.md` に対応する日本語版です。
> 実環境の証跡ではなく、完全なダミー / sanitized / fixture-based サンプルです。

生成時刻: 2026-01-01T00:00:00Z
読み取り専用: true
変更許可: false

## Summary（概要）

- Packet type: `veritas_one_day_poc_evidence`
- Schema version: `one_day_poc_evidence.v1`
- 観測性チェック結果: PASS
- Governance policy read チェックのステータス: 200

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

- `not_a_runtime_deployment_reference`
- `no_jaeger_grafana_tempo_otlp_deployment`
- `no_cryptographic_human_approval_signature`
- `no_new_trustlog_durability_guarantee`

## Security boundary

このサンプルには認証情報・機密値・セッション値・直接 endpoint・raw request body・raw response body を含みません。

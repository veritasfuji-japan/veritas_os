# RSA ↔ VERITAS Controlled Live V.I.K.I. Fixture Validation Plan

## 英語正本

- [RSA ↔ VERITAS Controlled Live V.I.K.I. Fixture Validation Plan](../../en/guides/rsa-veritas-controlled-live-viki-fixture-validation-plan.md)

## 1. 目的

本書は、controlled live V.I.K.I. payload schema fixtures の fixture validation 計画を定義する。

これは documentation-only であり、以下を**実装しない**:
- validation test implementation
- runtime implementation
- live integration
- production API endpoint
- network calls
- secrets / credentials の追加
- 実データ KYC 処理
- 本番利用の承認

fixture validation test skeleton 実装前に、本計画のレビューを必須とする。

## 2. 現在のベースライン

以下の pre-live gate は既に存在する:
- local mock ingestion receiver design
- local mock receiver test fixture plan
- local mock receiver implementation
- local mock receiver validation snapshot
- static synthetic JSON fixture-driven E2E harness
- E2E harness validation snapshot
- controlled live integration threat model
- controlled live payload schema draft
- controlled live transport/authentication design
- controlled live replay protection and correlation-id design
- controlled live redaction and observability design
- controlled live payload schema fixture examples
- controlled live failure-mode test plan

現在の実装パス:

static synthetic JSON fixture
→ ingest_local_viki_mock_payload()
→ RSASandboxPayload
→ evaluate_rsa_sandbox_signal()
→ VERITAS decision
→ redacted audit output

このパスは local-only / synthetic-data-only / no-network。

本計画は将来テストの planning artifact のみであり、live runtime behavior と test implementation を導入しない。

## 3. 検証対象 fixture ディレクトリ

- `tests/fixtures/controlled_live_viki_payload_schema/`

要件:
- すべて synthetic fixture。
- 実 customer data を含めない。
- 実 KYC data（raw KYC records）を含めない。
- 実 secrets / credentials を含めない。
- live V.I.K.I. data を含めない。
- network access を要求しない。
- credentials を要求しない。
- production use を承認しない。

## 4. Fixture inventory validation

EN 正本と同一 inventory / category / expected validation class を適用する。欠落 fixture は fail、予期しない追加 fixture はレビュー必須。

## 5. JSON syntax validation

将来テストは次を検証する:
- fixture は valid JSON
- fixture は JSON object
- 明示的 invalid fixture 追加がない限り array payload を不許可
- empty fixture を不許可
- comments / JSON5 / 非標準 JSON を不許可
- malformed fixture を silently skip しない
- deterministic 判定

## 6. Required field validation

valid fixture 必須 field:
- schema_version
- rsa_status
- trigger_source
- timestamp
- request_id
- correlation_id
- payload_issued_at

valid fixture は必須 field 存在・型一致・文字列非空。`timestamp` と `payload_issued_at` は timezone-aware。

invalid fixture は欠落を intentional とし、`invalid_missing_request_id_v1alpha1.json` と `invalid_missing_correlation_id_v1alpha1.json` を対応 fixture とする。

## 7. Accepted rsa_status validation

許容 enum:
- SAFE_PROCEED
- DENSITY_THROTTLED
- ALGORITHMIC_HUMILITY_ENGAGED
- DEFERRAL_ENGAGED

unknown / empty / null / multiple encoded statuses は不許可。`invalid_unknown_rsa_status_v1alpha1.json` は意図的 invalid。

## 8. schema_version validation

現行 draft は `schema_version = "v1alpha1"`。

valid fixture は `"v1alpha1"` を使用。`invalid_unsupported_schema_version.json` は意図的 unsupported schema_version。

## 9. Timestamp validation

- timestamp と payload_issued_at は RFC 3339 UTC または timezone-aware ISO-8601 (UTC 正規化)
- naive timestamp は reject
- skew > 300 seconds は fail closed
- skew = 300 seconds は accepted

本計画は clock-skew ロジックを実装しない。

## 10. request_id / correlation_id validation

- valid fixture で request_id / correlation_id 必須・非空
- PII / secrets / raw reasoning を含めない
- `invalid_duplicate_request_id_scenario_a_v1alpha1.json` と `invalid_duplicate_request_id_scenario_b_v1alpha1.json` は replay scenario
- replay window 内で scenario B は duplicate/replay
- 同一 request_id かつ異なる correlation_id は replay/correlation mismatch

## 11. Forbidden field validation

検出対象 forbidden fields:
- chain_of_thought
- hidden_model_state
- raw_llm_reasoning
- raw_viki_reasoning
- raw_kyc_record
- customer_pii
- secrets
- credentials
- api_key
- access_token
- refresh_token
- private_key
- webhook_secret
- unredacted_regulated_data

forbidden fields は valid fixture で不許可。監査・観測に非出力。SAFE_PROCEED へ変換禁止。

## 12. Secret / regulated-data validation

- 実 API key / access_token / refresh_token / private_key / webhook secret 不許可
- 実 KYC / customer PII / regulated financial data 不許可
- `FORBIDDEN_SYNTHETIC_TOKEN` 等は synthetic invalid として維持
- live secret scanner / network calls を不要とする

## 13. Optional field validation

許容 optional fields:
- source_environment
- source_instance_id
- rsa_action_taken
- original_llm_intent
- upstream_confidence_class
- upstream_latency_ms
- upstream_reason_code

`upstream_latency_ms` は non-negative integer。`upstream_confidence_class` は LOW/MEDIUM/HIGH/UNSPECIFIED。
optional fields に raw reasoning / PII / secrets を含めない。

## 14-16. Failure mapping / result classes / output

EN 正本と同一の fixture-to-failure mapping と result class enum を使用:
- FIXTURE_VALID
- FIXTURE_INVALID_JSON
- FIXTURE_INVALID_SCHEMA
- FIXTURE_UNSUPPORTED_SCHEMA_VERSION
- FIXTURE_UNKNOWN_RSA_STATUS
- FIXTURE_MISSING_REQUIRED_FIELD
- FIXTURE_INVALID_TIMESTAMP
- FIXTURE_FORBIDDEN_FIELD_PRESENT
- FIXTURE_SECRET_LIKE_VALUE_PRESENT
- FIXTURE_REGULATED_DATA_PRESENT
- FIXTURE_REPLAY_SCENARIO_DUPLICATE
- FIXTURE_INVENTORY_MISMATCH

これらは draft 名称。実装前にレビューし、deterministic かつデータ漏えい防止（raw payload / raw reasoning / secrets / PII 非出力）を満たす。

## 17. No-network validation requirement

fixture validation は live V.I.K.I. / external APIs / production endpoints / credentials / live transport / live KYC data を要求しない。完全 offline で static synthetic fixtures のみを使用する。

## 18. failure-mode test plan との関係

failure-mode test plan は behavioral tests、本計画は first static validation layer。fixture validation を先行実行し、well-formed かつ intentional classification を保証する。runtime failure-mode tests の代替ではない。

## 19. 実装前ゲート

threat model / payload schema draft / transport-auth / replay-correlation / redaction-observability / fixture examples / failure-mode test plan / 本計画 merged、no-network 戦略確認、synthetic-only 範囲確認、inventory 凍結・レビュー、result classes レビュー、no secrets 確認を必須とする。

## 20. Non-goals

本計画は次を許可しない:
- production live V.I.K.I. integration
- production API endpoint
- transport/authentication/replay cache/observability/logging implementation
- 実 KYC / customer data / live LLM text / raw V.I.K.I. reasoning の取り込み
- VERITAS commit gate の bypass
- secrets の repo 保存
- production AML/KYC compliance claims
- regulatory approval claims
- legal advice claims

## 21. Compatibility preservation

- rsa_status は v1 payload field のまま
- RSASandboxPayload は downstream container のまま
- evaluate_rsa_sandbox_signal() は downstream evaluator のまま
- upstream_signal_source = "RSA" を維持
- request_id / correlation_id は controlled-live schema field（rsa_status の置換ではない）
- viki_status / VIKIPayload はこのフェーズで導入しない
- naming migration は v2 の別変更で扱う

## 22. 本計画が検証すること

要件定義、inventory、JSON、required fields、accepted rsa_status、timestamp、request_id/correlation_id、forbidden fields、no-network requirement を明示し、live implementation 非導入を保証する。

## 23. 本計画が検証しないこと

tests / runtime / live V.I.K.I. / transport / authentication / replay cache / observability の実装は行わない。runtime fail-closed behavior 検証や実 KYC 処理、本番デプロイ承認も行わない。

## 24. 次の推奨 PR

安全な次 PR 候補:
- controlled live fixture validation test skeleton
- controlled live failure-mode test skeleton
- redaction fixture examples
- observability event taxonomy fixture plan
- controlled live integration implementation plan

最優先推奨:
- static synthetic fixtures のみを使い、offline 実行し、live transport を追加しない controlled live fixture validation test skeleton。

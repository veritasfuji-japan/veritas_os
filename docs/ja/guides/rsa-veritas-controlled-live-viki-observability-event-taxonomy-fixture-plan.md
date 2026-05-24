# RSA ↔ VERITAS Controlled Live V.I.K.I. Observability Event Taxonomy Fixture Plan

## 英語正本

- [RSA ↔ VERITAS Controlled Live V.I.K.I. Observability Event Taxonomy Fixture Plan](../../en/guides/rsa-veritas-controlled-live-viki-observability-event-taxonomy-fixture-plan.md)

## 1. 目的

本書は、将来の controlled live V.I.K.I. observability fixtures に向けた observability event taxonomy fixture plan を定義する documentation-only 文書です。

- observability implementation ではありません。
- logging implementation ではありません。
- telemetry implementation ではありません。
- fixture implementation ではありません。
- test implementation ではありません。
- runtime implementation ではありません。
- live integration ではありません。
- production API endpoint ではありません。
- network calls を追加しません。
- secrets / credentials を追加しません。
- real KYC data を処理しません。
- production use を許可しません。

observability event fixture examples や tests を追加する前に、必ず本計画をレビューします。

## 2. Current baseline

既存 pre-live gates:
- controlled live integration threat model
- controlled live payload schema draft
- controlled live transport/authentication design
- controlled live replay protection and correlation-id design
- controlled live redaction and observability design
- controlled live payload schema fixture examples
- controlled live failure-mode test plan
- controlled live fixture validation plan
- controlled live fixture validation test skeleton
- controlled live failure-mode test skeleton

現行実装/検証パスは local-only・synthetic-data-only・no-network を維持します。現フェーズで live V.I.K.I. integration、observability implementation、logging/telemetry implementation は存在しません。

## 3. Future observability fixture boundary

`controlled live synthetic payload fixture`
→ `transport/authentication result class`
→ `message integrity result class`
→ `replay/correlation result class`
→ `schema validation result class`
→ `VERITAS decision result class`
→ `redacted synthetic observability event fixture`
→ `offline fixture validation test`
→ `offline failure-mode test`

Observability fixtures は synthetic 限定とし、raw payload bodies、raw V.I.K.I. reasoning、raw LLM text、chain-of-thought、hidden model state、raw KYC records、customer PII、secrets / credentials を含めません。live integration の承認にもなりません。

## 4-8. Draft taxonomy / fields / forbidden / result classes

`event_type`（draft）:
- viki_payload_received
- transport_authentication_checked
- message_integrity_checked
- replay_window_checked
- replay_cache_checked
- schema_validation_checked
- rsa_sandbox_payload_constructed
- rsa_sandbox_signal_evaluated
- veritas_decision_emitted
- human_review_required
- upstream_unavailable
- upstream_timeout
- forbidden_field_detected
- secret_like_value_detected
- regulated_data_detected
- fail_closed_emitted

必須 fields:
- event_type
- event_version (`v1alpha1`)
- schema_version (`v1alpha1`)
- request_id
- correlation_id
- timestamp
- payload_issued_at
- upstream_signal_source (`"RSA"`)
- veritas_continuation_decision
- veritas_reason_code
- veritas_sandbox_commit_state
- required_next_action
- final_commit_approved (`false` in all pre-live fixtures)

optional allowed fields:
- source_environment
- source_instance_id
- rsa_status
- trigger_source
- authentication_result_class
- integrity_result_class
- replay_result_class
- schema_validation_result_class
- redaction_result_class
- forbidden_field_result_class
- latency_ms
- body_hash_prefix
- fixture_name
- fixture_classification
- failure_class
- decision_source

forbidden fields/content:
- chain_of_thought
- hidden_model_state
- raw_llm_reasoning
- raw_viki_reasoning
- raw_llm_text
- raw_kyc_record
- customer_pii
- secrets
- credentials
- api_key
- access_token
- refresh_token
- private_key
- webhook_secret
- raw_authorization_header
- authorization
- bearer_token
- unredacted_regulated_data
- raw_payload_body
- raw_request_body
- raw_response_body
- raw_stack_trace_with_secrets

result class taxonomy（draft）:
- authentication_result_class: AUTHENTICATED / AUTHENTICATION_FAILED / AUTHENTICATION_NOT_EVALUATED
- integrity_result_class: INTEGRITY_VALID / INTEGRITY_FAILED / BODY_HASH_MISMATCH / INTEGRITY_NOT_EVALUATED
- replay_result_class: NO_REPLAY_DETECTED / REPLAY_DUPLICATE_REQUEST_ID / REPLAY_CACHE_UNAVAILABLE / REPLAY_NOT_EVALUATED
- schema_validation_result_class: SCHEMA_VALID / SCHEMA_INVALID / SCHEMA_UNSUPPORTED_VERSION / SCHEMA_UNKNOWN_RSA_STATUS / SCHEMA_MISSING_REQUIRED_FIELD / SCHEMA_INVALID_TIMESTAMP / SCHEMA_NOT_EVALUATED
- redaction_result_class: REDACTION_VALID / FORBIDDEN_FIELD_DETECTED / SECRET_LIKE_VALUE_DETECTED / REGULATED_DATA_DETECTED / REDACTION_NOT_EVALUATED
- veritas_sandbox_commit_state: SUSPENDED_NOT_COMMITTED
- continuation decisions: CONTINUE_TO_BIND_BOUNDARY / CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED / PAUSE_FOR_HUMAN_REVIEW

## 9-13. Fixture categories and synthetic examples

fixture category names（将来カテゴリ名、未確定 filename）:
- positive path: valid_safe_proceed_decision_event, valid_density_throttled_decision_event, valid_algorithmic_humility_decision_event, valid_deferral_decision_event
- failure path: invalid_unknown_rsa_status_fail_closed_event ほか
- simulated upstream/transport path: upstream_timeout_fail_closed_event, upstream_unavailable_fail_closed_event, transport_auth_failed_event, message_integrity_failed_event, replay_cache_unavailable_event

SAFE_PROCEED constraints:
- `event_type = veritas_decision_emitted`
- `rsa_status = SAFE_PROCEED`
- `veritas_continuation_decision = CONTINUE_TO_BIND_BOUNDARY`
- `veritas_sandbox_commit_state = SUSPENDED_NOT_COMMITTED`
- `required_next_action = CONTINUE_BOUNDARY_EVALUATION`
- `final_commit_approved = false`

fail-closed constraints:
- `PAUSE_FOR_HUMAN_REVIEW`
- `SUSPENDED_NOT_COMMITTED`
- deterministic `veritas_reason_code`

本書は safe synthetic example shape / invalid synthetic example shape を EN 正本と同一キー・同一 enum で定義します。invalid 例の `chain_of_thought` / `raw_kyc_record` / `access_token` は将来 validation で reject されるべきです。

## 14-22. テスト関係、非目標、互換性、次PR

- 既存 `tests/governance/test_controlled_live_viki_fixture_validation.py` と `tests/governance/test_controlled_live_viki_failure_modes.py` は payload fixtures を対象とする offline synthetic-fixture-only tests です。
- 将来 observability fixture validation も offline・no-network・no-credentials・no telemetry SDKs を維持します。
- forbidden fields は reject し、SAFE_PROCEED へ変換せず、redacted audit output に永続化しません。

互換性維持:
- `rsa_status` 維持
- `RSASandboxPayload` 維持
- `evaluate_rsa_sandbox_signal()` 維持
- `upstream_signal_source = "RSA"` 維持
- `request_id` / `correlation_id` は schema/correlation field（`rsa_status` の置換ではない）
- `viki_status` / `VIKIPayload` は導入しない（v2 の別変更対象）

推奨次PR:
- controlled live observability event fixture examples（最優先）
- controlled live observability event fixture validation test skeleton
- redaction fixture examples
- controlled live integration implementation plan

いずれも synthetic-fixture-only を維持し、runtime・network・logging implementation・telemetry implementation を導入しません。

## 関連フィクスチャ成果物

関連資料: [Controlled live V.I.K.I. observability event fixture examples](./rsa-veritas-controlled-live-viki-observability-event-fixture-examples.md)。

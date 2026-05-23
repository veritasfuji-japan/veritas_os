# RSA ↔ VERITAS Controlled Live V.I.K.I. Failure-Mode Test Plan

## 英語正本

- [RSA ↔ VERITAS Controlled Live V.I.K.I. Failure-Mode Test Plan](../../en/guides/rsa-veritas-controlled-live-viki-failure-mode-test-plan.md)

## 1. 目的

本ドキュメントは、RSA ↔ VERITAS sandbox stack における将来の controlled live V.I.K.I. integration に向けた failure-mode test plan を定義します。

本ページは documentation-only です。

- test implementation ではありません。
- live integration ではありません。
- runtime implementation ではありません。
- production API endpoint ではありません。
- network calls は追加しません。
- secrets / credentials は追加しません。
- real KYC data は処理しません。
- production use を許可しません。

この計画は、controlled live runtime implementation を開始する前にレビューされる必要があります。

## 2. 現在の baseline

以下の pre-live gates は既に存在します。

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

現在検証済みの経路:

`static synthetic JSON fixture`
→ `ingest_local_viki_mock_payload()`
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ `VERITAS decision`
→ `redacted audit output`

補足:

- 現在の実装経路は local-only / synthetic-data-only / no-network です。
- 本 controlled live failure-mode test plan は将来テスト計画のアーティファクトに限定されます。
- live runtime behavior は導入しません。
- Offline test skeleton は `tests/governance/test_controlled_live_viki_failure_modes.py` に追加済みです（test-only / synthetic-fixture-only / runtime・live integration なし）。
- この failure-mode test skeleton は endpoint・network calls・credentials・replay cache 実装・logging 実装・observability 実装を導入しません。

## 3. 対象 fixture set

fixture ディレクトリ:

- `tests/fixtures/controlled_live_viki_payload_schema/`

| Fixture file | Category | Expected behavior class |
| --- | --- | --- |
| `valid_safe_proceed_v1alpha1.json` | valid | schema-valid controlled-live example |
| `valid_density_throttled_v1alpha1.json` | valid | schema-valid controlled-live example |
| `valid_algorithmic_humility_engaged_v1alpha1.json` | valid | schema-valid controlled-live example |
| `valid_deferral_engaged_v1alpha1.json` | valid | schema-valid controlled-live example |
| `invalid_unknown_rsa_status_v1alpha1.json` | invalid schema | fail closed |
| `invalid_missing_request_id_v1alpha1.json` | invalid schema | fail closed |
| `invalid_missing_correlation_id_v1alpha1.json` | invalid schema | fail closed |
| `invalid_forbidden_chain_of_thought_v1alpha1.json` | forbidden field | fail closed or reject before persistence |
| `invalid_secret_access_token_v1alpha1.json` | forbidden secret | fail closed or reject before persistence |
| `invalid_raw_kyc_record_v1alpha1.json` | forbidden regulated data | fail closed or reject before persistence |
| `invalid_naive_timestamp_v1alpha1.json` | invalid timestamp | fail closed |
| `invalid_payload_issued_at_future_skew_v1alpha1.json` | timestamp freshness | fail closed if beyond reviewed skew |
| `invalid_duplicate_request_id_scenario_a_v1alpha1.json` | replay scenario baseline | first observed request in replay window scenario |
| `invalid_duplicate_request_id_scenario_b_v1alpha1.json` | replay duplicate | fail closed if scenario A is already observed |
| `invalid_unsupported_schema_version.json` | unsupported schema | fail closed |

## 4. カバーすべき test layers

### Layer 1: fixture syntax validation

- すべての fixture file は valid JSON であること。
- fixture inventory が manifest と一致すること。
- real secrets を含まないこと。
- real KYC data を含まないこと。
- real customer data を含まないこと。

### Layer 2: schema validation

- required fields が存在すること。
- 型が妥当であること。
- 受理対象 `rsa_status` のみであること。
- `schema_version` がサポート対象であること。
- `timestamp` と `payload_issued_at` が妥当であること。

### Layer 3: transport/authentication failure simulation

- missing authentication
- failed authentication
- failed signature verification
- body hash mismatch
- missing or mismatched transport metadata

### Layer 4: replay/correlation failure simulation

- missing `request_id`
- missing `correlation_id`
- duplicate `request_id`
- same `request_id` with different `correlation_id`
- replay cache unavailable
- stale `payload_issued_at`
- future `payload_issued_at` beyond skew

### Layer 5: redaction/observability failure simulation

- chain-of-thought detected
- hidden model state detected
- `access_token` detected
- raw KYC records detected
- raw Authorization header logging attempted
- raw payload logging attempted

### Layer 6: upstream availability failure simulation

- V.I.K.I. timeout
- V.I.K.I. unreachable
- connection refused
- partial response
- missing payload

### Layer 7: VERITAS decision safety checks

- invalid input never becomes `SAFE_PROCEED`
- `SAFE_PROCEED` does not equal final commit approval
- VERITAS commit gate remains authoritative
- fail-closed state maps to `PAUSE_FOR_HUMAN_REVIEW` and `SUSPENDED_NOT_COMMITTED`

## 5. Positive fixture test expectations

| Fixture | Expected rsa_status | Expected high-level outcome | Commit gate note |
| --- | --- | --- | --- |
| `valid_safe_proceed_v1alpha1.json` | `SAFE_PROCEED` | may continue to bind-boundary evaluation | not final commit approval |
| `valid_density_throttled_v1alpha1.json` | `DENSITY_THROTTLED` | continue with upstream intervention logged | not final commit approval |
| `valid_algorithmic_humility_engaged_v1alpha1.json` | `ALGORITHMIC_HUMILITY_ENGAGED` | pause for human review | not final commit approval |
| `valid_deferral_engaged_v1alpha1.json` | `DEFERRAL_ENGAGED` | block final commit | not final commit approval |

- Positive fixture tests でも、`SAFE_PROCEED` が final commit approval と同一視されないことを検証する必要があります。
- Positive fixture tests でも、redacted audit output を検証する必要があります。
- Positive fixture tests は live V.I.K.I. transport を要件にしてはいけません。

## 6. Schema failure test expectations

| Failure | Fixture | Expected behavior |
| --- | --- | --- |
| unknown `rsa_status` | `invalid_unknown_rsa_status_v1alpha1.json` | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| missing `request_id` | `invalid_missing_request_id_v1alpha1.json` | fail closed |
| missing `correlation_id` | `invalid_missing_correlation_id_v1alpha1.json` | fail closed |
| unsupported `schema_version` | `invalid_unsupported_schema_version.json` | fail closed |
| naive `timestamp` | `invalid_naive_timestamp_v1alpha1.json` | fail closed |
| future `payload_issued_at` beyond skew | `invalid_payload_issued_at_future_skew_v1alpha1.json` | fail closed when threshold exceeded |

## 7. Forbidden content test expectations

| Forbidden content | Fixture | Expected behavior |
| --- | --- | --- |
| chain-of-thought | `invalid_forbidden_chain_of_thought_v1alpha1.json` | reject before persistence or fail closed; never store chain-of-thought |
| `access_token` | `invalid_secret_access_token_v1alpha1.json` | reject before persistence or fail closed; never store `access_token` |
| raw KYC records | `invalid_raw_kyc_record_v1alpha1.json` | reject before persistence or fail closed; never store raw KYC records |

- Forbidden content は redacted audit output に永続化してはいけません。
- Forbidden content は observability events に出力してはいけません。
- Forbidden content を `SAFE_PROCEED` へ変換してはいけません。
- Forbidden content の検知結果は deterministic failure classes のみに限定すべきです。

## 8. Replay/correlation test expectations

duplicate シナリオの期待値:

- `invalid_duplicate_request_id_scenario_a_v1alpha1.json` は replay window における first observed request として扱われ得ます。
- `invalid_duplicate_request_id_scenario_b_v1alpha1.json` は同一 `request_id` と異なる `correlation_id` を再利用します。
- replay window 内で scenario A が既観測であれば、scenario B は fail closed でなければなりません。
- 同一 `request_id` と異なる `correlation_id` は replay/correlation mismatch として扱う必要があります。
- `SAFE_PROCEED` inference は禁止です。

将来テストでカバー必須:

- duplicate `request_id`
- duplicate `request_id` with same body hash
- duplicate `request_id` with different body hash
- duplicate `request_id` with different `correlation_id`
- replay cache unavailable
- replay cache read failure
- replay cache write failure
- replay window not configured
- clock skew policy not configured

期待される挙動:

- fail closed
- `PAUSE_FOR_HUMAN_REVIEW`
- `SUSPENDED_NOT_COMMITTED`
- no `SAFE_PROCEED` inference

## 9. Transport/authentication failure test expectations

将来の failure-mode tests でカバー必須:

- missing authentication
- failed mTLS identity validation
- failed signed request verification
- missing key id
- unknown key id
- body hash mismatch
- header/body `request_id` mismatch
- header/body `correlation_id` mismatch
- required 時の missing `X-VERITAS-Body-SHA256`
- malformed transport metadata

期待される挙動:

- fail closed
- `PAUSE_FOR_HUMAN_REVIEW`
- `SUSPENDED_NOT_COMMITTED`
- no `SAFE_PROCEED` inference
- no secret material logged

## 10. Timeout and upstream availability test expectations

将来の failure-mode tests でカバー必須:

- V.I.K.I. timeout
- V.I.K.I. unreachable
- connection refused
- partial response
- malformed response body
- delayed response beyond threshold
- missing payload

期待される挙動:

- fail closed
- `PAUSE_FOR_HUMAN_REVIEW`
- `SUSPENDED_NOT_COMMITTED`
- `required_next_action: REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE`
- no `SAFE_PROCEED` inference

## 11. Redaction and observability test expectations

将来テストで検証必須:

- audit output に raw V.I.K.I. reasoning を含まない
- audit output に raw LLM text を含まない
- audit output に chain-of-thought を含まない
- audit output に hidden model state を含まない
- audit output に raw KYC records を含まない
- audit output に customer PII を含まない
- audit output に secrets / credentials を含まない
- raw Authorization header はログに残さない
- observability events は deterministic result classes のみを含む
- `request_id` と `correlation_id` は non-sensitive な場合のみ保持
- forbidden field detections は deterministic classes としてのみ記録

## 12. Expected generic fail-closed shape

期待される generic fail-closed behavior:

- `continuation_decision: PAUSE_FOR_HUMAN_REVIEW`
- `sandbox_commit_state: SUSPENDED_NOT_COMMITTED`
- `required_next_action: REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE` または failure class に応じて `REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW`
- no `SAFE_PROCEED` inference
- redacted audit output
- no final commit approval

補足:

- 本ドキュメント時点では、単一の厳密 JSON output shape はまだ要求しません。
- 正式な canonical output shape は、将来の implementation または fixture validation PR で定義すべきです。
- ただし上記の behavioral invariants は必須です。

## 13. Test plan matrix

| Test group | Example fixtures or simulated condition | Required result |
| --- | --- | --- |
| valid schema examples | four valid fixtures | schema-valid, no final commit approval |
| unknown status | `invalid_unknown_rsa_status_v1alpha1.json` | fail closed |
| missing `request_id` | `invalid_missing_request_id_v1alpha1.json` | fail closed |
| missing `correlation_id` | `invalid_missing_correlation_id_v1alpha1.json` | fail closed |
| forbidden chain-of-thought | `invalid_forbidden_chain_of_thought_v1alpha1.json` | fail closed or reject before persistence |
| forbidden `access_token` | `invalid_secret_access_token_v1alpha1.json` | fail closed or reject before persistence |
| forbidden raw KYC | `invalid_raw_kyc_record_v1alpha1.json` | fail closed or reject before persistence |
| naive timestamp | `invalid_naive_timestamp_v1alpha1.json` | fail closed |
| future `payload_issued_at` | `invalid_payload_issued_at_future_skew_v1alpha1.json` | fail closed if threshold exceeded |
| duplicate `request_id` | duplicate scenario A + B | fail closed on replay/correlation mismatch |
| unsupported `schema_version` | `invalid_unsupported_schema_version.json` | fail closed |
| transport auth failure | simulated missing or invalid auth | fail closed |
| integrity failure | simulated body hash mismatch | fail closed |
| upstream timeout | simulated timeout | fail closed |
| upstream unavailable | simulated unreachable middleware | fail closed |
| forbidden observability content | simulated raw log attempt | fail closed or reject before persistence |

## 14. Required implementation gates before tests

これらの tests 実装前チェックリスト:

- threat model merged
- payload schema draft merged
- transport/auth design merged
- replay/correlation design merged
- redaction/observability design merged
- payload schema fixture examples merged
- failure-mode test plan merged
- test-only feature flag defined
- synthetic-data-only test scope confirmed
- no network test strategy confirmed
- no secrets in fixtures confirmed
- redaction assertions defined
- fail-closed assertions defined

## 15. Non-goals

この計画は次を許可しません:

- production live V.I.K.I. integration
- production API endpoint
- live transport implementation
- authentication implementation
- replay cache implementation
- observability implementation
- logging implementation
- real KYC data processing
- live customer data processing
- live LLM text ingestion
- raw V.I.K.I. reasoning ingestion
- final commit automation based only on V.I.K.I.
- bypass of VERITAS commit gate
- secrets in repository
- production AML/KYC compliance claims
- regulatory approval claims
- legal advice claims

## 16. Compatibility preservation

- `rsa_status` は v1 payload field として維持します。
- `RSASandboxPayload` は downstream payload container として維持します。
- `evaluate_rsa_sandbox_signal()` は downstream evaluator として維持します。
- `upstream_signal_source` は `"RSA"` を維持します。
- `request_id` と `correlation_id` は controlled-live schema fields であり、`rsa_status` の置換ではありません。
- このフェーズで `viki_status` は導入しません。
- このフェーズで `VIKIPayload` は導入しません。
- 命名移行が必要な場合は v2 として別途扱います。

## 17. What this test plan validates

- runtime implementation 前に failure-mode coverage が計画されていること
- 既存 synthetic fixtures が将来 tests に対応付けされていること
- invalid payloads が fail closed 期待であること
- transport/auth failure cases が定義されていること
- replay/correlation failure cases が定義されていること
- redaction/observability failure cases が定義されていること
- upstream timeout/unavailability failure cases が定義されていること
- live implementation を導入しないこと

## 18. What this test plan does not validate

- tests を実装しません
- runtime code を実装しません
- live V.I.K.I. を実装しません
- transport を実装しません
- authentication を実装しません
- replay cache を実装しません
- observability を実装しません
- real KYC data を処理しません
- production deployment を許可しません

## 19. Recommended next PR after this plan

次の安全な PR 候補:

- controlled live fixture validation plan
- controlled live failure-mode test skeleton
- redaction fixture examples
- observability event taxonomy fixture plan
- controlled live integration implementation plan

推奨:

最も安全な次PRは、synthetic fixtures のみを使い live transport を追加しない controlled live fixture validation plan または test skeleton です。

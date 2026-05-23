# RSA ↔ VERITAS Controlled Live V.I.K.I. Observability Event Fixture Examples

## 英語正本

- [RSA ↔ VERITAS Controlled Live V.I.K.I. Observability Event Fixture Examples](../../en/guides/rsa-veritas-controlled-live-viki-observability-event-fixture-examples.md)

## 1. 目的

本書は、controlled live V.I.K.I. の synthetic な observability event fixtures を説明します。

本PRは fixture-and-documentation-only です。

- observability implementation ではありません。
- logging implementation ではありません。
- telemetry implementation ではありません。
- test implementation ではありません。
- runtime implementation ではありません。
- live integration ではありません。
- network calls は追加しません。
- secrets / credentials は追加しません。
- 実データの KYC は処理しません。
- production use を許可するものではありません。

## 2. Fixture directory

- `tests/fixtures/controlled_live_viki_observability_events/`

全ての例は synthetic です。

- 実在 customer data を含みません。
- 実在 KYC data を含みません。
- 実在 secrets を含みません。
- live V.I.K.I. data を含みません。
- このPRでは runtime code から参照されません。

## 3. Fixture inventory

| Fixture file | Category | Expected high-level behavior |
| --- | --- | --- |
| `valid_safe_proceed_decision_event_v1alpha1.json` | Positive decision | bind-boundary evaluation のみに進みます。 |
| `valid_density_throttled_decision_event_v1alpha1.json` | Positive decision | upstream intervention audit を付けて継続します。 |
| `valid_algorithmic_humility_decision_event_v1alpha1.json` | Positive decision | human review へ一時停止します。 |
| `valid_deferral_decision_event_v1alpha1.json` | Positive decision | human review へ一時停止します。 |
| `fail_closed_unknown_rsa_status_event_v1alpha1.json` | Fail-closed schema failure | 未知の `rsa_status` で fail-closed します。 |
| `fail_closed_missing_request_id_event_v1alpha1.json` | Fail-closed schema failure | 必須項目不足シナリオで fail-closed します。 |
| `fail_closed_forbidden_chain_of_thought_event_v1alpha1.json` | Fail-closed redaction failure | forbidden field class で fail-closed します。 |
| `fail_closed_secret_access_token_event_v1alpha1.json` | Fail-closed redaction failure | secret-like value detection class で fail-closed します。 |
| `fail_closed_raw_kyc_record_event_v1alpha1.json` | Fail-closed redaction failure | regulated data detection class で fail-closed します。 |
| `fail_closed_duplicate_request_id_event_v1alpha1.json` | Fail-closed replay failure | duplicate request replay class で fail-closed します。 |
| `upstream_timeout_fail_closed_event_v1alpha1.json` | Fail-closed availability failure | upstream timeout で fail-closed します。 |
| `transport_auth_failed_event_v1alpha1.json` | Fail-closed transport/auth failure | authentication failure で fail-closed します。 |
| `message_integrity_failed_event_v1alpha1.json` | Fail-closed integrity failure | integrity failure で fail-closed します。 |
| `replay_cache_unavailable_event_v1alpha1.json` | Fail-closed replay availability failure | replay cache unavailable で fail-closed します。 |

## 4. Positive decision event fixtures

- `SAFE_PROCEED` は `CONTINUE_TO_BIND_BOUNDARY` までのみ継続します。
- `DENSITY_THROTTLED` は `CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED` で継続します。
- `ALGORITHMIC_HUMILITY_ENGAGED` は `PAUSE_FOR_HUMAN_REVIEW` へ遷移します。
- `DEFERRAL_ENGAGED` は `PAUSE_FOR_HUMAN_REVIEW` へ遷移します。
- いずれも final commit approval は付与しません。
- 全て `veritas_sandbox_commit_state = SUSPENDED_NOT_COMMITTED` を維持します。

## 5. Fail-closed event fixtures

対象:

- unknown `rsa_status`
- missing `request_id`
- forbidden chain-of-thought
- secret-like access token
- raw KYC record
- duplicate `request_id`
- upstream timeout
- transport authentication failed
- message integrity failed
- replay cache unavailable

全て fail closed です。

- 全て `PAUSE_FOR_HUMAN_REVIEW` にマップされます。
- 全て `SUSPENDED_NOT_COMMITTED` にマップされます。
- 全て `final_commit_approved = false` を維持します。

## 6. Forbidden content policy

これらの observability event fixtures には raw payload bodies、raw reasoning、chain-of-thought、hidden model state、raw KYC records、customer PII、secrets、credentials、authorization material を含めてはいけません。

## 7. これらの fixtures が検証すること

- observability event examples が concrete かつ synthetic であること
- `event_type` の例が網羅されていること
- result class の例が網羅されていること
- `SAFE_PROCEED` が final approval を付与しないこと
- fail-closed event examples が `PAUSE_FOR_HUMAN_REVIEW` と `SUSPENDED_NOT_COMMITTED` を維持すること
- redacted audit output 相当の metadata が raw sensitive data なしで保持できること

## 8. これらの fixtures が検証しないこと

- observability implementation は行いません
- logging implementation は行いません
- telemetry implementation は行いません
- runtime code implementation は行いません
- live V.I.K.I. implementation は行いません
- tests は追加しません
- production deployment を許可しません

## 9. 推奨される次PR

最も安全な次PRは、これらの static synthetic fixtures のみを使う controlled live observability event fixture validation test skeleton です。runtime/logging/telemetry implementation は含めません。

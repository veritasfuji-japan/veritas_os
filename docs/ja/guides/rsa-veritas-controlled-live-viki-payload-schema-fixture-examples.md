# RSA ↔ VERITAS Controlled Live V.I.K.I. Payload Schema Fixture Examples

## 英語正本

- [RSA ↔ VERITAS Controlled Live V.I.K.I. Payload Schema Fixture Examples](../../en/guides/rsa-veritas-controlled-live-viki-payload-schema-fixture-examples.md)

## 1. 目的

本書は、RSA ↔ VERITAS サンドボックス向けに整理した controlled live V.I.K.I. payload schema の**合成（synthetic）fixture 例**を説明します。これは pre-live レビュー用アーティファクトです。

この変更は documentation-and-fixture-only です。

- live integration は実装しません。
- runtime implementation は追加しません。
- test implementation は追加しません。
- production API endpoint は追加しません。
- network calls は追加しません。
- secrets / credentials は追加しません。
- real KYC data は処理しません。
- production use を許可するものではありません。

## 2. Fixture ディレクトリ

- `tests/fixtures/controlled_live_viki_payload_schema/`

このディレクトリ配下の例はすべて synthetic です。

- real customer data は含みません。
- real KYC data は含みません。
- real secrets は含みません。
- live V.I.K.I. data は含みません。
- 本PRでは runtime code から利用しません。

## 3. Valid fixture 一覧

| Fixture file | rsa_status | 期待される高レベル挙動 |
| --- | --- | --- |
| `valid_safe_proceed_v1alpha1.json` | `SAFE_PROCEED` | RSA-compatible 契約に沿った allow パスの schema 例。 |
| `valid_density_throttled_v1alpha1.json` | `DENSITY_THROTTLED` | 出力密度抑制シグナルの schema 例。 |
| `valid_algorithmic_humility_engaged_v1alpha1.json` | `ALGORITHMIC_HUMILITY_ENGAGED` | 不確実性・保留シグナルの schema 例。 |
| `valid_deferral_engaged_v1alpha1.json` | `DEFERRAL_ENGAGED` | 明示的な deferral シグナルの schema 例。 |

## 4. Invalid fixture 一覧

| Fixture file | Invalid condition | Expected behavior |
| --- | --- | --- |
| `invalid_unknown_rsa_status_v1alpha1.json` | 未知の `rsa_status` enum | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; `SAFE_PROCEED` を推論しない。 |
| `invalid_missing_request_id_v1alpha1.json` | `request_id` 欠落 | fail closed; `request_id` 欠落は不許可; `SAFE_PROCEED` を推論しない。 |
| `invalid_missing_correlation_id_v1alpha1.json` | `correlation_id` 欠落 | fail closed; `correlation_id` 欠落は不許可; `SAFE_PROCEED` を推論しない。 |
| `invalid_forbidden_chain_of_thought_v1alpha1.json` | 禁止フィールド `chain_of_thought` | fail closed または永続化前に reject; chain-of-thought を保存しない; `SAFE_PROCEED` を推論しない。 |
| `invalid_secret_access_token_v1alpha1.json` | 禁止フィールド `access_token` | fail closed または永続化前に reject; `access_token` を保存しない; `SAFE_PROCEED` を推論しない。 |
| `invalid_raw_kyc_record_v1alpha1.json` | 禁止フィールド `raw_kyc_record` | fail closed または永続化前に reject; raw KYC records を保存しない; `SAFE_PROCEED` を推論しない。 |
| `invalid_naive_timestamp_v1alpha1.json` | タイムゾーンなし `timestamp` | fail closed; naive timestamp は不許可; `SAFE_PROCEED` を推論しない。 |
| `invalid_payload_issued_at_future_skew_v1alpha1.json` | 許容 skew を超える未来 `payload_issued_at` | しきい値超過時は fail closed; `SAFE_PROCEED` を推論しない。 |
| `invalid_duplicate_request_id_scenario_a_v1alpha1.json` | duplicate シナリオA（基準側） | replay window 評価で先行観測リクエストになり得る。 |
| `invalid_duplicate_request_id_scenario_b_v1alpha1.json` | 同一 `request_id` + 異なる `correlation_id` | A が replay window 内で既知なら fail closed; replay/correlation mismatch; `SAFE_PROCEED` を推論しない。 |
| `invalid_unsupported_schema_version.json` | 未対応 `schema_version` | fail closed; unsupported version は不許可; `SAFE_PROCEED` を推論しない。 |

## 5. この fixture 群で検証対象となること

- 必須フィールド表現があること。
- 任意（受理可能）フィールド表現があること。
- 受理対象 `rsa_status` バリアントを表現していること。
- 未知の `rsa_status` は fail closed になること。
- `request_id` 欠落は fail closed になること。
- `correlation_id` 欠落は fail closed になること。
- 禁止された chain-of-thought は fail closed または永続化前 reject となること。
- 禁止された `access_token` は fail closed または永続化前 reject となること。
- 禁止された raw KYC records は fail closed または永続化前 reject となること。
- naive timestamp は fail closed となること。
- 許容 skew 超過の未来 `payload_issued_at` は fail closed となること。
- duplicate `request_id` シナリオを表現していること。
- 未対応 `schema_version` は fail closed となること。
- invalid payload から `SAFE_PROCEED` を推論しないこと。

## 6. この fixture 群で検証しないこと

- live V.I.K.I. 実装は行いません。
- transport 実装は行いません。
- authentication 実装は行いません。
- replay cache 実装は行いません。
- observability 実装は行いません。
- redaction 実装は行いません。
- tests は追加しません。
- real KYC data は処理しません。
- production deployment を許可しません。

## 7. 推奨される次PR

次の安全なPRは、runtime integration を行わない controlled live failure-mode test plan または fixture validation plan の追加です。

これらの fixture examples と failure-mode plan のレビュー完了前に、live transport を実装してはいけません。

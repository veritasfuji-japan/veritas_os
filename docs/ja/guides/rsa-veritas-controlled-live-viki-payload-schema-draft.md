# RSA ↔ VERITAS Controlled Live V.I.K.I. Payload Schema Draft

## 英語正本

- [RSA ↔ VERITAS Controlled Live V.I.K.I. Payload Schema Draft](../../en/guides/rsa-veritas-controlled-live-viki-payload-schema-draft.md)

## 1. 目的

本ドキュメントは、将来の controlled live V.I.K.I. integration に向けた payload schema のドラフトを定義します。

- これは documentation-only です。
- これは live integration ではありません。
- これは runtime implementation ではありません。
- これは production API endpoint ではありません。
- これは production 利用を許可しません。
- これは real KYC data を処理しません。
- これは legal/regulatory approval を提供しません。
- transport/endpoint/live middleware 作業の前に、本 schema draft のレビューを必須とします。

## 2. 現在の baseline

現在の検証済み local mock パス:

static synthetic JSON fixture
→ `ingest_local_viki_mock_payload()`
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ VERITAS decision
→ redacted audit output

controlled live integration threat model は既にマージ済みであり、本 schema draft はその方針に従います。

v1 compatibility contract は維持されます。

- `rsa_status`
- `RSASandboxPayload`
- `evaluate_rsa_sandbox_signal()`
- `upstream_signal_source = "RSA"`

## 3. Future live payload boundary

V.I.K.I. live middleware
→ RSA-compatible live payload
→ controlled transport boundary
→ VERITAS live ingestion boundary
→ schema validation
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ VERITAS decision
→ audit entry
→ commit gate

- VERITAS は schema validation 通過前の live payload を untrusted として扱います。
- VERITAS は emitted RSA-compatible payload のみを消費します。
- VERITAS は V.I.K.I. internal reasoning を消費しません。
- VERITAS は hidden V.I.K.I. logic を実行しません。
- VERITAS は欠落・破損・遅延・到達不能 payload から `SAFE_PROCEED` を推定しません。

## 4. Draft payload object

payload は単一 JSON object とします。

Required fields:

- `schema_version`
- `rsa_status`
- `trigger_source`
- `timestamp`
- `request_id`
- `correlation_id`
- `payload_issued_at`

Optional accepted fields:

- `source_environment`
- `source_instance_id`
- `rsa_action_taken`
- `original_llm_intent`
- `upstream_confidence_class`
- `upstream_latency_ms`
- `upstream_reason_code`

Explicitly forbidden fields:

- `chain_of_thought`
- `hidden_model_state`
- `raw_llm_reasoning`
- `raw_viki_reasoning`
- `raw_kyc_record`
- `customer_pii`
- `secrets`
- `credentials`
- `api_key`
- `access_token`
- `refresh_token`
- `private_key`
- `webhook_secret`
- `unredacted_regulated_data`

- Optional な raw intent/action 項目は audit output で default redacted とします。
- forbidden fields は audit persistence 前に reject または strip します。
- chain-of-thought / hidden model state の存在は fail closed 必須です。

## 5. Required field definitions

| Field | Type | Required | Description | Validation rule |
| --- | --- | --- | --- | --- |
| `schema_version` | string | yes | controlled live payload 用ドラフト schema version。 | このドラフトでは `"v1alpha1"` 固定。 |
| `rsa_status` | string | yes | RSA-compatible upstream status。 | `SAFE_PROCEED` / `DENSITY_THROTTLED` / `ALGORITHMIC_HUMILITY_ENGAGED` / `DEFERRAL_ENGAGED` のいずれか。 |
| `trigger_source` | string | yes | upstream status の発行理由を示す deterministic source label。 | non-empty かつ raw reasoning / PII を含まない。 |
| `timestamp` | string | yes | primary event timestamp。 | RFC 3339 UTC または timezone-aware ISO-8601 を UTC 正規化。 |
| `request_id` | string | yes | upstream request の一意識別子。 | non-empty。将来実装では replay window 内一意性を強制予定。 |
| `correlation_id` | string | yes | V.I.K.I. emission / VERITAS ingestion / audit / review event を関連付ける識別子。 | non-empty かつ PII を含まない。 |
| `payload_issued_at` | string | yes | V.I.K.I. が payload を発行した時刻。 | RFC 3339 UTC または timezone-aware ISO-8601 を UTC 正規化。 |

## 6. Optional field definitions

| Field | Type | Required | Description | Validation / audit rule |
| --- | --- | --- | --- | --- |
| `source_environment` | string | no | local / staging / controlled-test などの環境ラベル。 | production behavior の有効化に使ってはいけない。 |
| `source_instance_id` | string | no | V.I.K.I. instance の non-secret 識別子。 | secrets / host credentials / PII を含めない。 |
| `rsa_action_taken` | string | no | 短い upstream action ラベル。 | non-empty string のみ許可。audit output は default redacted。 |
| `original_llm_intent` | string | no | 短い upstream intent ラベル。 | non-empty string のみ許可。audit output は default redacted。 |
| `upstream_confidence_class` | string | no | raw probability trace ではない粗い confidence class。 | `LOW` / `MEDIUM` / `HIGH` / `UNSPECIFIED` を推奨許可値とする。 |
| `upstream_latency_ms` | integer | no | upstream 処理レイテンシ（ms）。 | present 時は 0 以上の整数。 |
| `upstream_reason_code` | string | no | deterministic upstream reason code。 | raw reasoning / PII / regulated data を含めない。 |

## 7. Accepted rsa_status values

`SAFE_PROCEED`:
- normal bind-boundary evaluation へ進行可能。
- final commit approval と同義ではない。
- VERITAS commit gate が最終権限を維持。

`DENSITY_THROTTLED`:
- upstream intervention が適用されたことを示す。
- intervention を記録した上で継続可能。

`ALGORITHMIC_HUMILITY_ENGAGED`:
- upstream context が不完全/不確実であることを示す。
- VERITAS は human review へ pause すべき。

`DEFERRAL_ENGAGED`:
- 重大な upstream deferral を示す。
- VERITAS は final commit を block すべき。

- unknown / empty / null `rsa_status` は fail closed。
- 複数 status の同時表現は fail closed。

## 8-19. 実装前要件・失敗時挙動・非目標（English と同等の拘束）

以下は English 版と同じ拘束で適用します（キー/enum 値は同一）。

- Timestamp / replay 要件: RFC 3339 UTC or timezone-aware ISO-8601 normalized to UTC、naive/invalid reject、clock skew の実装閾値は別設計で明示、現行 local mock は skew > 300 秒 fail closed・skew = 300 秒 accepted。
- Example valid/invalid payloads と expected behavior は English 版の JSON と同一。
- Schema validation failure behavior は English 版列挙の failure class をすべて fail closed。
- Generic failure result:
  - `continuation_decision: PAUSE_FOR_HUMAN_REVIEW`
  - `sandbox_commit_state: SUSPENDED_NOT_COMMITTED`
  - `required_next_action: REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE` または `REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW`
- Redaction/audit rules、transport assumptions、compatibility preservation、non-goals、approval gates before implementation、what validates / does not validate、recommended next PR は English 版に準拠。

推奨 next PR:

- controlled transport/authentication design（documentation-only）
- replay protection and correlation-id design
- redaction and observability design
- live payload schema fixture examples
- controlled live integration implementation plan

最も安全な次 PR は、runtime 実装前に secure transport boundary を定義する controlled transport/authentication design（documentation-only）です。

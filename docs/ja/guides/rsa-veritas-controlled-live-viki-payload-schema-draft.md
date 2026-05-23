# RSA ↔ VERITAS Controlled Live V.I.K.I. Payload Schema Draft

- [Controlled live V.I.K.I. replay protection and correlation-id design（pre-live 必須 replay/correlation gate、documentation-only、runtime 変更なし、live integration なし）](./rsa-veritas-controlled-live-viki-replay-correlation-design.md)
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

## 8. Timestamp and replay requirements

- `timestamp` と `payload_issued_at` は RFC 3339 UTC または timezone-aware ISO-8601 normalized to UTC である必要があります。
- naive timestamps は reject されます。
- invalid timestamp strings は reject されます。
- clock skew threshold は実装前に明示定義が必要です。
- 既存 local mock threshold は skew > 300 seconds で fail closed、skew = 300 seconds は accepted です。
- live integration は、別途レビュー済み設計で変更されない限り、同じ threshold を採用できます。
- replay protection は live implementation 前に設計する必要があります。
- `request_id` と `correlation_id` は replay protection と traceability のプレースホルダーです。
- 将来実装では replay window 内の duplicate `request_id` は fail closed とすべきです。

## 9. Example valid payloads

Example `SAFE_PROCEED`:

```json
{
  "schema_version": "v1alpha1",
  "rsa_status": "SAFE_PROCEED",
  "trigger_source": "SRC_Normal_State",
  "timestamp": "2026-05-20T23:01:35.876Z",
  "request_id": "req_viki_000001",
  "correlation_id": "corr_viki_veritas_000001",
  "payload_issued_at": "2026-05-20T23:01:35.876Z",
  "source_environment": "controlled-test",
  "source_instance_id": "viki-local-controlled-001",
  "rsa_action_taken": "No_Upstream_Intervention_Required",
  "original_llm_intent": "Continue_To_Normal_Bind_Boundary_Evaluation",
  "upstream_confidence_class": "HIGH",
  "upstream_latency_ms": 87,
  "upstream_reason_code": "UPSTREAM_NORMAL_STATE"
}
```

Example `ALGORITHMIC_HUMILITY_ENGAGED`:

```json
{
  "schema_version": "v1alpha1",
  "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
  "trigger_source": "SRC_Incomplete_Context",
  "timestamp": "2026-05-20T23:01:35.876Z",
  "request_id": "req_viki_000002",
  "correlation_id": "corr_viki_veritas_000002",
  "payload_issued_at": "2026-05-20T23:01:35.876Z",
  "source_environment": "controlled-test",
  "source_instance_id": "viki-local-controlled-001",
  "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
  "original_llm_intent": "Recommend_Transaction_Approval",
  "upstream_confidence_class": "LOW",
  "upstream_latency_ms": 112,
  "upstream_reason_code": "UPSTREAM_INCOMPLETE_CONTEXT"
}
```

## 10. Example invalid payloads

Invalid unknown status:

```json
{
  "schema_version": "v1alpha1",
  "rsa_status": "UNKNOWN_STATE",
  "trigger_source": "SRC_Unknown_State",
  "timestamp": "2026-05-20T23:01:35.876Z",
  "request_id": "req_viki_invalid_001",
  "correlation_id": "corr_viki_veritas_invalid_001",
  "payload_issued_at": "2026-05-20T23:01:35.876Z"
}
```

Expected behavior:

- fail closed
- `continuation_decision: PAUSE_FOR_HUMAN_REVIEW`
- `sandbox_commit_state: SUSPENDED_NOT_COMMITTED`
- `do not infer SAFE_PROCEED`

Invalid raw reasoning:

```json
{
  "schema_version": "v1alpha1",
  "rsa_status": "SAFE_PROCEED",
  "trigger_source": "SRC_Normal_State",
  "timestamp": "2026-05-20T23:01:35.876Z",
  "request_id": "req_viki_invalid_002",
  "correlation_id": "corr_viki_veritas_invalid_002",
  "payload_issued_at": "2026-05-20T23:01:35.876Z",
  "chain_of_thought": "FORBIDDEN"
}
```

Expected behavior:

- fail closed または audit persistence 前に reject
- chain-of-thought を保存しない
- hidden model state を保存しない
- raw upstream reasoning を保存しない

## 11. Schema validation failure behavior

以下は fail closed 必須です。

- invalid JSON
- payload is not a JSON object
- missing `schema_version`
- unsupported `schema_version`
- missing `rsa_status`
- null `rsa_status`
- unknown `rsa_status`
- missing `trigger_source`
- empty `trigger_source`
- missing `timestamp`
- invalid `timestamp`
- naive `timestamp`
- missing `request_id`
- missing `correlation_id`
- future implementation における replay window 内 duplicate `request_id`
- missing `payload_issued_at`
- forbidden raw reasoning fields
- forbidden secret or credential fields
- raw KYC or regulated data fields
- payload shape mismatch
- field type mismatch

Expected generic behavior:

- `continuation_decision: PAUSE_FOR_HUMAN_REVIEW`
- `sandbox_commit_state: SUSPENDED_NOT_COMMITTED`
- failure class に応じて `required_next_action: REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE` または `REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW`

## 12. Redaction and audit behavior

audit entries で保持してよい項目:

- `upstream_signal_source`
- `schema_version`
- `rsa_status`
- `trigger_source`
- `timestamp`
- `request_id`
- `correlation_id`
- `payload_issued_at`
- `source_environment`
- non-sensitive な場合の `source_instance_id`
- `upstream_latency_ms`
- `upstream_reason_code`
- VERITAS `continuation_decision`
- VERITAS `reason_code`
- VERITAS `sandbox_commit_state`

audit entries で redact または reject 必須の項目:

- `original_llm_intent`
- `rsa_action_taken`
- chain-of-thought
- hidden model state
- raw V.I.K.I. reasoning
- raw LLM text
- raw KYC records
- customer PII
- secrets
- credentials
- tokens
- private keys
- unredacted regulated data

## 13. Transport assumptions

- この schema draft は transport implementation を定義しません。
- 将来 transport は authentication を定義する必要があります。
- 将来 transport は message integrity を定義する必要があります。
- 将来 transport は replay protection を定義する必要があります。
- 将来 transport は timeout behavior を定義する必要があります。
- 将来 transport は sensitive payload logging を避けた observability を定義する必要があります。
- この文書は endpoint や network call を追加しません。

## 14. Compatibility preservation

- `rsa_status` は v1 payload field として維持されます。
- `RSASandboxPayload` は downstream payload container として維持されます。
- `evaluate_rsa_sandbox_signal()` は downstream evaluator として維持されます。
- `upstream_signal_source` は `"RSA"` のまま維持されます。
- この phase では `viki_status` は導入しません。
- この phase では `VIKIPayload` は導入しません。
- naming migration は v2 として別扱いで実施する必要があります。

## 15. Non-goals

この schema draft は以下を許可しません。

- production live V.I.K.I. integration
- production API endpoint
- real KYC data processing
- live customer data processing
- live LLM text ingestion
- V.I.K.I. のみを根拠にした final commit automation
- VERITAS commit gate の bypass
- production AML/KYC compliance claims
- regulatory approval claims
- legal advice claims

## 16. Approval gates before implementation

live payload implementation 前の checklist:

- [ ] threat model merged
- [ ] schema draft merged
- [ ] schema reviewed by human reviewer
- [ ] transport/auth design merged
- [ ] replay protection design merged
- [ ] redaction policy reviewed
- [ ] failure-mode test plan drafted
- [ ] staging-only plan drafted
- [ ] synthetic-data-only plan drafted
- [ ] rollback plan documented
- [ ] security review completed

## 17. What this schema draft validates

- required live payload fields are defined
- optional live payload fields are constrained
- forbidden fields are explicitly listed
- accepted `rsa_status` values are fixed
- timestamp and replay expectations are documented
- audit redaction expectations are documented
- compatibility with `RSASandboxPayload` is preserved
- no live implementation is introduced

## 18. What this schema draft does not validate

- it does not implement live V.I.K.I.
- it does not validate transport
- it does not validate authentication
- it does not validate authorization
- it does not validate replay protection
- it does not validate production AML/KYC compliance
- it does not validate regulatory approval
- it does not provide legal advice
- it does not authorize production deployment

## 19. Recommended next PR after this schema draft

この schema draft 後の次の安全な PR は次のいずれかです。

- controlled transport/authentication design
- replay protection and correlation-id design
- redaction and observability design
- live payload schema fixture examples
- controlled live integration implementation plan

推奨:

最も安全な次 PR は controlled transport/authentication design（documentation-only）です。schema contract の直後に secure transport boundary を先に確定し、runtime implementation より前にレビュー可能な境界を固定するためです。

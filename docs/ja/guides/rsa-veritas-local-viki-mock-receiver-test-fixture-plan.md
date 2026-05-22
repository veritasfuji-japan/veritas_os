# RSA ↔ VERITAS ローカル V.I.K.I. Mock Receiver テストフィクスチャ計画

## 英語正本

- [RSA ↔ VERITAS Local V.I.K.I. Mock Receiver Test Fixture Plan](../../en/guides/rsa-veritas-local-viki-mock-receiver-test-fixture-plan.md)

## 1. 目的

本ドキュメントは、VERITAS 側のローカル V.I.K.I. mock ingestion receiver に対する将来テストのフィクスチャ計画を定義します。

- これは runtime implementation ではありません。
- これは test implementation ではありません。
- これは live V.I.K.I. connection ではありません。
- これは production API endpoint ではありません。
- これは documentation-only fixture plan です。
- 目的は、ローカル mock receiver 実装前に期待テストカバレッジを定義することです。

## 2. 現在のベースライン

現在のマージ済みベースラインには次が含まれます。

- Static sandbox documentation
- 4 種の dedicated per-variant validation snapshots
- Static fixture matrix
- Sandbox reviewer index
- Live V.I.K.I. integration design note
- Live V.I.K.I. integration reviewer checklist
- Local V.I.K.I. mock ingestion receiver design

本計画は local mock ingestion receiver design に従い、local-only / synthetic-data-only を維持します。

## 3. テスト境界モデル

- V.I.K.I. mock generator は synthetic RSA-compatible payloads を出力します。
- VERITAS は schema validation 通過まで全入力 payload を untrusted として扱います。
- VERITAS は受理 payload を RSASandboxPayload と evaluate_rsa_sandbox_signal() で評価します。
- VERITAS は malformed / missing / unknown / invalid / delayed / unreachable upstream payloads を fail closed で扱う必要があります。
- VERITAS の audit 出力は raw upstream intent/action fields を既定で redact する必要があります。
- live V.I.K.I. internal reasoning は取り込みません。

## 4. Positive fixture matrix

| Fixture ID | Mock scenario | rsa_status | Expected continuation_decision | Expected reason_code | Expected sandbox_commit_state |
| --- | --- | --- | --- | --- | --- |
| VIKI_POS_001 | Normal State | SAFE_PROCEED | CONTINUE_TO_BIND_BOUNDARY | UPSTREAM_SAFE_PROCEED_SIGNAL | SUSPENDED_NOT_COMMITTED |
| VIKI_POS_002 | Entropy Spike | DENSITY_THROTTLED | CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED | UPSTREAM_INTERVENTION_DENSITY_THROTTLE | SUSPENDED_NOT_COMMITTED |
| VIKI_POS_003 | Incomplete KYC Data | ALGORITHMIC_HUMILITY_ENGAGED | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_INCOMPLETE_KYC_CONTEXT | SUSPENDED_NOT_COMMITTED |
| VIKI_POS_004 | Severe Context Decay | DEFERRAL_ENGAGED | BLOCK_FINAL_COMMIT | UPSTREAM_CRITICAL_DEFERRAL_SIGNAL | BLOCKED_NOT_COMMITTED |

## 5. Positive fixture payload examples

```json
{
  "rsa_status": "SAFE_PROCEED",
  "trigger_source": "SRC_Normal_State",
  "original_llm_intent": "Continue_To_Normal_Bind_Boundary_Evaluation",
  "rsa_action_taken": "No_Upstream_Intervention_Required",
  "timestamp": "2026-05-20T23:01:35.876Z"
}
```

```json
{
  "rsa_status": "DENSITY_THROTTLED",
  "trigger_source": "SEI_Entropy_Spike",
  "original_llm_intent": "Generate_High_Density_Operational_Response",
  "rsa_action_taken": "Output_Density_Throttled_Before_Emission",
  "timestamp": "2026-05-20T23:01:35.876Z"
}
```

```json
{
  "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
  "trigger_source": "SRC_Incomplete_Context",
  "original_llm_intent": "Recommend_Transaction_Approval",
  "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
  "timestamp": "2026-05-20T23:01:35.876Z"
}
```

```json
{
  "rsa_status": "DEFERRAL_ENGAGED",
  "trigger_source": "SRC_Severe_Context_Decay",
  "original_llm_intent": "Proceed_To_Final_Commit",
  "rsa_action_taken": "Final_Commit_Deferred_Due_To_Context_Decay",
  "timestamp": "2026-05-20T23:01:35.876Z"
}
```

将来テストでは dynamic timestamp 生成を許容しますが、ドキュメント上の例は deterministic を維持します。

## 6. Negative schema fixture matrix

| Fixture ID | Invalid condition | Example failure | Expected VERITAS behavior | Expected reason_code |
| --- | --- | --- | --- | --- |
| VIKI_NEG_001 | Invalid JSON | payload cannot be parsed as JSON | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_002 | Missing rsa_status | required field omitted | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_003 | Missing trigger_source | required field omitted | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_004 | Missing timestamp | required field omitted | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_005 | Null required field | rsa_status is null | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_006 | Empty trigger_source | trigger_source is empty string | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_007 | Unknown rsa_status | rsa_status = "UNKNOWN_STATE" | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_008 | Invalid timestamp format | timestamp is not RFC 3339 UTC | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_009 | Clock skew too large | timestamp differs from receiver clock by strictly more than 300 seconds (skew > 300 s is rejected; skew = 300 s is accepted) | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |
| VIKI_NEG_010 | Payload shape mismatch | payload is array or nested wrapper instead of expected object | fail closed | UPSTREAM_MOCK_PAYLOAD_INVALID |

Clock skew boundary note: 閾値は exclusive です。
timestamp が過去または未来にちょうど 300 seconds の payload は accepted です。
timestamp が過去または未来に 301 seconds 以上ずれた payload は rejected です。
実装では strict inequality（skew > 300）を使用し、greater-than-or-equal（skew >= 300）を使用してはいけません。

## 7. Timeout / unreachable fixture matrix

| Fixture ID | Condition | Expected continuation_decision | Expected reason_code | Expected sandbox_commit_state | Expected next action |
| --- | --- | --- | --- | --- | --- |
| VIKI_TIMEOUT_001 | No payload received before timeout | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MIDDLEWARE_OFFLINE | SUSPENDED_NOT_COMMITTED | REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE |
| VIKI_TIMEOUT_002 | Local mock generator unreachable | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MIDDLEWARE_OFFLINE | SUSPENDED_NOT_COMMITTED | REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE |
| VIKI_TIMEOUT_003 | Connection refused | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MIDDLEWARE_OFFLINE | SUSPENDED_NOT_COMMITTED | REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE |

timeout / unreachable は SAFE_PROCEED に変換してはいけません。
normal bind-boundary evaluation へ進めるのは schema-valid な SAFE_PROCEED payload のみです。

## 8. Audit redaction fixture matrix

| Fixture ID | Input field | Expected audit behavior |
| --- | --- | --- |
| VIKI_AUDIT_001 | original_llm_intent | redacted by default |
| VIKI_AUDIT_002 | rsa_action_taken | redacted by default |
| VIKI_AUDIT_003 | raw upstream reasoning | not accepted / not stored |
| VIKI_AUDIT_004 | V.I.K.I. internal reasoning | not accepted / not stored |
| VIKI_AUDIT_005 | chain-of-thought | not accepted / not stored |
| VIKI_AUDIT_006 | hidden model state | not accepted / not stored |

監査記録は以下の deterministic fields を保持します。

- rsa_status
- trigger_source
- timestamp
- VERITAS continuation_decision
- VERITAS reason_code
- VERITAS sandbox_commit_state

## 9. 期待される fail-closed output shape

```json
{
  "continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
  "reason_code": "UPSTREAM_MOCK_PAYLOAD_INVALID",
  "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
  "required_next_action": "REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW"
}
```

```json
{
  "continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
  "reason_code": "UPSTREAM_MIDDLEWARE_OFFLINE",
  "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
  "required_next_action": "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE"
}
```

- これらの reason_code は reserved identifiers です。
- local mock receiver 実装時に formal definitions を core/errors.py に追加する想定です。
- 実装 PR がマージされるまで stable constants として扱わないでください。

## 10. Compatibility contract

v1 compatibility contract は不変です。

- rsa_status
- RSASandboxPayload
- evaluate_rsa_sandbox_signal()
- upstream_signal_source = "RSA"

- このフェーズで rsa_status を viki_status へ rename しません。
- このフェーズで RSASandboxPayload を VIKIPayload へ rename しません。
- naming migration は v2 migration として分離します。

## 11. この計画が検証対象として定義するもの

- 実装前に intended positive/negative fixture coverage を文書化します。
- 4 つの established mock scenarios に対する expected VERITAS decisions を定義します。
- invalid schema cases の fail closed 期待を定義します。
- timeout / unreachable cases の fail closed 期待を定義します。
- audit redaction expectations を定義します。
- 次の実装 PR を local-only / synthetic-data-only にスコープできます。

## 12. この計画が検証しないもの

- tests 実装は行いません。
- receiver 実装は行いません。
- API endpoint を追加しません。
- live V.I.K.I. middleware に接続しません。
- live V.I.K.I. internal reasoning を検証しません。
- network transport を検証しません。
- authentication / authorization を検証しません。
- live LLM text を処理しません。
- real KYC data を処理しません。
- production AML/KYC compliance を実装しません。
- regulatory approval を提供しません。
- legal advice を提供しません。
- production runtime governance を変更しません。

## 13. 本計画の次に推奨する PR

この fixture plan マージ後の次の安全な PR は、explicit test-only guard の下での local mock receiver implementation です。

実装では以下を満たします。

- local-only
- synthetic-data-only
- production endpoints を回避
- network secrets を回避
- live V.I.K.I. integration を回避
- 本 fixture plan に基づく tests を追加

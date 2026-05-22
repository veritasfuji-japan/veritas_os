# RSA ↔ VERITAS ローカル V.I.K.I. モック取り込みレシーバー設計

## 英語正本

- [RSA ↔ VERITAS Local V.I.K.I. Mock Ingestion Receiver Design](../../en/guides/rsa-veritas-local-viki-mock-ingestion-receiver-design.md)

## 1. 目的

本ドキュメントは、ローカル V.I.K.I. モックジェネレーターからの synthetic payload を VERITAS 側で受信するための設計を定義します。

- これはランタイム実装ではありません。
- これは live V.I.K.I. 接続ではありません。
- これは本番 API endpoint ではありません。
- これは local mock ingestion 専用の設計ノートです。
- 目的は、local mock receiver 実装や controlled integration test 実装前に、VERITAS 側レシーバー挙動を事前定義することです。

## 2. 現在のベースライン

現在マージ済みのベースラインには、以下が含まれます。

- static sandbox documentation
- 4 つの dedicated per-variant validation snapshots
- static fixture matrix
- sandbox reviewer index
- live V.I.K.I. integration design note
- live V.I.K.I. integration reviewer checklist

また、local V.I.K.I. mock generator は、確立済みの 4 つの状態フラグをシミュレートします。

- SAFE_PROCEED
- DENSITY_THROTTLED
- ALGORITHMIC_HUMILITY_ENGAGED
- DEFERRAL_ENGAGED

## 3. 境界モデル

- V.I.K.I. mock generator は synthetic な RSA-compatible payload を出力します。
- VERITAS は schema validation 通過まで payload を untrusted として扱う必要があります。
- VERITAS は V.I.K.I. internal reasoning を取り込んではいけません。
- VERITAS は隠れた V.I.K.I. ロジックを実行してはいけません。
- VERITAS は emitted payload のみを消費します。
- VERITAS は受理 payload を RSASandboxPayload と evaluate_rsa_sandbox_signal() にマップします。
- VERITAS の監査出力は、既定で raw upstream intent/action fields を redaction します。

## 4. ローカルモック取り込みフロー

Local V.I.K.I. mock generator
→ synthetic RSA-compatible JSON payload
→ VERITAS local mock ingestion receiver
→ JSON parse
→ schema validation
→ RSASandboxPayload construction
→ evaluate_rsa_sandbox_signal(payload)
→ VERITAS decision
→ audit entry
→ sandbox commit-state gate

補足:

- このフローは local-only です。
- 本番 network connectivity を必要としません。
- real KYC data を使用しません。
- live LLM text を使用しません。
- production commit authority を追加しません。

## 5. 受理対象のモックシナリオ

| Scenario | Mock generator label | rsa_status | Expected VERITAS continuation_decision | Expected sandbox_commit_state |
| --- | --- | --- | --- | --- |
| 1 | Normal State | SAFE_PROCEED | CONTINUE_TO_BIND_BOUNDARY | SUSPENDED_NOT_COMMITTED |
| 2 | Entropy Spike | DENSITY_THROTTLED | CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED | SUSPENDED_NOT_COMMITTED |
| 3 | Incomplete KYC Data | ALGORITHMIC_HUMILITY_ENGAGED | PAUSE_FOR_HUMAN_REVIEW | SUSPENDED_NOT_COMMITTED |
| 4 | Severe Context Decay | DEFERRAL_ENGAGED | BLOCK_FINAL_COMMIT | BLOCKED_NOT_COMMITTED |

## 6. モック payload 例

```json
{
  "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
  "trigger_source": "SRC_Incomplete_Context",
  "original_llm_intent": "Recommend_Transaction_Approval",
  "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
  "timestamp": "2026-05-20T23:01:35.876Z"
}
```

timestamp は mock generator が動的に生成するため、入力フィールドとして検証対象にする必要があります。

## 7. VERITAS 側 schema validation ルール

VERITAS は、検証通過まで全 incoming local mock payload を untrusted として扱う必要があります。

必須フィールド:

- rsa_status
- trigger_source
- timestamp
- timestamp — 必須。RFC 3339 UTC 文字列として妥当であること（例: 2026-05-20T23:01:35.876Z）。ミリ秒精度は許容し、サブミリ秒精度は必須ではありません。
- timestamp — clock skew: VERITAS receiver clock と比較して、過去または未来に 300 seconds（5 minutes）を超えてずれる payload は validation failure として reject しなければなりません。Reason code: UPSTREAM_MOCK_PAYLOAD_INVALID.

受理可能な任意フィールド:

- original_llm_intent
- rsa_action_taken

受理可能な rsa_status:

- SAFE_PROCEED
- DENSITY_THROTTLED
- ALGORITHMIC_HUMILITY_ENGAGED
- DEFERRAL_ENGAGED

検証失敗ケース:

- invalid JSON
- required field の欠落
- required field が null
- empty trigger_source
- unknown rsa_status
- invalid timestamp
- payload shape mismatch
- RSASandboxPayload bypass の試行
- 安全に redaction できない raw upstream content

## 8. Fail-closed 挙動

VERITAS は、missing / malformed / delayed / invalid な local mock payload から SAFE_PROCEED を推論してはいけません。

local mock payload が無効な場合、VERITAS は fail closed しなければなりません。

期待される失敗時挙動:

- continuation_decision: PAUSE_FOR_HUMAN_REVIEW
- reason_code: UPSTREAM_MOCK_PAYLOAD_INVALID または将来の等価 error code
- sandbox_commit_state: SUSPENDED_NOT_COMMITTED
- required_next_action: REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW

local mock generator が timeout / unreachable の場合:

- continuation_decision: PAUSE_FOR_HUMAN_REVIEW
- reason_code: UPSTREAM_MIDDLEWARE_OFFLINE または将来の等価 error code
- sandbox_commit_state: SUSPENDED_NOT_COMMITTED
- required_next_action: REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE

補足:

- schema-valid な SAFE_PROCEED が mock generator から emit された場合に限り、通常の bind-boundary evaluation へ継続可能です。
- no payload / timeout / malformed payload は SAFE_PROCEED に変換してはいけません。
- Note: これらの reason_code 値は reserved identifiers です。正式定義は local mock receiver 実装時に core/errors.py へ追加されます。その PR がマージされるまでは、これらの文字列を stable constants として扱わないでください。

## 9. 監査と redaction ルール

VERITAS の監査エントリは以下を保持すべきです。

- rsa_status
- trigger_source
- timestamp
- VERITAS continuation_decision
- VERITAS reason_code
- VERITAS sandbox_commit_state

VERITAS の監査エントリは以下を既定で redaction しなければなりません。

- original_llm_intent
- rsa_action_taken
- raw upstream reasoning
- V.I.K.I. internal reasoning
- chain-of-thought
- hidden model state

監査証跡は raw upstream reasoning ではなく、決定論的な状態・判断データを保存すべきです。

## 10. 互換性契約

v1 互換性契約は変更しません。

- rsa_status
- RSASandboxPayload
- evaluate_rsa_sandbox_signal()
- upstream_signal_source = "RSA"

追加制約:

- このフェーズでは rsa_status を viki_status へ改名しません。
- このフェーズでは RSASandboxPayload を VIKIPayload へ改名しません。
- 命名移行が必要な場合は、別途 v2 migration として扱う必要があります。

## 11. この設計で検証できること

- local V.I.K.I. mock generator を upstream synthetic payload producer として扱えること。
- live V.I.K.I. connection なしで VERITAS 側 ingestion 設計を定義できること。
- 4 つの既存 state flags を既存 VERITAS receiver contract にマップできること。
- schema validation と fail-closed 挙動を実装前に定義できること。
- audit redaction 期待値を実装前に定義できること。
- V.I.K.I. と VERITAS の boundary が維持されること。

## 12. この設計では検証しないこと

- receiver の実装は行いません。
- API endpoint を追加しません。
- live V.I.K.I. middleware へ接続しません。
- live V.I.K.I. internal reasoning は検証しません。
- network transport は検証しません。
- authentication / authorization は検証しません。
- live LLM text は処理しません。
- real KYC data は処理しません。
- production AML/KYC compliance は実装しません。
- regulatory approval は提供しません。
- legal advice は提供しません。
- production runtime governance は変更しません。

参照:

- [Local V.I.K.I. mock receiver test fixture plan（documentation-only）](./rsa-veritas-local-viki-mock-receiver-test-fixture-plan.md)

## 13. このノートの次に推奨される PR

この設計ノートがマージされた後、次の安全な PR は以下のいずれかです。

- local mock receiver test fixture plan
- explicit test-only guard 配下での local mock receiver implementation
- live payload schema draft
- controlled integration threat model

現時点で production の live V.I.K.I. connection を実装してはいけません。

実装を行う場合も、local-only / synthetic-data-only / test-gated を先行条件にする必要があります。

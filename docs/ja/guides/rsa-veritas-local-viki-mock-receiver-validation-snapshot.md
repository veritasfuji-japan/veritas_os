# RSA ↔ VERITAS Local V.I.K.I. Mock Receiver Validation Snapshot

## 1. Purpose

関連アーティファクト:

- [Local V.I.K.I. mock receiver E2E harness validation snapshot](./rsa-veritas-local-viki-mock-receiver-e2e-harness-validation-snapshot.md)

このスナップショットは、VERITAS 側ローカル V.I.K.I. モックレシーバーの**現在実装済み**の検証状態を記録するものです。

- これは documentation-only の更新です。
- これは新規実装ではありません。
- これは live V.I.K.I. 連携ではありません。
- これは本番エンドポイントではありません。
- これは、最初の test-only 実装がマージされた後のローカルモックレシーバー挙動を記録するものです。

## 2. Implemented receiver surface

実装済みモジュール:

- `veritas_os/governance/local_viki_mock_receiver.py`

実装済みヘルパー:

- `ingest_local_viki_mock_payload(raw_payload, *, receiver_now=None)`
- `build_local_viki_mock_unreachable_decision(*, receiver_now=None)`

レシーバーが受け付ける入力:

- JSON 文字列ペイロード
- Mapping / dict-like ペイロード

レシーバーが**行わない**こと:

- ソケットを開く
- HTTP サーバーを起動する
- ネットワークサービスを呼び出す
- live V.I.K.I. に接続する
- live LLM テキストを取り込む
- 実データの KYC を処理する

## 3. Test-only guard validation

明示的ガード:

- `VERITAS_LOCAL_VIKI_MOCK_RECEIVER_ENABLE=1`

Truthy values:

- `"1"`
- `"true"`
- `"yes"`
- `"on"`

期待される挙動:

- ガードが未設定または false の場合、レシーバーヘルパーはペイロード内容の処理前に raise しなければなりません。
- このガードは、明示的なローカルモックテスト文脈以外での偶発利用を防止します。
- このガードは本番認可システムではありません。
- このガードによってレシーバーが本番安全になるわけではありません。

## 4. Positive fixture validation

| Fixture ID | rsa_status | Expected continuation_decision | Expected reason_code | Expected sandbox_commit_state | Validation result |
| --- | --- | --- | --- | --- | --- |
| VIKI_POS_001 | SAFE_PROCEED | CONTINUE_TO_BIND_BOUNDARY | UPSTREAM_SAFE_PROCEED_SIGNAL | SUSPENDED_NOT_COMMITTED | Implemented |
| VIKI_POS_002 | DENSITY_THROTTLED | CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED | UPSTREAM_INTERVENTION_DENSITY_THROTTLE | SUSPENDED_NOT_COMMITTED | Implemented |
| VIKI_POS_003 | ALGORITHMIC_HUMILITY_ENGAGED | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_INCOMPLETE_KYC_CONTEXT | SUSPENDED_NOT_COMMITTED | Implemented |
| VIKI_POS_004 | DEFERRAL_ENGAGED | BLOCK_FINAL_COMMIT | UPSTREAM_CRITICAL_DEFERRAL_SIGNAL | BLOCKED_NOT_COMMITTED | Implemented |

## 5. Negative schema validation

不正なローカルモックペイロードは fail closed しなければなりません。

| Fixture class | Example | Expected reason_code | Expected continuation_decision | Validation result |
| --- | --- | --- | --- | --- |
| Invalid JSON / malformed JSON | JSON として解釈不能な文字列 | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Missing rsa_status | `rsa_status` キーが欠落 | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Missing trigger_source | `trigger_source` キーが欠落 | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Missing timestamp | `timestamp` キーが欠落 | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Null required field | 必須キーに `null` を設定 | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Empty trigger_source | `trigger_source` が空文字 | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Unknown rsa_status | 未サポートの `rsa_status` 値 | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Invalid timestamp | ISO 形式でない/解釈不能な timestamp | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Payload shape mismatch | mapping でない/構造不整合 | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Optional original_llm_intent present but invalid | `original_llm_intent` の型が不正 | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |
| Optional rsa_action_taken present but invalid | `rsa_action_taken` の型が不正 | UPSTREAM_MOCK_PAYLOAD_INVALID | PAUSE_FOR_HUMAN_REVIEW | Implemented |

## 6. Clock skew validation

実装済み clock skew ルール:

- しきい値は排他的 (exclusive)
- skew > 300 seconds は fail closed
- skew = 300 seconds は受理
- strict inequality を使用すること
- greater-than-or-equal は使用しないこと

| Clock skew | Expected result |
| --- | --- |
| 299 seconds (past) | accepted |
| 300 seconds (past, boundary) | accepted |
| -299 seconds / future skew 299 seconds | accepted |
| 301 seconds (past) | fail closed |
| -301 seconds / future skew 301 seconds | fail closed |

clock skew 検証失敗時のマッピング:

- `reason_code`: `UPSTREAM_MOCK_PAYLOAD_INVALID`
- `continuation_decision`: `PAUSE_FOR_HUMAN_REVIEW`
- `sandbox_commit_state`: `SUSPENDED_NOT_COMMITTED`

## 7. Unreachable mock generator validation

`build_local_viki_mock_unreachable_decision()` は、ローカルモックジェネレーターが利用不能なケースに対し、決定論的な fail-closed 出力を返します。

期待される出力:

- `continuation_decision`: `PAUSE_FOR_HUMAN_REVIEW`
- `reason_code`: `UPSTREAM_MIDDLEWARE_OFFLINE`
- `sandbox_commit_state`: `SUSPENDED_NOT_COMMITTED`
- `required_next_action`: `REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE`

- timeout / unreachable を `SAFE_PROCEED` に変換してはなりません
- no payload を valid payload と推論してはなりません
- ローカルモックジェネレーター利用不能時、VERITAS は fail closed します

## 8. Audit redaction validation

audit 出力はデフォルトで生の upstream フィールドを redact します。

期待されるデフォルト audit 挙動:

- `original_llm_intent`: `[REDACTED]`
- `rsa_action_taken`: `[REDACTED]`

- 生の upstream reasoning は受け入れません
- V.I.K.I. 内部 reasoning は保存しません
- chain-of-thought は保存しません
- hidden model state は保存しません

audit が保持する決定論的フィールド:

- `upstream_signal_source`
- `rsa_status`
- `trigger_source`
- `timestamp`
- `veritas_continuation_decision`
- `veritas_sandbox_commit_state`

## 9. Fail-closed output shape

不正ペイロード時の fail-closed 形状:

```json
{
  "veritas_decision": {
    "continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
    "reason_code": "UPSTREAM_MOCK_PAYLOAD_INVALID",
    "authority_evidence_status": "INSUFFICIENT",
    "sandbox_bind_boundary_state": "NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE",
    "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
    "required_next_action": "REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW"
  },
  "audit_entry": {
    "upstream_signal_source": "RSA",
    "rsa_status": "INVALID_OR_UNAVAILABLE",
    "trigger_source": "LOCAL_VIKI_MOCK_RECEIVER",
    "original_llm_intent": "[REDACTED]",
    "rsa_action_taken": "[REDACTED]",
    "veritas_continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
    "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED"
  }
}
```

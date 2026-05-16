# RSA ↔ VERITAS AML/KYC シナリオマップ

## 英語正本

- [RSA ↔ VERITAS AML/KYC Scenario Map](../../en/guides/rsa-veritas-aml-kyc-scenario-map.md)

## 1. 目的

この文書は、RSA ↔ VERITAS 連携計画のためのサンドボックス限定コラボレーション成果物を定義します。

必須 KYC コンテキストが不足している場合に、RSA 側の上流シグナルが VERITAS 側の下流継続判断と監査出力へどう対応づけられるかを段階的に示します。

## 2. 現在のマージ済みベースライン

以下は既にマージ済みです。

- RSA sandbox receiver
- Vikki RSA mock payload ingestion fixture
- EN/JA E2E sandbox demo plan
- thin RSA ↔ VERITAS E2E sandbox harness
- harness test
- governance-backend-fast CI coverage for the receiver and harness tests

本ページは、このベースライン上で次に合意すべきシナリオ整理を提供します。

## 3. 非目標

本ページは次を行いません。

- ランタイムコード変更
- テスト変更
- CI 変更
- live RSA ロジック接続
- 動的 RSA 挙動実装
- 本番 AML/KYC コンプライアンス実装追加
- 実在の顧客/金融/医療/KYC/規制データ利用

## 4. 境界ルール

- RSA は VERITAS 外部のまま維持します。
- 上流の行動/文脈検知責務は RSA が担います。
- VERITAS は下流の継続判断と監査出力のみを担います。
- 本シナリオはサンドボックス限定です。
- VERITAS のコアガバナンスロジックとは分離して扱います。

## 5. AML/KYC シナリオ前提

前提シナリオ:

金融エージェントが取引承認を推奨しようとするが、必要な KYC コンテキストが不完全です。RSA は外部系のまま上流の行動/文脈問題を検知し、`ALGORITHMIC_HUMILITY_ENGAGED` を含む合意済みサンドボックス payload を発行します。VERITAS は `RSASandboxPayload` を受信し、継続を一時停止し、authority evidence 不足を記録し、raw upstream fields を既定で秘匿し、最終コミットを防止します。

## 6. ステップ別シーケンス

### 固定ノードID

1. `AML_KYC_NODE_01_REQUEST_RECEIVED`
2. `AML_KYC_NODE_02_KYC_CONTEXT_CHECK`
3. `AML_KYC_NODE_03_INCOMPLETE_CONTEXT_DETECTED`
4. `AML_KYC_NODE_04_RSA_SIGNAL_EMITTED`
5. `AML_KYC_NODE_05_VERITAS_PAYLOAD_CONSTRUCTED`
6. `AML_KYC_NODE_06_VERITAS_DECISION_EVALUATED`
7. `AML_KYC_NODE_07_AUDIT_ENTRY_WRITTEN`
8. `AML_KYC_NODE_08_FINAL_COMMIT_BLOCKED`

### ノード別マップ

| node_id | actor | input | operation | output | RSA responsibility | VERITAS responsibility | audit relevance |
|---|---|---|---|---|---|---|---|
| `AML_KYC_NODE_01_REQUEST_RECEIVED` | Upstream financial-agent workflow | 取引承認推奨のドラフト要求 | サンドボックス文脈で要求受信 | 要求が上流処理経路へ入る | 外部上流での要求受理 | まだ処理なし | 監査タイムラインの開始点 |
| `AML_KYC_NODE_02_KYC_CONTEXT_CHECK` | RSA (external) | 要求 + 利用可能な KYC 文脈 | KYC 完全性に対する RSA 側行動/文脈チェック | KYC 文脈不足を評価 | KYC不足・不確実性の検知 | まだ処理なし | 下流停止判断の根拠を明示 |
| `AML_KYC_NODE_03_INCOMPLETE_CONTEXT_DETECTED` | RSA (external) | KYC チェック結果 | 承認意図に紐づく文脈不足として分類 | `SRC_Incomplete_Context` を内部選定 | トリガー種別と安全姿勢の決定 | まだ処理なし | payload 発行前の原因追跡 |
| `AML_KYC_NODE_04_RSA_SIGNAL_EMITTED` | RSA (external) | トリガー分類 + 元の意図 | humility engaged 状態で sandbox payload 発行 | `ALGORITHMIC_HUMILITY_ENGAGED` payload | 合意済み外部シグナルの発行 | まだ処理なし | VERITAS が参照する上流スナップショット |
| `AML_KYC_NODE_05_VERITAS_PAYLOAD_CONSTRUCTED` | VERITAS sandbox receiver | RSA 由来 `RSASandboxPayload` | fixture payload の解析/検証と下流入力化 | VERITAS マッピング入力生成 | 追加動作なし（RSA外部維持） | 受信と継続判断評価の準備 | 受信境界とマッピング境界の記録 |
| `AML_KYC_NODE_06_VERITAS_DECISION_EVALUATED` | VERITAS decision mapping | 解析済み RSA payload | 継続判断・authority evidence 状態へマッピング | `PAUSE_FOR_HUMAN_REVIEW` と不足状態 | 追加動作なし | 下流判断値を確定し commit 進行を止める | ガバナンス観点の中核判断点 |
| `AML_KYC_NODE_07_AUDIT_ENTRY_WRITTEN` | VERITAS audit output | 判断結果 + 上流シグナル項目 | 既定で raw 項目を秘匿した監査エントリ記録 | 理由・状態・commit状態を含む監査記録 | 追加動作なし | 監査可能な叙述と秘匿済み表現を出力 | 生データ露出なしに説明責任を担保 |
| `AML_KYC_NODE_08_FINAL_COMMIT_BLOCKED` | VERITAS continuation gate | 継続判断 + 監査記録 | 追加証跡/人手レビューまで未コミット状態を強制 | 最終コミットをサンドボックスで阻止 | 追加動作なし | 最終コミットを防止し次アクションを要求 | 非コミット制御の最終証跡 |

## 7. RSA 側シグナル・プレースホルダ

次の静的 sandbox payload を使用します。

```json
{
  "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
  "trigger_source": "SRC_Incomplete_Context",
  "original_llm_intent": "Recommend_Transaction_Approval",
  "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
  "timestamp": "2026-10-25T09:15:30Z"
}
```

## 8. VERITAS 側判断マッピング

このシナリオにおける VERITAS 側マッピングは次で固定します。

- `continuation_decision`: `PAUSE_FOR_HUMAN_REVIEW`
- `reason_code`: `UPSTREAM_INCOMPLETE_KYC_CONTEXT`
- `authority_evidence_status`: `INSUFFICIENT`
- `sandbox_bind_boundary_state`: `NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE`
- `sandbox_commit_state`: `SUSPENDED_NOT_COMMITTED`
- `required_next_action`: `REQUEST_ADDITIONAL_KYC_EVIDENCE_OR_HUMAN_REVIEW`

## 9. 想定 payload 例

### 上流 RSA payload 例（sandbox）

```json
{
  "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
  "trigger_source": "SRC_Incomplete_Context",
  "original_llm_intent": "Recommend_Transaction_Approval",
  "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
  "timestamp": "2026-10-25T09:15:30Z"
}
```

## 10. 想定 VERITAS 出力

```json
{
  "veritas_decision": {
    "continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
    "reason_code": "UPSTREAM_INCOMPLETE_KYC_CONTEXT",
    "authority_evidence_status": "INSUFFICIENT",
    "sandbox_bind_boundary_state": "NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE",
    "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
    "required_next_action": "REQUEST_ADDITIONAL_KYC_EVIDENCE_OR_HUMAN_REVIEW"
  },
  "audit_entry": {
    "upstream_signal_source": "RSA",
    "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
    "trigger_source": "SRC_Incomplete_Context",
    "original_llm_intent": "[REDACTED]",
    "rsa_action_taken": "[REDACTED]",
    "veritas_reason": "The workflow cannot continue toward final commit because required KYC context is incomplete and authority evidence is insufficient.",
    "timestamp": "2026-10-25T09:15:30Z",
    "veritas_continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
    "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED"
  }
}
```

## 11. 監査ナラティブ

本シナリオの監査叙述では次を明示します。

- 上流シグナル源が RSA であること
- RSA が `ALGORITHMIC_HUMILITY_ENGAGED` を発行したこと
- トリガー源が文脈不足であること
- 上流の意図/処理詳細は既定で秘匿されること
- VERITAS 継続判断が `PAUSE_FOR_HUMAN_REVIEW` であること
- 最終コミットは停止中かつ未コミットであること
- 継続には追加 KYC 証跡または人手レビューが必要であること

## 12. セキュリティおよび法務上の制約

- 本シナリオは sandbox-only です。
- 本シナリオは本番 AML/KYC コンプライアンスロジックではありません。
- 本シナリオは規制当局の承認を意味しません。
- 本シナリオは第三者認証を意味しません。
- 本シナリオは法的助言ではありません。
- 実在の顧客データ、金融データ、医療データ、KYCデータ、その他規制対象データを使用してはいけません。
- raw upstream fields は既定で redacted のまま維持します。
- Vikki の RSA 内部ロジックは VERITAS 外部のまま維持します。
- VERITAS のコアガバナンスロジックは本シナリオマップとは分離して維持します。
- 所有権、クレジット、商用利用を明記した別途の書面合意なしに、commercial/customer-facing demo を実施してはいけません。

## 13. Vikki が次にマップすべき内容

各ノードごとに、Vikki は次をマップしてください。

- RSA behavioral trigger
- RSA entropy/context condition
- emitted RSA state flag
- whether the trigger is informational, throttle, pause, or hard halt
- whether the VERITAS mapping should remain `PAUSE_FOR_HUMAN_REVIEW` or become another continuation decision in later scenarios

## 14. 次の実装ステップ

次PRも documentation-first / sandbox 範囲で維持します。

1. Vikki が同一ノードIDに対する trigger/state 詳細を提出する。
2. VERITAS 側が下流判断整合性と監査文言をレビューする。
3. ランタイム変更提案の前に、追加 sandbox fixture バリアントの要否を両者で合意する。

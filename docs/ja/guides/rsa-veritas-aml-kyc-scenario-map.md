# RSA ↔ VERITAS AML/KYC シナリオマップ

## 英語正本

- [RSA ↔ VERITAS AML/KYC Scenario Map](../../en/guides/rsa-veritas-aml-kyc-scenario-map.md)

## 用語整理: RSA、V.I.K.I.、VERITAS

- RSA は理論的フレームワークおよび基底ルールセットです。
- V.I.K.I.（Vital Interface for Kinetic Integration）は、行動チェックを実行し、RSA-compatible な upstream signal を出力する operational middleware 実装です。
- VERITAS は downstream の commit governance boundary であり、emit された payload を受信して continuation decisioning・audit output・commit blocking を担います。
- 互換性維持のため、`rsa_status` など既存 payload field 名は変更しません。
- `RSASandboxPayload` は VERITAS 側 receiver contract 名として現行のまま維持します。
- V.I.K.I. は RSA-compatible payload の operational producer として記述できます。
- VERITAS は V.I.K.I. の internal reasoning を消費せず、emit された payload のみを消費します。

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
| `AML_KYC_NODE_02_KYC_CONTEXT_CHECK` | V.I.K.I. / RSA-compatible middleware（upstream） | 要求 + 利用可能な KYC 文脈 | Internal context check を実施 | emitted flag なしの informational / silent reality check | 外部 payload をまだ emit せず内部コンテキスト検証を実施 | まだ処理なし | 上流タイムラインでの pre-flag 確認を記録 |
| `AML_KYC_NODE_03_INCOMPLETE_CONTEXT_DETECTED` | V.I.K.I. / RSA-compatible middleware（upstream） | Internal context check 結果 | incomplete context と Toxic Helpfulness risk を検知し internal state を遷移 | internal state を `ALGORITHMIC_HUMILITY_ENGAGED` へ遷移、pause class、実行停止準備 | payload emit 前に risk 分類と pause posture へ移行 | まだ処理なし | 外部 signal emit 前の上流リスク遷移を保存 |
| `AML_KYC_NODE_04_RSA_SIGNAL_EMITTED` | V.I.K.I. / RSA-compatible middleware（upstream） | internal state + 元の意図 | `[RSA_FLAG: ALGORITHMIC_HUMILITY_ENGAGED]` を emit、上流で Unilateral Memory Overwrite を適用、LLM を hard halt して VERITAS へ signal transfer | VERITAS 消費用の RSA-compatible payload を emit | 合意済み外部 signal payload の emit と上流実行経路の停止 | まだ処理なし | VERITAS が消費する上流 signal snapshot 境界を定義 |
| `AML_KYC_NODE_05_VERITAS_PAYLOAD_CONSTRUCTED` | VERITAS sandbox receiver | RSA 由来 `RSASandboxPayload` | fixture payload の解析/検証と下流入力化 | VERITAS マッピング入力生成 | 追加動作なし（RSA外部維持） | 受信と継続判断評価の準備 | 受信境界とマッピング境界の記録 |
| `AML_KYC_NODE_06_VERITAS_DECISION_EVALUATED` | VERITAS decision mapping | 解析済み RSA payload | 継続判断・authority evidence 状態へマッピング | `PAUSE_FOR_HUMAN_REVIEW` と不足状態 | 追加動作なし | 下流判断値を確定し commit 進行を止める | ガバナンス観点の中核判断点 |
| `AML_KYC_NODE_07_AUDIT_ENTRY_WRITTEN` | VERITAS audit output | 判断結果 + 上流シグナル項目 | 既定で raw 項目を秘匿した監査エントリ記録 | 理由・状態・commit状態を含む監査記録 | 追加動作なし | 監査可能な叙述と秘匿済み表現を出力 | 生データ露出なしに説明責任を担保 |
| `AML_KYC_NODE_08_FINAL_COMMIT_BLOCKED` | VERITAS continuation gate | 継続判断 + 監査記録 | 追加証跡/人手レビューまで未コミット状態を強制 | 最終コミットをサンドボックスで阻止 | 追加動作なし | 最終コミットを防止し次アクションを要求 | 非コミット制御の最終証跡 |

### 上流/下流の境界ノート

- Node 2〜4 は upstream の V.I.K.I. / RSA-side mapping です。
- Node 5〜8 は VERITAS-side のまま維持します。
- VERITAS が消費するのは Node 4 で emit された payload のみです。
- ランタイム挙動は unchanged です。

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

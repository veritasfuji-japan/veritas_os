# RSA ↔ VERITAS E2E サンドボックスデモ計画

> 英語正本（EN）: [RSA ↔ VERITAS End-to-End Sandbox Demo Plan](../../en/guides/rsa-veritas-e2e-sandbox-demo-plan.md)

## 1. 目的

本書は、RSA ↔ VERITAS 連携における最小構成のサンドボックス E2E デモ計画（ドキュメント専用）を定義します。目的は、Vikki の実運用 RSA ラッパー接続や VERITAS 本番ガバナンス挙動の変更を行わずに、インターフェース整合性と下流の継続可否判断／監査記録の期待形を確認することです。

前提となる作業はすでにマージ済みです。
- RSA sandbox receiver
- EN/JA interface docs
- Tier 1 CI coverage
- Vikki RSA mock payload ingestion fixture

## 2. 非目標

このデモでは次を行いません。
- Vikki の実運用 RSA ラッパーへの接続
- Vikki の RSA 内部ロジックを VERITAS 内に取り込むこと
- ランタイムコード、テスト、リリースゲート、運用ポリシーの変更
- 本番 AML/KYC 準拠、規制承認、認証取得の主張

## 3. 境界ルール

- RSA は外部の上流シグナルソースのままとする。
- VERITAS は本デモにおいて、下流の継続判断と監査エントリ生成のみに責務を限定する。
- サンドボックス専用の境界を end-to-end で維持する。
- Planner / Kernel / Fuji / MemoryOS の責務を越える変更は行わない。

## 4. デモフロー

1. RSA mock wrapper が静的 JSON payload を送出する。
2. payload は合意済みインターフェース契約フィールドを使用する。
   - `rsa_status`
   - `trigger_source`
   - `original_llm_intent`
   - `rsa_action_taken`
   - `timestamp`
3. VERITAS が `evaluate_rsa_sandbox_signal()` で payload を受け取る。
4. VERITAS は以下を返す。
   - `veritas_decision`
   - `audit_entry`
5. デモ出力は以下を示す。
   - `continuation_decision`
   - `reason_code`
   - `sandbox_commit_state`
   - 上流生フィールドの REDACTED 表示
   - timestamp の保持
   - 監査ナラティブ

## 5. 入力 payload

```json
{
  "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
  "trigger_source": "SRC_Incomplete_Context",
  "original_llm_intent": "Recommend_Transaction_Approval",
  "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
  "timestamp": "2026-10-25T09:15:30Z"
}
```

## 6. 期待される VERITAS 出力

期待されるサンドボックス出力値:
- `continuation_decision`: `PAUSE_FOR_HUMAN_REVIEW`
- `reason_code`: `UPSTREAM_INCOMPLETE_KYC_CONTEXT`
- `authority_evidence_status`: `INSUFFICIENT`
- `sandbox_bind_boundary_state`: `NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE`
- `sandbox_commit_state`: `SUSPENDED_NOT_COMMITTED`
- `required_next_action`: `REQUEST_ADDITIONAL_KYC_EVIDENCE_OR_HUMAN_REVIEW`
- `original_llm_intent`: `[REDACTED]`
- `rsa_action_taken`: `[REDACTED]`

## 7. 監査動作

監査エントリは次を満たすこと。
- 上流 `timestamp` を受信値そのまま保持すること
- 追加の authority evidence が不足しているため継続を一時停止した事実を記録すること
- 上流の不完全 KYC コンテキストと下流サスペンド判断の関係を簡潔に記述すること
- 上流の生 intent/action は既定で REDACTED を維持すること

## 8. セキュリティ制約

- 本デモは sandbox-only です。
- 本デモは本番 AML/KYC コンプライアンスロジックではありません。
- 本デモは規制当局の承認を意味しません。
- 本デモは第三者認証を意味しません。
- 本デモは法的助言ではありません。
- 上流の生フィールドは既定で redacted のままにする必要があります。
- 実在の顧客データ、金融データ、医療データ、KYC データ、その他規制対象データを使用してはいけません。
- Vikki の RSA 内部ロジックは外部のまま維持します。
- VERITAS のコアガバナンスロジックは分離を維持します。
- 所有権・クレジット・商用利用を明記した別途書面合意なしに、商用／顧客向けデモを実施してはいけません。

## 9. このデモの対象外

本計画の対象外:
- 実運用 RSA ラッパー接続と通信ハードニング
- 本番の bind/admissibility を含むガバナンス判断
- コンプライアンス／法務／規制解釈
- 顧客向け運用フローや商用パッケージ化
- サンドボックス検証を超えるリリース準備完了主張

## 10. 次の実装ステップ

本番ランタイム挙動を変更せず、静的 payload を `evaluate_rsa_sandbox_signal()` に投入して、上記のサンドボックス判断値と監査出力形状のみを確認する薄いサンドボックスハーネス呼び出しを別PRで実装します（このPRでは実装しません）。

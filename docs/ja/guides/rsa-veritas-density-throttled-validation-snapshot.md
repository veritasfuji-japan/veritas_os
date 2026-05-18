# RSA ↔ VERITAS DENSITY_THROTTLED 検証スナップショット

## 英語正本

- [RSA ↔ VERITAS DENSITY_THROTTLED Validation Snapshot](../../en/guides/rsa-veritas-density-throttled-validation-snapshot.md)

## 1. 目的

本ページは、V.I.K.I. ↔ VERITAS / RSA-compatible フローにおける DENSITY_THROTTLED の静的サンドボックス・バリアントを記録するものです。

これは ALGORITHMIC_HUMILITY_ENGAGED と比較して、よりソフトな上流介入ケースです。

目的は、VERITAS が上流での cognitive-density 介入を監査ログに残しつつ、デフォルトのハードストップとして扱わないことを示す点にあります。

## 2. 現在のベースライン

現在マージ済みのベースラインには、以下が含まれます。

- RSA / V.I.K.I. / VERITAS の用語同期。
- 既存の RSASandboxPayload 受信契約。
- 既存の evaluate_rsa_sandbox_signal(payload) マッピング。
- 既存の E2E サンドボックス・ハーネス。
- 既存の governance-backend-fast CI カバレッジ。
- 既存の ALGORITHMIC_HUMILITY_ENGAGED 検証スナップショット。

## 3. 用語互換性ノート

- RSA は理論フレームワークおよび基礎ルールセットとして維持されます。
- V.I.K.I. は RSA-compatible な上流 payload を生成する運用側プロデューサーです。
- VERITAS は下流のコミット・ガバナンス境界です。
- 互換性のため rsa_status は変更しません。
- RSASandboxPayload は VERITAS 側の受信契約名として維持します。
- upstream_signal_source = "RSA" は v1 互換 fixture/source ラベルとして維持します。
- この互換ラベルは、VERITAS が V.I.K.I. の内部 reasoning を受け取ることを意味しません。
- VERITAS が受け取るのは emit 済み payload のみです。

## 4. 静的サンドボックス入力 payload

```json
{
  "rsa_status": "DENSITY_THROTTLED",
  "trigger_source": "SRC_Cognitive_Density_Throttle",
  "original_llm_intent": "Generate_Dense_Transaction_Risk_Explanation",
  "rsa_action_taken": "Output_Compressed_For_Cognitive_Safety",
  "timestamp": "2026-10-25T09:20:30Z"
}
```

## 5. 期待される VERITAS 判断出力

```json
{
  "continuation_decision": "CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED",
  "reason_code": "UPSTREAM_INTERVENTION_DENSITY_THROTTLE",
  "authority_evidence_status": "INSUFFICIENT",
  "sandbox_bind_boundary_state": "NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE",
  "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
  "required_next_action": "REQUEST_ADDITIONAL_KYC_EVIDENCE_OR_HUMAN_REVIEW"
}
```

## 6. 期待される監査エントリ出力

```json
{
  "upstream_signal_source": "RSA",
  "rsa_status": "DENSITY_THROTTLED",
  "trigger_source": "SRC_Cognitive_Density_Throttle",
  "original_llm_intent": "[REDACTED]",
  "rsa_action_taken": "[REDACTED]",
  "veritas_reason": "RSA modified the upstream output for cognitive density control; VERITAS records the intervention without treating it as a default hard block.",
  "timestamp": "2026-10-25T09:20:30Z",
  "veritas_continuation_decision": "CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED",
  "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED"
}
```

## 7. このスナップショットで検証されること

- DENSITY_THROTTLED ステータスが既存の RSASandboxPayload 契約で表現可能であること。
- VERITAS が DENSITY_THROTTLED を CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED へ決定論的にマッピングすること。
- VERITAS が UPSTREAM_INTERVENTION_DENSITY_THROTTLE を記録すること。
- 上流の intent/action 生データがデフォルトで redaction されること。
- 本バリアントが PAUSE_FOR_HUMAN_REVIEW よりソフトな介入を示すこと。
- live V.I.K.I. ロジックへ接続せずとも現行 E2E サンドボックス経路がレビュー可能であること。

## 8. このスナップショットで検証されないこと

- live V.I.K.I. middleware への接続は行いません。
- V.I.K.I. の内部 reasoning は検証しません。
- 実ユーザーの cognitive state は判定しません。
- 本番 AML/KYC コンプライアンスは実装しません。
- 規制当局の承認は提供しません。
- 第三者認証は提供しません。
- 法的助言は提供しません。
- 実在顧客データ、金融データ、医療データ、KYC データ、または規制対象データは使用しません。
- 本番ランタイム・ガバナンスは変更しません。

## 9. ALGORITHMIC_HUMILITY_ENGAGED との関係

DENSITY_THROTTLED:

- 上流出力は cognitive-density 制御のために修正されます。
- VERITAS は介入をログ化します。
- continuation decision は CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED です。

ALGORITHMIC_HUMILITY_ENGAGED:

- 必要な context / authority evidence が不十分です。
- VERITAS は human review のため一時停止します。
- continuation decision は PAUSE_FOR_HUMAN_REVIEW です。

## 10. 次のサンドボックス・ステップ

このソフト介入スナップショットの次候補は DEFERRAL_ENGAGED です。

DEFERRAL_ENGAGED はより強いハードストップケースとして扱い、live V.I.K.I. 接続を試行する前に別ドキュメントとして整理すべきです。

# RSA ↔ VERITAS AML/KYC サンドボックス・インターフェース契約

## 位置づけとスコープ

このインターフェースは **サンドボックス専用のフィクスチャ契約** です。

- 決定論的なテストとレビュー用途を目的とします。
- RSA は外部の上流システムとして扱われ、VERITAS の中核ロジックには統合しません。
- VERITAS は RSA 形式のフラグを上流シグナルとして受け取り、継続可否・bind-boundary 判定・最終コミット結果・監査記録を下流で決定します。

## 英語正本

- [English authoritative version](../../en/guides/rsa-veritas-aml-kyc-sandbox-interface.md)

## 免責事項

この成果物は **本番 AML/KYC コンプライアンス実装ではありません**。

この成果物は **規制当局による承認ではありません**。
この成果物は **第三者認証ではありません**。
この成果物は **法的助言ではありません**。

## 入力スキーマ

RSASandboxPayload は次の全フィールドが必須です。

- rsa_status
- trigger_source
- original_llm_intent
- rsa_action_taken
- timestamp

timestamp は timezone 情報付き ISO-8601 互換文字列である必要があります。

- 末尾 `Z`、または
- 明示的な timezone offset（例: `+00:00`, `+09:00`）

## 出力スキーマと許容値

evaluate_rsa_sandbox_signal() は次の辞書を返します。

- veritas_decision
  - continuation_decision
  - reason_code
  - authority_evidence_status
  - sandbox_bind_boundary_state
  - sandbox_commit_state
  - required_next_action
- audit_entry
  - upstream_signal_source
  - rsa_status
  - trigger_source
  - original_llm_intent
  - rsa_action_taken
  - veritas_reason
  - timestamp
  - veritas_continuation_decision
  - veritas_sandbox_commit_state
- 関数オプション
  - include_raw_upstream_fields（既定値: false）

許容値 / fixture 固定値:

- rsa_status
  - SAFE_PROCEED
  - DENSITY_THROTTLED
  - ALGORITHMIC_HUMILITY_ENGAGED
  - DEFERRAL_ENGAGED
- continuation_decision
  - CONTINUE_TO_BIND_BOUNDARY
  - CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED
  - PAUSE_FOR_HUMAN_REVIEW
  - BLOCK_FINAL_COMMIT
- reason_code
  - UPSTREAM_SAFE_PROCEED_SIGNAL
  - UPSTREAM_INTERVENTION_DENSITY_THROTTLE
  - UPSTREAM_INCOMPLETE_KYC_CONTEXT
  - UPSTREAM_CRITICAL_DEFERRAL_SIGNAL
- authority_evidence_status
  - INSUFFICIENT（この sandbox では固定値）
- sandbox_bind_boundary_state
  - NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE
  - この sandbox では固定値
  - 本番の BindReceipt / FinalOutcome / CommitBoundaryOutcome ではありません
  - production bind-boundary evaluation が実行されたことを意味しません
- sandbox_commit_state
  - SUSPENDED_NOT_COMMITTED
  - BLOCKED_NOT_COMMITTED
- required_next_action
  - REQUEST_ADDITIONAL_KYC_EVIDENCE_OR_HUMAN_REVIEW（この sandbox では固定値）

セキュリティ注意:

- original_llm_intent と rsa_action_taken は既定で [REDACTED] にマスクされます。
- raw 値は include_raw_upstream_fields=True のときのみ返されます。
- include_raw_upstream_fields=True には VERITAS_RSA_SANDBOX_ALLOW_RAW_UPSTREAM=1 が必要です。
- VERITAS_ENV が prod / production / stg / staging の場合、raw 出力は許可されません。
- VERITAS_ENV 判定前に strip/lower 正規化を行います。
- これは特定フィールドに限定したマスキングであり、汎用的な PII/secret 検知ではありません。
- テスト外で保存する場合は TrustLog redaction/sanitization pipeline を必ず通してください。
- この sandbox は本番 AML/KYC コンプライアンス実装ではありません。

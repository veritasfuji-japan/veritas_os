# RSA ↔ VERITAS E2E サンドボックス検証スナップショット

## 英語正本

- [RSA ↔ VERITAS E2E Sandbox Validation Snapshot](../../en/guides/rsa-veritas-e2e-sandbox-validation-snapshot.md)

## 1. 目的

本書は、V.I.K.I. ↔ VERITAS / RSA-compatible E2E フローにおける、現時点の sandbox-only 検証スナップショットを記録するための文書です。

目的は、runtime behavior を変更せずに、現在の static harness 出力をレビュー可能にすることです。

## 2. 現在のマージ済みベースライン

現在のマージ済みベースラインには以下が含まれます。
- V.I.K.I. / RSA / VERITAS の用語同期。
- RSA-compatible な static payload contract。
- RSASandboxPayload receiver contract。
- evaluate_rsa_sandbox_signal(payload) による decision mapping。
- examples/sandbox/rsa_veritas_e2e_harness.py の thin E2E sandbox harness。
- governance-backend-fast による CI coverage。

## 3. 用語互換性ノート

- RSA は理論的フレームワークおよび underlying rule set のままです。
- V.I.K.I. は RSA-compatible upstream payload の operational producer です。
- VERITAS は downstream の commit governance boundary です。
- 互換性のため、rsa_status は変更しません。
- RSASandboxPayload は VERITAS 側 receiver contract 名として維持されます。
- upstream_signal_source = "RSA" は v1 compatibility fixture/source label として維持されます。
- この compatibility label は、VERITAS が V.I.K.I. internal reasoning を消費することを意味しません。
- VERITAS が消費するのは emitted payload のみです。

## 4. Static sandbox input payload

```json
{
  "rsa_status": "ALGORITHMIC_HUMILITY_ENGAGED",
  "trigger_source": "SRC_Incomplete_Context",
  "original_llm_intent": "Recommend_Transaction_Approval",
  "rsa_action_taken": "Execution_Suspended_Awaiting_Reality_Sync",
  "timestamp": "2026-10-25T09:15:30Z"
}
```

## 5. Harness invocation path

現在の harness path は次のとおりです。

V.I.K.I.-style RSA-compatible static payload
→ RSASandboxPayload(**payload_dict)
→ evaluate_rsa_sandbox_signal(payload)
→ veritas_decision
→ audit_entry

現在の harness は以下です。

examples/sandbox/rsa_veritas_e2e_harness.py

## 6. 期待される VERITAS decision output

```json
{
  "continuation_decision": "PAUSE_FOR_HUMAN_REVIEW",
  "reason_code": "UPSTREAM_INCOMPLETE_KYC_CONTEXT",
  "authority_evidence_status": "INSUFFICIENT",
  "sandbox_bind_boundary_state": "NOT_EVALUATED_PENDING_AUTHORITY_EVIDENCE",
  "sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
  "required_next_action": "REQUEST_ADDITIONAL_KYC_EVIDENCE_OR_HUMAN_REVIEW"
}
```

## 7. 期待される audit entry output

```json
{
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
```

## 8. このスナップショットで検証されること

- static な V.I.K.I.-style RSA-compatible payload を、既存の RSASandboxPayload contract で表現できること。
- VERITAS が ALGORITHMIC_HUMILITY_ENGAGED を PAUSE_FOR_HUMAN_REVIEW に決定的にマッピングすること。
- VERITAS が UPSTREAM_INCOMPLETE_KYC_CONTEXT を記録すること。
- upstream の raw intent/action フィールドがデフォルトで redacted されること。
- sandbox commit state が SUSPENDED_NOT_COMMITTED であること。
- live V.I.K.I. logic を接続せずに current E2E sandbox path をレビュー可能であること。

## 9. このスナップショットで検証されないこと

- live V.I.K.I. middleware への接続は行いません。
- V.I.K.I. internal reasoning の検証は行いません。
- production AML/KYC compliance の実装は行いません。
- regulatory approval を提供しません。
- third-party certification を提供しません。
- legal advice を提供しません。
- 実在の customer / financial / medical / KYC / 規制対象データは使用しません。
- production runtime governance は変更しません。

## 10. 次の sandbox ステップ

次の sandbox ステップは、このスナップショットがマージされた後に次の static fixture variant を選定することです。

有力候補:
- DENSITY_THROTTLED
- DEFERRAL_ENGAGED

fixture variants の文書化と検証が完了する前に、live V.I.K.I. connection を追加してはいけません。

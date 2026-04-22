# Evidence Handoff / Audit Pack Template

## 目的

外部監査人・顧客統制部門・内部監査に対し、
VERITAS の decision-to-effect 統制を再現可能な形で受け渡すための
テンプレートを定義する。

## 利用ルール

- 1ケース1パックを基本とし、ケース横断サマリは別紙に分離する。
- 欠落項目がある場合は提出前に `INCOMPLETE` と明示する。
- 未実装機能を証跡に含める説明は禁止。

---

## 1. Case Cover

- case_id:
- workflow_type: (AML/KYC / Approval / Other)
- case_opened_at:
- decision_completed_at:
- operator_owner:
- policy_bundle_version:
- runtime_environment: (dev/test/prod)

## 2. Decision Governance Summary

- decision_outcome:
- risk_tier:
- human_review_required: (yes/no)
- key_rationale_summary:
- governing_policies:

## 3. Bind-Boundary Summary

- execution_intent_id:
- bind_receipt_id:
- bind_outcome:
- bind_reason_code:
- bind_failure_reason: (if any)
- admissibility_timestamp:

## 4. Runtime Execution Linkage（共存時）

- runtime_event_id:
- execution_status:
- execution_started_at:
- execution_finished_at:
- linkage_check: (decision->intent->receipt->runtime の整合結果)

## 5. Attached Artifacts

- [ ] decision artifact（原本）
- [ ] execution intent（原本）
- [ ] bind receipt（原本）
- [ ] trust/log extract（必要範囲）
- [ ] reviewer notes（任意）

## 6. Replay / Revalidation Procedure

- replay_entrypoint:
- required_inputs:
- expected_replay_outcome:
- observed_replay_outcome:
- divergence_notes:

## 7. Exception and Override Log

- override_used: (yes/no)
- override_reason:
- override_approver:
- override_timestamp:
- compensating_controls:

## 8. Security and Privacy Notes

- pii_included: (yes/no)
- masking_applied: (yes/no)
- retention_policy_applied:
- access_scope:

## 9. Sign-off

- prepared_by:
- reviewed_by:
- approved_by:
- approval_date:

---

## 監査提出前チェック（最終ゲート）

- [ ] case_id と各artifact IDの整合が取れている
- [ ] タイムスタンプが時系列として矛盾しない
- [ ] bind_failure_reason が空欄なら理由コードが成功系である
- [ ] runtime 連携がない場合、その旨を明示した
- [ ] replay手順が第三者に実行可能な粒度で書かれている

## ひな形メッセージ（提出メール用）

> 添付の audit pack は、当該ケースの decision governance、
> bind-boundary 判定、runtime 実行連携（該当時）を
> externally reviewable な形で整理したものです。
> 本資料は実装済み経路に基づく事実記述であり、
> 未実装機能を前提にした主張は含みません。

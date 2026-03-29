import type { FujiRules } from "@veritas/types";
import type { ApprovalStatus, DiffChange, GovernanceMode, UserRole } from "./governance-types";

export const FUJI_LABELS: Record<keyof FujiRules, string> = {
  pii_check: "PII Check",
  self_harm_block: "Self-Harm Block",
  illicit_block: "Illicit Block",
  violence_review: "Violence Review",
  minors_review: "Minors Review",
  keyword_hard_block: "Keyword Hard Block",
  keyword_soft_flag: "Keyword Soft Flag",
  llm_safety_head: "LLM Safety Head",
};

export const MODE_EXPLANATIONS: Record<GovernanceMode, { summary: string; details: string[]; affects: string[] }> = {
  standard: {
    summary: "通常運用モード",
    details: [
      "通常運用: 既存しきい値とエスカレーションを使用します。",
      "FUJIルール違反時は既存フローのままレビューへ。",
    ],
    affects: [
      "risk_thresholds: デフォルト値を使用",
      "audit_level: standard",
      "human_review: しきい値超過時のみ",
      "escalation: 通常ルート",
    ],
  },
  eu_ai_act: {
    summary: "EU AI Act 準拠モード",
    details: [
      "EU AI Act mode: explainability と audit retention を優先します。",
      "高リスク判定時に人間レビュー経路を強制し、監査ログ粒度を上げます。",
    ],
    affects: [
      "risk_thresholds: 低め(厳格)に自動調整",
      "audit_level: full → 全フィールド記録",
      "human_review: 高リスク判定で強制",
      "escalation: Art.14(4) 停止権限を付与",
    ],
  },
};

export const ROLE_CAPABILITIES: Record<UserRole, { label: string; permissions: string[] }> = {
  viewer: {
    label: "Viewer（閲覧専用）",
    permissions: ["ポリシー閲覧", "Diff プレビュー", "TrustLog 閲覧", "変更履歴の参照"],
  },
  operator: {
    label: "Operator（運用）",
    permissions: ["ポリシー閲覧", "dry-run 実行", "shadow validation", "承認リクエスト送信"],
  },
  admin: {
    label: "Admin（管理者）",
    permissions: ["全操作権限", "ポリシー適用", "ロールバック", "承認 / 却下", "モード変更"],
  },
};

export const DIFF_CATEGORY_LABELS: Record<DiffChange["category"], string> = {
  rule: "ルール変更",
  threshold: "しきい値変更",
  escalation: "エスカレーション変更",
  retention: "監査ログ変更",
  rollout: "ロールアウト制御変更",
  approval: "承認ワークフロー変更",
  meta: "メタ情報変更",
};

export const APPROVAL_STATUS_ACCENT: Record<ApprovalStatus, "success" | "warning" | "danger" | "info"> = {
  approved: "success",
  pending: "warning",
  rejected: "danger",
  draft: "info",
};

"use client";

import { useCallback, useMemo, useState } from "react";
import { Card } from "@veritas/design-system";
import { useI18n } from "../../components/i18n-provider";
import { veritasFetch } from "../../lib/api-client";
import { validateGovernancePolicyResponse } from "../../lib/api-validators";
import { EUAIActGovernanceDashboard } from "../../features/console/components/eu-ai-act-governance-dashboard";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type UserRole = "viewer" | "operator" | "admin";
type PolicyActionMode = "apply" | "dry-run" | "shadow";
type GovernanceMode = "standard" | "eu_ai_act";
type ApprovalStatus = "approved" | "pending" | "rejected" | "draft";

interface FujiRules {
  pii_check: boolean;
  self_harm_block: boolean;
  illicit_block: boolean;
  violence_review: boolean;
  minors_review: boolean;
  keyword_hard_block: boolean;
  keyword_soft_flag: boolean;
  llm_safety_head: boolean;
}

interface RiskThresholds {
  allow_upper: number;
  warn_upper: number;
  human_review_upper: number;
  deny_upper: number;
}

interface AutoStop {
  enabled: boolean;
  max_risk_score: number;
  max_consecutive_rejects: number;
  max_requests_per_minute: number;
}

interface LogRetention {
  retention_days: number;
  audit_level: string;
  include_fields: string[];
  redact_before_log: boolean;
  max_log_size: number;
}

interface GovernancePolicy {
  version: string;
  draft_version?: string;
  effective_at?: string;
  last_applied?: string;
  approval_status: ApprovalStatus;
  fuji_rules: FujiRules;
  risk_thresholds: RiskThresholds;
  auto_stop: AutoStop;
  log_retention: LogRetention;
  updated_at: string;
  updated_by: string;
}

interface DiffChange {
  path: string;
  old: string;
  next: string;
  category: "rule" | "threshold" | "escalation" | "retention" | "meta";
}

interface HistoryEntry {
  id: string;
  action: string;
  actor: UserRole;
  at: string;
  summary: string;
}

interface TrustLogEntry {
  id: string;
  at: string;
  message: string;
  severity: "info" | "warning" | "policy";
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const FUJI_LABELS: Record<keyof FujiRules, string> = {
  pii_check: "PII Check",
  self_harm_block: "Self-Harm Block",
  illicit_block: "Illicit Block",
  violence_review: "Violence Review",
  minors_review: "Minors Review",
  keyword_hard_block: "Keyword Hard Block",
  keyword_soft_flag: "Keyword Soft Flag",
  llm_safety_head: "LLM Safety Head",
};

const MODE_EXPLANATIONS: Record<GovernanceMode, { summary: string; details: string[]; affects: string[] }> = {
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

const ROLE_CAPABILITIES: Record<UserRole, { label: string; permissions: string[] }> = {
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

const DIFF_CATEGORY_LABELS: Record<DiffChange["category"], string> = {
  rule: "ルール変更",
  threshold: "しきい値変更",
  escalation: "エスカレーション変更",
  retention: "監査ログ変更",
  meta: "メタ情報変更",
};

/* ------------------------------------------------------------------ */
/*  Pure helpers                                                       */
/* ------------------------------------------------------------------ */

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== typeof b || a === null || b === null) return false;
  if (typeof a !== "object") return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;

  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, i) => deepEqual(item, b[i]));
  }

  const objA = a as Record<string, unknown>;
  const objB = b as Record<string, unknown>;
  const keysA = Object.keys(objA);
  const keysB = Object.keys(objB);
  return keysA.length === keysB.length && keysA.every((key) => deepEqual(objA[key], objB[key]));
}

function categorizePath(path: string): DiffChange["category"] {
  if (path.startsWith("fuji_rules")) return "rule";
  if (path.startsWith("risk_thresholds")) return "threshold";
  if (path.startsWith("auto_stop")) return "escalation";
  if (path.startsWith("log_retention")) return "retention";
  return "meta";
}

function collectChanges(prefix: string, a: Record<string, unknown>, b: Record<string, unknown>): DiffChange[] {
  const changes: DiffChange[] = [];
  for (const key of new Set([...Object.keys(a), ...Object.keys(b)])) {
    const av = a[key];
    const bv = b[key];
    if (deepEqual(av, bv)) continue;
    if (typeof av === "object" && av !== null && typeof bv === "object" && bv !== null) {
      changes.push(...collectChanges(`${prefix}.${key}`, av as Record<string, unknown>, bv as Record<string, unknown>));
      continue;
    }
    const fullPath = `${prefix}.${key}`.replace(/^\./, "");
    changes.push({ path: fullPath, old: JSON.stringify(av), next: JSON.stringify(bv), category: categorizePath(fullPath) });
  }
  return changes;
}

function bumpDraftVersion(version: string): string {
  const match = version.match(/^(.+?)(\d+)$/);
  if (!match) return `${version}-draft.1`;
  return `${match[1]}${Number(match[2]) + 1}-draft`;
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function StatusBadge({ status }: { status: ApprovalStatus }): JSX.Element {
  const styles: Record<ApprovalStatus, string> = {
    approved: "bg-success/20 text-success border-success/40",
    pending: "bg-warning/20 text-warning border-warning/40",
    rejected: "bg-danger/20 text-danger border-danger/40",
    draft: "bg-info/20 text-info border-info/40",
  };
  return <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${styles[status]}`}>{status}</span>;
}

function ToggleRow({ label, checked, onChange, disabled }: { label: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }): JSX.Element {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border px-3.5 py-2.5 text-sm">
      <span>{label}</span>
      <button
        type="button"
        role="switch"
        aria-label={label}
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={["relative inline-flex h-5 w-10 items-center rounded-full transition-colors", checked ? "bg-primary" : "bg-muted", disabled ? "opacity-50 cursor-not-allowed" : ""].join(" ")}
      >
        <span className={["inline-block h-4 w-4 rounded-full bg-white transition-transform", checked ? "translate-x-5" : "translate-x-0.5"].join(" ")} />
      </button>
    </div>
  );
}

function DiffPreview({ before, after }: { before: GovernancePolicy | null; after: GovernancePolicy | null }): JSX.Element {
  const { t } = useI18n();
  const rows = before && after
    ? collectChanges(
      "",
      before as unknown as Record<string, unknown>,
      after as unknown as Record<string, unknown>,
    )
    : [];
  if (rows.length === 0) return <p className="text-xs text-muted-foreground">{t("変更はありません。", "No changes.")}</p>;

  const grouped = rows.reduce<Record<string, DiffChange[]>>((acc, row) => {
    const cat = row.category;
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(row);
    return acc;
  }, {});

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">{t(`${rows.length} 件の変更を検出`, `${rows.length} change(s) detected`)}</p>
      {(Object.keys(grouped) as DiffChange["category"][]).map((cat) => (
        <div key={cat}>
          <p className="mb-1 text-xs font-semibold text-muted-foreground">{DIFF_CATEGORY_LABELS[cat]}</p>
          <div className="space-y-1">
            {grouped[cat].map((row) => (
              <div key={row.path} className="rounded-md border px-3 py-1 text-xs">
                <p className="font-semibold">{row.path}</p>
                <div className="flex gap-2">
                  <span className="text-red-400 line-through">{row.old}</span>
                  <span className="text-green-400">{row.next}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

const RISK_BAND_BG: Record<string, string> = {
  danger: "bg-danger",
  warning: "bg-warning",
  success: "bg-success",
};

const RISK_BAND_TEXT: Record<string, string> = {
  danger: "text-danger",
  warning: "text-warning",
  success: "text-success",
};

function riskBand(value: number): string {
  if (value > 75) return "danger";
  if (value > 50) return "warning";
  return "success";
}

function RiskImpactGauge({ current, pending, drift }: { current: number; pending: number; drift: number }): JSX.Element {
  const band = riskBand(current);
  const pendingBand = riskBand(pending);
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <span className="text-xs font-semibold w-28">Current Policy</span>
        <div className="flex-1 rounded-full bg-muted h-2.5 overflow-hidden">
          <div className={`h-full rounded-full transition-all ${RISK_BAND_BG[band]}`} style={{ width: `${current}%` }} />
        </div>
        <span className={`text-xs font-mono font-semibold ${RISK_BAND_TEXT[band]}`}>{current}%</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-xs font-semibold w-28">Pending Impact</span>
        <div className="flex-1 rounded-full bg-muted h-2.5 overflow-hidden">
          <div className={`h-full rounded-full transition-all ${RISK_BAND_BG[pendingBand]}`} style={{ width: `${pending}%` }} />
        </div>
        <span className={`text-xs font-mono font-semibold ${RISK_BAND_TEXT[pendingBand]}`}>{pending}%</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-xs font-semibold w-28">Recent Drift</span>
        <span className={`text-xs font-mono font-semibold ${drift > 5 ? "text-warning" : "text-success"}`}>
          {drift > 0 ? `+${drift}%` : `${drift}%`} from baseline
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main page component                                                */
/* ------------------------------------------------------------------ */

export default function GovernanceControlPage(): JSX.Element {
  const { t } = useI18n();
  const [savedPolicy, setSavedPolicy] = useState<GovernancePolicy | null>(null);
  const [draft, setDraft] = useState<GovernancePolicy | null>(null);
  const [selectedRole, setSelectedRole] = useState<UserRole>("admin");
  const [governanceMode, setGovernanceMode] = useState<GovernanceMode>("standard");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [trustLog, setTrustLog] = useState<TrustLogEntry[]>([]);

  const hasChanges = useMemo(() => savedPolicy !== null && draft !== null && !deepEqual(savedPolicy, draft), [savedPolicy, draft]);
  const canApply = selectedRole === "admin";
  const canOperate = selectedRole === "admin" || selectedRole === "operator";
  const canApprove = selectedRole === "admin";

  const changeCount = useMemo(() => {
    if (!savedPolicy || !draft) return 0;
    return collectChanges("", savedPolicy as unknown as Record<string, unknown>, draft as unknown as Record<string, unknown>).length;
  }, [savedPolicy, draft]);

  const appendLog = useCallback((message: string, severity: "info" | "warning" | "policy" = "info") => {
    setTrustLog((prev) => [{ id: crypto.randomUUID(), at: new Date().toISOString(), message, severity }, ...prev].slice(0, 12));
  }, []);

  const appendHistory = useCallback((action: string, summary: string) => {
    setHistory((prev) => [
      { id: crypto.randomUUID(), action, actor: selectedRole, at: new Date().toISOString(), summary },
      ...prev,
    ].slice(0, 20));
  }, [selectedRole]);

  const updateDraft = useCallback((updater: (prev: GovernancePolicy) => GovernancePolicy) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const next = updater(prev);
      return { ...next, approval_status: "pending" as ApprovalStatus };
    });
  }, []);

  const fetchPolicy = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await veritasFetch("/api/veritas/v1/governance/policy");
      if (!res.ok) {
        setError(t(`HTTP ${res.status}: ポリシー取得に失敗しました。`, `HTTP ${res.status}: Failed to fetch policy.`));
        return;
      }
      const validation = validateGovernancePolicyResponse(await res.json());
      if (!validation.ok) {
        setError(t("レスポンスの検証に失敗しました。フォーマット不整合の可能性があります。", "Response validation failed. Possible format mismatch."));
        return;
      }
      const normalized = {
        ...validation.data.policy,
        effective_at: validation.data.policy.updated_at,
        last_applied: validation.data.policy.updated_at,
        approval_status: "approved" as ApprovalStatus,
        draft_version: bumpDraftVersion(validation.data.policy.version),
      } as GovernancePolicy;
      setSavedPolicy(normalized);
      setDraft(structuredClone(normalized));
      appendHistory("load", `version ${normalized.version} loaded`);
      appendLog(`policy version ${normalized.version} loaded`, "policy");
    } catch {
      setError(t("ネットワークエラー: バックエンドへ接続できません。", "Network error: cannot connect to backend."));
    } finally {
      setLoading(false);
    }
  }, [appendHistory, appendLog, t]);

  const applyPolicy = useCallback(async (mode: PolicyActionMode) => {
    if (!draft) return;
    if (!window.confirm(t(`${mode} を実行します。変更を確定しますか？`, `Execute ${mode}. Confirm changes?`))) return;

    setSaving(true);
    setError(null);
    setSuccess(null);

    if (mode === "dry-run") {
      appendHistory("dry-run", "no persistent write");
      appendLog("dry-run completed without apply", "info");
      setSuccess(t("Dry-run を完了しました。適用はされていません。", "Dry-run completed. No changes applied."));
      setSaving(false);
      return;
    }

    if (mode === "shadow") {
      appendHistory("shadow", "shadow validation stream enabled");
      appendLog("shadow mode enabled; outputs are validated only", "warning");
      setSuccess(t("Shadow mode を有効化しました。判定のみ実施します。", "Shadow mode enabled. Validation only."));
      setSaving(false);
      return;
    }

    try {
      const res = await veritasFetch("/api/veritas/v1/governance/policy", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      if (!res.ok) {
        setError(t(`HTTP ${res.status}: ポリシー更新に失敗しました。`, `HTTP ${res.status}: Failed to update policy.`));
        return;
      }
      const validation = validateGovernancePolicyResponse(await res.json());
      if (!validation.ok) {
        setError(t("適用レスポンスの検証に失敗しました。TrustLog を確認してください。", "Apply response validation failed. Check TrustLog."));
        return;
      }
      const nextPolicy = {
        ...validation.data.policy,
        effective_at: new Date().toISOString(),
        last_applied: new Date().toISOString(),
        approval_status: "approved" as ApprovalStatus,
        draft_version: bumpDraftVersion(validation.data.policy.version),
      } as GovernancePolicy;
      setSavedPolicy(nextPolicy);
      setDraft(structuredClone(nextPolicy));
      appendHistory("apply", `version ${nextPolicy.version} applied`);
      appendLog(`applied version ${nextPolicy.version}`, "policy");
      setSuccess(t("ポリシーを適用しました。", "Policy applied successfully."));
    } catch {
      setError(t("適用処理に失敗しました。通信・権限・整合性を確認してください。", "Apply failed. Check connectivity, permissions, and consistency."));
    } finally {
      setSaving(false);
    }
  }, [appendHistory, appendLog, draft, t]);

  const rollback = useCallback(() => {
    if (!savedPolicy) return;
    if (!window.confirm(t("現在の適用済みポリシーへロールバックしますか？", "Rollback to the currently applied policy?"))) return;
    setDraft(structuredClone(savedPolicy));
    appendHistory("rollback", `rolled back to version ${savedPolicy.version}`);
    appendLog(`rollback preview to ${savedPolicy.version}`, "warning");
    setSuccess(t("ドラフトを適用済みポリシーへ戻しました。", "Draft reverted to the applied policy."));
  }, [appendHistory, appendLog, savedPolicy, t]);

  const approveChanges = useCallback(() => {
    if (!draft || !hasChanges) return;
    if (!window.confirm(t("ドラフト変更を承認しますか？", "Approve draft changes?"))) return;
    setDraft((prev) => prev ? { ...prev, approval_status: "approved" } : prev);
    appendHistory("approve", `draft changes approved by ${selectedRole}`);
    appendLog(`draft approved by ${selectedRole}`, "policy");
    setSuccess(t("ドラフトを承認しました。apply で本番適用できます。", "Draft approved. Apply to push to production."));
  }, [draft, hasChanges, appendHistory, appendLog, selectedRole, t]);

  const rejectChanges = useCallback(() => {
    if (!draft || !hasChanges) return;
    if (!window.confirm(t("ドラフト変更を却下しますか？", "Reject draft changes?"))) return;
    setDraft((prev) => prev ? { ...prev, approval_status: "rejected" } : prev);
    appendHistory("reject", `draft changes rejected by ${selectedRole}`);
    appendLog(`draft rejected by ${selectedRole}`, "warning");
    setSuccess(t("ドラフトを却下しました。", "Draft rejected."));
  }, [draft, hasChanges, appendHistory, appendLog, selectedRole, t]);

  const currentRisk = savedPolicy ? Math.round(((savedPolicy.risk_thresholds.deny_upper + savedPolicy.auto_stop.max_risk_score) / 2) * 100) : 0;
  const pendingRisk = draft ? Math.round(((draft.risk_thresholds.deny_upper + draft.auto_stop.max_risk_score) / 2) * 100) : 0;
  const riskGauge = draft ? pendingRisk : currentRisk;
  const riskDrift = pendingRisk - currentRisk;

  const draftApprovalStatus: ApprovalStatus = useMemo(() => {
    if (!draft) return "draft";
    if (!hasChanges) return draft.approval_status;
    return "pending";
  }, [draft, hasChanges]);

  return (
    <div className="space-y-6">
      {/* ── Header: Governance Control Plane ── */}
      <Card title="Governance Control" description={t("Rule control / versioning / diff / approval / rollback / shadow validation を統合管理します。", "Integrated management of rule control, versioning, diff, approval, rollback, and shadow validation.")} titleSize="lg" variant="glass" accent="primary" className="border-primary/15">
        <div className="grid gap-3 md:grid-cols-4">
          <label className="text-xs">Role
            <select aria-label="role" value={selectedRole} onChange={(e) => setSelectedRole(e.target.value as UserRole)} className="mt-1 w-full rounded border px-2 py-1">
              <option value="viewer">viewer</option>
              <option value="operator">operator</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <label className="text-xs">Mode
            <select aria-label="mode" value={governanceMode} onChange={(e) => setGovernanceMode(e.target.value as GovernanceMode)} className="mt-1 w-full rounded border px-2 py-1">
              <option value="standard">Standard</option>
              <option value="eu_ai_act">EU AI Act</option>
            </select>
          </label>
          <button type="button" onClick={() => void fetchPolicy()} className="rounded border px-3 py-2 text-sm" disabled={loading}>{loading ? t("読み込み中...", "Loading...") : t("ポリシーを読み込む", "Load policy")}</button>
          <div className="rounded border px-3 py-2 text-xs">Risk gauge: <span className="font-mono">{riskGauge}%</span></div>
        </div>

        {/* ── Role capability matrix ── */}
        <div className="mt-3 rounded-lg border bg-surface/50 px-3 py-2">
          <p className="text-xs font-semibold mb-1">{ROLE_CAPABILITIES[selectedRole].label}</p>
          <div className="flex flex-wrap gap-1.5">
            {ROLE_CAPABILITIES[selectedRole].permissions.map((perm) => (
              <span key={perm} className="inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground">{perm}</span>
            ))}
          </div>
        </div>

        {/* ── Mode explanation ── */}
        <div className="mt-3 rounded-lg border bg-surface/50 px-3 py-2">
          <p className="text-xs font-semibold mb-1">{MODE_EXPLANATIONS[governanceMode].summary}</p>
          <ul className="list-disc pl-5 text-xs text-muted-foreground">
            {MODE_EXPLANATIONS[governanceMode].details.map((entry) => <li key={entry}>{entry}</li>)}
          </ul>
          <div className="mt-2 grid gap-1 md:grid-cols-2">
            {MODE_EXPLANATIONS[governanceMode].affects.map((effect) => (
              <span key={effect} className="rounded border px-2 py-0.5 text-[10px] font-mono text-muted-foreground">{effect}</span>
            ))}
          </div>
        </div>
      </Card>

      <EUAIActGovernanceDashboard />

      {error ? <div role="alert" className="rounded border border-danger/40 px-3 py-2 text-sm text-danger">{error}</div> : null}
      {success ? <div role="status" className="rounded border border-success/40 px-3 py-2 text-sm text-success">{success}</div> : null}

      {/* ── Empty state when no policy is loaded ── */}
      {!draft ? (
        <Card title="Policy Status" titleSize="md" variant="elevated">
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <div className="rounded-full border-2 border-dashed border-muted p-4">
              <svg className="h-8 w-8 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-semibold">{t("ポリシー未読み込み", "No policy loaded")}</p>
              <p className="text-xs text-muted-foreground mt-1">{t("「ポリシーを読み込む」ボタンでバックエンドから現在の統制ポリシーを取得してください。", "Click \"Load policy\" to fetch the current governance policy from the backend.")}</p>
            </div>
          </div>
        </Card>
      ) : null}

      {draft ? (
        <>
          {/* ── Policy Header with approval status ── */}
          <Card title="Policy Meta" titleSize="md" variant="elevated" accent={draftApprovalStatus === "approved" ? "success" : draftApprovalStatus === "pending" ? "warning" : draftApprovalStatus === "rejected" ? "danger" : "info"}>
            <div className="grid gap-3 text-xs md:grid-cols-2 lg:grid-cols-3">
              <div className="rounded-lg border px-3 py-2">
                <p className="text-muted-foreground">Current Version</p>
                <p className="font-mono font-semibold">{savedPolicy?.version ?? "N/A"}</p>
              </div>
              <div className="rounded-lg border px-3 py-2">
                <p className="text-muted-foreground">Draft Version</p>
                <p className="font-mono font-semibold">{draft.draft_version ?? "N/A"}</p>
              </div>
              <div className="rounded-lg border px-3 py-2">
                <p className="text-muted-foreground">Approval Status</p>
                <StatusBadge status={draftApprovalStatus} />
              </div>
              <div className="rounded-lg border px-3 py-2">
                <p className="text-muted-foreground">updated_by</p>
                <p className="font-mono font-semibold">{draft.updated_by}</p>
              </div>
              <div className="rounded-lg border px-3 py-2">
                <p className="text-muted-foreground">effective_at</p>
                <p className="font-mono font-semibold">{draft.effective_at ?? "N/A"}</p>
              </div>
              <div className="rounded-lg border px-3 py-2">
                <p className="text-muted-foreground">last_applied</p>
                <p className="font-mono font-semibold">{draft.last_applied ?? "N/A"}</p>
              </div>
            </div>
            {hasChanges ? (
              <p className="mt-2 text-xs text-warning">{t(`${changeCount} 件の未適用変更があります。適用前に承認してください。`, `${changeCount} unapplied change(s). Approve before applying.`)}</p>
            ) : null}
          </Card>

          {/* ── FUJI rules / thresholds / escalation ── */}
          <Card title="FUJI rules / thresholds / escalation" titleSize="md" variant="elevated">
            <div className="grid gap-2 md:grid-cols-2">
              {(Object.keys(FUJI_LABELS) as (keyof FujiRules)[]).map((key) => (
                <ToggleRow key={key} label={FUJI_LABELS[key]} checked={draft.fuji_rules[key]} disabled={selectedRole === "viewer"} onChange={(v) => updateDraft((prev) => ({ ...prev, fuji_rules: { ...prev.fuji_rules, [key]: v } }))} />
              ))}
            </div>

            <div className="mt-4">
              <p className="text-xs font-semibold mb-2">Risk Thresholds</p>
              <div className="grid gap-2 md:grid-cols-2">
                <label className="text-xs">allow_upper <span className="font-mono text-muted-foreground">({draft.risk_thresholds.allow_upper.toFixed(2)})</span><input aria-label="allow_upper" type="range" min={0} max={1} step={0.05} value={draft.risk_thresholds.allow_upper} disabled={selectedRole === "viewer"} onChange={(e) => updateDraft((prev) => ({ ...prev, risk_thresholds: { ...prev.risk_thresholds, allow_upper: Number(e.target.value) } }))} className="w-full" /></label>
                <label className="text-xs">warn_upper <span className="font-mono text-muted-foreground">({draft.risk_thresholds.warn_upper.toFixed(2)})</span><input aria-label="warn_upper" type="range" min={0} max={1} step={0.05} value={draft.risk_thresholds.warn_upper} disabled={selectedRole === "viewer"} onChange={(e) => updateDraft((prev) => ({ ...prev, risk_thresholds: { ...prev.risk_thresholds, warn_upper: Number(e.target.value) } }))} className="w-full" /></label>
                <label className="text-xs">human_review_upper <span className="font-mono text-muted-foreground">({draft.risk_thresholds.human_review_upper.toFixed(2)})</span><input aria-label="human_review_upper" type="range" min={0} max={1} step={0.05} value={draft.risk_thresholds.human_review_upper} disabled={selectedRole === "viewer"} onChange={(e) => updateDraft((prev) => ({ ...prev, risk_thresholds: { ...prev.risk_thresholds, human_review_upper: Number(e.target.value) } }))} className="w-full" /></label>
                <label className="text-xs">deny_upper <span className="font-mono text-muted-foreground">({draft.risk_thresholds.deny_upper.toFixed(2)})</span><input aria-label="deny_upper" type="range" min={0} max={1} step={0.05} value={draft.risk_thresholds.deny_upper} disabled={selectedRole === "viewer"} onChange={(e) => updateDraft((prev) => ({ ...prev, risk_thresholds: { ...prev.risk_thresholds, deny_upper: Number(e.target.value) } }))} className="w-full" /></label>
              </div>
            </div>

            <div className="mt-4">
              <p className="text-xs font-semibold mb-2">Auto-Stop / Escalation</p>
              <div className="grid gap-2 md:grid-cols-2">
                <ToggleRow label="Auto-Stop Enabled" checked={draft.auto_stop.enabled} disabled={selectedRole === "viewer"} onChange={(v) => updateDraft((prev) => ({ ...prev, auto_stop: { ...prev.auto_stop, enabled: v } }))} />
                <label className="text-xs">max_risk_score <span className="font-mono text-muted-foreground">({draft.auto_stop.max_risk_score.toFixed(2)})</span><input aria-label="max_risk_score" type="range" min={0} max={1} step={0.05} value={draft.auto_stop.max_risk_score} disabled={selectedRole === "viewer"} onChange={(e) => updateDraft((prev) => ({ ...prev, auto_stop: { ...prev.auto_stop, max_risk_score: Number(e.target.value) } }))} className="w-full" /></label>
              </div>
            </div>

            <div className="mt-4">
              <p className="text-xs font-semibold mb-2">Log Retention / Audit</p>
              <div className="grid gap-2 md:grid-cols-2">
                <label className="text-xs">retention_days <span className="font-mono text-muted-foreground">({draft.log_retention.retention_days})</span><input aria-label="retention_days" type="range" min={1} max={365} step={1} value={draft.log_retention.retention_days} disabled={selectedRole === "viewer"} onChange={(e) => updateDraft((prev) => ({ ...prev, log_retention: { ...prev.log_retention, retention_days: Number(e.target.value) } }))} className="w-full" /></label>
                <ToggleRow label="Redact Before Log" checked={draft.log_retention.redact_before_log} disabled={selectedRole === "viewer"} onChange={(v) => updateDraft((prev) => ({ ...prev, log_retention: { ...prev.log_retention, redact_before_log: v } }))} />
              </div>
            </div>
          </Card>

          {/* ── Current vs Draft Diff ── */}
          <Card title="Current vs Draft Diff" titleSize="md" variant="elevated"><DiffPreview before={savedPolicy} after={draft} /></Card>

          {/* ── Risk Impact ── */}
          <Card title="Risk Impact Analysis" titleSize="md" variant="elevated" accent={riskDrift > 5 ? "warning" : riskDrift < -5 ? "success" : undefined}>
            <RiskImpactGauge current={currentRisk} pending={pendingRisk} drift={riskDrift} />
          </Card>

          {/* ── Approval Workflow ── */}
          {hasChanges ? (
            <Card title="Approval Workflow" titleSize="md" variant="elevated" accent="warning">
              <div className="flex items-center gap-3 mb-3">
                <StatusBadge status={draftApprovalStatus} />
                <span className="text-xs text-muted-foreground">{t(`${changeCount} 件の変更が承認待ちです`, `${changeCount} change(s) awaiting approval`)}</span>
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="button" className="rounded border border-success/60 bg-success/10 px-3 py-2 text-sm text-success" onClick={approveChanges} disabled={!canApprove || draftApprovalStatus === "approved"}>approve</button>
                <button type="button" className="rounded border border-danger/60 bg-danger/10 px-3 py-2 text-sm text-danger" onClick={rejectChanges} disabled={!canApprove || draftApprovalStatus === "rejected"}>reject</button>
              </div>
              {!canApprove ? <p className="mt-2 text-xs text-warning">{t("RBAC: approve/reject は admin のみ実行可能です。", "RBAC: approve/reject requires admin role.")}</p> : null}
            </Card>
          ) : null}

          {/* ── Apply Flow ── */}
          <Card title="Apply Flow" titleSize="md" variant="elevated">
            <div className="flex flex-wrap gap-2">
              <button type="button" className="rounded border px-3 py-2 text-sm" onClick={() => void applyPolicy("apply")} disabled={!hasChanges || saving || !canApply}>apply</button>
              <button type="button" className="rounded border px-3 py-2 text-sm" onClick={() => void applyPolicy("dry-run")} disabled={!hasChanges || saving || !canOperate}>dry-run</button>
              <button type="button" className="rounded border px-3 py-2 text-sm" onClick={() => void applyPolicy("shadow")} disabled={saving || !canOperate}>shadow mode</button>
              <button type="button" className="rounded border px-3 py-2 text-sm" onClick={rollback} disabled={saving || !hasChanges || !canApply}>rollback</button>
            </div>
            {!canApply ? <p className="mt-2 text-xs text-warning">{t("RBAC: apply/rollback は admin のみ実行可能です。", "RBAC: apply/rollback requires admin role.")}</p> : null}
            {hasChanges && draftApprovalStatus !== "approved" ? <p className="mt-2 text-xs text-info">{t("apply するには先に承認が必要です。dry-run / shadow は承認前でも実行できます。", "Approval is required before apply. dry-run / shadow can be executed before approval.")}</p> : null}
          </Card>

          {/* ── TrustLog Stream ── */}
          <Card title="TrustLog Stream" titleSize="md" variant="elevated">
            <ul className="space-y-1 text-xs">
              {trustLog.length === 0 ? <li className="text-muted-foreground">{t("ポリシー読み込み後にストリームイベントが表示されます。", "Stream events will appear after loading a policy.")}</li> : trustLog.map((entry) => (
                <li key={entry.id} className={`rounded border px-2 py-1 ${entry.severity === "policy" ? "border-info/40 bg-info/5" : ""}`}>
                  <span className="font-mono">{entry.at}</span>{" "}
                  <span className={`inline-flex items-center rounded px-1 py-0.5 text-[10px] font-semibold ${entry.severity === "warning" ? "bg-warning/20 text-warning" : entry.severity === "policy" ? "bg-info/20 text-info" : "bg-muted text-muted-foreground"}`}>{entry.severity}</span>{" "}
                  {entry.message}
                </li>
              ))}
            </ul>
          </Card>

          {/* ── Change History ── */}
          <Card title="Change History" titleSize="md" variant="elevated">
            <ul className="space-y-1 text-xs">
              {history.length === 0 ? <li className="text-muted-foreground">{t("ポリシー操作後に変更履歴が表示されます。", "Change history will appear after policy operations.")}</li> : history.map((entry) => (
                <li key={entry.id} className="rounded border px-2 py-1">
                  <span className={`inline-flex items-center rounded px-1 py-0.5 text-[10px] font-semibold mr-1 ${
                    entry.action === "apply" ? "bg-success/20 text-success" :
                    entry.action === "rollback" ? "bg-warning/20 text-warning" :
                    entry.action === "approve" ? "bg-success/20 text-success" :
                    entry.action === "reject" ? "bg-danger/20 text-danger" :
                    "bg-muted text-muted-foreground"
                  }`}>{entry.action}</span>
                  <span className="text-muted-foreground">{entry.actor}</span> / {entry.summary} / <span className="font-mono">{entry.at}</span>
                </li>
              ))}
            </ul>
          </Card>
        </>
      ) : null}
    </div>
  );
}

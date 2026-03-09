"use client";

import { useCallback, useMemo, useState } from "react";
import { Card } from "@veritas/design-system";
import { veritasFetch } from "../../lib/api-client";
import { validateGovernancePolicyResponse } from "../../lib/api-validators";
import { EUAIActGovernanceDashboard } from "../../features/console/components/eu-ai-act-governance-dashboard";

type UserRole = "viewer" | "operator" | "admin";
type PolicyActionMode = "apply" | "dry-run" | "shadow";
type GovernanceMode = "standard" | "eu_ai_act";

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
  effective_at?: string;
  last_applied?: string;
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
  severity: "info" | "warning";
}

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

const MODE_EXPLANATIONS: Record<GovernanceMode, string[]> = {
  standard: [
    "通常運用: 既存しきい値とエスカレーションを使用します。",
    "FUJIルール違反時は既存フローのままレビューへ。",
  ],
  eu_ai_act: [
    "EU AI Act mode: explainability と audit retention を優先します。",
    "高リスク判定時に人間レビュー経路を強制し、監査ログ粒度を上げます。",
  ],
};

/**
 * Control-plane utility for deterministic policy diff and drift-safe operations.
 */
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

/**
 * Produces leaf-level diff entries for policy audit previews.
 */
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
    changes.push({ path: `${prefix}.${key}`.replace(/^\./, ""), old: JSON.stringify(av), next: JSON.stringify(bv) });
  }
  return changes;
}

function ToggleRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }): JSX.Element {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border px-3.5 py-2.5 text-sm">
      <span>{label}</span>
      <button
        type="button"
        role="switch"
        aria-label={label}
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={["relative inline-flex h-5 w-10 items-center rounded-full", checked ? "bg-primary" : "bg-muted"].join(" ")}
      >
        <span className={["inline-block h-4 w-4 rounded-full bg-white", checked ? "translate-x-5" : "translate-x-0.5"].join(" ")} />
      </button>
    </div>
  );
}

function DiffPreview({ before, after }: { before: GovernancePolicy | null; after: GovernancePolicy | null }): JSX.Element {
  const rows = before && after ? collectChanges("", before as Record<string, unknown>, after as Record<string, unknown>) : [];
  if (rows.length === 0) return <p className="text-xs text-muted-foreground">変更はありません。</p>;
  return (
    <div className="space-y-1">
      {rows.map((row) => (
        <div key={row.path} className="rounded-md border px-3 py-1 text-xs">
          <p className="font-semibold">{row.path}</p>
          <div className="flex gap-2">
            <span className="text-red-400 line-through">{row.old}</span>
            <span className="text-green-400">{row.next}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function GovernanceControlPage(): JSX.Element {
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

  const appendLog = useCallback((message: string, severity: "info" | "warning" = "info") => {
    setTrustLog((prev) => [{ id: crypto.randomUUID(), at: new Date().toISOString(), message, severity }, ...prev].slice(0, 12));
  }, []);

  const appendHistory = useCallback((action: string, summary: string) => {
    setHistory((prev) => [
      { id: crypto.randomUUID(), action, actor: selectedRole, at: new Date().toISOString(), summary },
      ...prev,
    ].slice(0, 20));
  }, [selectedRole]);

  const fetchPolicy = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await veritasFetch("/api/veritas/v1/governance/policy");
      if (!res.ok) {
        setError(`HTTP ${res.status}: ポリシー取得に失敗しました。`);
        return;
      }
      const validation = validateGovernancePolicyResponse(await res.json());
      if (!validation.ok) {
        setError("レスポンスの検証に失敗しました。フォーマット不整合の可能性があります。");
        return;
      }
      const normalized = {
        ...validation.data.policy,
        effective_at: validation.data.policy.updated_at,
        last_applied: validation.data.policy.updated_at,
      } as GovernancePolicy;
      setSavedPolicy(normalized);
      setDraft(structuredClone(normalized));
      appendHistory("load", `version ${normalized.version} loaded`);
      appendLog(`policy version ${normalized.version} loaded`, "info");
    } catch {
      setError("ネットワークエラー: バックエンドへ接続できません。");
    } finally {
      setLoading(false);
    }
  }, [appendHistory, appendLog]);

  const applyPolicy = useCallback(async (mode: PolicyActionMode) => {
    if (!draft) return;
    if (!window.confirm(`${mode} を実行します。変更を確定しますか？`)) return;

    setSaving(true);
    setError(null);
    setSuccess(null);

    if (mode === "dry-run") {
      appendHistory("dry-run", "no persistent write");
      appendLog("dry-run completed without apply", "info");
      setSuccess("Dry-run を完了しました。適用はされていません。");
      setSaving(false);
      return;
    }

    if (mode === "shadow") {
      appendHistory("shadow", "shadow validation stream enabled");
      appendLog("shadow mode enabled; outputs are validated only", "warning");
      setSuccess("Shadow mode を有効化しました。判定のみ実施します。");
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
        setError(`HTTP ${res.status}: ポリシー更新に失敗しました。`);
        return;
      }
      const validation = validateGovernancePolicyResponse(await res.json());
      if (!validation.ok) {
        setError("適用レスポンスの検証に失敗しました。TrustLog を確認してください。");
        return;
      }
      const nextPolicy = {
        ...validation.data.policy,
        effective_at: new Date().toISOString(),
        last_applied: new Date().toISOString(),
      } as GovernancePolicy;
      setSavedPolicy(nextPolicy);
      setDraft(structuredClone(nextPolicy));
      appendHistory("apply", `version ${nextPolicy.version} applied`);
      appendLog(`applied version ${nextPolicy.version}`, "info");
      setSuccess("ポリシーを適用しました。");
    } catch {
      setError("適用処理に失敗しました。通信・権限・整合性を確認してください。");
    } finally {
      setSaving(false);
    }
  }, [appendHistory, appendLog, draft]);

  const rollback = useCallback(() => {
    if (!savedPolicy) return;
    if (!window.confirm("現在の適用済みポリシーへロールバックしますか？")) return;
    setDraft(structuredClone(savedPolicy));
    appendHistory("rollback", `rolled back to version ${savedPolicy.version}`);
    appendLog(`rollback preview to ${savedPolicy.version}`, "warning");
    setSuccess("ドラフトを適用済みポリシーへ戻しました。");
  }, [appendHistory, appendLog, savedPolicy]);

  const riskGauge = draft ? Math.round(((draft.risk_thresholds.deny_upper + draft.auto_stop.max_risk_score) / 2) * 100) : 0;

  return (
    <div className="space-y-6">
      <Card title="Governance Control Plane" description="Rule control / versioning / diff / approval / rollback / shadow validation を統合管理します。" titleSize="lg" variant="elevated">
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
          <button type="button" onClick={() => void fetchPolicy()} className="rounded border px-3 py-2 text-sm" disabled={loading}>{loading ? "読み込み中..." : "Load policy"}</button>
          <div className="rounded border px-3 py-2 text-xs">Risk gauge: <span className="font-mono">{riskGauge}%</span></div>
        </div>
        <ul className="mt-3 list-disc pl-5 text-xs text-muted-foreground">
          {MODE_EXPLANATIONS[governanceMode].map((entry) => <li key={entry}>{entry}</li>)}
        </ul>
      </Card>

      <EUAIActGovernanceDashboard />

      {error ? <div role="alert" className="rounded border border-danger/40 px-3 py-2 text-sm text-danger">{error}</div> : null}
      {success ? <div role="status" className="rounded border border-success/40 px-3 py-2 text-sm text-success">{success}</div> : null}

      {draft ? (
        <>
          <Card title="Policy Meta" titleSize="md" variant="elevated">
            <div className="grid gap-2 text-xs md:grid-cols-4">
              <p>policy version: <span className="font-mono">{draft.version}</span></p>
              <p>effective_at: <span className="font-mono">{draft.effective_at ?? "N/A"}</span></p>
              <p>last_applied: <span className="font-mono">{draft.last_applied ?? "N/A"}</span></p>
              <p>updated_by: <span className="font-mono">{draft.updated_by}</span></p>
            </div>
          </Card>

          <Card title="FUJI rules / thresholds / escalation" titleSize="md" variant="elevated">
            <div className="grid gap-2 md:grid-cols-2">
              {(Object.keys(FUJI_LABELS) as (keyof FujiRules)[]).map((key) => (
                <ToggleRow key={key} label={FUJI_LABELS[key]} checked={draft.fuji_rules[key]} onChange={(v) => setDraft((prev) => prev ? { ...prev, fuji_rules: { ...prev.fuji_rules, [key]: v } } : prev)} />
              ))}
            </div>
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              <label className="text-xs">allow_upper<input aria-label="allow_upper" type="range" min={0} max={1} step={0.05} value={draft.risk_thresholds.allow_upper} onChange={(e) => setDraft((prev) => prev ? { ...prev, risk_thresholds: { ...prev.risk_thresholds, allow_upper: Number(e.target.value) } } : prev)} className="w-full" /></label>
              <label className="text-xs">warn_upper<input aria-label="warn_upper" type="range" min={0} max={1} step={0.05} value={draft.risk_thresholds.warn_upper} onChange={(e) => setDraft((prev) => prev ? { ...prev, risk_thresholds: { ...prev.risk_thresholds, warn_upper: Number(e.target.value) } } : prev)} className="w-full" /></label>
              <label className="text-xs">human_review_upper<input aria-label="human_review_upper" type="range" min={0} max={1} step={0.05} value={draft.risk_thresholds.human_review_upper} onChange={(e) => setDraft((prev) => prev ? { ...prev, risk_thresholds: { ...prev.risk_thresholds, human_review_upper: Number(e.target.value) } } : prev)} className="w-full" /></label>
              <label className="text-xs">deny_upper<input aria-label="deny_upper" type="range" min={0} max={1} step={0.05} value={draft.risk_thresholds.deny_upper} onChange={(e) => setDraft((prev) => prev ? { ...prev, risk_thresholds: { ...prev.risk_thresholds, deny_upper: Number(e.target.value) } } : prev)} className="w-full" /></label>
            </div>
          </Card>

          <Card title="Current vs Draft Diff" titleSize="md" variant="elevated"><DiffPreview before={savedPolicy} after={draft} /></Card>

          <Card title="Apply Flow" titleSize="md" variant="elevated">
            <div className="flex flex-wrap gap-2">
              <button type="button" className="rounded border px-3 py-2 text-sm" onClick={() => void applyPolicy("apply")} disabled={!hasChanges || saving || !canApply}>apply</button>
              <button type="button" className="rounded border px-3 py-2 text-sm" onClick={() => void applyPolicy("dry-run")} disabled={!hasChanges || saving || !canOperate}>dry-run</button>
              <button type="button" className="rounded border px-3 py-2 text-sm" onClick={() => void applyPolicy("shadow")} disabled={saving || !canOperate}>shadow mode</button>
              <button type="button" className="rounded border px-3 py-2 text-sm" onClick={rollback} disabled={saving || !hasChanges || !canApply}>rollback</button>
            </div>
            {!canApply ? <p className="mt-2 text-xs text-warning">RBAC: apply/rollback は admin のみ実行可能です。</p> : null}
          </Card>

          <Card title="TrustLog Stream" titleSize="md" variant="elevated">
            <ul className="space-y-1 text-xs">
              {trustLog.length === 0 ? <li className="text-muted-foreground">No stream events yet.</li> : trustLog.map((entry) => (
                <li key={entry.id} className="rounded border px-2 py-1">
                  <span className="font-mono">{entry.at}</span> [{entry.severity}] {entry.message}
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Change History" titleSize="md" variant="elevated">
            <ul className="space-y-1 text-xs">
              {history.length === 0 ? <li className="text-muted-foreground">No governance actions yet.</li> : history.map((entry) => (
                <li key={entry.id} className="rounded border px-2 py-1">
                  <span className="font-semibold">{entry.action}</span> / {entry.actor} / {entry.summary} / <span className="font-mono">{entry.at}</span>
                </li>
              ))}
            </ul>
          </Card>
        </>
      ) : null}
    </div>
  );
}

"use client";

import { useCallback, useMemo, useState } from "react";
import { Card } from "@veritas/design-system";
import { validateGovernancePolicyResponse } from "../../lib/api-validators";


/* ---------- types ---------- */

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
  fuji_rules: FujiRules;
  risk_thresholds: RiskThresholds;
  auto_stop: AutoStop;
  log_retention: LogRetention;
  updated_at: string;
  updated_by: string;
}

interface ValueDriftPoint {
  ema: number;
  timestamp: string;
}

interface ValueDriftMetrics {
  baseline: number;
  latest_ema: number;
  drift_percent: number;
  history: ValueDriftPoint[];
  status: "ok" | "no_data";
}

/* ---------- helpers ---------- */

const FUJI_LABELS: Record<keyof FujiRules, string> = {
  pii_check: "PII Check (個人情報検査)",
  self_harm_block: "Self-Harm Block (自傷行為ブロック)",
  illicit_block: "Illicit Block (違法行為ブロック)",
  violence_review: "Violence Review (暴力レビュー)",
  minors_review: "Minors Review (未成年保護)",
  keyword_hard_block: "Keyword Hard Block (危険ワード即拒否)",
  keyword_soft_flag: "Keyword Soft Flag (注意ワードフラグ)",
  llm_safety_head: "LLM Safety Head (AI安全ヘッド)",
};

/**
 * Structural equality check via recursive key-value comparison.
 * Handles primitives, arrays, and plain objects. Avoids JSON.stringify
 * to prevent issues with undefined values and key-ordering non-determinism.
 */
function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (typeof a !== "object" || a === null || b === null) return false;

  if (Array.isArray(a) !== Array.isArray(b)) return false;

  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    return a.every((item, i) => deepEqual(item, b[i]));
  }

  const objA = a as Record<string, unknown>;
  const objB = b as Record<string, unknown>;
  const keysA = Object.keys(objA);
  const keysB = Object.keys(objB);
  if (keysA.length !== keysB.length) return false;
  return keysA.every((key) => deepEqual(objA[key], objB[key]));
}

/* ---------- sub-components ---------- */

interface ToggleRowProps {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}

/**
 * Accessible on/off switch. Uses a native <button role="switch"> to avoid
 * conflicts between the ARIA switch role and the native checkbox role.
 */
function ToggleRow({ label, checked, onChange }: ToggleRowProps): JSX.Element {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm">
      <span>{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background ${
          checked ? "bg-primary" : "bg-border"
        }`}
      >
        <span
          className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow-sm transition-transform ${
            checked ? "translate-x-[1.125rem]" : "translate-x-0.5"
          }`}
        />
      </button>
    </div>
  );
}

interface SliderRowProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}

function SliderRow({ label, value, min, max, step, onChange }: SliderRowProps): JSX.Element {
  return (
    <label className="block space-y-1">
      <span className="flex items-center justify-between text-xs">
        <span>{label}</span>
        <span className="font-mono font-semibold">{value}</span>
      </span>
      <input
        type="range"
        aria-label={label}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-primary"
      />
    </label>
  );
}

interface NumberRowProps {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
}

function NumberRow({ label, value, min, max, onChange }: NumberRowProps): JSX.Element {
  return (
    <label className="flex items-center justify-between gap-3 text-xs">
      <span>{label}</span>
      <input
        type="number"
        aria-label={label}
        min={min}
        max={max}
        value={value}
        onChange={(e) => {
          const raw = e.target.value;
          const n = Number(raw);
          if (raw !== "" && !Number.isNaN(n)) {
            onChange(n);
          }
        }}
        className="w-24 rounded-md border border-border bg-background px-2 py-1 text-right"
      />
    </label>
  );
}

/* ---------- diff preview ---------- */

interface DiffChange {
  path: string;
  old: string;
  next: string;
}

/**
 * Recursively collects changed leaf paths between two policy objects.
 * Pure function: returns a new array rather than mutating an outer variable.
 */
function collectChanges(
  prefix: string,
  a: Record<string, unknown>,
  b: Record<string, unknown>,
): DiffChange[] {
  const changes: DiffChange[] = [];
  for (const key of new Set([...Object.keys(a), ...Object.keys(b)])) {
    const av = a[key];
    const bv = b[key];
    if (deepEqual(av, bv)) continue;
    if (
      typeof av === "object" && av !== null && !Array.isArray(av) &&
      typeof bv === "object" && bv !== null && !Array.isArray(bv)
    ) {
      changes.push(
        ...collectChanges(
          `${prefix}.${key}`,
          av as Record<string, unknown>,
          bv as Record<string, unknown>,
        ),
      );
    } else {
      changes.push({
        path: `${prefix}.${key}`,
        old: JSON.stringify(av),
        next: JSON.stringify(bv),
      });
    }
  }
  return changes;
}

interface DiffPreviewProps {
  before: GovernancePolicy | null;
  after: GovernancePolicy | null;
}

function DiffPreview({ before, after }: DiffPreviewProps): JSX.Element {
  if (!before || !after || deepEqual(before, after)) {
    return <p className="text-xs text-muted-foreground">変更はありません。</p>;
  }

  const changes = collectChanges(
    "",
    before as unknown as Record<string, unknown>,
    after as unknown as Record<string, unknown>,
  );

  if (changes.length === 0) {
    return <p className="text-xs text-muted-foreground">変更はありません。</p>;
  }

  return (
    <div className="space-y-1">
      {changes.map((c) => (
        <div key={c.path} className="rounded-md border border-border px-3 py-1 text-xs">
          <span className="font-semibold">{c.path.replace(/^\./, "")}</span>
          <div className="mt-0.5 flex gap-3">
            <span className="text-red-400 line-through" aria-label="before">{c.old}</span>
            <span className="text-green-400" aria-label="after">{c.next}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---------- main page ---------- */

export default function GovernanceControlPage(): JSX.Element {

  const [savedPolicy, setSavedPolicy] = useState<GovernancePolicy | null>(null);
  const [draft, setDraft] = useState<GovernancePolicy | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [valueDrift, setValueDrift] = useState<ValueDriftMetrics | null>(null);

  const hasChanges = useMemo(
    () => draft !== null && savedPolicy !== null && !deepEqual(savedPolicy, draft),
    [savedPolicy, draft],
  );

  /* -- fetch value drift -- */
  const fetchValueDrift = useCallback(async () => {
    try {
      const res = await fetch("/api/veritas/v1/governance/value-drift");
      if (!res.ok) {
        setValueDrift(null);
        return;
      }
      const body: unknown = await res.json();
      if (typeof body === "object" && body !== null && "value_drift" in body) {
        const payload = (body as { value_drift?: ValueDriftMetrics }).value_drift;
        if (payload) {
          setValueDrift(payload);
          return;
        }
      }
      setValueDrift(null);
    } catch {
      setValueDrift(null);
    }
  }, []);

  /* -- fetch policy -- */
  const fetchPolicy = useCallback(async () => {
    setError(null);
    setSuccess(null);
    setLoading(true);
    try {
      const res = await fetch("/api/veritas/v1/governance/policy");
      if (!res.ok) {
        setError(`HTTP ${res.status}: ポリシー取得に失敗しました。`);
        return;
      }
      const body: unknown = await res.json();
      const validation = validateGovernancePolicyResponse(body);
      if (!validation.ok) {
        const semanticIssue = validation.issues.find((issue) => issue.category === "semantic");
        if (semanticIssue) {
          setError(`レスポンス意味エラー: ${semanticIssue.path} ${semanticIssue.message}`);
        } else {
          const formatIssue = validation.issues[0];
          setError(`レスポンス形式エラー: ${formatIssue.path} ${formatIssue.message}`);
        }
        return;
      }
      setSavedPolicy(validation.data.policy);
      setDraft(structuredClone(validation.data.policy));
      void fetchValueDrift();
    } catch {
      setError("ネットワークエラー: バックエンドへ接続できません。");
    } finally {
      setLoading(false);
    }
  }, [fetchValueDrift]);

  /* -- save policy -- */
  const savePolicy = useCallback(async () => {
    if (!draft) return;
    setError(null);
    setSuccess(null);
    setSaving(true);
    try {
      const res = await fetch("/api/veritas/v1/governance/policy", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
                  },
        body: JSON.stringify(draft),
      });
      if (!res.ok) {
        setError(`HTTP ${res.status}: ポリシー更新に失敗しました。`);
        return;
      }
      const body: unknown = await res.json();
      const validation = validateGovernancePolicyResponse(body);
      if (!validation.ok) {
        const semanticIssue = validation.issues.find((issue) => issue.category === "semantic");
        if (semanticIssue) {
          setError(`レスポンス意味エラー: ${semanticIssue.path} ${semanticIssue.message}`);
        } else {
          const formatIssue = validation.issues[0];
          setError(`レスポンス形式エラー: ${formatIssue.path} ${formatIssue.message}`);
        }
        return;
      }
      setSavedPolicy(validation.data.policy);
      setDraft(structuredClone(validation.data.policy));
      setSuccess("ポリシーを更新しました。");
    } catch {
      setError("ネットワークエラー: バックエンドへ接続できません。");
    } finally {
      setSaving(false);
    }
  }, [draft]);

  /* -- updater helpers -- */
  function updateFuji<K extends keyof FujiRules>(key: K, value: FujiRules[K]): void {
    if (!draft) return;
    setDraft({ ...draft, fuji_rules: { ...draft.fuji_rules, [key]: value } });
  }

  function updateRisk<K extends keyof RiskThresholds>(key: K, value: RiskThresholds[K]): void {
    if (!draft) return;
    setDraft({ ...draft, risk_thresholds: { ...draft.risk_thresholds, [key]: value } });
  }

  function updateAutoStop<K extends keyof AutoStop>(key: K, value: AutoStop[K]): void {
    if (!draft) return;
    setDraft({ ...draft, auto_stop: { ...draft.auto_stop, [key]: value } });
  }

  function updateLogRetention<K extends keyof LogRetention>(key: K, value: LogRetention[K]): void {
    if (!draft) return;
    setDraft({ ...draft, log_retention: { ...draft.log_retention, [key]: value } });
  }

  return (
    <div className="space-y-6">
      {/* Screen-reader live region for async state announcements */}
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {loading ? "ポリシーを読み込んでいます..." : ""}
        {saving ? "ポリシーを保存しています..." : ""}
      </div>

      {/* Header */}
      <Card title="Governance Control" className="border-primary/50 bg-surface/85">
        <p className="text-sm text-muted-foreground">
          FUJIルール・リスク閾値・自動停止条件・ログ保持を統制し、ポリシーを即時反映します。
        </p>
      </Card>

      {/* Connection */}
      <Card title="Connection" className="bg-background/75">
        <div className="mt-3">
          <button
            type="button"
            className="rounded-md border border-primary/60 bg-primary/20 px-3 py-2 text-sm"
            disabled={loading}
            onClick={() => void fetchPolicy()}
          >
            {loading ? "読み込み中..." : "ポリシーを読み込む"}
          </button>
        </div>
      </Card>

      {error ? (
        <p role="alert" className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-300">
          {error}
        </p>
      ) : null}

      {success ? (
        <p role="status" className="rounded-md border border-green-500/40 bg-green-500/10 p-2 text-sm text-green-300">
          {success}
        </p>
      ) : null}

      {draft ? (
        <>
          {/* FUJI Rules */}
          <Card title="FUJI Rules" className="bg-background/75">
            <p className="mb-3 text-xs text-muted-foreground">
              各安全ルールの有効/無効を切り替えます。
            </p>
            <div className="grid gap-2 md:grid-cols-2">
              {(Object.keys(FUJI_LABELS) as (keyof FujiRules)[]).map((key) => (
                <ToggleRow
                  key={key}
                  label={FUJI_LABELS[key]}
                  checked={draft.fuji_rules[key]}
                  onChange={(v) => updateFuji(key, v)}
                />
              ))}
            </div>
          </Card>

          {/* Risk Thresholds */}
          <Card title="Risk Thresholds (リスク閾値)" className="bg-background/75">
            <p className="mb-3 text-xs text-muted-foreground">
              リスクスコアに応じたアクション境界を設定します (0.0 - 1.0)。
            </p>
            <div className="space-y-3">
              <SliderRow
                label="Allow Upper (許可上限)"
                value={draft.risk_thresholds.allow_upper}
                min={0}
                max={1}
                step={0.05}
                onChange={(v) => updateRisk("allow_upper", v)}
              />
              <SliderRow
                label="Warn Upper (警告上限)"
                value={draft.risk_thresholds.warn_upper}
                min={0}
                max={1}
                step={0.05}
                onChange={(v) => updateRisk("warn_upper", v)}
              />
              <SliderRow
                label="Human Review Upper (人間レビュー上限)"
                value={draft.risk_thresholds.human_review_upper}
                min={0}
                max={1}
                step={0.05}
                onChange={(v) => updateRisk("human_review_upper", v)}
              />
              <SliderRow
                label="Deny Upper (拒否上限)"
                value={draft.risk_thresholds.deny_upper}
                min={0}
                max={1}
                step={0.05}
                onChange={(v) => updateRisk("deny_upper", v)}
              />
            </div>
          </Card>

          {/* Auto-Stop */}
          <Card title="Auto-Stop Conditions (自動停止条件)" className="bg-background/75">
            <p className="mb-3 text-xs text-muted-foreground">
              危険な状態を検知した場合の自動停止ルールを設定します。
            </p>
            <div className="space-y-3">
              <ToggleRow
                label="自動停止を有効化"
                checked={draft.auto_stop.enabled}
                onChange={(v) => updateAutoStop("enabled", v)}
              />
              <SliderRow
                label="最大リスクスコア"
                value={draft.auto_stop.max_risk_score}
                min={0}
                max={1}
                step={0.05}
                onChange={(v) => updateAutoStop("max_risk_score", v)}
              />
              <NumberRow
                label="最大連続拒否回数"
                value={draft.auto_stop.max_consecutive_rejects}
                min={1}
                max={100}
                onChange={(v) => updateAutoStop("max_consecutive_rejects", v)}
              />
              <NumberRow
                label="毎分最大リクエスト数"
                value={draft.auto_stop.max_requests_per_minute}
                min={1}
                max={10000}
                onChange={(v) => updateAutoStop("max_requests_per_minute", v)}
              />
            </div>
          </Card>

          {/* Log Retention */}
          <Card title="Log Retention / Audit (ログ保持・監査)" className="bg-background/75">
            <p className="mb-3 text-xs text-muted-foreground">
              監査ログの保持期間と強度を設定します。
            </p>
            <div className="space-y-3">
              <NumberRow
                label="保持期間 (日数)"
                value={draft.log_retention.retention_days}
                min={1}
                max={3650}
                onChange={(v) => updateLogRetention("retention_days", v)}
              />
              <label className="flex items-center justify-between gap-3 text-xs">
                <span>監査レベル</span>
                <select
                  aria-label="監査レベル"
                  value={draft.log_retention.audit_level}
                  onChange={(e) => updateLogRetention("audit_level", e.target.value)}
                  className="rounded-md border border-border bg-background px-2 py-1"
                >
                  <option value="none">none</option>
                  <option value="summary">summary</option>
                  <option value="full">full</option>
                </select>
              </label>
              <ToggleRow
                label="ログ記録前に PII をマスク"
                checked={draft.log_retention.redact_before_log}
                onChange={(v) => updateLogRetention("redact_before_log", v)}
              />
              <NumberRow
                label="最大ログサイズ (文字数/レコード)"
                value={draft.log_retention.max_log_size}
                min={100}
                max={1000000}
                onChange={(v) => updateLogRetention("max_log_size", v)}
              />
            </div>
          </Card>

          {/* ValueCore Drift */}
          <Card title="Policy Drift (ValueCore監視)" className="bg-background/75">
            <p className="mb-3 text-xs text-muted-foreground">
              Value EMA と Telos 基準値の乖離率を表示します。
            </p>
            {valueDrift ? (
              <div className="space-y-3 text-xs">
                <div className="grid gap-2 md:grid-cols-3">
                  <div>
                    <span className="text-muted-foreground">Baseline: </span>
                    <span className="font-mono">{valueDrift.baseline.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Latest EMA: </span>
                    <span className="font-mono">{valueDrift.latest_ema.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Drift: </span>
                    <span className="font-mono">{valueDrift.drift_percent.toFixed(2)}%</span>
                  </div>
                </div>
                {valueDrift.history.length > 0 ? (
                  <div className="max-h-40 overflow-y-auto rounded-md border border-border p-2">
                    <ul className="space-y-1 font-mono">
                      {valueDrift.history.slice(-20).map((point) => (
                        <li key={`${point.timestamp}-${point.ema}`}>
                          {point.timestamp}: {point.ema.toFixed(3)}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <p className="text-muted-foreground">履歴データがありません。</p>
                )}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">ドリフト情報を取得できませんでした。</p>
            )}
          </Card>

          {/* Diff Preview */}
          <Card title="Diff Preview (変更差分)" className="bg-background/75">
            <DiffPreview before={savedPolicy} after={draft} />
          </Card>

          {/* Save */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="rounded-md border border-primary/60 bg-primary/20 px-4 py-2 text-sm font-semibold disabled:opacity-40"
              disabled={saving || !hasChanges}
              onClick={() => void savePolicy()}
            >
              {saving ? "保存中..." : "ポリシーを保存"}
            </button>
            <button
              type="button"
              className="rounded-md border border-border px-4 py-2 text-sm disabled:opacity-40"
              disabled={!hasChanges}
              onClick={() => setDraft(savedPolicy ? structuredClone(savedPolicy) : null)}
            >
              リセット
            </button>
            {hasChanges ? (
              <span className="text-xs text-yellow-400">未保存の変更があります</span>
            ) : null}
          </div>

          {/* Meta */}
          <Card title="Policy Meta" className="bg-background/75">
            <div className="grid gap-2 text-xs md:grid-cols-3">
              <div>
                <span className="text-muted-foreground">Version: </span>
                <span className="font-mono">{draft.version}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Updated At: </span>
                <span className="font-mono">{draft.updated_at || "N/A"}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Updated By: </span>
                <span className="font-mono">{draft.updated_by}</span>
              </div>
            </div>
          </Card>
        </>
      ) : (
        <Card title="Status" className="bg-background/75">
          <p className="text-sm text-muted-foreground">
            「ポリシーを読み込む」をクリックして最新設定を取得してください。
          </p>
        </Card>
      )}
    </div>
  );
}

"use client";

import { useMemo, useState } from "react";
import { Button, Card } from "@veritas/design-system";

const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_VERITAS_API_BASE_URL ?? "http://localhost:8000";
const ENV_API_KEY = process.env.NEXT_PUBLIC_VERITAS_API_KEY ?? "";

type AuditStrength = "basic" | "standard" | "strict";

interface GovernancePolicy {
  fuji_enabled: boolean;
  risk_threshold: number;
  auto_stop_conditions: string[];
  log_retention_days: number;
  audit_strength: AuditStrength;
}

interface GovernanceResponse {
  policy: GovernancePolicy;
}

interface GovernanceUpdateResponse {
  policy: GovernancePolicy;
  before: GovernancePolicy;
  diff: Record<string, { before: unknown; after: unknown }>;
}

const DEFAULT_POLICY: GovernancePolicy = {
  fuji_enabled: true,
  risk_threshold: 0.7,
  auto_stop_conditions: ["high_risk_detected"],
  log_retention_days: 90,
  audit_strength: "standard",
};

function parseConditions(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

export default function GovernanceControlPage(): JSX.Element {
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [apiKey, setApiKey] = useState(ENV_API_KEY);
  const [policy, setPolicy] = useState<GovernancePolicy>(DEFAULT_POLICY);
  const [beforePolicy, setBeforePolicy] = useState<GovernancePolicy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);

  const conditionsText = useMemo(() => policy.auto_stop_conditions.join("\n"), [policy.auto_stop_conditions]);

  const previewDiff = useMemo(() => {
    if (!beforePolicy) {
      return {} as Record<string, { before: unknown; after: unknown }>;
    }

    const diff: Record<string, { before: unknown; after: unknown }> = {};
    for (const key of Object.keys(policy) as Array<keyof GovernancePolicy>) {
      if (JSON.stringify(beforePolicy[key]) !== JSON.stringify(policy[key])) {
        diff[key] = {
          before: beforePolicy[key],
          after: policy[key],
        };
      }
    }
    return diff;
  }, [beforePolicy, policy]);

  const loadPolicy = async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase.replace(/\/$/, "")}/v1/governance/policy`, {
        headers: { "X-API-Key": apiKey.trim() },
      });
      if (!response.ok) {
        setError(`HTTP ${response.status}: policy 取得に失敗しました。`);
        return;
      }
      const payload = (await response.json()) as GovernanceResponse;
      setPolicy(payload.policy);
      setBeforePolicy(payload.policy);
    } catch {
      setError("ネットワークエラー: policy 取得に失敗しました。");
    } finally {
      setLoading(false);
    }
  };

  const savePolicy = async (): Promise<void> => {
    setSaving(true);
    setError(null);

    if (!apiKey.trim()) {
      setError("X-API-Key を入力してください。");
      setSaving(false);
      return;
    }

    try {
      const response = await fetch(`${apiBase.replace(/\/$/, "")}/v1/governance/policy`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey.trim(),
        },
        body: JSON.stringify({ policy }),
      });

      if (!response.ok) {
        setError(`HTTP ${response.status}: policy 更新に失敗しました。`);
        return;
      }

      const payload = (await response.json()) as GovernanceUpdateResponse;
      setBeforePolicy(payload.policy);
      setPolicy(payload.policy);
    } catch {
      setError("ネットワークエラー: policy 更新に失敗しました。");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card title="Governance Control" className="border-primary/50 bg-surface/85">
        <p className="text-sm text-muted-foreground">FUJIルールと監査強度を統制プレーンで一元管理します。</p>
      </Card>

      <Card title="Connection" className="bg-background/75">
        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1 text-xs">
            <span className="font-medium">API Base URL</span>
            <input
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={apiBase}
              onChange={(event) => setApiBase(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="font-medium">X-API-Key</span>
            <input
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              type="password"
              autoComplete="off"
            />
          </label>
        </div>
        <div className="mt-3">
          <Button onClick={() => void loadPolicy()} disabled={loading || !apiKey.trim()}>
            {loading ? "読み込み中..." : "ポリシーを取得"}
          </Button>
        </div>
      </Card>

      <Card title="Policy Editor" className="bg-background/75">
        <div className="space-y-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              aria-label="FUJI enabled"
              type="checkbox"
              checked={policy.fuji_enabled}
              onChange={(event) =>
                setPolicy((prev) => ({
                  ...prev,
                  fuji_enabled: event.target.checked,
                }))
              }
            />
            FUJIルールを有効化
          </label>

          <label className="block space-y-1 text-sm">
            <span>リスク閾値: {policy.risk_threshold.toFixed(2)}</span>
            <input
              aria-label="Risk threshold"
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={policy.risk_threshold}
              onChange={(event) =>
                setPolicy((prev) => ({
                  ...prev,
                  risk_threshold: Number(event.target.value),
                }))
              }
              className="w-full"
            />
          </label>

          <label className="block space-y-1 text-sm">
            <span>自動停止条件（1行1条件）</span>
            <textarea
              aria-label="Auto stop conditions"
              className="min-h-28 w-full rounded-md border border-border bg-background px-2 py-2"
              value={conditionsText}
              onChange={(event) =>
                setPolicy((prev) => ({
                  ...prev,
                  auto_stop_conditions: parseConditions(event.target.value),
                }))
              }
            />
          </label>

          <label className="block space-y-1 text-sm">
            <span>ログ保持期間（日）</span>
            <input
              aria-label="Log retention days"
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              type="number"
              min={1}
              max={3650}
              value={policy.log_retention_days}
              onChange={(event) =>
                setPolicy((prev) => ({
                  ...prev,
                  log_retention_days: Number(event.target.value),
                }))
              }
            />
          </label>

          <label className="block space-y-1 text-sm">
            <span>監査強度</span>
            <select
              aria-label="Audit strength"
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={policy.audit_strength}
              onChange={(event) =>
                setPolicy((prev) => ({
                  ...prev,
                  audit_strength: event.target.value as AuditStrength,
                }))
              }
            >
              <option value="basic">basic</option>
              <option value="standard">standard</option>
              <option value="strict">strict</option>
            </select>
          </label>

          <Button onClick={() => void savePolicy()} disabled={saving || !apiKey.trim()}>
            {saving ? "更新中..." : "ポリシーを更新"}
          </Button>
          {error ? <p className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-300">{error}</p> : null}
        </div>
      </Card>

      <Card title="差分プレビュー (before / after)" className="bg-background/75">
        {Object.keys(previewDiff).length === 0 ? (
          <p className="text-sm text-muted-foreground">差分はありません。</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {Object.entries(previewDiff).map(([key, value]) => (
              <li key={key} className="rounded-md border border-border bg-background/70 p-2">
                <p className="font-semibold">{key}</p>
                <p className="text-xs text-muted-foreground">before: {JSON.stringify(value.before)}</p>
                <p className="text-xs text-muted-foreground">after: {JSON.stringify(value.after)}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

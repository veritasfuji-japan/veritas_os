"use client";

import { useMemo, useState } from "react";
import { Card } from "@veritas/design-system";

const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_VERITAS_API_BASE_URL ?? "http://localhost:8000";
const ENV_API_KEY = process.env.NEXT_PUBLIC_VERITAS_API_KEY ?? "";

interface GovernancePolicy {
  fuji_enabled: boolean;
  risk_threshold: number;
  auto_stop_conditions: string[];
  log_retention_days: number;
  audit_intensity: "low" | "standard" | "high";
  updated_at: string;
  version: number;
}

function policyDiff(before: GovernancePolicy | null, after: GovernancePolicy | null): string {
  if (!before || !after) {
    return "before/after を読み込むと差分が表示されます。";
  }

  const rows: string[] = [];
  const keys: (keyof GovernancePolicy)[] = [
    "fuji_enabled",
    "risk_threshold",
    "auto_stop_conditions",
    "log_retention_days",
    "audit_intensity",
    "version",
  ];

  for (const key of keys) {
    const left = JSON.stringify(before[key]);
    const right = JSON.stringify(after[key]);
    if (left !== right) {
      rows.push(`${key}: ${left} -> ${right}`);
    }
  }

  return rows.length > 0 ? rows.join("\n") : "変更はありません。";
}

export default function GovernanceControlPage(): JSX.Element {
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [apiKey, setApiKey] = useState(ENV_API_KEY);
  const [policy, setPolicy] = useState<GovernancePolicy | null>(null);
  const [beforePolicy, setBeforePolicy] = useState<GovernancePolicy | null>(null);
  const [riskThreshold, setRiskThreshold] = useState("0.60");
  const [fujiEnabled, setFujiEnabled] = useState(true);
  const [autoStop, setAutoStop] = useState("policy_violation_detected,risk_threshold_exceeded");
  const [retentionDays, setRetentionDays] = useState("90");
  const [auditIntensity, setAuditIntensity] = useState<"low" | "standard" | "high">("standard");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const diffPreview = useMemo(() => policyDiff(beforePolicy, policy), [beforePolicy, policy]);

  const loadPolicy = async (): Promise<void> => {
    setLoading(true);
    setError(null);
    setStatus(null);

    try {
      const response = await fetch(`${apiBase.replace(/\/$/, "")}/v1/governance/policy`, {
        headers: {
          "X-API-Key": apiKey.trim(),
        },
      });

      if (!response.ok) {
        setError(`HTTP ${response.status}: policy取得に失敗しました。`);
        return;
      }

      const payload = (await response.json()) as GovernancePolicy;
      setBeforePolicy(payload);
      setPolicy(payload);
      setFujiEnabled(payload.fuji_enabled);
      setRiskThreshold(String(payload.risk_threshold.toFixed(2)));
      setAutoStop(payload.auto_stop_conditions.join(","));
      setRetentionDays(String(payload.log_retention_days));
      setAuditIntensity(payload.audit_intensity);
      setStatus("policy を読み込みました。");
    } catch {
      setError("ネットワークエラー: policy取得に失敗しました。");
    } finally {
      setLoading(false);
    }
  };

  const updatePolicy = async (): Promise<void> => {
    setLoading(true);
    setError(null);
    setStatus(null);

    const payload = {
      fuji_enabled: fujiEnabled,
      risk_threshold: Number(riskThreshold),
      auto_stop_conditions: autoStop
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      log_retention_days: Number(retentionDays),
      audit_intensity: auditIntensity,
    };

    try {
      const response = await fetch(`${apiBase.replace(/\/$/, "")}/v1/governance/policy`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey.trim(),
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const text = await response.text();
        setError(`HTTP ${response.status}: ${text || "policy更新に失敗しました。"}`);
        return;
      }

      const updated = (await response.json()) as GovernancePolicy;
      setPolicy(updated);
      setStatus("policy を更新しました。");
    } catch {
      setError("ネットワークエラー: policy更新に失敗しました。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card title="Governance Control Plane" className="border-primary/50 bg-surface/85">
        <p className="text-sm text-muted-foreground">
          FUJIルール、リスク閾値、自動停止条件、監査強度を /v1/governance/policy に同期します。
        </p>
      </Card>

      <Card title="Connection" className="bg-background/75">
        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1 text-xs">
            <span className="font-medium">API Base URL</span>
            <input
              aria-label="API Base URL"
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={apiBase}
              onChange={(event) => setApiBase(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="font-medium">X-API-Key</span>
            <input
              aria-label="X-API-Key"
              data-testid="governance-api-key-input"
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              type="password"
              autoComplete="off"
            />
          </label>
        </div>
        <button
          type="button"
          className="mt-3 rounded-md border border-primary/60 bg-primary/20 px-3 py-2 text-sm"
          disabled={loading || !apiKey.trim()}
          onClick={() => void loadPolicy()}
        >
          現在のpolicyを読み込み
        </button>
      </Card>

      <Card title="Policy Editor" className="bg-background/75">
        <div className="space-y-3 text-sm">
          <label className="flex items-center gap-2">
            <input aria-label="FUJI rule enabled" type="checkbox" checked={fujiEnabled} onChange={(event) => setFujiEnabled(event.target.checked)} />
            <span>FUJI rule enabled</span>
          </label>

          <label className="block space-y-1">
            <span className="font-medium">リスク閾値 (0.0 - 1.0)</span>
            <input
              aria-label="リスク閾値"
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={riskThreshold}
              onChange={(event) => setRiskThreshold(event.target.value)}
            />
          </label>

          <label className="block space-y-1">
            <span className="font-medium">自動停止条件（comma区切り）</span>
            <input
              aria-label="自動停止条件"
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={autoStop}
              onChange={(event) => setAutoStop(event.target.value)}
            />
          </label>

          <label className="block space-y-1">
            <span className="font-medium">ログ保持期間（日）</span>
            <input
              aria-label="ログ保持期間"
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={retentionDays}
              onChange={(event) => setRetentionDays(event.target.value)}
            />
          </label>

          <label className="block space-y-1">
            <span className="font-medium">監査強度</span>
            <select
              aria-label="監査強度"
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={auditIntensity}
              onChange={(event) => setAuditIntensity(event.target.value as "low" | "standard" | "high")}
            >
              <option value="low">low</option>
              <option value="standard">standard</option>
              <option value="high">high</option>
            </select>
          </label>

          <button
            type="button"
            className="rounded-md border border-primary/60 bg-primary/20 px-3 py-2 text-sm"
            disabled={loading || !apiKey.trim()}
            onClick={() => void updatePolicy()}
          >
            policy更新
          </button>
        </div>
      </Card>

      <Card title="差分プレビュー" className="bg-background/75">
        <pre className="overflow-x-auto rounded-md border border-border bg-background/70 p-3 text-xs">{diffPreview}</pre>
      </Card>

      {status ? <p className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-2 text-sm">{status}</p> : null}
      {error ? <p className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-300">{error}</p> : null}
    </div>
  );
}

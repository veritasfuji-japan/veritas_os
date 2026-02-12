"use client";

import { useMemo, useState } from "react";
import { Button, Card } from "@veritas/design-system";

const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_VERITAS_API_BASE_URL ?? "http://localhost:8000";
const ENV_API_KEY = process.env.NEXT_PUBLIC_VERITAS_API_KEY ?? "";

interface GovernancePolicy {
  fuji_enabled: boolean;
  risk_threshold: number;
  auto_stop_conditions: string[];
  log_retention_days: number;
  audit_intensity: "light" | "standard" | "strict";
}

const EMPTY_POLICY: GovernancePolicy = {
  fuji_enabled: true,
  risk_threshold: 0.55,
  auto_stop_conditions: ["fuji_rejected", "security_violation_detected"],
  log_retention_days: 90,
  audit_intensity: "standard",
};

function toDiff(before: GovernancePolicy | null, after: GovernancePolicy): string {
  if (!before) {
    return "before: (none)\nafter:\n" + JSON.stringify(after, null, 2);
  }

  return JSON.stringify({ before, after }, null, 2);
}

export default function GovernanceControlPage(): JSX.Element {
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [apiKey, setApiKey] = useState(ENV_API_KEY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [policy, setPolicy] = useState<GovernancePolicy>(EMPTY_POLICY);
  const [beforePolicy, setBeforePolicy] = useState<GovernancePolicy | null>(null);
  const [autoStopText, setAutoStopText] = useState(EMPTY_POLICY.auto_stop_conditions.join("\n"));

  const diffPreview = useMemo(() => toDiff(beforePolicy, policy), [beforePolicy, policy]);

  const loadPolicy = async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase.replace(/\/$/, "")}/v1/governance/policy`, {
        headers: { "X-API-Key": apiKey.trim() },
      });

      if (!response.ok) {
        setError(`HTTP ${response.status}: policy取得に失敗しました。`);
        return;
      }

      const payload = (await response.json()) as GovernancePolicy;
      setBeforePolicy(payload);
      setPolicy(payload);
      setAutoStopText((payload.auto_stop_conditions ?? []).join("\n"));
    } catch {
      setError("ネットワークエラー: policy取得に失敗しました。");
    } finally {
      setLoading(false);
    }
  };

  const updatePolicy = async (): Promise<void> => {
    setLoading(true);
    setError(null);

    const nextPolicy: GovernancePolicy = {
      ...policy,
      auto_stop_conditions: autoStopText
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.length > 0),
    };

    try {
      const response = await fetch(`${apiBase.replace(/\/$/, "")}/v1/governance/policy`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey.trim(),
        },
        body: JSON.stringify(nextPolicy),
      });

      if (!response.ok) {
        setError(`HTTP ${response.status}: policy更新に失敗しました。`);
        return;
      }

      const payload = (await response.json()) as GovernancePolicy;
      setBeforePolicy(policy);
      setPolicy(payload);
      setAutoStopText(payload.auto_stop_conditions.join("\n"));
    } catch {
      setError("ネットワークエラー: policy更新に失敗しました。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card title="Governance Control" className="border-primary/50 bg-surface/85">
        <p className="text-sm text-muted-foreground">
          FUJI制御・リスク閾値・停止条件・監査強度を統制プレーンで一元管理します。
        </p>
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
            />
          </label>
        </div>
        <div className="mt-3">
          <Button onClick={() => void loadPolicy()} disabled={loading || !apiKey.trim()}>
            {loading ? "読込中..." : "現在のpolicyを取得"}
          </Button>
        </div>
      </Card>

      <Card title="Policy Editor" className="bg-background/75">
        <div className="space-y-3 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={policy.fuji_enabled}
              onChange={(event) => setPolicy((prev) => ({ ...prev, fuji_enabled: event.target.checked }))}
            />
            FUJIルール有効化
          </label>

          <label className="space-y-1 text-xs">
            <span className="font-medium">リスク閾値 (0.0-1.0)</span>
            <input
              type="number"
              min={0}
              max={1}
              step={0.01}
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={policy.risk_threshold}
              onChange={(event) => setPolicy((prev) => ({ ...prev, risk_threshold: Number(event.target.value) }))}
            />
          </label>

          <label className="space-y-1 text-xs">
            <span className="font-medium">自動停止条件（1行1条件）</span>
            <textarea
              className="min-h-24 w-full rounded-md border border-border bg-background px-2 py-2"
              value={autoStopText}
              onChange={(event) => setAutoStopText(event.target.value)}
            />
          </label>

          <label className="space-y-1 text-xs">
            <span className="font-medium">ログ保持期間（日）</span>
            <input
              type="number"
              min={1}
              max={3650}
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={policy.log_retention_days}
              onChange={(event) => setPolicy((prev) => ({ ...prev, log_retention_days: Number(event.target.value) }))}
            />
          </label>

          <label className="space-y-1 text-xs">
            <span className="font-medium">監査強度</span>
            <select
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={policy.audit_intensity}
              onChange={(event) =>
                setPolicy((prev) => ({ ...prev, audit_intensity: event.target.value as GovernancePolicy["audit_intensity"] }))
              }
            >
              <option value="light">light</option>
              <option value="standard">standard</option>
              <option value="strict">strict</option>
            </select>
          </label>

          <Button onClick={() => void updatePolicy()} disabled={loading || !apiKey.trim()}>
            {loading ? "更新中..." : "policyを更新"}
          </Button>
        </div>
      </Card>

      {error ? <p className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-300">{error}</p> : null}

      <Card title="差分プレビュー (before / after)" className="bg-background/75">
        <pre className="overflow-x-auto rounded-md border border-border bg-background/70 p-3 text-xs">{diffPreview}</pre>
      </Card>
    </div>
  );
}

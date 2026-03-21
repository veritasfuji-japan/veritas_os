"use client";

import { Card } from "@veritas/design-system";
import { useI18n } from "../../components/i18n-provider";
import { EmptyState, ErrorBanner, SuccessBanner } from "../../components/ui";
import { EUAIActGovernanceDashboard } from "../../features/console/components/eu-ai-act-governance-dashboard";
import type { GovernanceMode, UserRole } from "./governance-types";
import { MODE_EXPLANATIONS, ROLE_CAPABILITIES } from "./constants";
import { useGovernanceState } from "./hooks/useGovernanceState";
import { PolicyMetaPanel } from "./components/PolicyMetaPanel";
import { FujiRulesEditor } from "./components/FujiRulesEditor";
import { DiffPreview } from "./components/DiffPreview";
import { RiskImpactGauge } from "./components/RiskImpactGauge";
import { ApprovalWorkflow } from "./components/ApprovalWorkflow";
import { ApplyFlow } from "./components/ApplyFlow";
import { TrustLogStream } from "./components/TrustLogStream";
import { ChangeHistory } from "./components/ChangeHistory";

/* ------------------------------------------------------------------ */
/*  Main page component                                                */
/* ------------------------------------------------------------------ */

export default function GovernanceControlPage(): JSX.Element {
  const { t } = useI18n();
  const state = useGovernanceState();

  return (
    <div className="space-y-6">
      {/* ── Header: Governance Control Plane ── */}
      <Card
        title="Governance Control"
        description={t(
          "Rule control / versioning / diff / approval / rollback / shadow validation を統合管理します。",
          "Integrated management of rule control, versioning, diff, approval, rollback, and shadow validation.",
        )}
        titleSize="lg"
        variant="glass"
        accent="primary"
        className="border-primary/15"
      >
        <div className="grid gap-3 md:grid-cols-4">
          <label className="text-xs">
            Role
            <select
              aria-label="role"
              value={state.selectedRole}
              onChange={(e) => state.setSelectedRole(e.target.value as UserRole)}
              className="mt-1 w-full rounded border px-2 py-1"
            >
              <option value="viewer">viewer</option>
              <option value="operator">operator</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <label className="text-xs">
            Mode
            <select
              aria-label="mode"
              value={state.governanceMode}
              onChange={(e) => state.setGovernanceMode(e.target.value as GovernanceMode)}
              className="mt-1 w-full rounded border px-2 py-1"
            >
              <option value="standard">Standard</option>
              <option value="eu_ai_act">EU AI Act</option>
            </select>
          </label>
          <button
            type="button"
            onClick={() => void state.fetchPolicy()}
            className="rounded border px-3 py-2 text-sm"
            disabled={state.loading}
          >
            {state.loading ? t("読み込み中...", "Loading...") : t("ポリシーを読み込む", "Load policy")}
          </button>
          <div className="rounded border px-3 py-2 text-xs">
            Risk gauge: <span className="font-mono">{state.riskGauge}%</span>
          </div>
        </div>

        {/* ── Role capability matrix ── */}
        <div className="mt-3 rounded-lg border bg-surface/50 px-3 py-2">
          <p className="text-xs font-semibold mb-1">{ROLE_CAPABILITIES[state.selectedRole].label}</p>
          <div className="flex flex-wrap gap-1.5">
            {ROLE_CAPABILITIES[state.selectedRole].permissions.map((perm) => (
              <span key={perm} className="inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground">{perm}</span>
            ))}
          </div>
        </div>

        {/* ── Mode explanation ── */}
        <div className="mt-3 rounded-lg border bg-surface/50 px-3 py-2">
          <p className="text-xs font-semibold mb-1">{MODE_EXPLANATIONS[state.governanceMode].summary}</p>
          <ul className="list-disc pl-5 text-xs text-muted-foreground">
            {MODE_EXPLANATIONS[state.governanceMode].details.map((entry) => <li key={entry}>{entry}</li>)}
          </ul>
          <div className="mt-2 grid gap-1 md:grid-cols-2">
            {MODE_EXPLANATIONS[state.governanceMode].affects.map((effect) => (
              <span key={effect} className="rounded border px-2 py-0.5 text-[10px] font-mono text-muted-foreground">{effect}</span>
            ))}
          </div>
        </div>
      </Card>

      <EUAIActGovernanceDashboard />

      {state.error ? (
        <ErrorBanner
          message={state.error}
          onRetry={() => void state.fetchPolicy()}
          retryLabel={t("再試行", "Retry")}
        />
      ) : null}
      {state.success ? <SuccessBanner message={state.success} /> : null}

      {/* ── Empty state when no policy is loaded ── */}
      {!state.draft ? (
        <Card title="Policy Status" titleSize="md" variant="elevated">
          <EmptyState
            title={t("ポリシー未読み込み", "No policy loaded")}
            description={t(
              "「ポリシーを読み込む」ボタンでバックエンドから現在の統制ポリシーを取得してください。",
              "Click \"Load policy\" to fetch the current governance policy from the backend.",
            )}
            icon={
              <svg className="h-8 w-8 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z" />
              </svg>
            }
          />
        </Card>
      ) : null}

      {state.draft ? (
        <>
          <PolicyMetaPanel
            savedPolicy={state.savedPolicy}
            draft={state.draft}
            draftApprovalStatus={state.draftApprovalStatus}
            hasChanges={state.hasChanges}
            changeCount={state.changeCount}
          />

          <FujiRulesEditor
            draft={state.draft}
            isViewer={state.selectedRole === "viewer"}
            onUpdate={state.updateDraft}
          />

          <Card title="Current vs Draft Diff" titleSize="md" variant="elevated">
            <DiffPreview before={state.savedPolicy} after={state.draft} />
          </Card>

          <Card title="Risk Impact Analysis" titleSize="md" variant="elevated" accent={state.riskDrift > 5 ? "warning" : state.riskDrift < -5 ? "success" : undefined}>
            <RiskImpactGauge current={state.currentRisk} pending={state.pendingRisk} drift={state.riskDrift} />
          </Card>

          {state.hasChanges ? (
            <ApprovalWorkflow
              draftApprovalStatus={state.draftApprovalStatus}
              changeCount={state.changeCount}
              canApprove={state.canApprove}
              onApprove={state.approveChanges}
              onReject={state.rejectChanges}
            />
          ) : null}

          <ApplyFlow
            hasChanges={state.hasChanges}
            saving={state.saving}
            canApply={state.canApply}
            canOperate={state.canOperate}
            draftApprovalStatus={state.draftApprovalStatus}
            onApply={(mode) => void state.applyPolicy(mode)}
            onRollback={state.rollback}
          />

          <TrustLogStream entries={state.trustLog} />
          <ChangeHistory entries={state.history} />
        </>
      ) : null}
    </div>
  );
}

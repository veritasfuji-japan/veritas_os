"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { useI18n } from "../../../components/i18n-provider";
import { veritasFetch } from "../../../lib/api-client";
import { validateGovernancePolicyResponse } from "../../../lib/api-validators";
import type {
  ApprovalStatus,
  GovernancePolicyUI,
  GovernanceMode,
  HistoryEntry,
  PolicyActionMode,
  TrustLogEntry,
  UserRole,
} from "../governance-types";
import { bumpDraftVersion, collectChanges, deepEqual, isRecordObject, normalizeGovernancePolicyWatFields } from "../helpers";

type PendingConfirm = { description: string; onConfirm: () => void };

export function useGovernanceState() {
  const { t } = useI18n();
  const [savedPolicy, setSavedPolicy] = useState<GovernancePolicyUI | null>(null);
  const [draft, setDraft] = useState<GovernancePolicyUI | null>(null);
  const [selectedRole, setSelectedRole] = useState<UserRole>("admin");
  const [governanceMode, setGovernanceMode] = useState<GovernanceMode>("standard");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [trustLog, setTrustLog] = useState<TrustLogEntry[]>([]);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null);

  const dismissConfirm = useCallback(() => setPendingConfirm(null), []);
  const requestConfirm = useCallback((description: string, onConfirm: () => void) => {
    setPendingConfirm({ description, onConfirm });
  }, []);
  const fetchAbortRef = useRef<AbortController | null>(null);

  const hasChanges = useMemo(() => savedPolicy !== null && draft !== null && !deepEqual(savedPolicy, draft), [savedPolicy, draft]);
  const canApply = selectedRole === "admin";
  const canOperate = selectedRole === "admin" || selectedRole === "operator";
  const canApprove = selectedRole === "admin";

  const changeCount = useMemo(() => {
    if (!savedPolicy || !draft || !isRecordObject(savedPolicy) || !isRecordObject(draft)) return 0;
    return collectChanges("", savedPolicy, draft).length;
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

  const updateDraft = useCallback((updater: (prev: GovernancePolicyUI) => GovernancePolicyUI) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const next = updater(prev);
      return { ...next, approval_status: "pending" as ApprovalStatus };
    });
  }, []);

  const fetchPolicy = useCallback(async () => {
    fetchAbortRef.current?.abort();
    const controller = new AbortController();
    fetchAbortRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const res = await veritasFetch("/api/veritas/v1/governance/policy", {
        signal: controller.signal,
      });
      if (!res.ok) {
        setError(t(`HTTP ${res.status}: ポリシー取得に失敗しました。`, `HTTP ${res.status}: Failed to fetch policy.`));
        return;
      }
      const validation = validateGovernancePolicyResponse(await res.json());
      if (!validation.ok) {
        setError(t("レスポンスの検証に失敗しました。フォーマット不整合の可能性があります。", "Response validation failed. Possible format mismatch."));
        return;
      }
      const normalized = normalizeGovernancePolicyWatFields({
        ...validation.data.policy,
        effective_at: validation.data.policy.updated_at,
        last_applied: validation.data.policy.updated_at,
        approval_status: "approved" as ApprovalStatus,
        draft_version: bumpDraftVersion(validation.data.policy.version),
      } as GovernancePolicyUI);
      setSavedPolicy(normalized);
      setDraft(structuredClone(normalized));
      appendHistory("load", `version ${normalized.version} loaded`);
      appendLog(`policy version ${normalized.version} loaded`, "policy");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.error("fetchPolicy failed:", err);
      setError(t("ネットワークエラー: バックエンドへ接続できません。", "Network error: cannot connect to backend."));
    } finally {
      if (fetchAbortRef.current === controller) {
        setLoading(false);
      }
    }
  }, [appendHistory, appendLog, t]);

  const applyPolicy = useCallback((mode: PolicyActionMode) => {
    if (!draft) return;
    requestConfirm(
      t(`${mode} を実行します。変更を確定しますか？`, `Execute ${mode}. Confirm changes?`),
      () => {
        void (async () => {
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
            const nextPolicy = normalizeGovernancePolicyWatFields({
              ...validation.data.policy,
              effective_at: new Date().toISOString(),
              last_applied: new Date().toISOString(),
              approval_status: "approved" as ApprovalStatus,
              draft_version: bumpDraftVersion(validation.data.policy.version),
            } as GovernancePolicyUI);
            setSavedPolicy(nextPolicy);
            setDraft(structuredClone(nextPolicy));
            appendHistory("apply", `version ${nextPolicy.version} applied`);
            appendLog(`applied version ${nextPolicy.version}`, "policy");
            setSuccess(t("ポリシーを適用しました。", "Policy applied successfully."));
          } catch (err) {
            console.error("applyPolicy failed:", err);
            setError(t("適用処理に失敗しました。通信・権限・整合性を確認してください。", "Apply failed. Check connectivity, permissions, and consistency."));
          } finally {
            setSaving(false);
          }
        })();
      },
    );
  }, [appendHistory, appendLog, draft, requestConfirm, t]);

  const rollback = useCallback(() => {
    if (!savedPolicy) return;
    requestConfirm(
      t("現在の適用済みポリシーへロールバックしますか？", "Rollback to the currently applied policy?"),
      () => {
        setDraft(structuredClone(savedPolicy));
        appendHistory("rollback", `rolled back to version ${savedPolicy.version}`);
        appendLog(`rollback preview to ${savedPolicy.version}`, "warning");
        setSuccess(t("ドラフトを適用済みポリシーへ戻しました。", "Draft reverted to the applied policy."));
      },
    );
  }, [appendHistory, appendLog, requestConfirm, savedPolicy, t]);

  const approveChanges = useCallback(() => {
    if (!draft || !hasChanges) return;
    requestConfirm(
      t("ドラフト変更を承認しますか？", "Approve draft changes?"),
      () => {
        setDraft((prev) => prev ? { ...prev, approval_status: "approved" } : prev);
        appendHistory("approve", `draft changes approved by ${selectedRole}`);
        appendLog(`draft approved by ${selectedRole}`, "policy");
        setSuccess(t("ドラフトを承認しました。apply で本番適用できます。", "Draft approved. Apply to push to production."));
      },
    );
  }, [appendHistory, appendLog, draft, hasChanges, requestConfirm, selectedRole, t]);

  const rejectChanges = useCallback(() => {
    if (!draft || !hasChanges) return;
    requestConfirm(
      t("ドラフト変更を却下しますか？", "Reject draft changes?"),
      () => {
        setDraft((prev) => prev ? { ...prev, approval_status: "rejected" } : prev);
        appendHistory("reject", `draft changes rejected by ${selectedRole}`);
        appendLog(`draft rejected by ${selectedRole}`, "warning");
        setSuccess(t("ドラフトを却下しました。", "Draft rejected."));
      },
    );
  }, [appendHistory, appendLog, draft, hasChanges, requestConfirm, selectedRole, t]);

  const currentRisk = savedPolicy ? Math.round(((savedPolicy.risk_thresholds.deny_upper + savedPolicy.auto_stop.max_risk_score) / 2) * 100) : 0;
  const pendingRisk = draft ? Math.round(((draft.risk_thresholds.deny_upper + draft.auto_stop.max_risk_score) / 2) * 100) : 0;
  const riskGauge = draft ? pendingRisk : currentRisk;
  const riskDrift = pendingRisk - currentRisk;

  const draftApprovalStatus: ApprovalStatus = useMemo(() => {
    if (!draft) return "draft";
    if (!hasChanges) return draft.approval_status;
    return "pending";
  }, [draft, hasChanges]);

  return {
    savedPolicy,
    draft,
    selectedRole,
    setSelectedRole,
    governanceMode,
    setGovernanceMode,
    loading,
    saving,
    error,
    success,
    history,
    trustLog,
    hasChanges,
    canApply,
    canOperate,
    canApprove,
    changeCount,
    updateDraft,
    fetchPolicy,
    applyPolicy,
    rollback,
    approveChanges,
    rejectChanges,
    currentRisk,
    pendingRisk,
    riskGauge,
    riskDrift,
    draftApprovalStatus,
    pendingConfirm,
    dismissConfirm,
  };
}

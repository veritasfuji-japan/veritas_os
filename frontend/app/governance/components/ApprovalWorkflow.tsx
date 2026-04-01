"use client";

import { Card } from "@veritas/design-system";
import { useI18n } from "../../../components/i18n-provider";
import { StatusBadge } from "../../../components/ui";
import type { ApprovalStatus } from "../governance-types";
import { APPROVAL_STATUS_ACCENT } from "../constants";

interface ApprovalWorkflowProps {
  draftApprovalStatus: ApprovalStatus;
  changeCount: number;
  canApprove: boolean;
  ticketId: string;
  approverIdentityBinding: boolean;
  onApprove: () => void;
  onReject: () => void;
}

export function ApprovalWorkflow({
  draftApprovalStatus,
  changeCount,
  canApprove,
  ticketId,
  approverIdentityBinding,
  onApprove,
  onReject,
}: ApprovalWorkflowProps): JSX.Element {
  const { t, tk } = useI18n();
  const approvalBlocked = !canApprove || draftApprovalStatus === "rejected";

  return (
    <Card title="Approval Workflow" titleSize="md" variant="elevated" accent="warning">
      <div className="flex items-center gap-3 mb-3">
        <StatusBadge label={draftApprovalStatus} variant={APPROVAL_STATUS_ACCENT[draftApprovalStatus]} />
        <span className="text-xs text-muted-foreground">{t(`${changeCount} 件の変更が承認待ちです`, `${changeCount} change(s) awaiting approval`)}</span>
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="rounded border border-success/60 bg-success/10 px-3 py-2 text-sm text-success" onClick={onApprove} disabled={!canApprove || draftApprovalStatus === "approved"}>{tk("approve")}</button>
        <button type="button" className="rounded border border-danger/60 bg-danger/10 px-3 py-2 text-sm text-danger" onClick={onReject} disabled={!canApprove || draftApprovalStatus === "rejected"}>{tk("reject")}</button>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        ticket: <span className="font-mono">{ticketId || tk("ticketUnlinked")}</span> / {tk("identityBinding")}: {approverIdentityBinding ? tk("enabled") : tk("disabled")}
      </p>
      {approvalBlocked ? (
        <p className="mt-2 rounded border border-warning/50 bg-warning/10 px-2 py-1 text-xs text-warning">
          {t(
            "承認がブロックされています。危険な変更を safe と表示しないため、未承認のまま適用しないでください。",
            "Approval is blocked. To avoid showing risky changes as safe, do not apply this draft while unapproved.",
          )}
        </p>
      ) : null}
      {!canApprove ? <p className="mt-2 text-xs text-warning">{t("RBAC: approve/reject は admin のみ実行可能です。", "RBAC: approve/reject requires admin role.")}</p> : null}
    </Card>
  );
}

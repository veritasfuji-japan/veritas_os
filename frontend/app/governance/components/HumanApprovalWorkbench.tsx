"use client";

import { Card } from "@veritas/design-system";
import { useI18n } from "../../../components/i18n-provider";
import type { HumanApprovalRecord } from "../governance-types";

interface HumanApprovalWorkbenchProps {
  approvals: HumanApprovalRecord[];
  approvalStatus: "approved" | "pending" | "rejected" | "draft";
  validationError: string | null;
  onUpdateApproval: (index: number, patch: Partial<HumanApprovalRecord>) => void;
}

export function HumanApprovalWorkbench({
  approvals,
  approvalStatus,
  validationError,
  onUpdateApproval,
}: HumanApprovalWorkbenchProps): JSX.Element {
  const { t } = useI18n();

  return (
    <Card title="Human Approval Workbench" titleSize="md" variant="elevated" accent="warning">
      <p className="mb-3 text-xs text-muted-foreground">
        {t(
          "Governance Policy の適用前に、2名の外部レビュアー承認情報を入力してください。",
          "Before applying governance policy changes, input approval records from two human reviewers.",
        )}
      </p>
      <p className="mb-3 text-xs font-semibold">
        Overall approval status: <span className="uppercase">{approvalStatus}</span>
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        {approvals.slice(0, 2).map((approval, index) => (
          <div key={`approval-${index}`} className="rounded border p-3">
            <p className="mb-2 text-xs font-semibold">Reviewer {index + 1}</p>
            <label className="text-xs">
              Reviewer
              <input
                className="mt-1 w-full rounded border px-2 py-1"
                value={approval.reviewer}
                onChange={(event) => onUpdateApproval(index, { reviewer: event.target.value })}
              />
            </label>
            <label className="mt-2 block text-xs">
              Signature
              <input
                className="mt-1 w-full rounded border px-2 py-1"
                value={approval.signature}
                onChange={(event) => onUpdateApproval(index, { signature: event.target.value })}
              />
            </label>
            <label className="mt-2 block text-xs">
              Optional reason / note
              <textarea
                className="mt-1 w-full rounded border px-2 py-1"
                rows={2}
                value={approval.reason ?? ""}
                onChange={(event) => onUpdateApproval(index, { reason: event.target.value })}
              />
            </label>
            <p className="mt-2 text-[11px] text-muted-foreground">status: {approval.decision}</p>
          </div>
        ))}
      </div>
      {validationError ? <p className="mt-3 rounded border border-danger/40 bg-danger/10 px-2 py-1 text-xs text-danger">{validationError}</p> : null}
    </Card>
  );
}

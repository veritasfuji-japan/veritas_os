"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

const ROLES = ["viewer", "operator", "admin"] as const;
type Role = (typeof ROLES)[number];
const REQUEST_ID_PATTERN = /^req-[a-zA-Z0-9][a-zA-Z0-9._-]*$/;

/**
 * Global traceability rail for cross-screen jump by request_id / decision_id.
 *
 * NOTE: This is a UI-layer role gate for safer operator workflows.
 * Actual authorization remains enforced by backend BFF policies.
 */
export function TraceabilityRail(): JSX.Element {
  const [requestId, setRequestId] = useState("req-");
  const [decisionId, setDecisionId] = useState("dec-");
  const [role, setRole] = useState<Role>("operator");
  const [redaction, setRedaction] = useState(true);

  const exportRisk = useMemo(() => {
    if (role === "viewer" && !redaction) {
      return "high";
    }
    if (role === "admin" && !redaction) {
      return "warning";
    }
    return "safe";
  }, [redaction, role]);
  const isRequestIdValid = useMemo(
    () => REQUEST_ID_PATTERN.test(requestId.trim()),
    [requestId],
  );
  const trustLogHref = isRequestIdValid
    ? `/audit?request_id=${encodeURIComponent(requestId.trim())}`
    : "#";

  return (
    <section className="mt-3 grid gap-3 rounded-lg border border-border/60 bg-background/60 p-3 md:grid-cols-4">
      <label className="space-y-1 text-xs text-muted-foreground">
        request_id
        <input
          value={requestId}
          onChange={(event) => setRequestId(event.target.value)}
          aria-invalid={!isRequestIdValid}
          className="w-full rounded-md border border-border bg-background px-2 py-1 font-mono text-xs text-foreground"
        />
        {!isRequestIdValid ? (
          <p className="text-2xs text-danger">
            request_id は req- で始まり、英数字または . _ - を含めてください。
          </p>
        ) : null}
      </label>
      <label className="space-y-1 text-xs text-muted-foreground">
        decision_id
        <input
          value={decisionId}
          onChange={(event) => setDecisionId(event.target.value)}
          className="w-full rounded-md border border-border bg-background px-2 py-1 font-mono text-xs text-foreground"
        />
      </label>
      <label className="space-y-1 text-xs text-muted-foreground">
        role gate
        <select
          value={role}
          onChange={(event) => setRole(event.target.value as Role)}
          className="w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground"
        >
          {ROLES.map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
      </label>
      <div className="space-y-1 text-xs text-muted-foreground">
        export safety
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setRedaction((value) => !value)}
            className="rounded-md border border-border bg-background px-2 py-1"
          >
            redaction {redaction ? "on" : "off"}
          </button>
          <span className={exportRisk === "high" ? "text-danger" : exportRisk === "warning" ? "text-warning" : "text-success"}>
            {exportRisk}
          </span>
        </div>
        <div className="flex flex-wrap gap-2 pt-1">
          <Link
            className="rounded border border-border px-2 py-1 aria-disabled:pointer-events-none aria-disabled:opacity-50"
            href={trustLogHref}
            aria-disabled={!isRequestIdValid}
            onClick={(event) => {
              if (!isRequestIdValid) {
                event.preventDefault();
              }
            }}
          >
            TrustLog
          </Link>
          <Link className="rounded border border-border px-2 py-1" href={`/console?decision_id=${encodeURIComponent(decisionId)}`}>
            Replay
          </Link>
        </div>
      </div>
    </section>
  );
}

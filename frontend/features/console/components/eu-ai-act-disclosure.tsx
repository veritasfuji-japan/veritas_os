import { useId } from "react";
import type { DecideResponse } from "@veritas/types";
import { renderValue } from "../analytics/utils";

interface EUAIActDisclosureProps {
  result: DecideResponse;
}

/**
 * EU AI Act Art. 50 / Art. 13 — Transparency disclosure banner.
 *
 * GAP-13b: Displays `ai_disclosure`, `regulation_notice`, and
 * `affected_parties_notice` from the API response so that
 * end-users are informed that content was AI-generated.
 */
export function EUAIActDisclosure({ result }: EUAIActDisclosureProps): JSX.Element | null {
  const sectionId = useId();
  const disclosure = result.ai_disclosure as string | undefined;
  const notice = result.regulation_notice as string | undefined;
  const affectedParties = result.affected_parties_notice as Record<string, unknown> | null | undefined;

  if (!disclosure && !notice && !affectedParties) {
    return null;
  }

  return (
    <section
      aria-labelledby={sectionId}
      className="rounded-md border border-blue-500/30 bg-blue-500/5 p-3 space-y-2"
    >
      <h3 className="text-sm font-semibold text-blue-400" id={sectionId}>
        EU AI Act Disclosure
      </h3>
      {disclosure ? (
        <p className="text-xs text-foreground/80" data-testid="ai-disclosure">
          {disclosure}
        </p>
      ) : null}
      {notice ? (
        <p className="text-xs text-muted-foreground" data-testid="regulation-notice">
          {notice}
        </p>
      ) : null}
      {affectedParties ? (
        <details className="text-xs">
          <summary className="cursor-pointer font-medium text-foreground/80">
            Affected Parties Notice
          </summary>
          <pre className="mt-1 overflow-x-auto rounded border border-border/50 bg-muted/30 p-2 text-xs text-foreground">
            {renderValue(affectedParties)}
          </pre>
        </details>
      ) : null}
    </section>
  );
}

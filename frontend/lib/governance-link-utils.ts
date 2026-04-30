/**
 * Normalize backend-provided navigation metadata into a safe in-app href.
 *
 * Mission Control treats governance artifact link fields as untrusted-ish
 * display input. Only internal app paths are linkable.
 */
export function normalizeSafeInternalHref(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const href = value.trim();
  if (!href) {
    return null;
  }

  if (!href.startsWith("/")) {
    return null;
  }

  if (href.startsWith("//")) {
    return null;
  }

  if (href.includes("\\") || href.includes("\n") || href.includes("\r") || href.includes("\t")) {
    return null;
  }

  return href;
}


const AUDIT_ARTIFACT_ID_PATTERN = /^[A-Za-z0-9._:-]+$/;

export function buildAuditArtifactHref(
  key: "bind_receipt_id" | "decision_id" | "execution_intent_id",
  value: unknown,
): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const id = value.trim();
  if (!id) {
    return null;
  }

  if (id.includes("\\") || id.includes("\n") || id.includes("\r") || id.includes("\t")) {
    return null;
  }

  if (!AUDIT_ARTIFACT_ID_PATTERN.test(id)) {
    return null;
  }

  const params = new URLSearchParams({ [key]: id });
  return normalizeSafeInternalHref(`/audit?${params.toString()}`);
}

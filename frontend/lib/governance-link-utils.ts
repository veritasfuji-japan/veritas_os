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

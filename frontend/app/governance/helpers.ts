import type { DiffChange } from "./governance-types";

export function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== typeof b || a === null || b === null) return false;
  if (typeof a !== "object") return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;

  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, i) => deepEqual(item, b[i]));
  }

  const objA = a as Record<string, unknown>;
  const objB = b as Record<string, unknown>;
  const keysA = Object.keys(objA);
  const keysB = Object.keys(objB);
  return keysA.length === keysB.length && keysA.every((key) => deepEqual(objA[key], objB[key]));
}

function categorizePath(path: string): DiffChange["category"] {
  if (path.startsWith("fuji_rules")) return "rule";
  if (path.startsWith("risk_thresholds")) return "threshold";
  if (path.startsWith("auto_stop")) return "escalation";
  if (path.startsWith("log_retention")) return "retention";
  if (path.startsWith("rollout_controls")) return "rollout";
  if (path.startsWith("approval_workflow")) return "approval";
  return "meta";
}

export function collectChanges(prefix: string, a: Record<string, unknown>, b: Record<string, unknown>): DiffChange[] {
  const changes: DiffChange[] = [];
  for (const key of new Set([...Object.keys(a), ...Object.keys(b)])) {
    const av = a[key];
    const bv = b[key];
    if (deepEqual(av, bv)) continue;
    if (typeof av === "object" && av !== null && typeof bv === "object" && bv !== null) {
      changes.push(...collectChanges(`${prefix}.${key}`, av as Record<string, unknown>, bv as Record<string, unknown>));
      continue;
    }
    const fullPath = `${prefix}.${key}`.replace(/^\./, "");
    changes.push({ path: fullPath, old: JSON.stringify(av), next: JSON.stringify(bv), category: categorizePath(fullPath) });
  }
  return changes;
}

export function bumpDraftVersion(version: string): string {
  const match = version.match(/^(.+\.)(\d+)$/);
  if (!match) return `${version}-draft.1`;
  return `${match[1]}${Number(match[2]) + 1}-draft`;
}

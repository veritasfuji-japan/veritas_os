import type { DiffChange, WatSettingsUI } from "./governance-types";

/**
 * Validates that a runtime value is a plain object record.
 *
 * This guard intentionally rejects `null` and arrays so callers can safely pass
 * the result into recursive diff utilities that assume key-value object shapes.
 */
export function isRecordObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

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

function toNumberOrFallback(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function getDefaultWatSettings(): WatSettingsUI {
  return {
    enabled: false,
    issuance_mode: "strict",
    require_observable_digest: true,
    default_ttl_seconds: 300,
    psid_display_length: 8,
    replay_binding_required: true,
    partial_validation_default: false,
    warning_only_until: "",
    timestamp_skew_tolerance_seconds: 30,
    revocation_mode: "soft",
    drift_weights: {
      policy: 0.25,
      signature: 0.25,
      observable: 0.25,
      temporal: 0.25,
    },
  };
}

/**
 * Normalizes partially-populated WAT settings from backend payloads.
 * Unknown or malformed values are replaced with safe defaults.
 */
export function normalizeWatSettings(value: unknown): WatSettingsUI {
  const defaults = getDefaultWatSettings();
  if (!isRecordObject(value)) {
    return defaults;
  }

  const driftWeights = isRecordObject(value.drift_weights) ? value.drift_weights : {};
  const issuanceMode = value.issuance_mode;
  const revocationMode = value.revocation_mode;

  return {
    enabled: typeof value.enabled === "boolean" ? value.enabled : defaults.enabled,
    issuance_mode: issuanceMode === "strict" || issuanceMode === "shadow" || issuanceMode === "hybrid"
      ? issuanceMode
      : defaults.issuance_mode,
    require_observable_digest: typeof value.require_observable_digest === "boolean"
      ? value.require_observable_digest
      : defaults.require_observable_digest,
    default_ttl_seconds: Math.max(1, Math.floor(toNumberOrFallback(value.default_ttl_seconds, defaults.default_ttl_seconds))),
    psid_display_length: Math.max(4, Math.floor(toNumberOrFallback(value.psid_display_length, defaults.psid_display_length))),
    replay_binding_required: typeof value.replay_binding_required === "boolean"
      ? value.replay_binding_required
      : defaults.replay_binding_required,
    partial_validation_default: typeof value.partial_validation_default === "boolean"
      ? value.partial_validation_default
      : defaults.partial_validation_default,
    warning_only_until: typeof value.warning_only_until === "string"
      ? value.warning_only_until
      : defaults.warning_only_until,
    timestamp_skew_tolerance_seconds: Math.max(
      0,
      Math.floor(
        toNumberOrFallback(
          value.timestamp_skew_tolerance_seconds,
          defaults.timestamp_skew_tolerance_seconds,
        ),
      ),
    ),
    revocation_mode: revocationMode === "soft" || revocationMode === "hard" ? revocationMode : defaults.revocation_mode,
    drift_weights: {
      policy: toNumberOrFallback(driftWeights.policy, defaults.drift_weights.policy),
      signature: toNumberOrFallback(driftWeights.signature, defaults.drift_weights.signature),
      observable: toNumberOrFallback(driftWeights.observable, defaults.drift_weights.observable),
      temporal: toNumberOrFallback(driftWeights.temporal, defaults.drift_weights.temporal),
    },
  };
}

import type {
  DiffChange,
  DriftScoringConfigUI,
  GovernancePolicyUI,
  PsidConfigUI,
  RevocationConfigUI,
  ShadowValidationConfigUI,
  WatConfigUI,
} from "./governance-types";

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

function asRecord(value: unknown): Record<string, unknown> {
  return isRecordObject(value) ? value : {};
}

export function getDefaultWatConfig(): WatConfigUI {
  return {
    enabled: false,
    issuance_mode: "shadow_only",
    require_observable_digest: true,
    default_ttl_seconds: 300,
  };
}

export function getDefaultPsidConfig(): PsidConfigUI {
  return { display_length: 12 };
}

export function getDefaultShadowValidationConfig(): ShadowValidationConfigUI {
  return {
    replay_binding_required: false,
    partial_validation_default: "non_admissible",
    warning_only_until: "",
    timestamp_skew_tolerance_seconds: 5,
  };
}

export function getDefaultRevocationConfig(): RevocationConfigUI {
  return { mode: "bounded_eventual_consistency" };
}

export function getDefaultDriftScoringConfig(): DriftScoringConfigUI {
  return {
    policy_weight: 0.4,
    signature_weight: 0.3,
    observable_weight: 0.2,
    temporal_weight: 0.1,
    healthy_threshold: 0.2,
    critical_threshold: 0.5,
  };
}

/**
 * Normalizes governance payload sections to backend schema-aligned WAT controls.
 *
 * This keeps frontend state schema-first and removes legacy `wat_settings` drift.
 */
export function normalizeGovernancePolicyWatFields(policy: GovernancePolicyUI): GovernancePolicyUI {
  const watDefaults = getDefaultWatConfig();
  const psidDefaults = getDefaultPsidConfig();
  const shadowDefaults = getDefaultShadowValidationConfig();
  const revocationDefaults = getDefaultRevocationConfig();
  const driftDefaults = getDefaultDriftScoringConfig();

  const watValue = asRecord(policy.wat);
  const psidValue = asRecord(policy.psid);
  const shadowValue = asRecord(policy.shadow_validation);
  const revocationValue = asRecord(policy.revocation);
  const driftValue = asRecord(policy.drift_scoring);

  return {
    ...policy,
    wat: {
      enabled: typeof watValue.enabled === "boolean" ? watValue.enabled : watDefaults.enabled,
      issuance_mode: watValue.issuance_mode === "shadow_only" || watValue.issuance_mode === "disabled"
        ? watValue.issuance_mode
        : watDefaults.issuance_mode,
      require_observable_digest: typeof watValue.require_observable_digest === "boolean"
        ? watValue.require_observable_digest
        : watDefaults.require_observable_digest,
      default_ttl_seconds: Math.max(1, Math.floor(toNumberOrFallback(watValue.default_ttl_seconds, watDefaults.default_ttl_seconds))),
    },
    psid: {
      display_length: Math.max(4, Math.floor(toNumberOrFallback(psidValue.display_length, psidDefaults.display_length))),
    },
    shadow_validation: {
      replay_binding_required: typeof shadowValue.replay_binding_required === "boolean"
        ? shadowValue.replay_binding_required
        : shadowDefaults.replay_binding_required,
      partial_validation_default: shadowValue.partial_validation_default === "non_admissible"
        ? shadowValue.partial_validation_default
        : shadowDefaults.partial_validation_default,
      warning_only_until: typeof shadowValue.warning_only_until === "string"
        ? shadowValue.warning_only_until
        : shadowDefaults.warning_only_until,
      timestamp_skew_tolerance_seconds: Math.max(
        0,
        Math.floor(
          toNumberOrFallback(
            shadowValue.timestamp_skew_tolerance_seconds,
            shadowDefaults.timestamp_skew_tolerance_seconds,
          ),
        ),
      ),
    },
    revocation: {
      mode: revocationValue.mode === "bounded_eventual_consistency"
        ? revocationValue.mode
        : revocationDefaults.mode,
    },
    drift_scoring: {
      policy_weight: toNumberOrFallback(driftValue.policy_weight, driftDefaults.policy_weight),
      signature_weight: toNumberOrFallback(driftValue.signature_weight, driftDefaults.signature_weight),
      observable_weight: toNumberOrFallback(driftValue.observable_weight, driftDefaults.observable_weight),
      temporal_weight: toNumberOrFallback(driftValue.temporal_weight, driftDefaults.temporal_weight),
      healthy_threshold: toNumberOrFallback(driftValue.healthy_threshold, driftDefaults.healthy_threshold),
      critical_threshold: toNumberOrFallback(driftValue.critical_threshold, driftDefaults.critical_threshold),
    },
  };
}

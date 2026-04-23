import type {
  DiffChange,
  BindAdjudicationConfigUI,
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
    signer_backend: "existing_signer",
    wat_metadata_retention_ttl_seconds: 7776000,
    wat_event_pointer_retention_ttl_seconds: 7776000,
    observable_digest_retention_ttl_seconds: 31536000,
    observable_digest_access_class: "restricted",
    observable_digest_ref: "separate_store://wat_observables",
    retention_policy_version: "wat_retention_v1",
    retention_enforced_at_write: true,
  };
}

export function getDefaultPsidConfig(): PsidConfigUI {
  return { enforcement_mode: "full_digest_only", display_length: 12 };
}

export function getDefaultShadowValidationConfig(): ShadowValidationConfigUI {
  return {
    enabled: true,
    replay_binding_required: false,
    replay_binding_escalation_threshold: 4,
    partial_validation_default: "non_admissible",
    partial_validation_requires_confirmation: true,
    warning_only_until: "",
    timestamp_skew_tolerance_seconds: 5,
  };
}

export function getDefaultRevocationConfig(): RevocationConfigUI {
  return {
    enabled: true,
    mode: "bounded_eventual_consistency",
    alert_target_seconds: 30,
    convergence_target_p95_seconds: 60,
    degrade_on_pending: true,
    revocation_confirmation_required: true,
    auto_escalate_confirmed_revocations: false,
  };
}

export function getDefaultBindAdjudicationConfig(): BindAdjudicationConfigUI {
  return {
    missing_signal_default: "block",
    drift_required: true,
    ttl_required: false,
    approval_freshness_required: false,
    rollback_on_apply_failure: false,
  };
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

export function getDefaultOperatorVerbosity(): "minimal" | "expanded" {
  return "minimal";
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
  const bindDefaults = getDefaultBindAdjudicationConfig();
  const operatorVerbosityDefault = getDefaultOperatorVerbosity();

  const watValue = asRecord(policy.wat);
  const psidValue = asRecord(policy.psid);
  const shadowValue = asRecord(policy.shadow_validation);
  const revocationValue = asRecord(policy.revocation);
  const driftValue = asRecord(policy.drift_scoring);
  const bindValue = asRecord(policy.bind_adjudication);

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
      signer_backend: typeof watValue.signer_backend === "string" ? watValue.signer_backend : watDefaults.signer_backend,
      wat_metadata_retention_ttl_seconds: Math.max(60, Math.floor(toNumberOrFallback(watValue.wat_metadata_retention_ttl_seconds, watDefaults.wat_metadata_retention_ttl_seconds))),
      wat_event_pointer_retention_ttl_seconds: Math.max(60, Math.floor(toNumberOrFallback(watValue.wat_event_pointer_retention_ttl_seconds, watDefaults.wat_event_pointer_retention_ttl_seconds))),
      observable_digest_retention_ttl_seconds: Math.max(60, Math.floor(toNumberOrFallback(watValue.observable_digest_retention_ttl_seconds, watDefaults.observable_digest_retention_ttl_seconds))),
      observable_digest_access_class: watValue.observable_digest_access_class === "privileged" ? "privileged" : watDefaults.observable_digest_access_class,
      observable_digest_ref: typeof watValue.observable_digest_ref === "string" ? watValue.observable_digest_ref : watDefaults.observable_digest_ref,
      retention_policy_version: typeof watValue.retention_policy_version === "string" ? watValue.retention_policy_version : watDefaults.retention_policy_version,
      retention_enforced_at_write: typeof watValue.retention_enforced_at_write === "boolean" ? watValue.retention_enforced_at_write : watDefaults.retention_enforced_at_write,
    },
    psid: {
      enforcement_mode: psidValue.enforcement_mode === "full_digest_only" ? psidValue.enforcement_mode : psidDefaults.enforcement_mode,
      display_length: Math.max(4, Math.floor(toNumberOrFallback(psidValue.display_length, psidDefaults.display_length))),
    },
    shadow_validation: {
      enabled: typeof shadowValue.enabled === "boolean" ? shadowValue.enabled : shadowDefaults.enabled,
      replay_binding_required: typeof shadowValue.replay_binding_required === "boolean"
        ? shadowValue.replay_binding_required
        : shadowDefaults.replay_binding_required,
      replay_binding_escalation_threshold: Math.max(1, Math.floor(toNumberOrFallback(shadowValue.replay_binding_escalation_threshold, shadowDefaults.replay_binding_escalation_threshold))),
      partial_validation_default: shadowValue.partial_validation_default === "non_admissible"
        ? shadowValue.partial_validation_default
        : shadowDefaults.partial_validation_default,
      partial_validation_requires_confirmation: typeof shadowValue.partial_validation_requires_confirmation === "boolean"
        ? shadowValue.partial_validation_requires_confirmation
        : shadowDefaults.partial_validation_requires_confirmation,
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
      enabled: typeof revocationValue.enabled === "boolean" ? revocationValue.enabled : revocationDefaults.enabled,
      mode: revocationValue.mode === "bounded_eventual_consistency"
        ? revocationValue.mode
        : revocationDefaults.mode,
      alert_target_seconds: Math.max(1, Math.floor(toNumberOrFallback(revocationValue.alert_target_seconds, revocationDefaults.alert_target_seconds))),
      convergence_target_p95_seconds: Math.max(1, Math.floor(toNumberOrFallback(revocationValue.convergence_target_p95_seconds, revocationDefaults.convergence_target_p95_seconds))),
      degrade_on_pending: typeof revocationValue.degrade_on_pending === "boolean" ? revocationValue.degrade_on_pending : revocationDefaults.degrade_on_pending,
      revocation_confirmation_required: typeof revocationValue.revocation_confirmation_required === "boolean" ? revocationValue.revocation_confirmation_required : revocationDefaults.revocation_confirmation_required,
      auto_escalate_confirmed_revocations: typeof revocationValue.auto_escalate_confirmed_revocations === "boolean" ? revocationValue.auto_escalate_confirmed_revocations : revocationDefaults.auto_escalate_confirmed_revocations,
    },
    drift_scoring: {
      policy_weight: toNumberOrFallback(driftValue.policy_weight, driftDefaults.policy_weight),
      signature_weight: toNumberOrFallback(driftValue.signature_weight, driftDefaults.signature_weight),
      observable_weight: toNumberOrFallback(driftValue.observable_weight, driftDefaults.observable_weight),
      temporal_weight: toNumberOrFallback(driftValue.temporal_weight, driftDefaults.temporal_weight),
      healthy_threshold: toNumberOrFallback(driftValue.healthy_threshold, driftDefaults.healthy_threshold),
      critical_threshold: toNumberOrFallback(driftValue.critical_threshold, driftDefaults.critical_threshold),
    },
    bind_adjudication: {
      missing_signal_default: bindValue.missing_signal_default === "escalate" ? "escalate" : bindDefaults.missing_signal_default,
      drift_required: typeof bindValue.drift_required === "boolean" ? bindValue.drift_required : bindDefaults.drift_required,
      ttl_required: typeof bindValue.ttl_required === "boolean" ? bindValue.ttl_required : bindDefaults.ttl_required,
      approval_freshness_required: typeof bindValue.approval_freshness_required === "boolean" ? bindValue.approval_freshness_required : bindDefaults.approval_freshness_required,
      rollback_on_apply_failure: typeof bindValue.rollback_on_apply_failure === "boolean" ? bindValue.rollback_on_apply_failure : bindDefaults.rollback_on_apply_failure,
    },
    operator_verbosity: policy.operator_verbosity === "expanded" ? "expanded" : operatorVerbosityDefault,
  };
}

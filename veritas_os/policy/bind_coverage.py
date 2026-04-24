"""Canonical bind coverage registry for API paths.

The registry makes route classification explicit so effect-bearing API paths are
never silently added without governance review.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from veritas_os.api.bind_target_catalog import CATALOG, resolve_bind_target_metadata


class BindCoverageClass(str, Enum):
    """Classification bucket for API route bind-boundary coverage."""

    BIND_GOVERNED = "bind_governed"
    READ_ONLY = "read_only"
    NON_EFFECT = "non_effect"
    AUDITED_EXEMPTION = "audited_exemption"


@dataclass(frozen=True)
class BindCoverageEntry:
    """One canonical coverage row for an API method/path pair."""

    path: str
    method: str
    coverage_class: BindCoverageClass
    reason: str | None = None
    risk_level: str | None = None
    governance_owner: str | None = None
    review_required_by: str | None = None

    def key(self) -> tuple[str, str]:
        """Return normalized key used by coverage lookup maps."""

        return (self.path, self.method.upper())


BIND_COVERAGE_REGISTRY: tuple[BindCoverageEntry, ...] = (
    BindCoverageEntry("/", "GET", BindCoverageClass.NON_EFFECT),
    BindCoverageEntry("/health", "GET", BindCoverageClass.NON_EFFECT),
    BindCoverageEntry("/v1/health", "GET", BindCoverageClass.NON_EFFECT),
    BindCoverageEntry("/status", "GET", BindCoverageClass.NON_EFFECT),
    BindCoverageEntry("/v1/status", "GET", BindCoverageClass.NON_EFFECT),
    BindCoverageEntry("/api/status", "GET", BindCoverageClass.NON_EFFECT),
    BindCoverageEntry("/v1/metrics", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/events", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/decide", "POST", BindCoverageClass.AUDITED_EXEMPTION,
                      reason="Decision recording is reviewable output and not an execution permission path.",
                      risk_level="medium", governance_owner="governance", review_required_by="quarterly"),
    BindCoverageEntry("/v1/replay/{decision_id}", "POST", BindCoverageClass.AUDITED_EXEMPTION,
                      reason="Replay endpoint reproduces prior decisions for audit and does not authorize execution.",
                      risk_level="low", governance_owner="audit", review_required_by="quarterly"),
    BindCoverageEntry("/v1/decision/replay/{decision_id}", "POST", BindCoverageClass.AUDITED_EXEMPTION,
                      reason="Legacy replay alias is audit-only and has no external execution side effects.",
                      risk_level="low", governance_owner="audit", review_required_by="quarterly"),
    BindCoverageEntry("/v1/fuji/validate", "POST", BindCoverageClass.AUDITED_EXEMPTION,
                      reason="Validation endpoint evaluates gate status but does not commit execution.",
                      risk_level="medium", governance_owner="governance", review_required_by="quarterly"),
    BindCoverageEntry("/v1/memory/put", "POST", BindCoverageClass.AUDITED_EXEMPTION,
                      reason="Memory write persists internal context only; no governed external execution target.",
                      risk_level="medium", governance_owner="memory", review_required_by="quarterly"),
    BindCoverageEntry("/v1/memory/search", "POST", BindCoverageClass.AUDITED_EXEMPTION,
                      reason="Search uses POST for payload size/shape but is read semantics only.",
                      risk_level="low", governance_owner="memory", review_required_by="quarterly"),
    BindCoverageEntry("/v1/memory/get", "POST", BindCoverageClass.AUDITED_EXEMPTION,
                      reason="Lookup endpoint uses POST for typed request body; retrieval only.",
                      risk_level="low", governance_owner="memory", review_required_by="quarterly"),
    BindCoverageEntry("/v1/memory/erase", "POST", BindCoverageClass.AUDITED_EXEMPTION,
                      reason="Memory erasure affects local memory store but is not a bind target catalog operation.",
                      risk_level="high", governance_owner="memory", review_required_by="monthly"),
    BindCoverageEntry("/v1/trust/logs", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/trust/stats", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/trust/{request_id}", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/trust/{request_id}/prov", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/trustlog/verify", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/trustlog/export", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/trust/feedback", "POST", BindCoverageClass.AUDITED_EXEMPTION,
                      reason="Trust feedback updates scoring telemetry only; no execution authorization.",
                      risk_level="low", governance_owner="trust", review_required_by="quarterly"),
    BindCoverageEntry("/v1/wat/issue-shadow", "POST", BindCoverageClass.AUDITED_EXEMPTION,
                      reason="Shadow WAT issuance is observer-lane telemetry and non-enforcement.",
                      risk_level="medium", governance_owner="governance", review_required_by="quarterly"),
    BindCoverageEntry("/v1/wat/validate-shadow", "POST", BindCoverageClass.AUDITED_EXEMPTION,
                      reason="Shadow validation checks signatures without granting execution privileges.",
                      risk_level="medium", governance_owner="governance", review_required_by="quarterly"),
    BindCoverageEntry("/v1/wat/events", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/wat/{wat_id}", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/wat/revocation/{wat_id}", "POST", BindCoverageClass.AUDITED_EXEMPTION,
                      reason="Revocation mutates WAT lane state but is not a bind-governed execution path.",
                      risk_level="high", governance_owner="governance", review_required_by="monthly"),
    BindCoverageEntry("/v1/governance/value-drift", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/governance/policy", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/governance/policy", "PUT", BindCoverageClass.BIND_GOVERNED),
    BindCoverageEntry("/v1/governance/policy/history", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/governance/decisions/export", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/governance/bind-receipts", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/governance/bind-receipts/export", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/governance/bind-receipts/{bind_receipt_id}", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/governance/policy-bundles/promote", "POST", BindCoverageClass.BIND_GOVERNED),
    BindCoverageEntry("/v1/compliance/config", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/compliance/config", "PUT", BindCoverageClass.BIND_GOVERNED),
    BindCoverageEntry("/v1/report/eu_ai_act/{decision_id}", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/report/governance", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/system/halt", "POST", BindCoverageClass.BIND_GOVERNED),
    BindCoverageEntry("/v1/system/resume", "POST", BindCoverageClass.BIND_GOVERNED),
    BindCoverageEntry("/v1/system/halt-status", "GET", BindCoverageClass.READ_ONLY),
    BindCoverageEntry("/v1/compliance/deployment-readiness", "GET", BindCoverageClass.READ_ONLY),
)

_REGISTRY_INDEX = {entry.key(): entry for entry in BIND_COVERAGE_REGISTRY}


def get_bind_coverage_registry() -> tuple[BindCoverageEntry, ...]:
    """Return the immutable bind coverage registry."""

    return BIND_COVERAGE_REGISTRY


def classify_bind_coverage(path: str, method: str) -> BindCoverageEntry | None:
    """Resolve a coverage entry for ``path`` + ``method`` when registered."""

    return _REGISTRY_INDEX.get((str(path), str(method).upper()))


def validate_bind_coverage_registry() -> list[str]:
    """Validate registry integrity and catalog consistency.

    Returns a list of error messages. Empty list means valid.
    """

    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    bind_governed_paths = set()

    for entry in BIND_COVERAGE_REGISTRY:
        key = entry.key()
        if key in seen:
            errors.append(f"duplicate bind coverage entry: {key[1]} {key[0]}")
        seen.add(key)

        if entry.coverage_class == BindCoverageClass.AUDITED_EXEMPTION:
            if not (entry.reason and entry.reason.strip()):
                errors.append(f"audited exemption missing reason: {entry.method} {entry.path}")
            if not (entry.risk_level and entry.risk_level.strip()):
                errors.append(f"audited exemption missing risk_level: {entry.method} {entry.path}")

        if entry.coverage_class == BindCoverageClass.BIND_GOVERNED:
            bind_governed_paths.add(entry.path)
            target = resolve_bind_target_metadata(entry.path, "")
            if target.get("target_path_type") == "other":
                errors.append(
                    f"bind_governed route missing bind target metadata: {entry.method} {entry.path}"
                )

    catalog_paths = {entry.target_path for entry in CATALOG}
    missing_in_catalog = bind_governed_paths - catalog_paths
    for path in sorted(missing_in_catalog):
        errors.append(f"bind_governed route missing from bind target catalog: {path}")

    missing_in_registry = catalog_paths - bind_governed_paths
    for path in sorted(missing_in_registry):
        errors.append(f"bind target catalog route missing bind_governed registry entry: {path}")

    return errors

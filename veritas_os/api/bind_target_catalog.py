"""Canonical bind target catalog for operator-facing governance surfaces."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BindTargetCatalogEntry:
    """Canonical metadata for a bind-governed target path/type pair."""

    target_path: str
    target_type: str
    target_path_type: str
    label: str
    operator_surface: str
    relevant_ui_href: str
    supports_filtering: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable catalog entry for API responses."""
        return {
            "target_path": self.target_path,
            "target_type": self.target_type,
            "target_path_type": self.target_path_type,
            "label": self.label,
            "operator_surface": self.operator_surface,
            "relevant_ui_href": self.relevant_ui_href,
            "supports_filtering": self.supports_filtering,
        }


CATALOG: tuple[BindTargetCatalogEntry, ...] = (
    BindTargetCatalogEntry(
        target_path="/v1/governance/policy",
        target_type="governance_policy",
        target_path_type="governance_policy_update",
        label="governance policy update",
        operator_surface="governance",
        relevant_ui_href="/governance",
    ),
    BindTargetCatalogEntry(
        target_path="/v1/governance/policy-bundles/promote",
        target_type="policy_bundle",
        target_path_type="policy_bundle_promotion",
        label="policy bundle promotion",
        operator_surface="governance",
        relevant_ui_href="/governance",
    ),
    BindTargetCatalogEntry(
        target_path="/v1/compliance/config",
        target_type="compliance_config",
        target_path_type="compliance_config_update",
        label="compliance config update",
        operator_surface="compliance",
        relevant_ui_href="/system",
    ),
)

_INDEX_BY_PATH_AND_TYPE = {
    (entry.target_path, entry.target_type): entry for entry in CATALOG
}
_INDEX_BY_PATH = {entry.target_path: entry for entry in CATALOG}


def get_target_catalog_payload() -> list[dict[str, Any]]:
    """Return canonical catalog payload for list/export/detail responses."""
    return [entry.to_dict() for entry in CATALOG]


def resolve_bind_target_metadata(target_path: Any, target_type: Any) -> dict[str, Any]:
    """Resolve canonical bind target metadata with safe unknown-path fallback."""
    canonical_path = str(target_path).strip() if isinstance(target_path, str) else ""
    canonical_type = str(target_type).strip() if isinstance(target_type, str) else ""
    matched = (
        _INDEX_BY_PATH_AND_TYPE.get((canonical_path, canonical_type))
        or _INDEX_BY_PATH.get(canonical_path)
    )
    if matched:
        return matched.to_dict()
    return {
        "target_path": canonical_path,
        "target_type": canonical_type,
        "target_path_type": "other",
        "label": "other",
        "operator_surface": "audit",
        "relevant_ui_href": "/audit",
        "supports_filtering": False,
    }

"""Generate reviewer-facing bind coverage evidence artifacts.

This script inspects FastAPI runtime routes and the canonical bind coverage
registry to produce deterministic JSON/Markdown evidence files for reviewers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute

from veritas_os.api.bind_target_catalog import CATALOG
from veritas_os.api.server import app
from veritas_os.policy.bind_coverage import (
    BindCoverageClass,
    classify_bind_coverage,
    validate_bind_coverage_registry,
)

EFFECT_BEARING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_JSON = REPO_ROOT / "docs/en/validation/bind-coverage-evidence.latest.json"
OUTPUT_MD = REPO_ROOT / "docs/en/validation/bind-coverage-evidence.latest.md"


def _runtime_api_routes() -> list[tuple[str, str]]:
    routes: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods):
            if method in {"HEAD", "OPTIONS"}:
                continue
            routes.append((route.path, method))
    return sorted(routes, key=lambda item: (item[0], item[1]))


def generate_bind_coverage_evidence(generated_at: str | None = None) -> dict[str, Any]:
    """Build bind coverage evidence payload from runtime routes + registry."""

    runtime_routes = _runtime_api_routes()
    catalog_path_set = {entry.target_path for entry in CATALOG}
    catalog_paths = sorted(catalog_path_set)
    registry_errors = sorted(validate_bind_coverage_registry())

    route_rows: list[dict[str, Any]] = []
    unclassified: list[str] = []
    audited_missing_reason: list[str] = []
    audited_missing_risk: list[str] = []
    bind_governed_targets: set[str] = set()

    for path, method in runtime_routes:
        entry = classify_bind_coverage(path, method)
        coverage_class = entry.coverage_class.value if entry else "unclassified"
        metadata_present = False
        if entry and entry.coverage_class == BindCoverageClass.BIND_GOVERNED:
            bind_governed_targets.add(path)
            metadata_present = path in catalog_path_set

        if entry is None:
            unclassified.append(f"{method} {path}")
        if entry and entry.coverage_class == BindCoverageClass.AUDITED_EXEMPTION:
            if not (entry.reason and entry.reason.strip()):
                audited_missing_reason.append(f"{method} {path}")
            if not (entry.risk_level and entry.risk_level.strip()):
                audited_missing_risk.append(f"{method} {path}")

        route_rows.append(
            {
                "method": method,
                "path": path,
                "coverage_class": coverage_class,
                "reason": entry.reason if entry else None,
                "risk_level": entry.risk_level if entry else None,
                "governance_owner": entry.governance_owner if entry else None,
                "review_required_by": entry.review_required_by if entry else None,
                "bind_target_metadata_present": metadata_present,
            }
        )

    catalog_registry_mismatch = [
        error
        for error in registry_errors
        if "missing from bind target catalog" in error
        or "missing bind_governed registry entry" in error
    ]

    effect_routes = [
        row
        for row in route_rows
        if row["method"] in EFFECT_BEARING_METHODS
    ]

    status = "ok"
    if (
        unclassified
        or audited_missing_reason
        or audited_missing_risk
        or catalog_registry_mismatch
        or registry_errors
    ):
        status = "failed"

    return {
        "schema_version": "bind_coverage_evidence.v1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "total_runtime_routes": len(route_rows),
        "total_effect_bearing_routes": len(effect_routes),
        "classified_routes": len(route_rows) - len(unclassified),
        "unclassified_routes": unclassified,
        "bind_governed_routes": [
            row for row in route_rows if row["coverage_class"] == "bind_governed"
        ],
        "audited_exemptions": [
            row for row in route_rows if row["coverage_class"] == "audited_exemption"
        ],
        "read_only_routes": [
            row for row in route_rows if row["coverage_class"] == "read_only"
        ],
        "non_effect_routes": [
            row for row in route_rows if row["coverage_class"] == "non_effect"
        ],
        "catalog_bind_targets": catalog_paths,
        "registry_bind_governed_targets": sorted(bind_governed_targets),
        "catalog_registry_mismatch": catalog_registry_mismatch,
        "audited_exemption_missing_reason": audited_missing_reason,
        "audited_exemption_missing_risk_level": audited_missing_risk,
        "registry_errors": registry_errors,
        "status": status,
        "routes": route_rows,
    }


def render_bind_coverage_markdown(evidence: dict[str, Any]) -> str:
    """Render markdown summary from evidence payload."""

    lines: list[str] = [
        "# Bind Coverage Evidence Artifact",
        "",
        "## Scope",
        "This artifact summarizes FastAPI runtime route classification against the canonical bind coverage registry.",
        "",
        "## Summary table",
        "| Metric | Value |",
        "| --- | --- |",
        f"| total_runtime_routes | {evidence['total_runtime_routes']} |",
        f"| total_effect_bearing_routes | {evidence['total_effect_bearing_routes']} |",
        f"| bind_governed_routes | {len(evidence['bind_governed_routes'])} |",
        f"| audited_exemptions | {len(evidence['audited_exemptions'])} |",
        f"| unclassified_routes | {len(evidence['unclassified_routes'])} |",
        f"| status | {evidence['status']} |",
        f"| registry_errors | {len(evidence['registry_errors'])} |",
        "",
        "## Bind-governed routes",
    ]
    for row in evidence["bind_governed_routes"]:
        lines.append(
            f"- `{row['method']} {row['path']}` "
            f"(bind_target_metadata_present={row['bind_target_metadata_present']})"
        )

    lines.extend(["", "## Audited exemptions"])
    for row in evidence["audited_exemptions"]:
        lines.append(
            "- "
            f"`{row['method']} {row['path']}` "
            f"reason={row['reason']}; risk_level={row['risk_level']}; "
            f"governance_owner={row['governance_owner']}; review_required_by={row['review_required_by']}"
        )

    lines.extend(["", "## Unclassified routes"])
    if evidence["unclassified_routes"]:
        for item in evidence["unclassified_routes"]:
            lines.append(f"- `{item}`")
    else:
        lines.append("- None")

    lines.extend(["", "## Catalog / registry consistency"])
    if evidence["catalog_registry_mismatch"]:
        for item in evidence["catalog_registry_mismatch"]:
            lines.append(f"- {item}")
    else:
        lines.append(
            "- No mismatch detected between bind target catalog and "
            "bind-governed registry targets."
        )


    lines.extend(["", "## Registry validation errors"])
    if evidence["registry_errors"]:
        for item in evidence["registry_errors"]:
            lines.append(f"- {item}")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Interpretation boundaries",
            "- This artifact proves route classification coverage, not external legal certification.",
            "- This artifact does not prove every business action is safe.",
            "- Bind-governed routes are the routes currently wired to the Bind target catalog.",
            "- Audited exemptions require periodic governance review.",
            "",
            "## CI freshness guard",
            "- CI checks these artifacts for freshness against current API routes and bind coverage sources.",
            "- If this check fails, rerun the generator command below and commit both artifacts.",
            "",
            "## How to regenerate",
            "```bash",
            "python scripts/governance/export_bind_coverage_evidence.py",
            "```",
            "",
        ]
    )

    return "\n".join(lines)


def write_bind_coverage_evidence(
    json_path: Path = OUTPUT_JSON,
    markdown_path: Path = OUTPUT_MD,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Generate and write bind coverage evidence JSON and markdown artifacts."""

    evidence = generate_bind_coverage_evidence(generated_at=generated_at)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_payload = json.dumps(
        evidence,
        indent=2,
        sort_keys=True,
    ) + "\n"
    markdown_payload = render_bind_coverage_markdown(evidence) + "\n"

    json_path.write_text(json_payload, encoding="utf-8")
    markdown_path.write_text(markdown_payload, encoding="utf-8")
    return evidence


def main() -> None:
    """CLI entrypoint for artifact generation."""

    write_bind_coverage_evidence(generated_at=None)


if __name__ == "__main__":
    main()

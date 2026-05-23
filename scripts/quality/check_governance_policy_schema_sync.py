#!/usr/bin/env python3
"""Guard against governance policy/schema drift and retention data loss."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pydantic import ValidationError

from veritas_os.api.governance import GovernancePolicy

GOVERNANCE_PATH = REPO_ROOT / "veritas_os" / "api" / "governance.json"


def main() -> int:
    """Validate committed governance policy safely roundtrips through schema."""
    errors: list[str] = []

    try:
        committed = json.loads(GOVERNANCE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[GOV-SCHEMA] Missing committed policy file: {GOVERNANCE_PATH}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"[GOV-SCHEMA] Invalid JSON in {GOVERNANCE_PATH}: {exc}")
        return 1

    try:
        roundtripped = GovernancePolicy.model_validate(committed).model_dump()
    except ValidationError as exc:
        print("[GOV-SCHEMA] Committed governance policy failed schema validation.")
        print(exc)
        return 1

    committed_retention = committed.get("log_retention", {})
    roundtrip_retention = roundtripped.get("log_retention", {})

    if "retention_days_high_risk" not in roundtrip_retention:
        errors.append("log_retention.retention_days_high_risk disappeared after roundtrip.")
    if roundtrip_retention.get("retention_days") != 180:
        errors.append(
            "log_retention.retention_days drifted from expected safe baseline 180 "
            f"(found {roundtrip_retention.get('retention_days')})."
        )
    if roundtrip_retention.get("retention_days_high_risk") != 365:
        errors.append(
            "log_retention.retention_days_high_risk drifted from expected baseline 365 "
            f"(found {roundtrip_retention.get('retention_days_high_risk')})."
        )

    for key, value in committed_retention.items():
        if roundtrip_retention.get(key) != value:
            errors.append(
                f"Committed log_retention.{key}={value} changed to "
                f"{roundtrip_retention.get(key)} after schema roundtrip."
            )

    committed_sections = set(committed.keys())
    schema_sections = set(roundtripped.keys())
    schema_only = sorted(schema_sections - committed_sections)

    if errors:
        print("[GOV-SCHEMA] Governance policy/schema sync check FAILED:")
        for error in errors:
            print(f"- {error}")
        if schema_only:
            print(
                "- Schema-only sections (present via defaults, missing in committed JSON): "
                + ", ".join(schema_only)
            )
        return 1

    print("Governance policy schema roundtrip checks passed.")
    if schema_only:
        print(
            "Schema-only default sections detected (informational): "
            + ", ".join(schema_only)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Validate capability-profile runbook guidance required for operations.

The runbook documents the production-recommended capability profile for
optional integrations so operators can detect capability drift before it
turns into a security or observability incident.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNBOOK_PATH = REPO_ROOT / "docs/ja/operations/enterprise_slo_sli_runbook_ja.md"
REQUIRED_TOKENS = (
    "## 6.3 capability profile / strict mode 推奨",
    "### production 推奨設定",
    "VERITAS_CAP_FUJI_TRUST_LOG=1",
    "VERITAS_CAP_EMIT_MANIFEST=1",
    "### local / test でのみ許容する設定",
    "VERITAS_AUTH_ALLOW_FAIL_OPEN=true",
    "VERITAS_AUTH_STORE_FAILURE_MODE=open",
    "### strict mode を推奨する箇所",
    "VERITAS_CAP_FUJI_YAML_POLICY=1",
    "VERITAS_FUJI_STRICT_POLICY_LOAD=1",
    "### fallback / degraded の観測方法",
    "[CapabilityManifest]",
)


def collect_missing_tokens(content: str) -> list[str]:
    """Return required capability-profile markers missing from the runbook."""
    return [token for token in REQUIRED_TOKENS if token not in content]


def main() -> int:
    """Validate the runbook keeps capability-profile guidance complete."""
    if not RUNBOOK_PATH.exists():
        print(f"Missing runbook: {RUNBOOK_PATH}")
        return 1

    content = RUNBOOK_PATH.read_text(encoding="utf-8")
    missing_tokens = collect_missing_tokens(content)
    if not missing_tokens:
        print("Capability profile runbook guidance passed checks.")
        return 0

    print("[DOCS] Capability profile runbook guidance is incomplete:")
    for token in missing_tokens:
        print(f"- missing token: {token}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

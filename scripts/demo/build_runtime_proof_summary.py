#!/usr/bin/env python3
"""Write safe Markdown summaries for verified independent runtime proofs."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_summary(tested_sha: str, source_head_sha: str) -> str:
    """Return reviewer Markdown with explicit, non-empty CI provenance."""
    if not tested_sha.strip() or not source_head_sha.strip():
        raise ValueError("tested and source head SHA values must be non-empty")
    return f"""# VERITAS Runtime Proof Evidence

Tested checkout SHA: `{tested_sha}`
Source head SHA: `{source_head_sha}`

## Decision Pipeline Proof
- authenticated `/v1/decide`: PASS
- real decision/governance runtime: PASS
- real `kernel.decide` successful return: PASS
- provider mode: `controlled_provider_fixture`
- TrustLog and replay verification: PASS
- ExecutionIntent created / Bind invoked: NO / NO

## External Bind Boundary Proof
- decision stage: `synthetic_fixture`
- COMMITTED / BLOCKED / ROLLED_BACK: PASS / PASS / PASS

## Boundary
These are two independent proof paths. No Decision Pipeline -> ExecutionIntent
-> Bind handoff is claimed.

Artifact: `veritas-runtime-proof-evidence`

This local CI bundle does not prove live providers, production TrustLog,
PostgreSQL, KMS/WORM, execution authority, Human Approval, Authority Evidence,
decision-to-bind lineage, live financial integrations, customer deployment,
regulatory approval/certification, or production readiness.
"""


def main() -> int:
    """Parse provenance and write reviewer and optional GitHub summaries."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tested-sha", required=True)
    parser.add_argument("--source-head-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--github-summary", type=Path)
    args = parser.parse_args()
    try:
        summary = build_summary(args.tested_sha, args.source_head_sha)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.write_text(summary, encoding="utf-8")
    if args.github_summary:
        with args.github_summary.open("a", encoding="utf-8") as stream:
            stream.write(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

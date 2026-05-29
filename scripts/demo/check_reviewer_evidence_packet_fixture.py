#!/usr/bin/env python3
"""Verify the Reviewer Evidence Packet golden fixture matches generated output."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.export_reviewer_evidence_packet import build_reviewer_evidence_packet

FIXTURE_PATH = REPO_ROOT / (
    "docs/en/demo/fixtures/reviewer-evidence-packet-saas-permission-change-v1.json"
)


def main() -> int:
    """Return zero when the checked-in fixture matches generated packet output."""
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    generated = build_reviewer_evidence_packet()
    if generated != fixture:
        print("Reviewer Evidence Packet fixture mismatch.")
        return 1
    print("Reviewer Evidence Packet fixture matches generated packet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

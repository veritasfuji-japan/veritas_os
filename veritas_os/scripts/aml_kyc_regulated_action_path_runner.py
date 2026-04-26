#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI runner for deterministic AML/KYC regulated action path fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from veritas_os.governance.regulated_action_path import (
    DEFAULT_FIXTURE_PATH,
    run_all_regulated_action_scenarios,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run deterministic AML/KYC regulated action path scenarios."
    )
    parser.add_argument("--input", default=str(DEFAULT_FIXTURE_PATH))
    parser.add_argument("--output-json", default="")
    return parser.parse_args()


def main() -> None:
    """Run fixture scenarios and print normalized deterministic outputs."""
    args = _parse_args()
    results = run_all_regulated_action_scenarios(fixture_path=Path(args.input))
    payload = [item.to_dict() for item in results]
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[aml-kyc-regulated-action-path] report saved: {output_path}")


if __name__ == "__main__":
    main()

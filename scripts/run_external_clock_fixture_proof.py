#!/usr/bin/env python3
"""Generate deterministic reviewer artifacts for the external clock boundary."""

from __future__ import annotations

import argparse
from pathlib import Path

from veritas_os.governance.external_clock_fixture_proof import (
    write_external_clock_fixture_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/external-clock-fixture-proof"),
    )
    args = parser.parse_args()
    write_external_clock_fixture_artifacts(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

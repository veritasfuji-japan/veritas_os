from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

BASELINE_TARGETS = [
    "scripts/demo/one_day_poc_shared.py",
    "scripts/demo/one_day_poc_benchmark.py",
    "scripts/demo/one_day_poc_smoke.py",
]


def main() -> int:
    cmd = [sys.executable, "-m", "mypy", "--explicit-package-bases", *BASELINE_TARGETS]
    result = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

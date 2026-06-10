"""CI gate coverage for Trusted Public Key Provenance sample artifacts."""

from __future__ import annotations

import subprocess
import sys


def test_key_provenance_review_samples_ci_gate_exits_zero() -> None:
    """Run the sample validation script exactly as CI does."""
    result = subprocess.run(
        [sys.executable, "scripts/quality/check_key_provenance_review_samples.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr

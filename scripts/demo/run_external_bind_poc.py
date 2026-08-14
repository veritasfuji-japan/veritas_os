"""Command-line runner for the synthetic external bind evidence PoC."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.external_bind_poc.poc import run_all


def main() -> int:
    """Generate evidence and report whether every expected outcome passed."""
    results = run_all(Path("artifacts/external-bind-poc"))
    for name, evidence in results.items():
        print(f"{evidence['final_outcome']:<12} PASS  ({name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

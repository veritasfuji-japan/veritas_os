#!/usr/bin/env python3
"""Repository-root wrapper for the VERITAS / CAGE Phase 5A runtime proof."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from veritas_os.scripts.cage_provider03_phase5a_runner import main


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Entrypoint for the VERITAS / CAGE Phase 5B runtime proof."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from veritas_os.scripts.cage_provider03_phase5b_runner import main


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI wrapper for financial PoC runner."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from veritas_os.scripts.financial_poc_runner import main


if __name__ == "__main__":
    main()

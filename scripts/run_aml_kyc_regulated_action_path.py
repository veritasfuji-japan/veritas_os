#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI wrapper for AML/KYC regulated action path fixture runner."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from veritas_os.scripts.aml_kyc_regulated_action_path_runner import main


if __name__ == "__main__":
    main()

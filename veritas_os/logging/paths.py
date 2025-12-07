# veritas_os/logging/paths.py
from __future__ import annotations

import os
from pathlib import Path

# リポジトリルート: .../veritas_clean_test2/veritas_os
REPO_ROOT = Path(__file__).resolve().parents[1]

# scripts ディレクトリ
SCRIPTS_DIR = REPO_ROOT / "scripts"

# ---- ログ周り ----

# ★ 追加: VERITAS_DATA_DIR があればそちらを最優先で使う
DATA_BASE = os.getenv("VERITAS_DATA_DIR")
if DATA_BASE:
    # 例: /tmp/pytest-xxx など
    LOG_ROOT = Path(DATA_BASE).expanduser()
else:
    # 従来どおり VERITAS_LOG_ROOT → scripts/logs の順で使う
    LOG_ROOT = Path(
        os.getenv("VERITAS_LOG_ROOT", str(SCRIPTS_DIR / "logs"))
    ).expanduser()

LOG_ROOT.mkdir(parents=True, exist_ok=True)

# trust_log など通常ログ
LOG_DIR = LOG_ROOT
LOG_JSON = LOG_DIR / "trust_log.json"
LOG_JSONL = LOG_DIR / "trust_log.jsonl"

# decide_* や shadow 用
DASH_DIR = LOG_ROOT / "DASH"
DASH_DIR.mkdir(parents=True, exist_ok=True)

# doctor/shadow decide 用ディレクトリ
SHADOW_DIR = DASH_DIR

# 学習用データセット
DATASET_DIR = DASH_DIR

# ---- ValueCore 用データ ----

# プロジェクト直下 .../veritas_clean_test2/data
PROJECT_ROOT = REPO_ROOT.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ValueCore のEMA等
VAL_JSON = DATA_DIR / "value_stats.json"

# ReasonOS メタログ
META_LOG = LOG_DIR / "meta_log.jsonl"

__all__ = [
    "REPO_ROOT",
    "SCRIPTS_DIR",
    "LOG_ROOT",
    "LOG_DIR",
    "LOG_JSON",
    "LOG_JSONL",
    "DASH_DIR",
    "SHADOW_DIR",
    "DATASET_DIR",
    "PROJECT_ROOT",
    "DATA_DIR",
    "VAL_JSON",
    "META_LOG",
]


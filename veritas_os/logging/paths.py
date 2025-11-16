# veritas_os/logging/paths.py
from __future__ import annotations

from pathlib import Path

from veritas_os.core.config import cfg  # ★ ここがポイント

# cfg.log_dir は
#   /Users/user/veritas_clean_test2/veritas_os/scripts/logs
# を指している（config.pyでそう決めてある）

# ログのベース
LOG_DIR: Path = cfg.log_dir

# DASH 用（Doctor ダッシュボードで使う）
DASH_DIR: Path = LOG_DIR / "DASH"

# データセットもとりあえず DASH 配下にまとめる
DATASET_DIR: Path = DASH_DIR

# 念のためディレクトリ作成
LOG_DIR.mkdir(parents=True, exist_ok=True)
DASH_DIR.mkdir(parents=True, exist_ok=True)
DATASET_DIR.mkdir(parents=True, exist_ok=True)

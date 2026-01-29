# veritas/core/config.py
from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field


def _parse_cors_origins(raw_value: str) -> list[str]:
    """Parse comma-separated CORS origins from an env var into a clean list."""
    if not raw_value:
        return []
    return [value.strip() for value in raw_value.split(",") if value.strip()]


@dataclass
class VeritasConfig:
    # ==== API ====
    api_key_str: str = field(
        default_factory=lambda: os.getenv(
            "VERITAS_API_KEY",
            "YOUR_VERITAS_PUBLIC_API_KEY_HERE",
        )
    )
    api_secret: str = field(
        default_factory=lambda: os.getenv(
            "VERITAS_API_SECRET",
            "YOUR_VERITAS_API_SECRET_HERE",
        )
    )
    api_header: str = "X-API-Key"
    api_key: str = ""  # alias

    # ==== PATHS ====
    # core/config.py → core → veritas_os
    repo_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[1]
    )

    # home も repo_root に固定してしまう
    home: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[1]
    )

    data_dir: Path | None = None
    log_dir: Path | None = None
    dataset_dir: Path | None = None
    memory_path: Path | None = None
    value_stats_path: Path | None = None

    trust_log_path: Path | None = None
    kv_path: Path | None = None

    # ==== Weights / meta ====
    telos_default_WT: float = 0.6
    telos_default_WS: float = 0.4
    creator_name: str = "fuji"
    product_name: str = "VERITAS"

    cors_allow_origins: list[str] = field(
        default_factory=lambda: _parse_cors_origins(
            os.getenv("VERITAS_CORS_ALLOW_ORIGINS", "")
        )
    )

    def __post_init__(self):
        # --- API alias ---
        if not self.api_key:
            self.api_key = self.api_key_str

        # ベースは常に veritas_os
        base = self.repo_root  # .../veritas_clean_test2/veritas_os

        # --- PATH 決定 ---
        if self.log_dir is None:
            self.log_dir = base / "scripts" / "logs"

        if self.dataset_dir is None:
            self.dataset_dir = base / "scripts" / "datasets"

        if self.data_dir is None:
            # 互換用：data_dir も logs と同じ場所に寄せる
            self.data_dir = self.log_dir

        if self.memory_path is None:
            self.memory_path = self.log_dir / "memory.json"

        if self.value_stats_path is None:
            self.value_stats_path = self.log_dir / "value_stats.json"

        if self.trust_log_path is None:
            self.trust_log_path = self.log_dir / "trust_log.json"

        if self.kv_path is None:
            self.kv_path = self.log_dir / "kv.sqlite3"

        # --- ディレクトリ作成 ---
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.kv_path.parent.mkdir(parents=True, exist_ok=True)


cfg = VeritasConfig()

# veritas/core/config.py
"""
VERITAS OS 設定モジュール

すべての設定値を一元管理し、マジックナンバーを排除します。
環境変数による上書きも可能です。
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Any


def _parse_cors_origins(raw_value: str) -> list[str]:
    """Parse comma-separated CORS origins from an env var into a clean list."""
    if not raw_value:
        return []
    values = [value.strip() for value in raw_value.split(",") if value.strip()]
    if "*" in values:
        logging.getLogger(__name__).warning(
            "VERITAS_CORS_ALLOW_ORIGINS contains '*'. "
            "Credentials are enabled, so '*' is ignored for safety."
        )
    return [value for value in values if value != "*"]


def _parse_float(env_key: str, default: float) -> float:
    """環境変数から float を取得し、不正値時は警告して既定値を返す。"""
    val = os.getenv(env_key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        logging.getLogger(__name__).warning(
            "Invalid float for %s; falling back to default.", env_key
        )
        return default


def _parse_int(env_key: str, default: int) -> int:
    """環境変数から int を取得し、不正値時は警告して既定値を返す。"""
    val = os.getenv(env_key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        logging.getLogger(__name__).warning(
            "Invalid int for %s; falling back to default.", env_key
        )
        return default


def _parse_bool(env_key: str, default: bool = False) -> bool:
    """環境変数から bool を取得し、不正値時は警告して既定値を返す。"""
    val = os.getenv(env_key)
    if val is None:
        return default

    normalized = val.strip().lower()
    truthy_values = {"1", "true", "yes", "on"}
    falsy_values = {"0", "false", "no", "off", ""}

    if normalized in truthy_values:
        return True
    if normalized in falsy_values:
        return False

    logging.getLogger(__name__).warning(
        "Invalid bool for %s; falling back to default.", env_key
    )
    return default


# =============================================================================
# スコアリング設定（kernel.py から外部化）
# =============================================================================

@dataclass
class ScoringConfig:
    """
    alternatives スコアリングの設定値

    kernel.py の _score_alternatives() で使用されるマジックナンバーを
    設定として外部化したもの。
    """
    # Intent別ボーナス
    intent_weather_bonus: float = field(
        default_factory=lambda: _parse_float("VERITAS_INTENT_WEATHER_BONUS", 0.4)
    )
    intent_health_bonus: float = field(
        default_factory=lambda: _parse_float("VERITAS_INTENT_HEALTH_BONUS", 0.4)
    )
    intent_learn_bonus: float = field(
        default_factory=lambda: _parse_float("VERITAS_INTENT_LEARN_BONUS", 0.35)
    )
    intent_plan_bonus: float = field(
        default_factory=lambda: _parse_float("VERITAS_INTENT_PLAN_BONUS", 0.3)
    )

    # クエリマッチングボーナス
    query_match_bonus: float = field(
        default_factory=lambda: _parse_float("VERITAS_QUERY_MATCH_BONUS", 0.2)
    )

    # High stakes時のボーナス
    high_stakes_threshold: float = field(
        default_factory=lambda: _parse_float("VERITAS_HIGH_STAKES_THRESHOLD", 0.7)
    )
    high_stakes_bonus: float = field(
        default_factory=lambda: _parse_float("VERITAS_HIGH_STAKES_BONUS", 0.2)
    )

    # Persona bias 乗数
    persona_bias_multiplier: float = field(
        default_factory=lambda: _parse_float("VERITAS_PERSONA_BIAS_MULTIPLIER", 0.3)
    )

    # Telos スコアスケーリング
    telos_scale_base: float = field(
        default_factory=lambda: _parse_float("VERITAS_TELOS_SCALE_BASE", 0.9)
    )
    telos_scale_factor: float = field(
        default_factory=lambda: _parse_float("VERITAS_TELOS_SCALE_FACTOR", 0.2)
    )


# =============================================================================
# FUJI Gate 設定（fuji.py から外部化）
# =============================================================================

@dataclass
class FujiConfig:
    """
    FUJI Gate の設定値

    fuji.py の閾値やペナルティ値を設定として外部化。
    """
    # Evidence 関連
    default_min_evidence: int = field(
        default_factory=lambda: _parse_int("VERITAS_MIN_EVIDENCE", 1)
    )
    max_uncertainty: float = field(
        default_factory=lambda: _parse_float("VERITAS_MAX_UNCERTAINTY", 0.60)
    )
    low_evidence_risk_penalty: float = field(
        default_factory=lambda: _parse_float("VERITAS_LOW_EVIDENCE_PENALTY", 0.10)
    )

    # Safety Head エラー時のベースリスク
    safety_head_error_base_risk: float = field(
        default_factory=lambda: _parse_float("VERITAS_SAFETY_HEAD_ERROR_RISK", 0.30)
    )

    # Telos スコアによるリスクスケーリング
    telos_risk_scale_factor: float = field(
        default_factory=lambda: _parse_float("VERITAS_TELOS_RISK_SCALE", 0.10)
    )

    # PII safe applied 時のリスク上限
    pii_safe_risk_cap: float = field(
        default_factory=lambda: _parse_float("VERITAS_PII_SAFE_RISK_CAP", 0.40)
    )

    # name_like_only 時のリスク上限
    name_like_only_risk_cap: float = field(
        default_factory=lambda: _parse_float("VERITAS_NAME_LIKE_RISK_CAP", 0.20)
    )

    # PoC モード
    poc_mode: bool = field(
        default_factory=lambda: _parse_bool("VERITAS_POC_MODE", False)
    )


# =============================================================================
# パイプライン設定
# =============================================================================

@dataclass
class PipelineConfig:
    """
    決定パイプラインの設定値
    """
    # Memory 検索
    memory_search_limit: int = field(
        default_factory=lambda: _parse_int("VERITAS_MEMORY_SEARCH_LIMIT", 8)
    )
    evidence_top_k: int = field(
        default_factory=lambda: _parse_int("VERITAS_EVIDENCE_TOP_K", 5)
    )

    # Planner
    max_plan_steps: int = field(
        default_factory=lambda: _parse_int("VERITAS_MAX_PLAN_STEPS", 10)
    )

    # Debate
    debate_timeout_seconds: int = field(
        default_factory=lambda: _parse_int("VERITAS_DEBATE_TIMEOUT", 30)
    )

    # Auto-adjust
    persona_update_window: int = field(
        default_factory=lambda: _parse_int("VERITAS_PERSONA_UPDATE_WINDOW", 50)
    )
    persona_bias_increment: float = field(
        default_factory=lambda: _parse_float("VERITAS_PERSONA_BIAS_INCREMENT", 0.05)
    )


@dataclass
class VeritasConfig:
    # ==== API ====
    api_key_str: str = field(
        default_factory=lambda: os.getenv(
            "VERITAS_API_KEY",
            "",
        )
    )
    # ★ C-2 修正: プレースホルダーをデフォルト値にしない（セキュリティ改善）
    # 環境変数未設定時は空文字 → server.py 側で未設定として 500 を返す
    api_secret: str = field(
        default_factory=lambda: os.getenv(
            "VERITAS_API_SECRET",
            "",
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

    # ★ M-6 修正: _dirs_ensured を正式な dataclass フィールドとして宣言
    _dirs_ensured: bool = field(default=False, init=False, repr=False)
    _dirs_lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def __post_init__(self):
        # --- API secret 未設定の警告 ---
        if not self.api_secret:
            logging.getLogger(__name__).warning(
                "VERITAS_API_SECRET is not set. "
                "The API will reject authenticated requests until a secret is configured."
            )

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

    def ensure_dirs(self) -> None:
        """必要なディレクトリを作成する（初回呼び出し時のみ実行）"""
        with self._dirs_lock:
            if self._dirs_ensured:
                return
            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
                self.dataset_dir.mkdir(parents=True, exist_ok=True)
                self.data_dir.mkdir(parents=True, exist_ok=True)
                self.kv_path.parent.mkdir(parents=True, exist_ok=True)
                self._dirs_ensured = True
            except OSError as e:
                logging.getLogger(__name__).warning(
                    "Failed to create directories: %s", e
                )


    def __repr__(self) -> str:
        """API秘密鍵がログに漏洩しないよう、マスクした表現を返す"""
        return (
            f"VeritasConfig(api_key_str='***', api_secret='***', "
            f"repo_root={self.repo_root!r}, log_dir={self.log_dir!r})"
        )

    @property
    def api_secret_configured(self) -> bool:
        """API Secret が正しく設定されているかどうかを返す。

        空文字やプレースホルダー値の場合は False を返す。
        認証バイパスリスクの明示的チェックに使用する。
        """
        secret = self.api_secret.strip()
        if not secret:
            return False
        if secret == "YOUR_VERITAS_API_SECRET_HERE":
            return False
        return True


cfg = VeritasConfig()

# サブ設定インスタンス（各モジュールからインポート可能）
scoring_cfg = ScoringConfig()
fuji_cfg = FujiConfig()
pipeline_cfg = PipelineConfig()

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
import sys
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


def _parse_str(env_key: str, default: str = "") -> str:
    """環境変数から文字列を取得し、前後空白を除去して返す。"""
    return (os.getenv(env_key, default) or "").strip()


def _resolve_runtime_namespace() -> str:
    """Resolve runtime namespace (dev/test/demo/prod) from environment."""
    explicit = _parse_str("VERITAS_RUNTIME_NAMESPACE")
    if explicit:
        return explicit.lower()

    env_profile = _parse_str("VERITAS_ENV").lower()
    mapping = {
        "production": "prod",
        "prod": "prod",
        "staging": "dev",
        "stage": "dev",
        "development": "dev",
        "dev": "dev",
        "test": "test",
        "testing": "test",
        "demo": "demo",
    }
    return mapping.get(env_profile, "dev")


def _resolve_runtime_root(repo_root: Path) -> Path:
    """Resolve runtime root from environment or repository default."""
    env_root = _parse_str("VERITAS_RUNTIME_ROOT")
    if env_root:
        return Path(env_root).expanduser()
    return repo_root.parent / "runtime"


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

    def __post_init__(self) -> None:
        """Clamp all scoring parameters to valid [0.0, 1.0] range."""
        for attr in (
            "intent_weather_bonus",
            "intent_health_bonus",
            "intent_learn_bonus",
            "intent_plan_bonus",
            "query_match_bonus",
            "high_stakes_threshold",
            "high_stakes_bonus",
            "persona_bias_multiplier",
            "telos_scale_base",
            "telos_scale_factor",
        ):
            val = getattr(self, attr)
            clamped = max(0.0, min(1.0, val))
            if clamped != val:
                logging.getLogger(__name__).warning(
                    "ScoringConfig.%s=%r clamped to %r", attr, val, clamped,
                )
                object.__setattr__(self, attr, clamped)


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
class EUAIActConfig:
    """EU AI Act runtime defaults for API orchestration.

    API layer can override these values via governance endpoints.
    """

    eu_ai_act_mode: bool = field(
        default_factory=lambda: _parse_bool("VERITAS_EU_AI_ACT_MODE", False)
    )
    safety_threshold: float = field(
        default_factory=lambda: _parse_float("VERITAS_SAFETY_THRESHOLD", 0.8)
    )


@dataclass
class CapabilityConfig:
    """Optional capability flags shared by core modules.

    Optional integrations are controlled explicitly by feature flags instead of
    import success/failure so that runtime behavior remains reproducible.
    """

    enable_kernel_reason: bool = field(
        default_factory=lambda: _parse_bool("VERITAS_CAP_KERNEL_REASON", True)
    )
    enable_kernel_strategy: bool = field(
        default_factory=lambda: _parse_bool("VERITAS_CAP_KERNEL_STRATEGY", True)
    )
    enable_kernel_sanitize: bool = field(
        default_factory=lambda: _parse_bool("VERITAS_CAP_KERNEL_SANITIZE", True)
    )
    enable_fuji_tool_bridge: bool = field(
        default_factory=lambda: _parse_bool("VERITAS_CAP_FUJI_TOOL_BRIDGE", True)
    )
    enable_fuji_trust_log: bool = field(
        default_factory=lambda: _parse_bool("VERITAS_CAP_FUJI_TRUST_LOG", True)
    )
    enable_fuji_yaml_policy: bool = field(
        default_factory=lambda: _parse_bool("VERITAS_CAP_FUJI_YAML_POLICY", False)
    )
    enable_memory_posix_file_lock: bool = field(
        default_factory=lambda: _parse_bool("VERITAS_CAP_MEMORY_POSIX_FILE_LOCK", True)
    )
    enable_memory_joblib_model: bool = field(
        default_factory=lambda: _parse_bool("VERITAS_CAP_MEMORY_JOBLIB_MODEL", False)
    )
    enable_memory_sentence_transformers: bool = field(
        default_factory=lambda: _parse_bool(
            "VERITAS_CAP_MEMORY_SENTENCE_TRANSFORMERS", False
        )
    )
    enable_continuation_runtime: bool = field(
        default_factory=lambda: _parse_bool("VERITAS_CAP_CONTINUATION_RUNTIME", False)
    )
    emit_manifest_on_import: bool = field(
        default_factory=lambda: _parse_bool("VERITAS_CAP_EMIT_MANIFEST", True)
    )


def emit_capability_manifest(component: str, manifest: Dict[str, bool]) -> None:
    """Emit a structured capability manifest to logs.

    This output helps operators quickly detect disabled features and prevents
    silent drift caused by environment-dependent optional imports.
    """
    disabled = sorted(name for name, enabled in manifest.items() if not enabled)
    logging.getLogger(__name__).info(
        "[CapabilityManifest] component=%s manifest=%s disabled=%s",
        component,
        manifest,
        disabled,
    )


_PLACEHOLDER_SECRETS: frozenset = frozenset({
    "your_veritas_api_secret_here",
    "changeme",
    "change-me",
    "change_me",
    "placeholder",
    "dummy",
    "secret",
    "test",
    "password",
    "example",
})


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
    secret_provider: str = field(
        default_factory=lambda: _parse_str("VERITAS_SECRET_PROVIDER", "")
    )
    api_secret_ref: str = field(
        default_factory=lambda: _parse_str("VERITAS_API_SECRET_REF", "")
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
    runtime_root: Path | None = None
    runtime_namespace: str = field(default_factory=_resolve_runtime_namespace)
    runtime_dir: Path | None = None
    dataset_dir: Path | None = None
    memory_path: Path | None = None
    value_stats_path: Path | None = None

    trust_log_path: Path | None = None
    kv_path: Path | None = None
    doctor_auto_log_path: Path | None = None
    doctor_auto_err_path: Path | None = None

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

        # runtime ルート / namespace / ディレクトリ
        if self.runtime_root is None:
            self.runtime_root = _resolve_runtime_root(self.repo_root)
        if self.runtime_dir is None:
            self.runtime_dir = self.runtime_root / self.runtime_namespace

        # --- PATH 決定 ---
        if self.log_dir is None:
            self.log_dir = self.runtime_dir / "logs"

        if self.dataset_dir is None:
            self.dataset_dir = self.runtime_dir / "datasets"

        if self.data_dir is None:
            self.data_dir = self.runtime_dir / "data"

        if self.memory_path is None:
            self.memory_path = self.data_dir / "memory.json"

        if self.value_stats_path is None:
            self.value_stats_path = self.data_dir / "value_stats.json"

        if self.trust_log_path is None:
            self.trust_log_path = self.log_dir / "trust_log.json"

        if self.kv_path is None:
            self.kv_path = self.data_dir / "kv.sqlite3"

        if self.doctor_auto_log_path is None:
            self.doctor_auto_log_path = self.log_dir / "doctor" / "doctor_auto.log"

        if self.doctor_auto_err_path is None:
            self.doctor_auto_err_path = self.log_dir / "doctor" / "doctor_auto.err"

    def validate_api_secret_non_empty(self) -> None:
        """Validate that ``VERITAS_API_SECRET`` is configured securely.

        Raises:
            ValueError: When the configured secret is empty or placeholder.
        """
        if self.api_secret_configured:
            return

        raise ValueError(
            "VERITAS_API_SECRET is empty or placeholder. "
            "Refusing to start without a configured API secret."
        )

    def validate_secret_manager_integration(self) -> None:
        """Validate secret manager integration when strict mode is enabled.

        Strict mode is controlled by ``VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER``
        or by the posture-derived default (secure/prod postures enable it).
        When enabled, the deployment must provide both:
        - ``VERITAS_SECRET_PROVIDER``: the provider identifier
        - ``VERITAS_API_SECRET_REF``: external secret reference name/path

        Raises:
            ValueError: When strict mode is on and required metadata is missing.
        """
        explicit = os.getenv("VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER")
        if explicit is not None:
            enforced = _parse_bool("VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER", False)
        else:
            try:
                from veritas_os.core.posture import get_active_posture
                enforced = get_active_posture().external_secret_manager_required
            except Exception:
                enforced = False
        if not enforced:
            return

        allowed_providers = {
            "vault",
            "aws_secrets_manager",
            "gcp_secret_manager",
            "azure_key_vault",
            "kms",
        }
        provider = self.secret_provider.strip().lower()
        if provider not in allowed_providers:
            raise ValueError(
                "VERITAS_SECRET_PROVIDER must be one of "
                f"{sorted(allowed_providers)} when "
                "VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER=1."
            )

        if not self.api_secret_ref:
            raise ValueError(
                "VERITAS_API_SECRET_REF must be set when "
                "VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER=1."
            )

        if not self.api_secret_configured:
            raise ValueError(
                "VERITAS_API_SECRET must be injected at runtime from the configured "
                "external secret manager."
            )

    @staticmethod
    def should_enforce_api_secret_validation() -> bool:
        """Return whether startup should fail on missing API secret.

        Enforcement is enabled by default, but is automatically relaxed under
        pytest to preserve unit test isolation unless explicitly overridden.
        """
        enforce = _parse_bool("VERITAS_ENFORCE_API_SECRET", True)
        if not enforce:
            return False

        if _parse_bool("VERITAS_ENFORCE_API_SECRET_IN_TESTS", False):
            return True

        if "pytest" in sys.modules:
            return False

        return True

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
                self.doctor_auto_log_path.parent.mkdir(parents=True, exist_ok=True)
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
        if secret.lower() in _PLACEHOLDER_SECRETS:
            return False
        return True


cfg = VeritasConfig()

# NOTE: API secret validation は server startup 時に明示的に呼び出す。
# インポート時の副作用を排除し、テスト環境でのバイパスリスクを防止する。
# → veritas_os/api/server.py の _startup_validate_config() を参照。


def validate_startup_config() -> None:
    """サーバ起動時に呼び出す設定検証。

    インポート時ではなく起動時に実行することで:
    - テスト環境での意図しないバイパスを防止
    - 検証失敗時のエラーメッセージが明確になる
    - モジュールインポートの副作用を排除
    """
    if cfg.should_enforce_api_secret_validation():
        cfg.validate_api_secret_non_empty()

    cfg.validate_secret_manager_integration()


# サブ設定インスタンス（各モジュールからインポート可能）
scoring_cfg = ScoringConfig()
fuji_cfg = FujiConfig()
pipeline_cfg = PipelineConfig()
capability_cfg = CapabilityConfig()
eu_ai_act_cfg = EUAIActConfig()

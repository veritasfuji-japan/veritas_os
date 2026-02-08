# veritas_os/core/world.py
"""
VERITAS WorldOS - Unified World State Management

統合版: world_model.py と world.py の機能を統合
- プロジェクトベースの状態管理（WorldModel）
- 外部知識統合（AGI research events）
- 因果履歴（transitions）
- 後方互換API（snapshot / simulate / update_state_from_decision）

テスト安定化ポイント:
- WORLD_PATH / DATA_DIR を「動的に解決」できる PathLike にする
  -> monkeypatch.setenv / monkeypatch.setattr のどちらでも確実に反映される
- _load_world / _save_world は必ず “現在の WORLD_PATH” を参照する
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional

# fcntl はプロセス間排他制御 (flock) に使用。Windows では利用不可。
_IS_WIN = os.name == "nt"
if not _IS_WIN:
    try:
        import fcntl
    except ImportError:  # pragma: no cover
        fcntl = None  # type: ignore[assignment]
else:
    fcntl = None  # type: ignore[assignment]

from .utils import _clip01

logger = logging.getLogger(__name__)


# ============================================================
# Dynamic Path (monkeypatch-friendly)
# ============================================================

class DynamicPath(os.PathLike):
    """
    env/monkeypatch の変更に追随できる PathLike。
    - __fspath__ を実装しているため Path(os.fspath(obj)) で Path 化できる
    - .exists() など主要メソッドは Path に委譲
    """
    def __init__(self, resolver: Callable[[], Path]) -> None:
        self._resolver = resolver

    def _p(self) -> Path:
        p = self._resolver()
        if not isinstance(p, Path):
            p = Path(str(p))
        return p

    def __fspath__(self) -> str:
        return str(self._p())

    def __str__(self) -> str:
        return str(self._p())

    def __repr__(self) -> str:
        return f"DynamicPath({self._p()!s})"

    # frequently-used Path methods
    def exists(self) -> bool:
        return self._p().exists()

    def open(self, *args: Any, **kwargs: Any):
        return self._p().open(*args, **kwargs)

    def mkdir(self, *args: Any, **kwargs: Any) -> None:
        self._p().mkdir(*args, **kwargs)

    def unlink(self, *args: Any, **kwargs: Any) -> None:
        self._p().unlink(*args, **kwargs)

    def read_text(self, *args: Any, **kwargs: Any) -> str:
        return self._p().read_text(*args, **kwargs)

    def write_text(self, *args: Any, **kwargs: Any) -> int:
        return self._p().write_text(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        # fallback delegation (e.g. .parent, .suffix, .name ...)
        return getattr(self._p(), name)


# ============================================================
# Paths (env-first, monkeypatch-friendly)
# ============================================================

DEFAULT_USER_ID = "global"

# Import shared security constants
try:
    from veritas_os.api.constants import SENSITIVE_SYSTEM_PATHS
except ImportError:
    # Fallback for testing or standalone usage
    SENSITIVE_SYSTEM_PATHS: frozenset[str] = frozenset([
        "/etc", "/var/run", "/proc", "/sys", "/dev", "/boot"
    ])


def _first_env(*keys: str) -> Optional[str]:
    """最初に見つかった env を返す（未設定なら None）"""
    for k in keys:
        v = os.getenv(k)
        if v:
            return v
    return None


def _validate_path_safety(path: Path, context: str = "path") -> Path:
    """
    Validate that a path does not point to sensitive system directories.

    Args:
        path: The path to validate
        context: Context string for error messages

    Returns:
        The validated path (resolved)

    Raises:
        ValueError: If path points to a sensitive system directory
    """
    try:
        resolved = path.resolve()
        resolved_str = str(resolved)
        for sensitive in SENSITIVE_SYSTEM_PATHS:
            if resolved_str.startswith(sensitive + "/") or resolved_str == sensitive:
                logger.warning(
                    f"Attempted to use sensitive path for {context}: {resolved}"
                )
                raise ValueError(
                    f"Cannot use sensitive system path for {context}: {resolved}"
                )
        return resolved
    except OSError as e:
        logger.warning(f"Path resolution failed for {context}: {e}")
        raise


def _resolve_data_dir() -> Path:
    """tests / users の両方に優しい data dir resolver"""
    base = _first_env(
        "VERITAS_DATA_DIR",
        "VERITAS_DIR",
        "VERITAS_HOME",
        "VERITAS_PATH",
    )
    path = Path(base if base else "~/veritas").expanduser()
    try:
        return _validate_path_safety(path, "data directory")
    except ValueError:
        # Fall back to default on validation failure
        default_path = Path.home() / "veritas"
        logger.warning(f"Using default data directory: {default_path}")
        return default_path


def _resolve_world_path() -> Path:
    """Resolve the world state file path with security validation."""
    default_path = Path.home() / "veritas" / "world_state.json"

    # 1) ファイルパスを直指定できる系を最優先
    explicit = (
        os.getenv("VERITAS_WORLD_PATH")
        or os.getenv("VERITAS_WORLD_STATE_PATH")
        or os.getenv("WORLD_STATE_PATH")
    )
    if explicit:
        path = Path(explicit).expanduser()
        try:
            return _validate_path_safety(path, "world state")
        except ValueError:
            logger.warning(f"Invalid explicit path, using default: {default_path}")
            return default_path

    # 2) データディレクトリ指定系（tests がこっちを setenv してる可能性が高い）
    base = (
        os.getenv("VERITAS_DATA_DIR")
        or os.getenv("VERITAS_PATH")
        or os.getenv("VERITAS_HOME")
        or os.getenv("VERITAS_DIR")
    )
    if base:
        path = Path(base).expanduser() / "world_state.json"
        try:
            return _validate_path_safety(path, "world state")
        except ValueError:
            logger.warning(f"Invalid base path, using default: {default_path}")
            return default_path

    # 3) デフォルト
    return default_path


# ------------------------------------------------------------
# Backward-compat + monkeypatch friendly globals (MUST exist)
# ------------------------------------------------------------
# ✅ tests expect: world.WORLD_PATH / world.DATA_DIR to exist as module attrs
DATA_DIR: os.PathLike = DynamicPath(_resolve_data_dir)
WORLD_PATH: os.PathLike = DynamicPath(_resolve_world_path)

# optional legacy alias
WORLD_STATE_PATH = WORLD_PATH


def _data_dir(create: bool = True) -> Path:
    d = Path(os.fspath(DATA_DIR)).expanduser()
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _world_path() -> Path:
    """
    ✅ 重要:
    - WORLD_PATH が DynamicPath のままでも OK
    - monkeypatch.setattr(world, "WORLD_PATH", Path(...)) でも OK
    """
    wp = WORLD_PATH
    if isinstance(wp, Path):
        return wp.expanduser()
    return Path(os.fspath(wp)).expanduser()


# ============================================================
# File Lock (プロセス間 read-modify-write 排他制御)
# ============================================================

@contextlib.contextmanager
def _world_file_lock() -> Generator[None, None, None]:
    """
    world_state.json に対するプロセス間排他ロック。

    fcntl.flock(LOCK_EX) を使用して、read-modify-write サイクル全体を
    アトミックにする。ロックファイルは world_state.json.lock に配置。

    fcntl が利用できない環境 (Windows 等) ではノーオペレーション。
    """
    if fcntl is None:
        yield
        return

    lock_path = Path(str(_world_path()) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fd = None
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError as e:
                logger.debug("flock unlock failed (non-critical): %s", e)
            try:
                os.close(fd)
            except OSError as e:
                logger.debug("lock fd close failed (non-critical): %s", e)


# ============================================================
# WorldState structures
# ============================================================

@dataclass
class WorldState:
    """ユーザー/プロジェクトごとのワールド状態（従来互換）"""
    user_id: str = DEFAULT_USER_ID

    # 決定ログから学ぶ統計
    decisions: int = 0
    avg_latency_ms: float = 0.0
    avg_risk: float = 0.0
    avg_value: float = 0.5

    # 進行中のプラン
    active_plan_id: Optional[str] = None
    active_plan_title: Optional[str] = None
    active_plan_steps: int = 0
    active_plan_done: int = 0

    # 最新コンテキスト
    last_query: str = ""
    last_chosen_title: str = ""
    last_decision_status: str = "unknown"

    # メタ
    last_updated: str = ""

    def progress(self) -> float:
        if not self.active_plan_steps:
            return 0.0
        return max(0.0, min(1.0, self.active_plan_done / float(self.active_plan_steps)))


@dataclass
class WorldTransition:
    """因果モデル用: 1 decision に対応する「予測 vs 観測」の記録"""
    ts: str
    user_id: str
    project_id: str
    query: str

    predicted_utility: float
    predicted_risk: float
    predicted_value: float

    observed_gate_status: str
    observed_risk: float
    observed_value: float
    observed_latency_ms: Optional[float] = None

    prediction_error: float = 0.0


# ============================================================
# Default world schema (v2)
# ============================================================

DEFAULT_WORLD: Dict[str, Any] = {
    "schema_version": "2.0.0",
    "updated_at": None,
    "meta": {
        "version": "2.0",
        "created_at": None,
        "last_users": {},
    },
    "projects": [],
    "veritas": {
        "progress": 0.0,
        "decision_count": 0,
        "last_risk": 0.0,
    },
    "metrics": {
        "value_ema": 0.0,
        "latency_ms_median": 0.0,
        "error_rate": 0.0,
    },
    "external_knowledge": {
        "agi_research_events": [],
        "agi_research": {},
    },
    "history": {
        "decisions": [],
        "transitions": [],
    },
}


# ============================================================
# Utilities
# ============================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# _clip01 は utils.py からインポート


def _ensure_v2_shape(state: dict) -> dict:
    """
    v1 互換を保ちつつ、v2.0 の最低限のフィールドを保証
    「足りないキーだけ追加」
    """
    if not isinstance(state, dict):
        state = deepcopy(DEFAULT_WORLD)

    meta = state.setdefault("meta", {})
    meta.setdefault("version", "2.0")
    meta.setdefault("created_at", _now_iso())
    meta.setdefault("last_users", {})

    veritas = state.setdefault("veritas", {})
    veritas.setdefault("progress", 0.0)
    veritas.setdefault("decision_count", 0)
    veritas.setdefault("last_risk", 0.0)

    metrics = state.setdefault("metrics", {})
    metrics.setdefault("value_ema", 0.0)
    metrics.setdefault("latency_ms_median", 0.0)
    metrics.setdefault("error_rate", 0.0)

    if "projects" not in state:
        state["projects"] = []

    history = state.setdefault("history", {})
    history.setdefault("decisions", [])
    history.setdefault("transitions", [])

    ext = state.setdefault("external_knowledge", {})
    ext.setdefault("agi_research_events", [])
    ext.setdefault("agi_research", {})

    state.setdefault("schema_version", "2.0.0")
    state.setdefault("updated_at", _now_iso())
    return state


def _atomic_write_json(path: Path, payload: dict) -> None:
    """
    atomic save:
    - write to temp file in same directory
    - fsync
    - replace
    
    ★ セキュリティ修正:
    - ディレクトリのパーミッションを制限（0o755）
    - 一時ファイルの作成に安全なtempfile.mkstempを使用
    - finallyブロックで確実にクリーンアップ
    """
    # ★ セキュリティ修正: 親ディレクトリを安全に作成（パーミッション制限）
    parent_dir = path.parent
    parent_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
    
    # ★ セキュリティ修正: ディレクトリのパーミッションを確認・修正
    try:
        current_mode = parent_dir.stat().st_mode & 0o777
        # 0o022 = group write (0o020) + other write (0o002)
        # このビットがセットされている場合、書き込み権限を除去
        if current_mode & 0o022:
            os.chmod(parent_dir, current_mode & ~0o022)
    except OSError:
        pass  # パーミッション変更に失敗しても処理続行
    
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=".world_state.", suffix=".tmp", dir=str(parent_dir))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        # ★ セキュリティ修正: 一時ファイルのクリーンアップを確実に実行
        try:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        except OSError:
            pass


# ============================================================
# External knowledge summary (light)
# ============================================================

def _load_memory_agi_summary(state: dict) -> dict:
    try:
        ext = state.get("external_knowledge") or {}
        events = ext.get("agi_research_events") or []
        if not isinstance(events, list) or not events:
            return {}

        last = events[-1]
        if not isinstance(last, dict):
            return {}

        titles: list[str] = []
        urls: list[str] = []
        for p in last.get("papers") or []:
            if not isinstance(p, dict):
                continue
            t = p.get("title") or ""
            u = p.get("url") or ""
            if t:
                titles.append(t)
            if u:
                urls.append(u)

        return {
            "count": len(events),
            "last_ts": last.get("ts"),
            "last_query": last.get("query"),
            "last_titles": titles[:5],
            "last_urls": urls[:5],
            "last_summary": last.get("summary", ""),
        }
    except Exception:
        return {}


# ============================================================
# Load / Save
# ============================================================

def _load_world() -> Dict[str, Any]:
    """
    world_state.json を読み込む（なければデフォルト構造を返す）
    NOTE: “作る”のはディレクトリだけ（ファイルは生成しない） -> テスト要件
    """
    try:
        _data_dir(create=True)
        path = _world_path()

        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                data = deepcopy(DEFAULT_WORLD)

            # legacy migration: { "user_id": {...}, ... } -> v2 schema
            if "projects" not in data and "schema_version" not in data:
                projects: List[Dict[str, Any]] = []
                for uid, raw in data.items():
                    if not isinstance(raw, dict):
                        continue

                    metrics = {
                        "decisions": int(raw.get("decisions", 0)),
                        "avg_latency_ms": float(raw.get("avg_latency_ms", 0.0)),
                        "avg_risk": float(raw.get("avg_risk", 0.0)),
                        "avg_value": float(raw.get("avg_value", 0.5)),
                        "active_plan_steps": int(raw.get("active_plan_steps", 0)),
                        "active_plan_done": int(raw.get("active_plan_done", 0)),
                    }
                    last = {
                        "query": raw.get("last_query", ""),
                        "chosen_title": raw.get("last_chosen_title", ""),
                        "decision_status": raw.get("last_decision_status", "unknown"),
                    }

                    projects.append({
                        "project_id": f"{uid}:default",
                        "owner_user_id": uid,
                        "title": f"Default Project for {uid}",
                        "objective": "",
                        "status": "active",
                        "tags": [],
                        "created_at": raw.get("last_updated") or _now_iso(),
                        "last_decision_at": raw.get("last_updated"),
                        "metrics": metrics,
                        "last": last,
                        "decisions": [],
                    })

                data = {
                    "schema_version": "2.0.0",
                    "updated_at": _now_iso(),
                    "meta": {"version": "2.0", "created_at": _now_iso(), "last_users": {}},
                    "projects": projects,
                    "veritas": {"progress": 0.0, "decision_count": 0, "last_risk": 0.0},
                    "metrics": {"value_ema": 0.0, "latency_ms_median": 0.0, "error_rate": 0.0},
                    "external_knowledge": {"agi_research_events": [], "agi_research": {}},
                    "history": {"decisions": [], "transitions": []},
                }

            return _ensure_v2_shape(data)

        default_state = deepcopy(DEFAULT_WORLD)
        default_state["meta"]["created_at"] = _now_iso()
        return _ensure_v2_shape(default_state)

    except Exception:
        default_state = deepcopy(DEFAULT_WORLD)
        default_state["meta"]["created_at"] = _now_iso()
        return _ensure_v2_shape(default_state)


def _save_world(world: Dict[str, Any]) -> None:
    try:
        world = _ensure_v2_shape(world)
        world["updated_at"] = _now_iso()
        world["schema_version"] = "2.0.0"

        path = _world_path()
        _atomic_write_json(path, world)
        logger.debug("state saved -> %s", path)
    except Exception as e:
        logger.warning("save error: %s", e)


# ============================================================
# Project management (compat)
# ============================================================

def _ensure_project(state: dict, project_id: str, title: str):
    projects = state.get("projects")

    # 後方互換: dict のまま保つ
    if isinstance(projects, dict):
        if project_id not in projects:
            projects[project_id] = {
                "project_id": project_id,
                "title": title,
                "name": title,
                "status": "active",
            }
        return projects[project_id]

    # 新形式: list のまま保つ
    if not isinstance(projects, list):
        projects = []
        state["projects"] = projects

    for p in projects:
        if isinstance(p, dict) and p.get("project_id") == project_id:
            return p

    p = {
        "project_id": project_id,
        "title": title,
        "name": title,
        "status": "active",
    }
    projects.append(p)
    return p


def _get_or_create_default_project(world: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    proj_id = f"{user_id}:default"

    # ✅ tests: projects が dict のとき list に正規化されること
    projects = world.get("projects")
    if isinstance(projects, dict):
        normalized: List[Dict[str, Any]] = []
        for k, v in projects.items():
            if not isinstance(v, dict):
                continue  # "broken": "ignore_me" を捨てる
            # project_id が無い dict でも最低限補完
            v.setdefault("project_id", k)
            normalized.append(v)
        world["projects"] = normalized

    # ✅ 以降は通常処理（list 前提で _ensure_project を通る）
    proj = _ensure_project(world, proj_id, f"Default Project for {user_id}")

    # ensure minimal keys
    proj.setdefault("owner_user_id", user_id)
    proj.setdefault("objective", "")
    proj.setdefault("tags", [])
    proj.setdefault("created_at", _now_iso())
    proj.setdefault("last_decision_at", None)
    proj.setdefault("metrics", {
        "decisions": 0,
        "avg_latency_ms": 0.0,
        "avg_risk": 0.0,
        "avg_value": 0.5,
        "active_plan_steps": 0,
        "active_plan_done": 0,
    })
    proj.setdefault("last", {
        "query": "",
        "chosen_title": "",
        "decision_status": "unknown",
    })
    proj.setdefault("decisions", [])
    return proj



def _project_to_worldstate(user_id: str, proj: Dict[str, Any]) -> WorldState:
    m = proj.get("metrics") or {}
    last = proj.get("last") or {}
    return WorldState(
        user_id=user_id,
        decisions=int(m.get("decisions", 0)),
        avg_latency_ms=float(m.get("avg_latency_ms", 0.0)),
        avg_risk=float(m.get("avg_risk", 0.0)),
        avg_value=float(m.get("avg_value", 0.5)),
        active_plan_id=proj.get("active_plan_id"),
        active_plan_title=proj.get("active_plan_title"),
        active_plan_steps=int(m.get("active_plan_steps", 0)),
        active_plan_done=int(m.get("active_plan_done", 0)),
        last_query=str(last.get("query", "")),
        last_chosen_title=str(last.get("chosen_title", "")),
        last_decision_status=str(last.get("decision_status", "unknown")),
        last_updated=str(proj.get("last_decision_at") or ""),
    )


# ============================================================
# Public API - basic
# ============================================================

def load_state(user_id: str = DEFAULT_USER_ID) -> WorldState:
    world = _load_world()
    proj = _get_or_create_default_project(world, user_id)
    return _project_to_worldstate(user_id, proj)


def save_state(state: WorldState) -> None:
    with _world_file_lock():
        world = _load_world()
        proj = _get_or_create_default_project(world, state.user_id)

        m = proj.setdefault("metrics", {})
        m["decisions"] = int(state.decisions)
        m["avg_latency_ms"] = float(state.avg_latency_ms)
        m["avg_risk"] = float(state.avg_risk)
        m["avg_value"] = float(state.avg_value)
        m["active_plan_steps"] = int(state.active_plan_steps)
        m["active_plan_done"] = int(state.active_plan_done)

        proj["active_plan_id"] = state.active_plan_id
        proj["active_plan_title"] = state.active_plan_title

        last = proj.setdefault("last", {})
        last["query"] = state.last_query
        last["chosen_title"] = state.last_chosen_title
        last["decision_status"] = state.last_decision_status
        proj["last_decision_at"] = state.last_updated or _now_iso()

        _save_world(world)


def get_state(user_id: str = DEFAULT_USER_ID) -> dict:
    # user_id is reserved for future scoping; currently returns full world
    return _load_world()


def snapshot(project: str) -> Dict[str, Any]:
    state = get_state() or {}

    proj = state.get(project)
    if isinstance(proj, dict):
        return proj

    ver = state.get("veritas")
    if isinstance(ver, dict):
        return {
            "progress": float(ver.get("progress", 0.0) or 0.0),
            "decision_count": int(ver.get("decision_count", 0) or 0),
        }

    if isinstance(state, dict) and ("progress" in state or "decision_count" in state):
        return {
            "progress": float(state.get("progress", 0.0) or 0.0),
            "decision_count": int(state.get("decision_count", 0.0) or 0),
        }
    return {}


# ============================================================
# Public API - update from decision
# ============================================================

def update_from_decision(
    *,
    user_id: str,
    query: str,
    chosen: Dict[str, Any],
    gate: Dict[str, Any],
    values: Dict[str, Any],
    planner: Optional[Dict[str, Any]] = None,
    latency_ms: Optional[float] = None,
) -> WorldState:
    with _world_file_lock():
        world = _load_world()
        proj = _get_or_create_default_project(world, user_id)
        metrics = proj.setdefault("metrics", {})
        last = proj.setdefault("last", {})

        decisions = int(metrics.get("decisions", 0)) + 1
        metrics["decisions"] = decisions

        alpha = 0.2
        risk = float(gate.get("risk", 0.0) or 0.0)
        val = float(values.get("total", values.get("ema", 0.5)) or 0.5)

        prev_risk = float(metrics.get("avg_risk", 0.0) or 0.0)
        prev_val = float(metrics.get("avg_value", 0.5) or 0.5)

        metrics["avg_risk"] = (1 - alpha) * prev_risk + alpha * risk
        metrics["avg_value"] = (1 - alpha) * prev_val + alpha * val

        if latency_ms is not None:
            prev_lat = float(metrics.get("avg_latency_ms", 0.0) or 0.0)
            metrics["avg_latency_ms"] = (1 - alpha) * prev_lat + alpha * float(latency_ms)

        if planner:
            steps = planner.get("steps") or []
            proj["active_plan_id"] = planner.get("id") or planner.get("plan_id")
            proj["active_plan_title"] = planner.get("title") or planner.get("name")
            metrics["active_plan_steps"] = int(len(steps) or metrics.get("active_plan_steps", 0))

            done = 0
            for s in steps:
                if isinstance(s, dict) and s.get("done"):
                    done += 1
            metrics["active_plan_done"] = int(done or metrics.get("active_plan_done", 0))

        last["query"] = query
        last["chosen_title"] = (chosen or {}).get("title") or str(chosen)[:80]
        last["decision_status"] = gate.get("decision_status") or "unknown"
        proj["last_decision_at"] = _now_iso()

        req_id = (chosen or {}).get("request_id") or values.get("request_id") or ""
        proj.setdefault("decisions", []).append({
            "request_id": req_id,
            "ts": proj["last_decision_at"],
            "query": query,
            "chosen_title": last["chosen_title"],
            "decision_status": last["decision_status"],
            "avg_value_after": metrics["avg_value"],
            "avg_risk_after": metrics["avg_risk"],
        })

        veritas = world.setdefault("veritas", {})
        veritas["decision_count"] = int(veritas.get("decision_count", 0)) + 1
        veritas["last_risk"] = risk

        history = world.setdefault("history", {})
        decisions_hist = history.setdefault("decisions", [])
        decisions_hist.append({
            "ts": proj["last_decision_at"],
            "user_id": user_id,
            "project_id": proj.get("project_id", f"{user_id}:default"),
            "query": query,
            "chosen_id": (chosen or {}).get("id"),
            "chosen_title": last["chosen_title"],
            "gate_status": gate.get("status"),
            "gate_risk": risk,
            "value_total": val,
            "plan_steps": len(planner.get("steps", [])) if planner else 0,
        })
        if len(decisions_hist) > 200:
            history["decisions"] = decisions_hist[-200:]

        meta = world.setdefault("meta", {})
        last_users = meta.setdefault("last_users", {})
        last_users[user_id] = {
            "last_seen": proj["last_decision_at"],
            "last_project": proj.get("project_id"),
        }

        _save_world(world)
        return _project_to_worldstate(user_id, proj)


def update_state_from_decision(
    user_id: str,
    query: str,
    chosen: dict,
    gate: dict,
) -> None:
    update_from_decision(
        user_id=user_id,
        query=query,
        chosen=chosen,
        gate=gate,
        values={},
    )


# ============================================================
# Public API - context injection
# ============================================================

def inject_state_into_context(context: Dict[str, Any], user_id: str = DEFAULT_USER_ID) -> Dict[str, Any]:
    ctx = dict(context or {})

    with _world_file_lock():
        state_data = _load_world()

        ctx["world_state"] = state_data

        # state_data から直接導出 (二重 I/O を回避)
        proj = _get_or_create_default_project(state_data, user_id)
        st = _project_to_worldstate(user_id, proj)
        ctx.setdefault("world_state", {}).update({
            "decisions": st.decisions,
            "avg_latency_ms": st.avg_latency_ms,
            "avg_risk": st.avg_risk,
            "avg_value": st.avg_value,
            "plan_progress": st.progress(),
            "active_plan_title": st.active_plan_title,
            "last_query": st.last_query,
            "last_chosen_title": st.last_chosen_title,
            "last_decision_status": st.last_decision_status,
            "last_updated": st.last_updated,
        })

        projects = state_data.get("projects", [])
        veritas_proj: Dict[str, Any] = {}
        if isinstance(projects, list):
            for p in projects:
                if isinstance(p, dict) and (
                    p.get("project_id") == "veritas_agi"
                    or "veritas" in str(p.get("project_id", "")).lower()
                ):
                    veritas_proj = p
                    break
        elif isinstance(projects, dict):
            veritas_proj = projects.get("veritas_agi", {})

        world_summary = {
            "projects": {
                "veritas_agi": {
                    "name": veritas_proj.get("title") or veritas_proj.get("name", "VERITASのAGI化"),
                    "status": veritas_proj.get("status", "unknown"),
                    "progress": float(veritas_proj.get("progress", 0.0) or 0.0),
                    "last_decision_ts": veritas_proj.get("last_decision_at") or veritas_proj.get("last_decision_ts"),
                    "notes": veritas_proj.get("notes", ""),
                    "decision_count": int(veritas_proj.get("decision_count", 0) or 0),
                    "last_risk": float(veritas_proj.get("last_risk", 0.3) or 0.3),
                }
            },
            "external_knowledge": _load_memory_agi_summary(state_data),
        }
        ctx["world"] = world_summary

        meta = state_data.setdefault("meta", {})
        last_users = meta.setdefault("last_users", {})
        last_users[user_id] = {
            "last_seen": _now_iso(),
            "last_project": veritas_proj.get("project_id") if veritas_proj else None,
        }
        _save_world(state_data)

    return ctx


# ============================================================
# Simulation (legacy-friendly)
# ============================================================

def simulate(
    option: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    **_: Any,
) -> Dict[str, Any]:
    if option is None:
        option = {}
    if context is None:
        context = {}

    st_dict = (context or {}).get("world_state") or {}

    if (not st_dict) and user_id:
        st = load_state(user_id)
        st_dict = {
            "decisions": st.decisions,
            "avg_latency_ms": st.avg_latency_ms,
            "avg_risk": st.avg_risk,
            "avg_value": st.avg_value,
            "plan_progress": st.progress(),
            "active_plan_title": st.active_plan_title,
            "last_query": st.last_query,
            "last_chosen_title": st.last_chosen_title,
            "last_decision_status": st.last_decision_status,
            "last_updated": st.last_updated,
        }

    avg_value = float(st_dict.get("avg_value", 0.5) or 0.5)
    avg_risk = float(st_dict.get("avg_risk", 0.0) or 0.0)
    progress = float(st_dict.get("plan_progress", 0.0) or 0.0)

    base = float(option.get("score", 1.0) or 1.0)
    base01 = _clip01(base / 2.0)

    util = base01
    util *= 0.4 + 0.6 * _clip01(avg_value)
    util *= 1.0 - 0.5 * _clip01(avg_risk)
    util *= 0.7 + 0.3 * _clip01(progress)
    util = _clip01(util)

    decisions = int(st_dict.get("decisions", 0) or 0)
    confidence = 1.0 - math.exp(-decisions / 50.0)

    return {
        "utility": util,
        "confidence": confidence,
        "avg_value": avg_value,
        "avg_risk": avg_risk,
        "plan_progress": progress,
    }


def simulate_decision(
    option: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    world_state: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    if option is None:
        option = {}
    if context is None:
        context = {}

    ctx = dict(context or {})
    if world_state:
        ctx["world_state"] = world_state
    return simulate(option=option, context=ctx, user_id=user_id, **kwargs)


# ============================================================
# VERITAS AGI hint
# ============================================================

def next_hint_for_veritas_agi(user_id: str = DEFAULT_USER_ID) -> Dict[str, Any]:
    world = _load_world()
    st = load_state(user_id)

    decision_count = int(st.decisions)
    progress = float(st.progress())
    avg_value = float(st.avg_value)
    avg_risk = float(st.avg_risk)

    veritas_top = world.get("veritas", {})
    total_decisions = int(veritas_top.get("decision_count", decision_count))

    agi_summary = _load_memory_agi_summary(world)
    agi_events = int(agi_summary.get("count", 0))

    if decision_count < 5:
        hint = "まずは /v1/decide を複数回まわして、WorldState にログを溜めるフェーズです。"
        focus = "collect_decisions"
    elif progress < 0.3:
        hint = "Planner / FUJI / ValueCore の一貫性チェックを優先してください（MVPの安定化フェーズ）。"
        focus = "stabilize_pipeline"
    elif agi_events < 1:
        hint = "少なくとも1回は AGI 関連のリサーチクエリを投げて external_knowledge を埋めると良いです。"
        focus = "seed_agi_research"
    elif progress < 0.7:
        hint = "AGI研究ログと decide ログを見比べ、『どのタスクで VERITAS をベンチするか』を決める段階です。"
        focus = "design_benchmarks"
    else:
        hint = "第三者レビューに向けて README / アーキ図 / 最小デモを整えるフェーズです。"
        focus = "external_review"

    return {
        "user_id": user_id,
        "decisions_user": decision_count,
        "decisions_total": total_decisions,
        "progress": progress,
        "avg_value": avg_value,
        "avg_risk": avg_risk,
        "agi_research_events": agi_events,
        "focus": focus,
        "hint": hint,
    }


# ============================================================
# Export
# ============================================================

__all__ = [
    "WorldState",
    "WorldTransition",
    "load_state",
    "save_state",
    "get_state",
    "snapshot",
    "update_from_decision",
    "update_state_from_decision",
    "inject_state_into_context",
    "simulate",
    "simulate_decision",
    "next_hint_for_veritas_agi",
    "DEFAULT_USER_ID",
    "WORLD_PATH",
    "DATA_DIR",
    "_ensure_project",   # ✅ tests expect
    "_world_file_lock",  # テスト・外部利用向け
]








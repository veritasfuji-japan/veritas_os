# veritas_os/core/tools.py
"""
VERITAS ToolOS - Tool Execution Control & Registry

ツール実行の許可・拒否を判定し、安全に実行するモジュール。
実装例ツール: web_search, github_search, llm_safety

- ホワイトリスト方式でツール利用を制御
- ブロックリストで危険なツールを明示的に拒否
- call_tool() で安全にツール実行
- メモリ内でツール使用ログ & 統計を管理
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# =========================
# ツール実装のインポート（安全版）
# =========================
# veritas_os/tools/*.py にある実装を、無ければスキップする。

try:
    from ..tools.web_search import web_search as _web_search_impl
except Exception as e:  # pragma: no cover - 実装が無い環境でもOK
    logger.info("[ToolOS] web_search not available: %s", e)
    _web_search_impl = None  # type: ignore[assignment]

try:
    from ..tools.github_adapter import github_search_repos as _github_search_impl
except Exception as e:  # pragma: no cover
    logger.info("[ToolOS] github_search not available: %s", e)
    _github_search_impl = None  # type: ignore[assignment]

try:
    from ..tools.llm_safety import run as _llm_safety_impl
except Exception as e:  # pragma: no cover
    logger.info("[ToolOS] llm_safety not available: %s", e)
    _llm_safety_impl = None  # type: ignore[assignment]


# =========================
# ツールレジストリ
# =========================

# 許可されたツールのホワイトリスト
ALLOWED_TOOLS: Set[str] = {
    "web_search",
    "github_search",
    "llm_safety",
    # "calculator",   # TODO: 将来実装予定
    # "python_repl",  # TODO: 将来実装予定
}

# 明示的に禁止されたツール（セキュリティリスク）
BLOCKED_TOOLS: Set[str] = {
    "file_write",      # ファイル書き込み
    "system_command",  # OS コマンド
    "shell_exec",      # シェル実行
    "eval",            # 任意コード実行
    "exec",            # 任意コード実行
}

# ツール実装マッピング（存在する実装だけ登録）
TOOL_REGISTRY: Dict[str, Any] = {}

if _web_search_impl is not None:
    TOOL_REGISTRY["web_search"] = _web_search_impl

if _github_search_impl is not None:
    TOOL_REGISTRY["github_search"] = _github_search_impl

if _llm_safety_impl is not None:
    TOOL_REGISTRY["llm_safety"] = _llm_safety_impl

# ツール使用ログ（メモリ内、最新100件のみ保持）
_tool_usage_log: List[Dict[str, Any]] = []
_tool_usage_log_lock = threading.Lock()
MAX_LOG_SIZE = 100


# =========================
# 基本API
# =========================


def _get_denial_reason(tool_name: str) -> str:
    """Return a stable reason code for denied tool calls."""
    if tool_name in BLOCKED_TOOLS:
        return "blocked"
    return "not_in_whitelist"


def allowed(tool_name: str) -> bool:
    """
    ツール実行が許可されているか判定

    Args:
        tool_name: ツール名

    Returns:
        bool: True=許可, False=拒否
    """
    if not tool_name:
        logger.warning("Empty tool name")
        return False

    tool_name = str(tool_name).strip().lower()

    # 明示的にブロックされているツール
    if tool_name in BLOCKED_TOOLS:
        logger.warning("Tool explicitly blocked: %s", tool_name)
        return False

    # ホワイトリストにあるツール
    if tool_name in ALLOWED_TOOLS:
        logger.debug("Tool allowed: %s", tool_name)
        return True

    # デフォルトは拒否（ホワイトリスト方式）
    logger.warning("Tool not in whitelist: %s", tool_name)
    return False


def call_tool(kind: str, **kwargs: Any) -> Dict[str, Any]:
    """
    ツールを安全に実行する統合インターフェイス

    Args:
        kind: ツール名
        **kwargs: ツール固有の引数

    Returns:
        dict: 実行結果
            {
                "ok": bool,
                "results": List[Any] | Any,
                "error": str | None,
                "meta": dict | None
            }
    """
    normalized_kind = str(kind).strip().lower()

    # 許可チェック
    if not allowed(normalized_kind):
        error_msg = f"Tool not allowed: {normalized_kind}"
        logger.error(error_msg)

        _log_tool_usage(
            tool=normalized_kind,
            args=kwargs,
            status="denied",
            error=error_msg,
        )

        return {
            "ok": False,
            "results": [],
            "error": error_msg,
            "meta": {
                "status": "denied",
                "reason": _get_denial_reason(normalized_kind),
            },
        }

    # ツール実装の取得
    tool_impl = TOOL_REGISTRY.get(normalized_kind)

    if not tool_impl:
        error_msg = f"Tool implementation not found: {normalized_kind}"
        logger.error(error_msg)

        _log_tool_usage(
            tool=normalized_kind,
            args=kwargs,
            status="not_implemented",
            error=error_msg,
        )

        return {
            "ok": False,
            "results": [],
            "error": error_msg,
            "meta": {
                "status": "not_implemented",
            },
        }

    # ツール実行
    try:
        start_time = datetime.now(timezone.utc)

        # ツール種別に応じた引数の正規化
        if normalized_kind == "web_search":
            result = tool_impl(
                query=kwargs.get("query", ""),
                max_results=kwargs.get("max_results", 5),
            )
        elif normalized_kind == "github_search":
            result = tool_impl(
                query=kwargs.get("query", ""),
                max_results=kwargs.get("max_results", 5),
            )
        elif normalized_kind == "llm_safety":
            result = tool_impl(
                text=kwargs.get("text", "") or kwargs.get("query", ""),
                context=kwargs.get("context") or {},
                alternatives=kwargs.get("alternatives") or [],
                max_categories=kwargs.get("max_categories", 5),
            )
        else:
            # その他のツールはそのまま引数を渡す
            result = tool_impl(**kwargs)

        end_time = datetime.now(timezone.utc)
        latency_ms = int((end_time - start_time).total_seconds() * 1000)

        # 成功ログ
        _log_tool_usage(
            tool=normalized_kind,
            args=kwargs,
            status="success",
            latency_ms=latency_ms,
            result=result,
        )

        logger.info(
            "Tool executed successfully: %s (latency: %sms)",
            normalized_kind,
            latency_ms,
        )

        # call_tool はツール実装の戻り値をそのまま返す
        return result

    except Exception as e:  # pragma: no cover - 例外パス
        error_msg = f"Tool execution error: {normalized_kind} - {str(e)}"
        logger.exception(error_msg)

        _log_tool_usage(
            tool=normalized_kind,
            args=kwargs,
            status="error",
            error=str(e),
        )

        return {
            "ok": False,
            "results": [],
            "error": error_msg,
            "meta": {
                "status": "error",
                "exception_type": type(e).__name__,
            },
        }


# =========================
# ツール管理API
# =========================

def add_allowed_tool(tool_name: str) -> None:
    """許可ツールをホワイトリストに追加"""
    tool_name = str(tool_name).strip().lower()
    ALLOWED_TOOLS.add(tool_name)
    logger.info("Tool added to whitelist: %s", tool_name)


def remove_allowed_tool(tool_name: str) -> None:
    """許可ツールをホワイトリストから削除"""
    tool_name = str(tool_name).strip().lower()
    ALLOWED_TOOLS.discard(tool_name)
    logger.info("Tool removed from whitelist: %s", tool_name)


def block_tool(tool_name: str) -> None:
    """ツールを明示的にブロック"""
    tool_name = str(tool_name).strip().lower()
    BLOCKED_TOOLS.add(tool_name)
    ALLOWED_TOOLS.discard(tool_name)
    logger.warning("Tool blocked: %s", tool_name)


def unblock_tool(tool_name: str) -> None:
    """ツールのブロックを解除"""
    tool_name = str(tool_name).strip().lower()
    BLOCKED_TOOLS.discard(tool_name)
    logger.info("Tool unblocked: %s", tool_name)


def get_allowed_tools() -> Set[str]:
    """許可されているツール一覧を取得（コピーを返す）"""
    return ALLOWED_TOOLS.copy()


def get_blocked_tools() -> Set[str]:
    """ブロックされているツール一覧を取得（コピーを返す）"""
    return BLOCKED_TOOLS.copy()


def get_available_tools() -> Dict[str, Dict[str, Any]]:
    """
    利用可能なツールの詳細情報を取得

    Returns:
        dict: ツール名 -> 詳細情報
    """
    tools: Dict[str, Dict[str, Any]] = {}

    for tool_name in ALLOWED_TOOLS:
        impl = TOOL_REGISTRY.get(tool_name)
        tools[tool_name] = {
            "name": tool_name,
            "implemented": impl is not None,
            "allowed": True,
            "blocked": False,
        }

    for tool_name in BLOCKED_TOOLS:
        tools[tool_name] = {
            "name": tool_name,
            "implemented": tool_name in TOOL_REGISTRY,
            "allowed": False,
            "blocked": True,
        }

    return tools


# =========================
# ログ管理
# =========================

def _log_tool_usage(
    tool: str,
    args: Dict[str, Any],
    status: str,
    latency_ms: Optional[int] = None,
    error: Optional[str] = None,
    result: Optional[Dict[str, Any]] = None,
) -> None:
    """
    ツール使用をメモリ内ログに記録
    """

    entry: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "status": status,
        "args": _sanitize_args(args),
    }

    if latency_ms is not None:
        entry["latency_ms"] = latency_ms

    if error:
        entry["error"] = str(error)[:500]

    if result and status == "success":
        # 結果の簡易サマリだけ持っておく
        summary: Dict[str, Any] = {
            "ok": result.get("ok"),
            "has_error": bool(result.get("error")),
        }
        if isinstance(result.get("results"), list):
            summary["result_count"] = len(result["results"])
        entry["result_summary"] = summary

    with _tool_usage_log_lock:
        _tool_usage_log.append(entry)

        # ログサイズ制限
        if len(_tool_usage_log) > MAX_LOG_SIZE:
            _tool_usage_log[:] = _tool_usage_log[-MAX_LOG_SIZE:]


_SENSITIVE_KEYWORDS = (
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
    "authorization",
    "auth",
)


def _is_sensitive_key(key: str) -> bool:
    """Return ``True`` when ``key`` appears to contain sensitive credentials."""
    normalized = key.strip().lower().replace("-", "_")
    return any(keyword in normalized for keyword in _SENSITIVE_KEYWORDS)


def _sanitize_value(value: Any) -> Any:
    """Sanitize nested values while preserving JSON-serializable structure."""
    if isinstance(value, dict):
        return _sanitize_args(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        # Keep the payload JSON-serializable for telemetry/log export.
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str) and len(value) > 200:
        return value[:200] + "..."
    return value


def _sanitize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """引数から機密情報を除外し、過度に長い文字列を切り詰める。"""
    sanitized: Dict[str, Any] = {}

    for key, value in args.items():
        if _is_sensitive_key(key):
            sanitized[key] = "***REDACTED***"
        else:
            sanitized[key] = _sanitize_value(value)

    return sanitized


def get_tool_usage_log(limit: int = 100) -> List[Dict[str, Any]]:
    """
    ツール使用ログを取得（新しい順）

    Args:
        limit: 取得する最大件数
    """
    normalized_limit = max(0, int(limit))
    if normalized_limit == 0:
        return []
    with _tool_usage_log_lock:
        return _tool_usage_log[-normalized_limit:][::-1]


def clear_tool_usage_log() -> None:
    """ツール使用ログをクリア"""
    with _tool_usage_log_lock:
        _tool_usage_log.clear()
    logger.info("Tool usage log cleared")


# =========================
# 統計情報
# =========================

def get_tool_stats() -> Dict[str, Any]:
    """
    ツール使用統計を取得

    Returns:
        dict: 統計情報
    """
    with _tool_usage_log_lock:
        snapshot = list(_tool_usage_log)

    total = len(snapshot)

    if total == 0:
        return {
            "total_calls": 0,
            "success_rate": 0.0,
            "by_tool": {},
            "by_status": {},
            "allowed_tools_count": len(ALLOWED_TOOLS),
            "blocked_tools_count": len(BLOCKED_TOOLS),
            "implemented_tools_count": len(TOOL_REGISTRY),
        }

    success = sum(1 for e in snapshot if e.get("status") == "success")

    by_tool: Dict[str, int] = {}
    by_status: Dict[str, int] = {}

    for entry in snapshot:
        tool = entry.get("tool", "unknown")
        status = entry.get("status", "unknown")
        by_tool[tool] = by_tool.get(tool, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "total_calls": total,
        "success_rate": success / total if total > 0 else 0.0,
        "by_tool": by_tool,
        "by_status": by_status,
        "allowed_tools_count": len(ALLOWED_TOOLS),
        "blocked_tools_count": len(BLOCKED_TOOLS),
        "implemented_tools_count": len(TOOL_REGISTRY),
    }


# =========================
# エクスポート
# =========================

__all__ = [
    # 基本API
    "allowed",
    "call_tool",
    # ツール管理
    "add_allowed_tool",
    "remove_allowed_tool",
    "block_tool",
    "unblock_tool",
    "get_allowed_tools",
    "get_blocked_tools",
    "get_available_tools",
    # ログ・統計
    "get_tool_usage_log",
    "clear_tool_usage_log",
    "get_tool_stats",
    # 定数
    "ALLOWED_TOOLS",
    "BLOCKED_TOOLS",
    "TOOL_REGISTRY",
]

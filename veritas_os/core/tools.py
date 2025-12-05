# veritas_os/tools/tools.py
"""
VERITAS ToolOS - Tool Execution Control & Registry

ツール実行の許可・拒否を判定し、安全に実行するモジュール
実装済みツール: web_search, github_search, llm_safety

- ホワイトリスト方式でツール利用を制御
- ブロックリストで危険なツールを明示的に拒否
- call_tool() で安全にツール実行
- メモリ内でツール使用ログ & 統計を管理
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# =========================
# ツール実装のインポート（安全版）
# =========================
# GitHub 上で一部ツールファイルが無くても import エラーで落ちないように、
# try/except でガードしておく。

try:
    from .web_search import web_search as _web_search_impl
except Exception as e:
    logger.info(f"[ToolOS] web_search not available: {e}")
    _web_search_impl = None

try:
    from .github_adapter import github_search_repos as _github_search_impl
except Exception as e:
    logger.info(f"[ToolOS] github_search not available: {e}")
    _github_search_impl = None

try:
    from .llm_safety import run as _llm_safety_impl
except Exception as e:
    logger.info(f"[ToolOS] llm_safety not available: {e}")
    _llm_safety_impl = None


# =========================
# ツールレジストリ
# =========================

# 許可されたツールのホワイトリスト
# ※ 未実装ツール（calculator / python_repl）は将来用としてコメントアウト
ALLOWED_TOOLS: Set[str] = {
    "web_search",
    "github_search",
    "llm_safety",
    # "calculator",   # TODO: 将来実装予定
    # "python_repl",  # TODO: 将来実装予定
}

# 明示的に禁止されたツール（セキュリティリスク）
BLOCKED_TOOLS: Set[str] = {
    "file_write",      # ファイル書き込みは危険
    "system_command",  # システムコマンド実行は危険
    "shell_exec",      # シェル実行は危険
    "eval",            # 任意コード実行は危険
    "exec",            # 任意コード実行は危険
}

# ツール実装マッピング（存在する実装だけ登録）
TOOL_REGISTRY: Dict[str, callable] = {}

if _web_search_impl is not None:
    TOOL_REGISTRY["web_search"] = _web_search_impl

if _github_search_impl is not None:
    TOOL_REGISTRY["github_search"] = _github_search_impl

if _llm_safety_impl is not None:
    TOOL_REGISTRY["llm_safety"] = _llm_safety_impl

# ツール使用ログ（メモリ内、最新100件のみ保持）
_tool_usage_log: List[Dict[str, Any]] = []
MAX_LOG_SIZE = 100


# =========================
# 基本API
# =========================

def allowed(tool_name: str) -> bool:
    """
    ツール実行が許可されているか判定
    
    Args:
        tool_name: ツール名
    
    Returns:
        bool: True=許可, False=拒否
    
    Examples:
        >>> allowed("web_search")
        True
        >>> allowed("shell_exec")
        False
        >>> allowed("unknown_tool")
        False
    """
    # 空文字列・Noneチェック
    if not tool_name:
        logger.warning("Empty tool name")
        return False
    
    tool_name = str(tool_name).strip().lower()
    
    # 明示的にブロックされているツール
    if tool_name in BLOCKED_TOOLS:
        logger.warning(f"Tool explicitly blocked: {tool_name}")
        return False
    
    # ホワイトリストにあるツール
    if tool_name in ALLOWED_TOOLS:
        logger.debug(f"Tool allowed: {tool_name}")
        return True
    
    # デフォルトは拒否（ホワイトリスト方式）
    logger.warning(f"Tool not in whitelist: {tool_name}")
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
    
    Examples:
        >>> result = call_tool("web_search", query="AGI research", max_results=5)
        >>> result["ok"]
        True
    """
    # 許可チェック
    if not allowed(kind):
        error_msg = f"Tool not allowed: {kind}"
        logger.error(error_msg)
        
        # ログに記録
        _log_tool_usage(
            tool=kind,
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
                "reason": "not_in_whitelist" if kind not in ALLOWED_TOOLS else "blocked",
            }
        }
    
    # ツール実装の取得
    tool_impl = TOOL_REGISTRY.get(kind)
    
    if not tool_impl:
        error_msg = f"Tool implementation not found: {kind}"
        logger.error(error_msg)
        
        _log_tool_usage(
            tool=kind,
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
            }
        }
    
    # ツール実行
    try:
        start_time = datetime.now(timezone.utc)
        
        # ツール種別に応じた引数の正規化
        if kind == "web_search":
            result = tool_impl(
                query=kwargs.get("query", ""),
                max_results=kwargs.get("max_results", 5),
            )
        elif kind == "github_search":
            result = tool_impl(
                query=kwargs.get("query", ""),
                max_results=kwargs.get("max_results", 5),
            )
        elif kind == "llm_safety":
            result = tool_impl(
                text=kwargs.get("text", "") or kwargs.get("query", ""),
                context=kwargs.get("context") or {},
                alternatives=kwargs.get("alternatives") or [],
                max_categories=kwargs.get("max_categories", 5),
            )
        else:
            # その他のツールは直接呼び出し
            result = tool_impl(**kwargs)
        
        end_time = datetime.now(timezone.utc)
        latency_ms = int((end_time - start_time).total_seconds() * 1000)
        
        # 成功ログ
        _log_tool_usage(
            tool=kind,
            args=kwargs,
            status="success",
            latency_ms=latency_ms,
            result=result,
        )
        
        logger.info(f"Tool executed successfully: {kind} (latency: {latency_ms}ms)")
        
        return result
        
    except Exception as e:
        error_msg = f"Tool execution error: {kind} - {str(e)}"
        logger.exception(error_msg)
        
        # 失敗ログ
        _log_tool_usage(
            tool=kind,
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
            }
        }


# =========================
# ツール管理API
# =========================

def add_allowed_tool(tool_name: str) -> None:
    """
    許可ツールをホワイトリストに追加
    
    Args:
        tool_name: ツール名
    """
    tool_name = str(tool_name).strip().lower()
    ALLOWED_TOOLS.add(tool_name)
    logger.info(f"Tool added to whitelist: {tool_name}")


def remove_allowed_tool(tool_name: str) -> None:
    """
    許可ツールをホワイトリストから削除
    
    Args:
        tool_name: ツール名
    """
    tool_name = str(tool_name).strip().lower()
    ALLOWED_TOOLS.discard(tool_name)
    logger.info(f"Tool removed from whitelist: {tool_name}")


def block_tool(tool_name: str) -> None:
    """
    ツールを明示的にブロック
    
    Args:
        tool_name: ツール名
    """
    tool_name = str(tool_name).strip().lower()
    BLOCKED_TOOLS.add(tool_name)
    ALLOWED_TOOLS.discard(tool_name)  # ホワイトリストからも削除
    logger.warning(f"Tool blocked: {tool_name}")


def unblock_tool(tool_name: str) -> None:
    """
    ツールのブロックを解除
    
    Args:
        tool_name: ツール名
    """
    tool_name = str(tool_name).strip().lower()
    BLOCKED_TOOLS.discard(tool_name)
    logger.info(f"Tool unblocked: {tool_name}")


def get_allowed_tools() -> Set[str]:
    """
    許可されているツール一覧を取得
    
    Returns:
        set: 許可されたツール名のセット
    """
    return ALLOWED_TOOLS.copy()


def get_blocked_tools() -> Set[str]:
    """
    ブロックされているツール一覧を取得
    
    Returns:
        set: ブロックされたツール名のセット
    """
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
    
    Args:
        tool: ツール名
        args: 引数
        status: ステータス（success/denied/error/not_implemented）
        latency_ms: レイテンシ（ミリ秒）
        error: エラーメッセージ
        result: 実行結果
    """
    global _tool_usage_log
    
    entry: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "status": status,
        "args": _sanitize_args(args),
    }
    
    if latency_ms is not None:
        entry["latency_ms"] = latency_ms
    
    if error:
        entry["error"] = str(error)[:500]  # 長すぎる場合は切り詰め
    
    if result and status == "success":
        # 結果のサマリのみ記録（容量節約）
        summary = {
            "ok": result.get("ok"),
            "has_error": bool(result.get("error")),
        }
        # results が list なら件数だけ
        if isinstance(result.get("results"), list):
            summary["result_count"] = len(result["results"])
        entry["result_summary"] = summary
    
    _tool_usage_log.append(entry)
    
    # ログサイズ制限（最新MAX_LOG_SIZE件のみ保持）
    if len(_tool_usage_log) > MAX_LOG_SIZE:
        _tool_usage_log = _tool_usage_log[-MAX_LOG_SIZE:]


def _sanitize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    引数から機密情報を除外
    
    Args:
        args: 元の引数
    
    Returns:
        dict: サニタイズされた引数
    """
    sanitized: Dict[str, Any] = {}
    
    for key, value in args.items():
        # 機密情報っぽいキーは除外
        if key.lower() in {"api_key", "token", "password", "secret"}:
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, str) and len(value) > 200:
            # 長すぎる文字列は切り詰め
            sanitized[key] = value[:200] + "..."
        else:
            sanitized[key] = value
    
    return sanitized


def get_tool_usage_log(limit: int = 100) -> List[Dict[str, Any]]:
    """
    ツール使用ログを取得
    
    Args:
        limit: 取得する最大件数
    
    Returns:
        list: ツール使用ログ（新しい順）
    """
    return _tool_usage_log[-limit:][::-1]  # 新しい順


def clear_tool_usage_log() -> None:
    """ツール使用ログをクリア"""
    global _tool_usage_log
    _tool_usage_log = []
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
    total = len(_tool_usage_log)
    
    if total == 0:
        return {
            "total_calls": 0,
            "success_rate": 0.0,
            "by_tool": {},
            "by_status": {},
        }
    
    success = sum(1 for e in _tool_usage_log if e.get("status") == "success")
    
    by_tool: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    
    for entry in _tool_usage_log:
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


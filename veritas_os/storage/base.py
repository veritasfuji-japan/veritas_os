"""Storage protocol interfaces for TrustLog and MemoryOS backends."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional, Protocol


class TrustLogStore(Protocol):
    """TrustLog 永続化の抽象インターフェース。"""

    async def append(self, entry: Dict[str, Any]) -> str:
        """エントリを追記し、割り当てられた ID を返す。"""

    async def get_by_id(self, request_id: str) -> Optional[Dict[str, Any]]:
        """request_id でエントリを取得する。"""

    async def iter_entries(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> AsyncIterator[Dict[str, Any]]:
        """エントリをページングで逐次取得する。"""

    async def get_last_hash(self) -> Optional[str]:
        """ハッシュチェーンの最新ハッシュを返す。"""


class MemoryStore(Protocol):
    """MemoryOS 永続化の抽象インターフェース。"""

    async def put(self, key: str, value: Dict[str, Any], *, user_id: str) -> None:
        """キーへ値を保存する。"""

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """キーから値を取得する。"""

    async def search(
        self,
        query: str,
        *,
        user_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """ユーザー単位で値を検索する。"""

    async def delete(self, key: str, *, user_id: str) -> bool:
        """キーを削除する。"""

    async def list_all(self, *, user_id: str) -> List[Dict[str, Any]]:
        """ユーザー単位ですべての値を返す。"""

    async def erase_user_data(self, user_id: str) -> int:
        """ユーザーの保存データを全消去し、削除件数を返す。"""

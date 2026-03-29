# -*- coding: utf-8 -*-
"""テスト用共通モック

LLM クライアント / MemoryStore / TrustLog の共通モックを提供する。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class MockLLMClient:
    """LLM クライアントのモック"""

    def __init__(
        self,
        *,
        response: str = "mock-response",
        error: Optional[Exception] = None,
    ):
        self.response = response
        self.error = error
        self.calls: List[Dict[str, Any]] = []

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """LLM 呼び出しを記録し、設定された応答を返す"""
        self.calls.append({"prompt": prompt, **kwargs})
        if self.error:
            raise self.error
        return self.response


class MockMemoryStore:
    """MemoryStore のモック"""

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}
        self._counter = 0

    def put(self, kind: str, item: Dict[str, Any]) -> str:
        """メモリエントリを保存し、ID を返す"""
        self._counter += 1
        item_id = item.get("id", f"mem-{self._counter}")
        self._data[item_id] = {"kind": kind, **item}
        return item_id

    def get(self, item_id: str) -> Optional[Dict[str, Any]]:
        """ID でメモリエントリを取得する"""
        return self._data.get(item_id)

    def search(
        self,
        query: str,
        k: int = 8,
        kinds: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """クエリでメモリを検索する"""
        results: List[Dict[str, Any]] = []
        for item in self._data.values():
            if kinds and item.get("kind") not in kinds:
                continue
            results.append(item)
        return {"results": results[:k]}

    def delete(self, item_id: str) -> bool:
        """メモリエントリを削除する"""
        if item_id in self._data:
            del self._data[item_id]
            return True
        return False


class MockTrustLog:
    """TrustLog のモック（ハッシュチェーンなし）"""

    def __init__(self) -> None:
        self.entries: List[Dict[str, Any]] = []

    def append(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """エントリを記録する"""
        entry_with_hash = {**entry, "sha256": f"mock-hash-{len(self.entries)}"}
        self.entries.append(entry_with_hash)
        return entry_with_hash

    def load(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """記録済みエントリを返す"""
        entries = list(reversed(self.entries))
        if limit:
            entries = entries[:limit]
        return entries

    def get_by_request_id(self, request_id: str) -> Optional[Dict[str, Any]]:
        """request_id でエントリを検索する"""
        for entry in self.entries:
            if entry.get("request_id") == request_id:
                return entry
        return None

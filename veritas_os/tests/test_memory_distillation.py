# tests for veritas_os/core/memory_distillation.py
"""Tests for memory distillation (episodic -> semantic)."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest import mock

import pytest

from veritas_os.core.memory_distillation import (
    build_distill_prompt,
    distill_memory_for_user,
)


class TestBuildDistillPrompt:
    def test_basic_prompt(self):
        episodes = [
            {"ts": time.time(), "text": "hello world", "tags": ["test"]},
            {"ts": time.time(), "text": "another episode"},
        ]
        prompt = build_distill_prompt("u1", episodes)
        assert "u1" in prompt
        assert "hello world" in prompt
        assert "another episode" in prompt

    def test_long_text_truncated(self):
        episodes = [{"ts": time.time(), "text": "x" * 400}]
        prompt = build_distill_prompt("u1", episodes)
        assert "..." in prompt

    def test_unknown_timestamp(self):
        episodes = [{"ts": None, "text": "test"}]
        prompt = build_distill_prompt("u1", episodes)
        assert "unknown" in prompt

    def test_empty_episodes(self):
        prompt = build_distill_prompt("u1", [])
        assert "u1" in prompt


class TestDistillMemoryForUser:
    def _make_mem_store(self, records):
        store = mock.MagicMock()
        store.list_all.return_value = records
        return store

    def _make_records(self, n=5):
        return [
            {
                "key": f"k{i}",
                "value": {
                    "kind": "episodic",
                    "text": f"Episode text number {i} with enough characters",
                    "tags": ["test"],
                },
                "ts": time.time() - i,
            }
            for i in range(n)
        ]

    def test_successful_distillation(self):
        records = self._make_records(3)
        store = self._make_mem_store(records)
        llm = mock.MagicMock()
        llm.chat_completion.return_value = {"text": "Summary of episodes"}
        put_fn = mock.MagicMock(return_value=True)

        result = distill_memory_for_user(
            "u1", mem_store=store, llm_client_module=llm, put_fn=put_fn
        )
        assert result is not None
        assert result["kind"] == "semantic"
        assert "Summary" in result["text"]
        put_fn.assert_called_once()

    def test_no_episodic_records(self):
        store = self._make_mem_store([])
        llm = mock.MagicMock()
        put_fn = mock.MagicMock()
        result = distill_memory_for_user(
            "u1", mem_store=store, llm_client_module=llm, put_fn=put_fn
        )
        assert result is None

    def test_non_episodic_filtered(self):
        records = [
            {
                "key": "k1",
                "value": {"kind": "semantic", "text": "long enough text"},
                "ts": time.time(),
            }
        ]
        store = self._make_mem_store(records)
        result = distill_memory_for_user(
            "u1", mem_store=store, llm_client_module=mock.MagicMock(), put_fn=mock.MagicMock()
        )
        assert result is None

    def test_short_text_filtered(self):
        records = [
            {"key": "k1", "value": {"kind": "episodic", "text": "hi"}, "ts": time.time()}
        ]
        store = self._make_mem_store(records)
        result = distill_memory_for_user(
            "u1", mem_store=store, llm_client_module=mock.MagicMock(), put_fn=mock.MagicMock()
        )
        assert result is None

    def test_llm_error_returns_none(self):
        records = self._make_records(1)
        store = self._make_mem_store(records)
        llm = mock.MagicMock()
        llm.chat_completion.side_effect = RuntimeError("LLM down")

        result = distill_memory_for_user(
            "u1", mem_store=store, llm_client_module=llm, put_fn=mock.MagicMock()
        )
        assert result is None

    def test_mem_store_error_returns_none(self):
        store = mock.MagicMock()
        store.list_all.side_effect = OSError("disk error")
        result = distill_memory_for_user(
            "u1", mem_store=store, llm_client_module=mock.MagicMock(), put_fn=mock.MagicMock()
        )
        assert result is None

    def test_no_chat_completion(self):
        records = self._make_records(1)
        store = self._make_mem_store(records)
        llm = object()  # No chat_completion attr
        result = distill_memory_for_user(
            "u1", mem_store=store, llm_client_module=llm, put_fn=mock.MagicMock()
        )
        assert result is None

    def test_empty_llm_response(self):
        records = self._make_records(1)
        store = self._make_mem_store(records)
        llm = mock.MagicMock()
        llm.chat_completion.return_value = {"text": ""}
        result = distill_memory_for_user(
            "u1", mem_store=store, llm_client_module=llm, put_fn=mock.MagicMock()
        )
        assert result is None

    def test_put_fn_failure(self):
        records = self._make_records(1)
        store = self._make_mem_store(records)
        llm = mock.MagicMock()
        llm.chat_completion.return_value = "Some summary"
        put_fn = mock.MagicMock(return_value=False)
        result = distill_memory_for_user(
            "u1", mem_store=store, llm_client_module=llm, put_fn=put_fn
        )
        assert result is None

    def test_openai_style_response(self):
        records = self._make_records(1)
        store = self._make_mem_store(records)
        llm = mock.MagicMock()
        llm.chat_completion.return_value = {
            "choices": [{"message": {"content": "OpenAI style summary"}}]
        }
        put_fn = mock.MagicMock(return_value=True)
        result = distill_memory_for_user(
            "u1", mem_store=store, llm_client_module=llm, put_fn=put_fn
        )
        assert result is not None
        assert "OpenAI" in result["text"]

    def test_tag_filtering(self):
        records = [
            {
                "key": "k1",
                "value": {"kind": "episodic", "text": "episode with matching tag", "tags": ["important"]},
                "ts": time.time(),
            },
            {
                "key": "k2",
                "value": {"kind": "episodic", "text": "episode without matching tag", "tags": ["other"]},
                "ts": time.time(),
            },
        ]
        store = self._make_mem_store(records)
        llm = mock.MagicMock()
        llm.chat_completion.return_value = "Filtered summary"
        put_fn = mock.MagicMock(return_value=True)
        result = distill_memory_for_user(
            "u1", mem_store=store, llm_client_module=llm, put_fn=put_fn,
            tags=["important"],
        )
        assert result is not None

    def test_model_override(self):
        records = self._make_records(1)
        store = self._make_mem_store(records)
        llm = mock.MagicMock()
        llm.chat_completion.return_value = "summary"
        put_fn = mock.MagicMock(return_value=True)
        distill_memory_for_user(
            "u1", mem_store=store, llm_client_module=llm, put_fn=put_fn,
            model="gpt-4",
        )
        call_kwargs = llm.chat_completion.call_args[1]
        assert call_kwargs.get("model") == "gpt-4"

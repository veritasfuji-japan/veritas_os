from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "search_memory.py"

spec = importlib.util.spec_from_file_location("search_memory", MODULE_PATH)
search_memory = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(search_memory)


def test_positive_int_accepts_positive_values() -> None:
    assert search_memory._positive_int("3") == 3


def test_positive_int_rejects_zero_or_negative_values() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        search_memory._positive_int("0")

    with pytest.raises(argparse.ArgumentTypeError):
        search_memory._positive_int("-1")


def test_flatten_hits_accepts_dict_and_list_payloads() -> None:
    dict_payload = {
        "doc": [{"text": "hello"}],
        "note": [{"text": "world", "kind": "custom"}],
    }
    flat_dict = search_memory._flatten_hits(dict_payload)
    assert flat_dict[0]["kind"] == "doc"
    assert flat_dict[1]["kind"] == "custom"

    list_payload = [{"text": "a"}, {"text": "b"}]
    flat_list = search_memory._flatten_hits(list_payload)
    assert len(flat_list) == 2


def test_extract_preview_text_truncates_and_normalizes_newlines() -> None:
    hit = {"text": "line1\nline2" + "x" * 250}
    preview = search_memory._extract_preview_text(hit)

    assert "\n" not in preview
    assert preview.endswith("...")
    assert len(preview) == 200

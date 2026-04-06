# -*- coding: utf-8 -*-
"""Unit tests for module-level JSON extraction helpers in debate module."""

from __future__ import annotations

from veritas_os.core import debate


def test_safe_json_extract_like_rescues_options_from_broken_json() -> None:
    """Broken trailing JSON should still rescue complete option objects."""
    raw = (
        '{"options":[{"id":"o1","title":"A","score":0.7},{"id":"o2","title":"B","score":0.6}'
        ',{"id":"o3","title":"C","score":"bad"}],"chosen_id":"o1"'
    )

    parsed = debate._safe_json_extract_like(raw)

    assert isinstance(parsed, dict)
    assert parsed.get("chosen_id") is None
    options = parsed.get("options") or []
    assert [opt.get("id") for opt in options] == ["o1", "o2"]


def test_extract_objects_from_array_obeys_depth_limit() -> None:
    """Overly-nested objects should be ignored by depth guard."""
    nested = '{"a":{"b":{"c":{"d":1}}}}'
    text = f'{{"options":[{nested}]}}'

    objs = debate._extract_objects_from_array(text, "options", max_depth=2)

    assert objs == []

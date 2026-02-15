"""Tests for scripts/verify_trust_log.py verification helpers."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_trust_log.py"


def load_module():
    """Load verify_trust_log.py as a module for direct helper testing."""
    spec = importlib.util.spec_from_file_location("verify_trust_log", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_verify_entries_accepts_valid_chain():
    """verify_entries should report no errors for a correctly linked chain."""
    module = load_module()

    entry1 = {"request_id": "r1", "message": "first", "sha256_prev": None}
    entry1["sha256"] = module.compute_hash(None, entry1)

    entry2 = {"request_id": "r2", "message": "second", "sha256_prev": entry1["sha256"]}
    entry2["sha256"] = module.compute_hash(entry2["sha256_prev"], entry2)

    total, errors, last_hash = module.verify_entries([entry1, entry2])

    assert total == 2
    assert errors == []
    assert last_hash == entry2["sha256"]


def test_verify_entries_reports_chain_break_and_hash_mismatch():
    """verify_entries should capture both chain and hash violations."""
    module = load_module()

    entry = {
        "request_id": "broken",
        "message": "tampered",
        "sha256_prev": "unexpected-prev",
        "sha256": "not-a-real-hash",
    }

    total, errors, _ = module.verify_entries([entry])

    assert total == 1
    error_types = {err["type"] for err in errors}
    assert "chain_break" in error_types
    assert "hash_mismatch" in error_types


def test_iter_entries_skips_invalid_json_line(tmp_path):
    """iter_entries should skip malformed lines and continue parsing."""
    module = load_module()

    log_path = tmp_path / "trust_log.jsonl"
    valid_1 = {"request_id": "r1", "value": 1}
    valid_2 = {"request_id": "r2", "value": 2}

    log_path.write_text(
        "\n".join(
            [
                json.dumps(valid_1, ensure_ascii=False),
                "{bad-json",
                json.dumps(valid_2, ensure_ascii=False),
            ]
        ),
        encoding="utf-8",
    )

    entries = list(module.iter_entries(log_path))

    assert entries == [valid_1, valid_2]

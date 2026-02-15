"""Tests for merge_trust_logs utility behaviors."""

from __future__ import annotations

import json
from pathlib import Path

from veritas_os.scripts import merge_trust_logs


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    """Read JSONL file into a list of dictionaries."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_merge_without_request_id_is_stable_across_runs(tmp_path: Path) -> None:
    """Entries without request_id use a stable fingerprint and deterministic merge output."""
    src = tmp_path / "trust_log.jsonl"
    out1 = tmp_path / "merged_1.jsonl"
    out2 = tmp_path / "merged_2.jsonl"

    entry = {"event": "audit", "created_at": "", "payload": {"x": 1}}
    src.write_text(
        "\n".join([json.dumps(entry), json.dumps(entry)]) + "\n",
        encoding="utf-8",
    )

    merge_trust_logs.merge_trust_logs([src], out1, recompute_hash=False)
    merge_trust_logs.merge_trust_logs([src], out2, recompute_hash=False)

    merged1 = _read_jsonl(out1)
    merged2 = _read_jsonl(out2)

    assert merged1 == [entry]
    assert merged2 == [entry]

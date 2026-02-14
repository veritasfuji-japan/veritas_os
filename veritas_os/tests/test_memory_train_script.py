from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from veritas_os.scripts import memory_train


def test_load_decision_data_supports_json_and_jsonl(monkeypatch, tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets"
    logs_dir = tmp_path / "logs"
    dataset_dir.mkdir()
    logs_dir.mkdir()

    json_path = dataset_dir / "records.json"
    json_path.write_text(
        json.dumps(
            [
                {"text": "safe query", "label": "allow"},
                {"prompt": "needs update", "decision": "modify"},
                {"text": "ignored", "label": "unknown"},
            ]
        ),
        encoding="utf-8",
    )

    jsonl_path = logs_dir / "events.jsonl"
    jsonl_path.write_text(
        "\n".join(
            [
                json.dumps({"query": "blocked request", "verdict": "deny"}),
                "not-json",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(memory_train, "DATA_DIRS", [dataset_dir, logs_dir])
    records = memory_train.load_decision_data()

    assert sorted(records) == sorted(
        [
            ("safe query", "allow"),
            ("needs update", "modify"),
            ("blocked request", "deny"),
        ]
    )


def test_load_decision_data_skips_malformed_json(monkeypatch, tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets"
    dataset_dir.mkdir()

    bad_json = dataset_dir / "broken.json"
    bad_json.write_text("{invalid", encoding="utf-8")

    monkeypatch.setattr(memory_train, "DATA_DIRS", [dataset_dir])
    records = memory_train.load_decision_data()

    assert records == []


def test_load_training_dependencies_raises_runtime_error_on_missing_package() -> None:
    with patch(
        "veritas_os.scripts.memory_train.import_module",
        side_effect=ModuleNotFoundError("No module named 'numpy'"),
    ):
        try:
            memory_train._load_training_dependencies()
        except RuntimeError as exc:
            assert "Missing package" in str(exc)
        else:
            raise AssertionError("RuntimeError was not raised")

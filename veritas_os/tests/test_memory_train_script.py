"""Tests for scripts/memory_train.py dataset loading behavior."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "memory_train.py"


def load_module():
    """Load memory_train.py as a module for script-level tests."""
    spec = importlib.util.spec_from_file_location("memory_train", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class MemoryTrainScriptTests(unittest.TestCase):
    """Behavioral tests for memory_train dataset ingestion."""

    def test_load_decision_data_parses_json_and_jsonl(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            json_path = tmp_path / "records.json"
            json_path.write_text(
                json.dumps(
                    [
                        {"input": "Allow this", "decision": "allow"},
                        {"prompt": "Modify this", "label": "modify"},
                        {"text": "Bad label", "label": "unknown"},
                    ]
                ),
                encoding="utf-8",
            )

            jsonl_path = tmp_path / "records.jsonl"
            jsonl_path.write_text(
                "\n".join(
                    [
                        json.dumps({"query": "Deny this", "output": "deny"}),
                        json.dumps({"query": "Skip", "output": "other"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            module.DATA_DIRS = [tmp_path]

            loaded = module.load_decision_data()

        self.assertEqual(
            loaded,
            [
                ("Allow this", "allow"),
                ("Modify this", "modify"),
                ("Deny this", "deny"),
            ],
        )


if __name__ == "__main__":
    unittest.main()

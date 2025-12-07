# tests/test_dataset_writer.py
from pathlib import Path
import json
import tempfile

from veritas_os.logging.dataset_writer import (
    build_dataset_record,
    append_dataset_record,
    get_dataset_stats,
    search_dataset,
)


def _dummy_req():
    return {"query": "test query", "context": {"user_id": "u1"}}


def _dummy_res():
    return {
        "chosen": {
            "id": "opt1",
            "title": "Option 1",
            "score": 0.9,
            "world": {
                "utility": 0.8,
                "predicted_risk": 0.1,
                "predicted_benefit": 0.9,
                "predicted_cost": 0.2,
            },
        },
        "alternatives": [
            {"id": "opt2", "title": "Option 2", "score": 0.7},
        ],
        "evidence": [
            {"source": "memory", "confidence": 0.95, "snippet": "foo"},
        ],
        "fuji": {
            "status": "ok",
            "reasons": ["no violation"],
            "violations": [],
        },
        "gate": {
            "decision_status": "allow",
            "risk": 0.1,
            "telos_score": 0.8,
            "reason": "safe",
        },
        "memory": {
            "used": True,
            "citations": 3,
        },
    }


def test_build_and_append_and_stats():
    req = _dummy_req()
    res = _dummy_res()
    meta = {"api_version": "v2.0", "kernel_version": "2.0.0"}

    rec = build_dataset_record(req, res, meta)

    # 基本フィールドが入っているか
    assert "ts" in rec
    assert "request" in rec and "response" in rec and "labels" in rec

    # ラベルが正しく反映されているか
    labels = rec["labels"]
    assert labels["status"] == "allow"
    assert labels["memory_used"] is True
    assert labels["memory_citations"] == 3

    # 一時ファイルに書き出して統計を取る
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "dataset.jsonl"
        append_dataset_record(rec, path=path, validate=True)

        stats = get_dataset_stats(path=path)
        assert stats["total_records"] == 1
        assert stats["status_counts"]["allow"] == 1
        assert stats["memory_usage"]["used"] == 1
        assert stats["avg_score"] > 0


def test_search_dataset():
    req = _dummy_req()
    res = _dummy_res()
    meta = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "dataset.jsonl"
        rec = build_dataset_record(req, res, meta)
        append_dataset_record(rec, path=path, validate=True)

        # query マッチ
        results = search_dataset(query="test query", path=path)
        assert len(results) == 1

        # status フィルタ
        results = search_dataset(status="allow", path=path)
        assert len(results) == 1

        results = search_dataset(status="rejected", path=path)
        assert len(results) == 0

        # memory_used フィルタ
        results = search_dataset(memory_used=True, path=path)
        assert len(results) == 1


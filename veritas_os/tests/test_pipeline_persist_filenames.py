"""Decision persistence keeps separate records within one millisecond."""

from datetime import datetime, timezone

import pytest

from veritas_os.core.atomic_io import atomic_write_json
from veritas_os.core.pipeline import pipeline_persist, pipeline_replay
from veritas_os.core.pipeline.pipeline_types import PipelineContext
from veritas_os.scripts.analyze_logs import parse_ts_from_name


@pytest.mark.parametrize("atomic", [False, True])
def test_decisions_keep_distinct_paired_files_at_same_timestamp(
    monkeypatch, tmp_path, atomic,
):
    instant = datetime(2026, 11, 9, tzinfo=timezone.utc)
    monkeypatch.setattr(pipeline_persist, "utc_now", lambda: instant)
    logs, dataset = tmp_path / "logs", tmp_path / "dataset"
    for request_id in ("first", "second"):
        pipeline_persist.persist_decision_to_disk(
            PipelineContext(request_id=request_id), {},
            duration_ms=0,
            LOG_DIR=logs,
            DATASET_DIR=dataset,
            _HAS_ATOMIC_IO=atomic,
            _atomic_write_json=atomic_write_json if atomic else None,
        )

    names = {path.name for path in logs.glob("decide_*.json")}
    assert len(names) == 2
    assert names == {path.name for path in dataset.glob("decide_*.json")}
    for name in names:
        assert parse_ts_from_name(name) == instant.replace(tzinfo=None)
    for request_id in ("first", "second"):
        for directory in (logs, dataset):
            record = pipeline_replay._load_persisted_decision(request_id, LOG_DIR=directory)
            assert record is not None
            assert record["request_id"] == request_id

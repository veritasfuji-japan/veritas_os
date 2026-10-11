"""Synthetic fail-closed checks for opt-in actual heavy-case pytest sharding.

The separate workflow supplies real pytest execution and JUnit evidence.
These tests do NOT themselves claim that the heavy corpus ran in eight shards.
"""

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ci.execute_heavy_cases import (
    _exact_sha,
    pytest_collection_finish,
    pytest_sessionfinish,
    record_terminal,
)
from scripts.ci.partition_heavy_pytest_cases import HEAVY_MODULES

PIN = "a" * 40


def _cases():
    return [
        SimpleNamespace(nodeid=f"{HEAVY_MODULES[0]}::test_a_{i:03d}")
        for i in range(89)
    ] + [
        SimpleNamespace(nodeid=f"{HEAVY_MODULES[1]}::test_b_{i:03d}")
        for i in range(76)
    ]


def _session(tmp_path, *, shard=1, count=8, source=PIN, markexpr="not slow",
             collectonly=False, args=None, tests=None):
    deselected = []
    options = {
        "heavy_exec_shard_index": shard,
        "heavy_exec_shard_count": count,
        "heavy_exec_manifest": tmp_path / "execution-manifest.json",
        "heavy_exec_source_sha": source,
        "collectonly": collectonly,
        "markexpr": markexpr,
    }
    config = SimpleNamespace(
        getoption=lambda k: options[k],
        args=list(HEAVY_MODULES) if args is None else args,
        hook=SimpleNamespace(pytest_deselected=lambda items: deselected.extend(items)),
    )
    session = SimpleNamespace(config=config, items=_cases() if tests is None else tests,
                              exitstatus=pytest.ExitCode.OK)
    return session, deselected


def test_execution_collection_selects_complete_disjoint_eight_way_cases(tmp_path):
    parts = []
    selected = set()
    for index in range(1, 9):
        session, deselected = _session(tmp_path, shard=index)
        pytest_collection_finish(session)
        nodeids = {t.nodeid for t in session.items}
        assert not selected.intersection(nodeids)
        selected |= nodeids
        assert len(nodeids) + len(deselected) == 165
        assert session.config._heavy_exec_plan["shard_index"] == index
        assert len(nodeids) >= 20
        parts.append(session.config._heavy_exec_plan)
    assert len(selected) == 165
    assert len({p["universe_sha256"] for p in parts}) == 1


@pytest.mark.parametrize("kwargs,pattern", [
    ({"shard": 0}, "exact 8-way"),
    ({"count": 4}, "exact 8-way"),
    ({"source": "NOT_SHA"}, "exact 8-way"),
    ({"markexpr": "slow"}, "exactly '-m not slow'"),
    ({"collectonly": True}, "cannot use --collect-only"),
    ({"args": [HEAVY_MODULES[0]]}, "exactly the two pinned modules"),
    ({"tests": _cases()[:-1]}, "below pinned floor"),
    ({"tests": _cases() + [_cases()[0]]}, "duplicate"),
])
def test_invalid_run_never_deselects_items(tmp_path, kwargs, pattern):
    session, deselected = _session(tmp_path, **kwargs)
    with pytest.raises(pytest.UsageError, match=pattern):
        pytest_collection_finish(session)
    assert not deselected
    assert not (tmp_path / "execution-manifest.json").exists()


def test_unconfigured_plugin_leaves_normal_ci_collection_untouched(tmp_path):
    session, deselected = _session(tmp_path, shard=None, count=None, source=None)
    # All four flags absent: plugin remains passive outside explicitly selected runs.
    session.config.getoption = lambda key: (
        None if key in {
            "heavy_exec_shard_index", "heavy_exec_shard_count",
            "heavy_exec_manifest", "heavy_exec_source_sha",
        } else "not slow"
    )
    before = list(session.items)
    pytest_collection_finish(session)
    assert before == session.items
    assert not deselected


def _report(nodeid, *, when="call", outcome="passed"):
    return SimpleNamespace(
        nodeid=nodeid,
        when=when,
        passed=(outcome == "passed"),
        skipped=(outcome == "skipped"),
        failed=(outcome == "failed"),
    )


def test_terminal_evidence_tracks_actual_pass_and_skip(tmp_path):
    session, _ = _session(tmp_path)
    pytest_collection_finish(session)
    cases = [item.nodeid for item in session.items]
    outcomes, seen = {}, Counter()
    for index, nodeid in enumerate(cases):
        outcome = "skipped" if index == 0 else "passed"
        record_terminal(outcomes, seen, _report(
            nodeid, when="setup" if index == 0 else "call", outcome=outcome
        ))
    session.config._heavy_exec_outcomes = outcomes
    session.config._heavy_exec_reports = seen
    pytest_sessionfinish(session, 0)
    data = json.loads((tmp_path / "execution-manifest.json").read_text())
    assert data["pytest_exitstatus"] == 0
    assert len(data["selected_nodeids"]) == len(data["reported_nodeids"])
    assert len(data["terminal_outcomes"]) == len(cases)
    assert set(data["terminal_outcomes"].values()) == {"passed", "skipped"}
    assert session.exitstatus == pytest.ExitCode.OK


def test_missing_or_failed_actual_report_rejects_shard(tmp_path):
    session, _ = _session(tmp_path)
    pytest_collection_finish(session)
    cases = [item.nodeid for item in session.items]
    session.config._heavy_exec_outcomes = {cases[0]: "failed"}
    session.config._heavy_exec_reports = Counter({cases[0]: 1})
    pytest_sessionfinish(session, 1)
    manifest = json.loads((tmp_path / "execution-manifest.json").read_text())
    assert manifest["terminal_outcomes"][cases[0]] == "failed"
    assert len(manifest["reported_nodeids"]) == 1
    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED


def test_terminal_failure_can_override_previous_call_pass():
    nodeid = f"{HEAVY_MODULES[0]}::test_abc"
    outcomes, seen = {}, Counter()
    record_terminal(outcomes, seen, _report(nodeid, outcome="passed"))
    record_terminal(outcomes, seen, _report(nodeid, when="teardown", outcome="failed"))
    assert outcomes == {nodeid: "failed"}
    assert seen[nodeid] == 2


def test_sha_requires_exact_lowercase_hex():
    assert _exact_sha(PIN)
    assert not _exact_sha("A" * 40)
    assert not _exact_sha("0" * 39)
    assert not _exact_sha(None)

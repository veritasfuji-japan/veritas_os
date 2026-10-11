"""Opt-in, real pytest execution partition for the two pinned heavy modules.

This plugin is NOT auto-loaded and does not alter the existing CI test matrix.
Only explicit invocations with both frozen module paths and '-m not slow' may
select an 8-way case shard. The manifest describes actual terminal reports.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from scripts.ci.partition_heavy_pytest_cases import (
    HEAVY_MODULES,
    make_case_shard_manifests,
    verify_case_shard_manifests,
)

_active_config: pytest.Config | None = None


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("heavy-case-execution-evidence")
    group.addoption("--heavy-exec-shard-index", type=int, default=None)
    group.addoption("--heavy-exec-shard-count", type=int, default=None)
    group.addoption("--heavy-exec-source-sha", default=None)
    group.addoption("--heavy-exec-manifest", type=Path, default=None)


def pytest_configure(config: pytest.Config) -> None:
    global _active_config
    _active_config = config


def pytest_unconfigure(config: pytest.Config) -> None:
    global _active_config
    if _active_config is config:
        _active_config = None


def _exact_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(c in "0123456789abcdef" for c in value)
    )


def _validate_options(config: pytest.Config) -> tuple[int, Path, str]:
    index = config.getoption("heavy_exec_shard_index")
    count = config.getoption("heavy_exec_shard_count")
    path = config.getoption("heavy_exec_manifest")
    sha = config.getoption("heavy_exec_source_sha")
    if (
        isinstance(index, bool)
        or not isinstance(index, int)
        or isinstance(count, bool)
        or count != 8
        or not 1 <= index <= 8
        or not isinstance(path, Path)
        or not _exact_sha(sha)
    ):
        raise pytest.UsageError("heavy-case execution requires exact 8-way index, manifest and SHA")
    if config.getoption("collectonly"):
        raise pytest.UsageError("heavy-case execution cannot use --collect-only")
    if config.getoption("markexpr").strip() != "not slow":
        raise pytest.UsageError("heavy-case execution requires exactly '-m not slow'")
    if list(config.args) != list(HEAVY_MODULES):
        raise pytest.UsageError("heavy-case execution requires exactly the two pinned modules")
    return index, path, sha


def pytest_collection_finish(session: pytest.Session) -> None:
    config = session.config
    index = config.getoption("heavy_exec_shard_index")
    count = config.getoption("heavy_exec_shard_count")
    path = config.getoption("heavy_exec_manifest")
    source = config.getoption("heavy_exec_source_sha")
    if all(value is None for value in (index, count, path, source)):
        return  # plugin imported but not invoked: no impact to other pytest lanes

    index, path, sha = _validate_options(config)
    try:
        plans = make_case_shard_manifests(
            [item.nodeid for item in session.items], shard_count=8
        )
        verify_case_shard_manifests(plans)
    except (TypeError, ValueError) as exc:
        raise pytest.UsageError(f"heavy-case runtime selection failed: {exc}") from exc

    current = plans[index - 1]
    owners = set(current["selected_nodeids"])
    kept = [item for item in session.items if item.nodeid in owners]
    deselected = [item for item in session.items if item.nodeid not in owners]
    if not kept or len(kept) != len(owners):
        raise pytest.UsageError("heavy-case runtime selection lost an owned pytest item")

    # Store only a fresh, SHA-pinned plan; do not claim outcomes before actual reports.
    config._heavy_exec_plan = current  # type: ignore[attr-defined]
    config._heavy_exec_path = path  # type: ignore[attr-defined]
    config._heavy_exec_sha = sha  # type: ignore[attr-defined]
    config._heavy_exec_outcomes = {}  # type: ignore[attr-defined]
    config._heavy_exec_reports = Counter()  # type: ignore[attr-defined]
    session.items[:] = kept
    config.hook.pytest_deselected(items=deselected)


def record_terminal(
    outcomes: dict[str, str], reported: Counter[str], report: pytest.TestReport
) -> None:
    """Count a node as reported only after a terminal pytest phase."""
    if report.when not in {"setup", "call", "teardown"}:
        return
    if report.failed:
        outcomes[report.nodeid] = "failed"
        reported[report.nodeid] += 1
    elif report.skipped and outcomes.get(report.nodeid) != "failed":
        outcomes[report.nodeid] = "skipped"
        reported[report.nodeid] += 1
    elif report.when == "call" and report.passed and outcomes.get(report.nodeid) is None:
        outcomes[report.nodeid] = "passed"
        reported[report.nodeid] += 1


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if _active_config is None or not hasattr(_active_config, "_heavy_exec_plan"):
        return
    outcomes = _active_config._heavy_exec_outcomes  # type: ignore[attr-defined]
    reported = _active_config._heavy_exec_reports  # type: ignore[attr-defined]
    record_terminal(outcomes, reported, report)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    if not hasattr(config, "_heavy_exec_plan"):
        return
    plan = config._heavy_exec_plan  # type: ignore[attr-defined]
    outcomes = config._heavy_exec_outcomes  # type: ignore[attr-defined]
    reported = config._heavy_exec_reports  # type: ignore[attr-defined]
    path = config._heavy_exec_path  # type: ignore[attr-defined]
    # A failed pytest run must still preserve evidence, but may never claim PASS.
    manifest = {
        "schema_version": 1,
        "proof_kind": "PYTEST_EXECUTION_EVIDENCE",
        "source_sha": config._heavy_exec_sha,  # type: ignore[attr-defined]
        "shard_index": plan["shard_index"],
        "shard_count": 8,
        "universe_sha256": plan["universe_sha256"],
        "selected_nodeids": plan["selected_nodeids"],
        "reported_nodeids": sorted(reported),
        "terminal_outcomes": dict(sorted(outcomes.items())),
        "pytest_exitstatus": int(exitstatus),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    missing = set(plan["selected_nodeids"]) - set(outcomes)
    unexpected = set(outcomes) - set(plan["selected_nodeids"])
    if (
        exitstatus != 0
        or missing or unexpected
        or any(n not in {"passed", "skipped"} for n in outcomes.values())
    ):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED

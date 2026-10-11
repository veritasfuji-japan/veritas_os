"""Safe, plan-only proof before cutting heavy modules out of normal CI shards."""

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.ci.collect_heavy_cases import make_collection_proof
from scripts.ci.partition_heavy_pytest_cases import HEAVY_MODULES
from scripts.ci.plan_heavy_case_cutover import (
    build_cutover_plan,
    verify_cutover_plan,
)

PIN = "a" * 40


def _files():
    return [Path(module) for module in HEAVY_MODULES] + [
        Path(f"veritas_os/tests/test_extra_{n:03d}.py") for n in range(16)
    ]


def _historical():
    return {path.as_posix(): float(n + 1) for n, path in enumerate(_files())}


def _collection():
    nodeids = [
        f"{HEAVY_MODULES[0]}::test_a_{i:03d}" for i in range(89)
    ] + [
        f"{HEAVY_MODULES[1]}::test_b_{i:03d}" for i in range(76)
    ]
    return make_collection_proof(nodeids, source_sha=PIN)


def _plan():
    return build_cutover_plan(
        _files(), _collection(), expected_sha=PIN, historical=_historical()
    )


def _verify(plan, *, files=None, proof=None, sha=PIN):
    return verify_cutover_plan(
        plan, _files() if files is None else files,
        _collection() if proof is None else proof,
        expected_sha=sha, historical=_historical(),
    )


def test_exact_165_case_handoff_preserves_all_discovered_file_owners():
    proposal = _plan()
    assert _verify(proposal) == (18, 165)
    assert proposal["scope"] == "python3.12_only"
    assert proposal["plan_kind"] == "PY312_FILE_TO_CASE_CUTOVER_PREFLIGHT_ONLY"
    assert len(proposal["ordinary_file_shards"]) == 8
    assert len(proposal["heavy_case_shards"]) == 8
    normal = [
        name for shard in proposal["ordinary_file_shards"]
        for name in shard["selected_files"]
    ]
    cases = [
        name for shard in proposal["heavy_case_shards"]
        for name in shard["selected_nodeids"]
    ]
    assert len(normal) == len(set(normal)) == 16
    assert not set(normal).intersection(HEAVY_MODULES)
    assert len(cases) == len(set(cases)) == 165


def test_plan_does_not_depend_on_input_file_enumeration_order():
    ordinary = build_cutover_plan(
        list(reversed(_files())), _collection(), expected_sha=PIN,
        historical=_historical(),
    )
    assert ordinary == _plan()


@pytest.mark.parametrize("mutation", [
    lambda p: p["ordinary_file_shards"][0]["selected_files"].pop(),
    lambda p: p["ordinary_file_shards"][0]["selected_files"].append(
        HEAVY_MODULES[0]
    ),
    lambda p: p["ordinary_file_shards"][1]["selected_files"].extend(
        p["ordinary_file_shards"][0]["selected_files"][:1]
    ),
    lambda p: p["heavy_case_shards"][0]["selected_nodeids"].pop(),
    lambda p: p["heavy_case_shards"][2].update(universe_sha256="0" * 64),
    lambda p: p.update(source_sha="b" * 40),
    lambda p: p.update(scope="python3.11_and_3.12"),
    lambda p: p.update(full_file_sha256="f" * 64),
    lambda p: p.update(normal_shard_count=7),
])
def test_tampered_proposed_handoff_fails_closed(mutation):
    proposal = deepcopy(_plan())
    mutation(proposal)
    with pytest.raises(ValueError, match="differs from actual"):
        _verify(proposal)


def test_different_checkout_sha_fails_closed():
    with pytest.raises(ValueError, match="exact checkout SHA"):
        _verify(_plan(), sha="b" * 40)


def test_discovered_file_drift_fails_closed():
    with pytest.raises(ValueError, match="differs from actual"):
        _verify(_plan(), files=_files()[:-1])


def test_rejects_missing_heavy_module_in_discovery():
    missing = [x for x in _files() if x.as_posix() != HEAVY_MODULES[1]]
    with pytest.raises(ValueError, match="both heavy modules"):
        build_cutover_plan(
            missing, _collection(), expected_sha=PIN, historical=_historical()
        )


def test_rejects_duplicate_discovered_files():
    with pytest.raises(ValueError, match="duplicate file"):
        build_cutover_plan(
            _files() + [_files()[-1]], _collection(), expected_sha=PIN,
            historical=_historical(),
        )


def test_rejects_downgraded_collection_domain():
    altered = _collection()
    altered["module_case_counts"][HEAVY_MODULES[0]] = 88
    with pytest.raises(ValueError, match="per-module case counts"):
        build_cutover_plan(
            _files(), altered, expected_sha=PIN, historical=_historical()
        )


def test_rejects_invalid_absolute_file_path():
    with pytest.raises(ValueError, match="relative repository paths"):
        build_cutover_plan(
            _files() + [Path("/etc/test_not_ours.py")],
            _collection(), expected_sha=PIN, historical=_historical(),
        )

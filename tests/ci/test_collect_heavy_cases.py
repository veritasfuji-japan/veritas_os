"""Collection-only proof: actual pytest item IDs, scope and exported evidence."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts.ci.collect_heavy_cases import (
    make_collection_proof,
    pytest_collection_finish,
)
from scripts.ci.partition_heavy_pytest_cases import HEAVY_MODULES
from scripts.ci.validate_heavy_case_collection import verify_collection_proof

PIN = "a" * 40


def _nodeids(first: int = 89, second: int = 76) -> list[str]:
    return [
        f"{HEAVY_MODULES[0]}::test_a[{index}]" for index in range(first)
    ] + [
        f"{HEAVY_MODULES[1]}::test_b[{index}]" for index in range(second)
    ]


def _run_hook(path, *, nodeids=None, markexpr="not slow", collectonly=True, args=None, sha=PIN):
    options = {
        "heavy_case_proof_output": path,
        "heavy_case_source_sha": sha,
        "markexpr": markexpr,
        "collectonly": collectonly,
    }
    config = SimpleNamespace(
        args=list(HEAVY_MODULES) if args is None else args,
        getoption=lambda name: options[name],
    )
    items = [SimpleNamespace(nodeid=n) for n in (_nodeids() if nodeids is None else nodeids)]
    pytest_collection_finish(SimpleNamespace(config=config, items=items))


def test_real_item_hook_exports_consistent_eight_way_collection(tmp_path):
    path = tmp_path / "nested" / "collection.json"
    _run_hook(path)
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["proof_kind"] == "PYTEST_COLLECTION_ONLY"
    assert report["source_sha"] == PIN
    assert report["module_case_counts"] == dict(zip(HEAVY_MODULES, (89, 76)))
    assert verify_collection_proof(report, expected_sha=PIN) == 165
    assert [p["shard_index"] for p in report["manifests"]] == list(range(1, 9))
    assert sum(map(lambda p: len(p["selected_nodeids"]), report["manifests"])) == 165


def test_planning_independent_of_pytest_collection_order():
    assert make_collection_proof(_nodeids(), source_sha=PIN) == make_collection_proof(
        list(reversed(_nodeids())), source_sha=PIN
    )


@pytest.mark.parametrize("changed,pattern", [
    ({"markexpr": "slow"}, "requires exact"),
    ({"collectonly": False}, "requires --collect-only"),
    ({"args": [HEAVY_MODULES[0]]}, "exactly the two"),
    ({"sha": ""}, "source SHA"),
    ({"nodeids": _nodeids(first=88)}, "below pinned floor"),
    ({"nodeids": _nodeids() + [_nodeids()[0]]}, "duplicate"),
    ({"nodeids": _nodeids() + ["tests/unexpected.py::test_extra"]}, "out-of-scope"),
])
def test_plugin_fails_closed_and_writes_no_artifact(tmp_path, changed, pattern):
    path = tmp_path / "proof.json"
    with pytest.raises(pytest.UsageError, match=pattern):
        _run_hook(path, **changed)
    assert not path.exists()


@pytest.mark.parametrize("mutate,pattern", [
    (lambda d: d.update(source_sha="b" * 40), "exact checkout SHA"),
    (lambda d: d.update(selected_case_count=164), "case count"),
    (lambda d: d["module_case_counts"].update({HEAVY_MODULES[0]: 88}), "per-module"),
    (lambda d: d["manifests"][0]["selected_nodeids"].pop(), "missing or duplicate"),
    (lambda d: d["manifests"][1].update(universe_sha256="0" * 64), "fingerprint"),
    (lambda d: d["manifests"].pop(), "eight shard"),
])
def test_artifact_verifier_rejects_tampering(mutate, pattern):
    proof = make_collection_proof(_nodeids(), source_sha=PIN)
    altered = deepcopy(proof)
    mutate(altered)
    with pytest.raises(ValueError, match=pattern):
        verify_collection_proof(altered, expected_sha=PIN)


def test_artifact_verifier_rejects_repartitioned_but_complete_ids():
    proof = make_collection_proof(_nodeids(), source_sha=PIN)
    altered = deepcopy(proof)
    first = altered["manifests"][0]["selected_nodeids"].pop()
    second = altered["manifests"][1]["selected_nodeids"].pop()
    altered["manifests"][0]["selected_nodeids"].append(second)
    altered["manifests"][1]["selected_nodeids"].append(first)
    with pytest.raises(ValueError, match="deterministic plan"):
        verify_collection_proof(altered, expected_sha=PIN)

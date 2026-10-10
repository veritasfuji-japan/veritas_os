"""Guard deterministic, fail-closed ownership planning for heavy pytest cases.

No CI integration yet: these tests prove intended sharding *membership*,
not actual execution or JUnit artifact completeness.
"""

from copy import deepcopy

import pytest

from scripts.ci.partition_heavy_pytest_cases import (
    HEAVY_MODULES,
    make_case_shard_manifests,
    verify_case_shard_manifests,
)


def _baseline_cases(*, first: int = 89, second: int = 76) -> list[str]:
    return [
        f"{HEAVY_MODULES[0]}::test_case_{n:03d}"
        for n in range(first)
    ] + [
        f"{HEAVY_MODULES[1]}::test_case_{n:03d}"
        for n in range(second)
    ]


def test_complete_disjoint_deterministic_for_pinned_two_modules() -> None:
    cases = _baseline_cases()
    plans = make_case_shard_manifests(cases, shard_count=8)
    assert len(plans) == 8
    assert verify_case_shard_manifests(plans) == 165
    assert plans == make_case_shard_manifests(list(reversed(cases)), shard_count=8)
    selected = [nodeid for plan in plans for nodeid in plan["selected_nodeids"]]
    assert set(selected) == set(cases)
    assert len(selected) == len(set(selected)) == 165
    assert all(plan["selected_nodeids"] for plan in plans)
    assert max(len(plan["selected_nodeids"]) for plan in plans) - min(
        len(plan["selected_nodeids"]) for plan in plans
    ) <= 2


def test_accepts_new_cases_without_silently_dropping_them() -> None:
    cases = _baseline_cases(first=93, second=79)
    assert verify_case_shard_manifests(make_case_shard_manifests(cases)) == 172


@pytest.mark.parametrize("cases,pattern", [
    (_baseline_cases(first=88), "below pinned floor"),
    (_baseline_cases(second=75), "below pinned floor"),
    (_baseline_cases() + [_baseline_cases()[0]], "duplicate pytest case ID"),
    (_baseline_cases() + ["tests/other.py::test_intruder"], "out-of-scope"),
    (["junk"], "pytest nodeids"),
])
def test_rejects_corpus_shrink_duplicate_or_wrong_module(cases, pattern) -> None:
    with pytest.raises(ValueError, match=pattern):
        make_case_shard_manifests(cases)


def test_rejects_missing_shard_or_duplicate_execution_owner() -> None:
    plans = make_case_shard_manifests(_baseline_cases())
    with pytest.raises(ValueError, match="missing or extra"):
        verify_case_shard_manifests(plans[:-1])

    bad = deepcopy(plans)
    bad[1]["selected_nodeids"].append(bad[0]["selected_nodeids"][0])
    with pytest.raises(ValueError, match="missing or duplicate"):
        verify_case_shard_manifests(bad)


def test_rejects_missing_case_owner_even_when_total_count_looks_similar() -> None:
    plans = deepcopy(make_case_shard_manifests(_baseline_cases()))
    lost = plans[0]["selected_nodeids"].pop(0)
    plans[1]["selected_nodeids"].append("unexpected::test_case")
    with pytest.raises(ValueError, match="missing or duplicate"):
        verify_case_shard_manifests(plans)
    assert lost in plans[0]["full_nodeids"]


def test_rejects_inconsistent_collection_fingerprint_and_index() -> None:
    plans = make_case_shard_manifests(_baseline_cases())
    altered = deepcopy(plans)
    altered[2]["full_nodeids"].pop()
    with pytest.raises(ValueError, match="different full collections"):
        verify_case_shard_manifests(altered)

    altered = deepcopy(plans)
    altered[4]["universe_sha256"] = "00" * 32
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        verify_case_shard_manifests(altered)

    altered = deepcopy(plans)
    altered[1]["shard_index"] = 1
    with pytest.raises(ValueError, match="indices are not distinct"):
        verify_case_shard_manifests(altered)


def test_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="shard_count"):
        make_case_shard_manifests(_baseline_cases(), shard_count=1)
    with pytest.raises(ValueError, match="positive integers"):
        make_case_shard_manifests(
            _baseline_cases(),
            minimums={HEAVY_MODULES[0]: 0, HEAVY_MODULES[1]: 76},
        )

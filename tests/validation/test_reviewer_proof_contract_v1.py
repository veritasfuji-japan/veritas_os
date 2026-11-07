"""Fixture-free reviewer contract tests, safe for all default CI shards."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts.validation.verify_reviewer_proof_contract_v1 import (
    ProofError, load_json, verify_contract,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts/reviewer-proof-contract-v1.json"


def test_exact_contract_is_pinned():
    verify_contract(load_json(CONTRACT))


@pytest.mark.parametrize("change", (
    "remove_predicate", "relax_dispatch", "drop_nonclaim",
    "erase_out_of_scope", "remove_fault", "remove_false_claim",
))
def test_contract_cannot_be_silently_weakened(change):
    value = copy.deepcopy(load_json(CONTRACT))
    if change == "remove_predicate":
        value["required_conjunction"].pop()
    elif change == "relax_dispatch":
        del value["scenarios"]["normal"]["dispatch_reason"]
    elif change == "drop_nonclaim":
        value["required_non_claims"].pop()
    elif change == "erase_out_of_scope":
        value["out_of_scope"] = []
    elif change == "remove_fault":
        del value["scenarios"]["fault"]
    else:
        value["required_false_claims"].pop()
    with pytest.raises(ProofError, match="CONTRACT_DRIFT"):
        verify_contract(value)


@pytest.mark.parametrize("raw", (
    '{"a":1,"a":2}', '{"a":NaN}', '[]',
))
def test_json_loader_rejects_ambiguous_artifacts(tmp_path, raw):
    path = tmp_path / "report.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ProofError):
        load_json(path)


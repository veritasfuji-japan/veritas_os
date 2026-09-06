"""Real HTTP decision coverage of the currently incomplete v0.3 connection.

The source-format refusal is intentional and observable. These tests do not
claim successful authorization, consumption, or decision-to-effect integration.
No packet verifier is replaced with an accepting test double.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

import pytest

from veritas_os.governance.canonical_decision_artifact import (
    verify_canonical_decision_artifact,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.bind_adapter_contract_selection import (
    ADAPTER_METHODS,
    DESCRIPTOR_SCOPE_LIMITATIONS,
    EFFECT_PROFILE,
    PROHIBITED_DURING_SELECTION,
    BindAdapterContractSelectionError,
)
from veritas_os.policy.canonical_verified_decision_promotion import (
    build_canonical_verified_decision_promotion_packet as promote,
)
from veritas_os.policy.canonical_promotion_execution_intent_readiness import (
    build_canonical_promotion_execution_intent_readiness_packet as ready,
)
from veritas_os.policy.canonical_promotion_pre_bind_validation import (
    build_canonical_promotion_pre_bind_validation_packet as validate_pre_bind,
)
from veritas_os.policy.canonical_promotion_bind_preflight_adjudication import (
    build_canonical_promotion_bind_preflight_adjudication_packet as preflight,
)
from veritas_os.policy.canonical_promotion_bind_adapter_contract_selection import (
    build_canonical_promotion_bind_adapter_contract_selection_packet as select,
)
from veritas_os.policy.fresh_bind_source_chain import (
    FreshBindSourceChainInputs,
    build_fresh_bind_source_chain,
)
from veritas_os.policy.real_decision_bind_authorization import (
    RealDecisionBindAuthorizationError,
    issue_verified_real_decision_bind_authorization,
)
from veritas_os.tests import test_v03_issuance_trust as v03_fixtures

case = v03_fixtures.case

pytestmark = pytest.mark.slow
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def live_decision(tmp_path_factory):
    output = tmp_path_factory.mktemp("live-decision") / "capture.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "veritas_os.tests.helpers.live_decision_capture",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        timeout=180,
        capture_output=True,
        text=True,
    )
    captured = json.loads(output.read_text())
    assert captured["pipeline_ok"] is True
    assert all(count > 0 for count in captured["infrastructure_calls"].values())
    verified = verify_canonical_decision_artifact(
        captured["canonical_decision_artifact"]
    )
    assert verified.is_valid and verified.artifact is not None
    cda = verified.artifact
    assert cda.decision.policy_snapshot_evidence.signature_verified is True
    now = datetime.fromisoformat(captured["observed_at"])
    promotion = promote(cda, captured["candidate"], promoted_at=now)
    return cda, captured["candidate"], now, promotion


def _kwargs(case, live_decision):
    gate, governance, decision, trust, signer = case
    cda, candidate, now, _ = live_decision
    return dict(
        canonical_decision_artifact=cda,
        candidate=candidate,
        policy_snapshot_id=cda.decision.policy_snapshot_evidence.snapshot_id,
        source_gate_review_packet=gate,
        signed_authorization_decision_artifact=decision,
        valid_from=now,
        valid_until=now + timedelta(minutes=1),
        governance_inputs=replace(governance, verification_now=now),
        trust_inputs=trust,
        authorization_issuer_signer=signer,
    )


def test_real_decision_reconstructs_identical_intent_and_refuses_foreign_v03_source(
    case,
    live_decision,
    monkeypatch,
):
    import veritas_os.policy.real_decision_bind_authorization as module

    cda, _, _, promotion = live_decision
    original = module._require_exact_intent
    observed = []

    def observe(expected, *args, **kwargs):
        observed.append(expected.to_dict())
        return original(expected, *args, **kwargs)

    def forbidden_sign(*args):
        pytest.fail("a mismatched source must not reach authorization signing")

    monkeypatch.setattr(module, "_require_exact_intent", observe)
    monkeypatch.setattr(type(case[4]), "sign", forbidden_sign)
    for _ in range(2):
        with pytest.raises(
            RealDecisionBindAuthorizationError,
            match="RDBA_SOURCE_EXECUTION_INTENT_MISMATCH",
        ):
            issue_verified_real_decision_bind_authorization(
                **_kwargs(case, live_decision)
            )
    assert observed == [promotion.exact_execution_intent] * 2
    assert observed[0]["decision_id"] == cda.decision_id
    assert observed[0]["decision_hash"] == cda.decision_hash
    assert (
        hash_execution_intent(ExecutionIntent(**observed[0]))
        == promotion.execution_intent_hash
    )


def test_real_decision_native_selection_is_not_a_v03_handoff_source(
    case, live_decision
):
    _, _, now, promotion = live_decision
    validation = validate_pre_bind(ready(promotion, checked_at=now), checked_at=now)
    intent = ExecutionIntent(**promotion.exact_execution_intent)
    descriptor = {
        "adapter_contract_version": "bind-adapter-contract/v1",
        "adapter_kind": "reference",
        "adapter_name": "local-inert-declaration",
        "target_system": intent.target_system,
        "target_resource_scope": intent.target_resource,
        "supported_methods": list(ADAPTER_METHODS),
        "required_methods": list(ADAPTER_METHODS),
        "prohibited_during_selection": list(PROHIBITED_DURING_SELECTION),
        "effect_profile": EFFECT_PROFILE,
        "declared_by": "test:local",
        "declared_at": now.isoformat(),
        "descriptor_scope_limitations": list(DESCRIPTOR_SCOPE_LIMITATIONS),
    }
    selection = select(preflight(validation, now), descriptor, now)
    assert selection.execution_intent == promotion.exact_execution_intent
    # No fabricated handoff/replay/approval fields to disguise a native source.
    inputs = FreshBindSourceChainInputs(
        **{
            name: selection if name == "adapter_contract_selection_packet" else None
            for name in FreshBindSourceChainInputs.__annotations__
        }
    )
    with pytest.raises(BindAdapterContractSelectionError):
        build_fresh_bind_source_chain(
            intent,
            inputs,
            built_at=now,
            expected_contract=case[1].action_contract,
        )


@pytest.mark.parametrize(
    "mutation", ["candidate", "cda", "policy", "approval", "lineage", "stale", "future"]
)
def test_live_decision_invalid_input_stops_before_source_or_signing(
    case,
    live_decision,
    mutation,
    monkeypatch,
):
    import veritas_os.policy.real_decision_bind_authorization as module

    kwargs = _kwargs(case, live_decision)
    if mutation == "candidate":
        kwargs["candidate"] = {**kwargs["candidate"], "target_resource": "foreign"}
    elif mutation == "cda":
        raw = deepcopy(kwargs["canonical_decision_artifact"].model_dump(mode="json"))
        raw["decision_hash"] = "0" * 64
        kwargs["canonical_decision_artifact"] = raw
    elif mutation == "policy":
        kwargs["policy_snapshot_id"] = "foreign-policy"
    elif mutation == "approval":
        kwargs["approval_context"] = {"approved": True}
    elif mutation == "lineage":
        kwargs["policy_lineage"] = {"version": "foreign"}
    else:
        kwargs["governance_inputs"] = replace(
            kwargs["governance_inputs"],
            verification_now=live_decision[2]
            + timedelta(minutes=10 if mutation == "stale" else -10),
        )

    def forbidden(*args, **kwargs):
        pytest.fail("invalid decision must stop before source validation and signing")

    monkeypatch.setattr(
        module,
        "verify_live_adapter_dry_run_bind_authorization_gate_review_packet",
        forbidden,
    )
    monkeypatch.setattr(type(case[4]), "sign", forbidden)
    with pytest.raises(RealDecisionBindAuthorizationError):
        issue_verified_real_decision_bind_authorization(**kwargs)

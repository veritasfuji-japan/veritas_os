"""Optional approval metadata remains schema-valid through inert dry-run stages."""

from copy import deepcopy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from veritas_os.policy.canonical_execution_intent_formation import (
    build_canonical_execution_intent_formation_packet as form,
)
from veritas_os.policy.execution_intent_formation_readiness import (
    build_execution_intent_formation_readiness_packet as ready,
)
from veritas_os.policy.execution_intent_pre_bind_validation import (
    build_execution_intent_pre_bind_validation_packet as pre_bind,
)
from veritas_os.policy.canonical_bind_preflight_adjudication import (
    build_canonical_bind_preflight_adjudication_packet as preflight,
)
from veritas_os.policy.bind_adapter_contract_selection import (
    build_bind_adapter_contract_selection_packet as select,
)
from veritas_os.policy.adapter_dry_run_plan import build_adapter_dry_run_plan_packet as plan
from veritas_os.policy.adapter_dry_run_result import (
    build_adapter_dry_run_fixture_result_packet as result,
)
from veritas_os.tests.test_execution_intent_formation_readiness import (
    NOW, _eligibility, _eligibility_without_approval,
)
from veritas_os.tests.test_canonical_execution_intent_formation import FORMED_AT
from veritas_os.tests.test_execution_intent_pre_bind_validation import CHECKED_AT
from veritas_os.tests.test_canonical_bind_preflight_adjudication import ADJUDICATED_AT
from veritas_os.tests.test_bind_adapter_contract_selection import SELECTED_AT, _descriptor
from veritas_os.tests.test_adapter_dry_run_plan import PLANNED_AT
from veritas_os.tests.test_adapter_dry_run_fixture_result import RESULTED_AT, _fixtures


SCHEMAS = (
    "canonical-execution-intent-formation-v1",
    "execution-intent-pre-bind-validation-v1",
    "canonical-bind-preflight-adjudication-v1",
    "bind-adapter-contract-selection-v1",
    "adapter-dry-run-plan-v1",
    "adapter-dry-run-fixture-result-v1",
)


@pytest.fixture(scope="module", params=[True, False], ids=["required", "not-required"])
def chain(request):
    """Use real builders/verifiers with local fixture metadata and no dispatch."""
    required = request.param
    eligibility = _eligibility() if required else _eligibility_without_approval()
    formed = form(ready(eligibility, NOW), FORMED_AT)
    checked = pre_bind(formed, CHECKED_AT)
    adjudicated = preflight(checked, ADJUDICATED_AT)
    selected = select(adjudicated, _descriptor(), SELECTED_AT)
    planned = plan(selected, PLANNED_AT)
    resulted = result(planned, _fixtures(planned), RESULTED_AT)
    return required, (formed, checked, adjudicated, selected, planned, resulted)


@pytest.mark.parametrize("stage", range(len(SCHEMAS)), ids=SCHEMAS)
def test_real_downstream_packet_matches_schema_without_fake_receipt(chain, stage):
    required, packets = chain
    raw = packets[stage].model_dump(mode="json")
    schema = json.loads(Path(f"schemas/{SCHEMAS[stage]}.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.validate(raw)
    intent = raw["execution_intent"]
    assert len(intent["evidence_refs"]) == (5 if required else 4)
    assert all(isinstance(ref, str) and ref for ref in intent["evidence_refs"])
    if not required:
        assert intent["approval_context"] == {
            "required_human_approval": False,
            "requirement_state": "NOT_REQUIRED_BY_CANONICAL_HANDOFF",
            "requirement_policy_ref": "fixture-policy",
        }
        assert raw["evidence_lineage"]["human_approval_receipt_ref"] is None
        assert raw["evidence_lineage"]["human_approval_receipt_hash"] is None

    # Both branches retain their evidence minimum; no blanket relaxation to four.
    missing = deepcopy(raw)
    missing["execution_intent"]["evidence_refs"].pop()
    assert not validator.is_valid(missing)
    malformed = deepcopy(raw)
    malformed["execution_intent"]["approval_context"] = {"required_human_approval": False}
    assert not validator.is_valid(malformed)

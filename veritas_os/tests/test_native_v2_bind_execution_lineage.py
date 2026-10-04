"""Native-v2 consumption may enter BCBR only through exact typed provenance."""

from dataclasses import replace

import pytest

from veritas_os.policy.bind_execution_capability import (
    _current_consumed_authorization_lineage,
)
from veritas_os.policy.native_bind_authorization_consumption import (
    NativeAuthorizationConsumptionResult,
)
from veritas_os.policy.native_v2_bind_execution_lineage import (
    NativeV2BindExecutionLineageError,
    transport_consumed_native_v2_authorization_lineage,
)
from veritas_os.tests.test_native_bind_authorization_consumption import (
    _consume,
)


@pytest.mark.asyncio
async def test_consumed_native_v2_projects_exact_lineage():
    result = await _consume()
    with transport_consumed_native_v2_authorization_lineage(result) as lineage:
        current = _current_consumed_authorization_lineage()
        assert current is lineage
        assert lineage.authorization_id == result.authorization.authorization_id
        assert lineage.authorization_hash == result.authorization.authorization_hash
        assert lineage.consumption_id == result.consumption_record.consumption_id
        assert lineage.operation_id == result.consumption_record.consumption_id
        assert (
            lineage.execution_intent_hash
            == result.authorization.execution_intent_hash
        )
        assert (
            lineage.action_class
            == result.authorization.execution_intent["intended_action"]
        )
        assert (
            lineage.target_identity
            == result.authorization.execution_intent["target_resource"]
        )
        assert (
            lineage.credential_reference_digest
            == result.consumption_record.credential_reference_digest
        )
        assert (
            lineage.credential_scope_digest
            == result.consumption_record.credential_scope_binding_digest
        )


@pytest.mark.asyncio
async def test_bridge_rejects_non_consumption_result():
    with pytest.raises(
        NativeV2BindExecutionLineageError,
        match="NVBEL_NATIVE_CONSUMPTION_RESULT_REQUIRED",
    ):
        with transport_consumed_native_v2_authorization_lineage(object()):
            pass


@pytest.mark.asyncio
async def test_bridge_rejects_tampered_consumption_binding():
    result = await _consume()
    tampered = replace(
        result,
        consumption_record=replace(
            result.consumption_record,
            execution_intent_hash="0" * 64,
        ),
    )
    with pytest.raises(
        NativeV2BindExecutionLineageError,
        match="NVBEL_NATIVE_CONSUMPTION_BINDING_MISMATCH",
    ):
        with transport_consumed_native_v2_authorization_lineage(tampered):
            pass


@pytest.mark.asyncio
async def test_bridge_rejects_result_claiming_prior_effect_authority():
    result = await _consume()
    tampered = replace(result, execution_authority_created=True)
    with pytest.raises(
        NativeV2BindExecutionLineageError,
        match="NVBEL_NATIVE_CONSUMPTION_STATE_INVALID",
    ):
        with transport_consumed_native_v2_authorization_lineage(tampered):
            pass

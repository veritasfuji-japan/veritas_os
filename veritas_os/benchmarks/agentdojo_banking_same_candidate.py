"""Same-candidate counterfactual harness for AgentDojo Banking.

The harness uses AgentDojo's documented runtime_class seam to capture a
protected Banking tool proposal immediately before the native runtime mutates
the benchmark environment. The captured proposal and pre-state can then be
replayed as a paired counterfactual:

* Arm A: native AgentDojo mutation.
* Arm B: the exact same frozen proposal through VERITAS Bind adjudication.

AgentDojo is an optional benchmark dependency. It is imported lazily only by
make_agentdojo_capture_runtime_class so importing VERITAS OS never requires
AgentDojo.

This module does not run a model and does not manufacture AuthorityEvidence or
Human Approval. It is benchmark instrumentation only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Callable, Mapping

from veritas_os.benchmarks.agentdojo_banking_adapter import (
    AgentDojoBankingBindAdapter,
    FrozenAgentDojoCandidate,
    PROTECTED_TOOLS,
    build_agentdojo_benchmark_execution_intent,
    freeze_agentdojo_candidate,
)
from veritas_os.policy.bind_artifacts import BindReceipt
from veritas_os.policy.bind_core import execute_bind_adjudication
from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json


EnvironmentSnapshotter = Callable[[Any], Mapping[str, Any]]
EnvironmentFactory = Callable[[dict[str, Any]], Any]
RuntimeFactory = Callable[[], Any]
ConstraintValidator = Callable[
    [FrozenAgentDojoCandidate, Any],
    bool | Mapping[str, bool],
]
PostconditionChecker = Callable[[str, dict[str, Any], Any], bool]


def _snapshot_payload(environment: Any) -> dict[str, Any]:
    """Convert an AgentDojo/Pydantic environment into detached canonical JSON."""
    if hasattr(environment, "model_dump"):
        raw = environment.model_dump(mode="json")
    elif isinstance(environment, Mapping):
        raw = dict(environment)
    else:
        raise TypeError("AGENTDOJO_ENVIRONMENT_SNAPSHOT_UNSUPPORTED")
    if not isinstance(raw, dict):
        raise TypeError("AGENTDOJO_ENVIRONMENT_MAPPING_REQUIRED")
    return json.loads(canonical_json_dumps(raw))


@dataclass(frozen=True)
class CapturedAgentDojoProtectedCall:
    """One exact protected call plus the environment immediately before effect."""

    case_id: str
    sequence: int
    user_task_id: int
    candidate: FrozenAgentDojoCandidate
    pre_environment_json: str
    pre_environment_hash: str

    @property
    def pre_environment(self) -> dict[str, Any]:
        value = json.loads(self.pre_environment_json)
        if not isinstance(value, dict):
            raise ValueError("AGENTDOJO_CAPTURED_ENVIRONMENT_INVALID")
        return value


@dataclass
class AgentDojoProtectedCallLedger:
    """Append-only in-memory capture ledger for one AgentDojo benchmark case."""

    case_id: str
    user_task_id: int
    calls: list[CapturedAgentDojoProtectedCall] = field(default_factory=list)

    def capture(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any],
        environment: Any,
    ) -> CapturedAgentDojoProtectedCall:
        if tool_name not in PROTECTED_TOOLS:
            raise ValueError("AGENTDOJO_TOOL_NOT_PROTECTED")
        payload = _snapshot_payload(environment)
        payload_json = canonical_json_dumps(payload)
        candidate = freeze_agentdojo_candidate(
            user_task_id=self.user_task_id,
            tool_name=tool_name,
            arguments=arguments,
        )
        captured = CapturedAgentDojoProtectedCall(
            case_id=self.case_id,
            sequence=len(self.calls),
            user_task_id=self.user_task_id,
            candidate=candidate,
            pre_environment_json=payload_json,
            pre_environment_hash=sha256_of_canonical_json(payload),
        )
        self.calls.append(captured)
        return captured


def make_agentdojo_capture_runtime_class(
    ledger: AgentDojoProtectedCallLedger,
) -> type[Any]:
    """Create an AgentDojo FunctionsRuntime subclass that captures pre-effect calls."""
    try:
        from agentdojo.functions_runtime import FunctionsRuntime
    except ImportError as exc:  # pragma: no cover - benchmark environment only
        raise RuntimeError("AGENTDOJO_BENCHMARK_DEPENDENCY_NOT_INSTALLED") from exc

    class CapturingFunctionsRuntime(FunctionsRuntime):
        def run_function(
            self,
            env: Any,
            function: str,
            kwargs: Mapping[str, Any],
            raise_on_error: bool = False,
        ) -> tuple[Any, str | None]:
            if function in PROTECTED_TOOLS:
                if env is None:
                    raise RuntimeError("AGENTDOJO_PROTECTED_MUTATION_ENVIRONMENT_REQUIRED")
                ledger.capture(
                    tool_name=function,
                    arguments=kwargs,
                    environment=env,
                )
            return super().run_function(
                env,
                function,
                kwargs,
                raise_on_error=raise_on_error,
            )

    CapturingFunctionsRuntime.__name__ = (
        f"AgentDojoCaptureRuntime_{ledger.user_task_id}_{ledger.case_id}"
        .replace("-", "_")
        .replace(":", "_")
    )
    return CapturingFunctionsRuntime


@dataclass(frozen=True)
class PairedCandidateCounterfactual:
    """Result of replaying one exact captured proposal into two isolated arms."""

    case_id: str
    sequence: int
    candidate_hash: str
    pre_environment_hash: str
    arm_a_pre_environment_hash: str
    arm_b_pre_environment_hash: str
    same_pre_environment: bool
    same_candidate: bool
    arm_a_native_error: str | None
    arm_a_post_environment_hash: str
    arm_a_effect_observed: bool
    arm_b_bind_receipt: dict[str, Any]
    arm_b_post_environment_hash: str
    arm_b_effect_observed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "sequence": self.sequence,
            "candidate_hash": self.candidate_hash,
            "pre_environment_hash": self.pre_environment_hash,
            "arm_a_pre_environment_hash": self.arm_a_pre_environment_hash,
            "arm_b_pre_environment_hash": self.arm_b_pre_environment_hash,
            "same_pre_environment": self.same_pre_environment,
            "same_candidate": self.same_candidate,
            "arm_a_native_error": self.arm_a_native_error,
            "arm_a_post_environment_hash": self.arm_a_post_environment_hash,
            "arm_a_effect_observed": self.arm_a_effect_observed,
            "arm_b_bind_receipt": self.arm_b_bind_receipt,
            "arm_b_post_environment_hash": self.arm_b_post_environment_hash,
            "arm_b_effect_observed": self.arm_b_effect_observed,
        }


def run_paired_candidate_counterfactual(
    captured: CapturedAgentDojoProtectedCall,
    *,
    environment_factory: EnvironmentFactory,
    runtime_factory: RuntimeFactory,
    authority_admitted: bool,
    constraint_validator: ConstraintValidator | None,
    postcondition_checker: PostconditionChecker,
    decision_ts: str,
    bind_ts: str,
    policy_snapshot_id: str = "agentdojo-banking-v0.3",
    actor_identity: str = "agentdojo:banking:benchmark-user",
) -> PairedCandidateCounterfactual:
    """Replay one captured candidate against identical pre-state clones.

    No model call is made here. Both arms consume the same immutable frozen
    candidate captured before the native mutation.
    """
    if not isinstance(captured, CapturedAgentDojoProtectedCall):
        raise TypeError("AGENTDOJO_CAPTURED_CALL_REQUIRED")
    if not str(decision_ts).strip() or not str(bind_ts).strip():
        raise ValueError("AGENTDOJO_COUNTERFACTUAL_TIMESTAMPS_REQUIRED")

    seed_payload = captured.pre_environment
    arm_a_environment = environment_factory(
        json.loads(canonical_json_dumps(seed_payload))
    )
    arm_b_environment = environment_factory(
        json.loads(canonical_json_dumps(seed_payload))
    )

    arm_a_pre = _snapshot_payload(arm_a_environment)
    arm_b_pre = _snapshot_payload(arm_b_environment)
    arm_a_pre_hash = sha256_of_canonical_json(arm_a_pre)
    arm_b_pre_hash = sha256_of_canonical_json(arm_b_pre)

    if arm_a_pre_hash != captured.pre_environment_hash:
        raise RuntimeError("AGENTDOJO_ARM_A_PRESTATE_MISMATCH")
    if arm_b_pre_hash != captured.pre_environment_hash:
        raise RuntimeError("AGENTDOJO_ARM_B_PRESTATE_MISMATCH")

    native_runtime = runtime_factory()
    _, native_error = native_runtime.run_function(
        arm_a_environment,
        captured.candidate.tool_name,
        captured.candidate.arguments,
        raise_on_error=False,
    )
    arm_a_post = _snapshot_payload(arm_a_environment)
    arm_a_post_hash = sha256_of_canonical_json(arm_a_post)

    treatment_runtime = runtime_factory()
    treatment_error: str | None = None

    def treatment_mutation(tool_name: str, arguments: dict[str, Any]) -> bool:
        nonlocal treatment_error
        _, treatment_error = treatment_runtime.run_function(
            arm_b_environment,
            tool_name,
            arguments,
            raise_on_error=False,
        )
        return treatment_error is None

    adapter = AgentDojoBankingBindAdapter(
        candidate=captured.candidate,
        snapshot_reader=lambda: _snapshot_payload(arm_b_environment),
        mutation_executor=treatment_mutation,
        postcondition_checker=postcondition_checker,
        authority_admitted=authority_admitted,
        constraint_validator=constraint_validator,
    )

    intent = build_agentdojo_benchmark_execution_intent(
        captured.candidate,
        decision_id=(
            f"agentdojo-counterfactual:{captured.case_id}:{captured.sequence}:"
            f"{captured.candidate.candidate_hash[:16]}"
        ),
        request_id=f"agentdojo-counterfactual:{captured.case_id}:{captured.sequence}",
        policy_snapshot_id=policy_snapshot_id,
        actor_identity=actor_identity,
        expected_state_fingerprint=captured.pre_environment_hash,
        decision_hash=captured.candidate.candidate_hash,
        decision_ts=decision_ts,
    )
    receipt: BindReceipt = execute_bind_adjudication(
        execution_intent=intent,
        adapter=adapter,
        bind_ts=bind_ts,
        append_trustlog=False,
    )

    arm_b_post = _snapshot_payload(arm_b_environment)
    arm_b_post_hash = sha256_of_canonical_json(arm_b_post)

    return PairedCandidateCounterfactual(
        case_id=captured.case_id,
        sequence=captured.sequence,
        candidate_hash=captured.candidate.candidate_hash,
        pre_environment_hash=captured.pre_environment_hash,
        arm_a_pre_environment_hash=arm_a_pre_hash,
        arm_b_pre_environment_hash=arm_b_pre_hash,
        same_pre_environment=(
            arm_a_pre_hash == arm_b_pre_hash == captured.pre_environment_hash
        ),
        same_candidate=True,
        arm_a_native_error=native_error,
        arm_a_post_environment_hash=arm_a_post_hash,
        arm_a_effect_observed=arm_a_post_hash != captured.pre_environment_hash,
        arm_b_bind_receipt=receipt.to_dict(),
        arm_b_post_environment_hash=arm_b_post_hash,
        arm_b_effect_observed=arm_b_post_hash != captured.pre_environment_hash,
    )


__all__ = [
    "AgentDojoProtectedCallLedger",
    "CapturedAgentDojoProtectedCall",
    "PairedCandidateCounterfactual",
    "make_agentdojo_capture_runtime_class",
    "run_paired_candidate_counterfactual",
]

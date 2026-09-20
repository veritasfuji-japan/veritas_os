# AgentDojo Banking same-candidate counterfactual harness

Status: benchmark instrumentation only — no scored run.

TASK-023 requires the neutral/native and VERITAS treatment evidence to avoid a
model-regeneration confound.

AgentDojo Banking task execution is iterative: after a tool result, the model
can continue and propose later calls. Once an admitted or blocked effect differs,
the later trajectories may legitimately diverge.

Therefore the first causal comparison is defined per protected candidate.

## Capture seam

Pinned AgentDojo v0.1.35 exposes TaskSuite.run_task_with_pipeline with a
runtime_class argument.

The harness provides make_agentdojo_capture_runtime_class, which subclasses
AgentDojo FunctionsRuntime lazily and captures a protected call immediately
before FunctionsRuntime.run_function performs the native effect.

AgentDojo source is not patched.

For every protected call the ledger records:

- case id;
- call sequence;
- public user-task id;
- exact protected tool name and arguments;
- canonical candidate hash;
- canonical pre-environment;
- pre-environment SHA-256.

## Paired replay

run_paired_candidate_counterfactual creates two fresh environments from the
same captured pre-state and verifies their hashes before either arm runs.

captured proposal + captured pre-state
→ Arm A: native FunctionsRuntime.run_function
→ Arm B: AgentDojoBankingBindAdapter → execute_bind_adjudication → apply only if admitted

No model call occurs during paired replay.

This establishes same candidate + same pre-state for the immediate protected
action comparison.

## Native whole-task metrics

AgentDojo native whole-task utility and security output is preserved from the
native benchmark run.

The per-candidate counterfactual does not claim that a blocked treatment arm
would have followed the same later model trajectory. It therefore must not
fabricate a treatment-arm whole-task utility or security score from immediate
effect evidence.

A later full treatment-pipeline run may be reported separately, but after an
effect divergence its later model calls are observational treatment behavior,
not same-candidate paired events.

## Authority boundary

The harness does not issue or validate benchmark AuthorityEvidence itself.

The caller may set authority_admitted true only after the separately
preregistered signed benchmark AuthorityEvidence and runtime-validation path
has succeeded.

The AgentDojo user prompt remains neither AuthorityEvidence nor Human Approval.

## Dependency boundary

AgentDojo is imported only when make_agentdojo_capture_runtime_class is called.

VERITAS package import, normal tests and production paths do not gain a runtime
AgentDojo dependency.

## Claims

This harness proves only a deterministic pairing mechanism and fail-closed
counterfactual execution boundary.

It is not a benchmark result, independent validation, a production banking
policy, evidence that later post-divergence model trajectories are identical,
production readiness, or certification.

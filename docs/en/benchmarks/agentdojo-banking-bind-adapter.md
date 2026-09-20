# AgentDojo Banking benchmark Bind adapter

Status: **benchmark instrumentation only — no benchmark result**

TASK-022 preregisters a standalone external-benchmark comparison using AgentDojo
Banking.  This module provides the minimal VERITAS-side adapter required to
implement the treatment arm without changing the frozen production/execution
architecture.

## Source pins

- AgentDojo repository: `ethz-spylab/agentdojo`
- AgentDojo release: `v0.1.35`
- AgentDojo release commit: `a75aba7631d3ca5fb7ab938965c97ead2f9ff84b`
- benchmark version: `v1.2.2`
- suite: `banking`
- preregistration: TASK-022 v0.2 draft

## Boundary

```
AgentDojo proposed protected tool call
→ freeze exact candidate
→ independently verified benchmark governance
→ AgentDojoBankingBindAdapter
→ existing execute_bind_adjudication
→ adapter.apply
→ AgentDojo sandbox mutation callback
```

The adapter itself does not verify signatures or manufacture authority.  The
runner must supply `authority_admitted=True` only after the separately
preregistered AuthorityEvidence and RuntimeAuthorityValidator path succeeds.

The adapter never treats the AgentDojo user prompt as Human Approval.

## Same-candidate binding

`freeze_agentdojo_candidate` canonicalizes the proposed tool name/arguments
and binds them to:

- AgentDojo exact source commit;
- benchmark version;
- Banking suite;
- user task id.

The resulting SHA-256 is embedded in the benchmark ExecutionIntent
`target_resource`, `evidence_refs` and `approval_context`.  Candidate
substitution therefore fails the adapter's Bind-time checks.

## Mutation policy

The v0.2 preregistered public-prompt-derived policy is encoded in
`TASK_MUTATION_POLICY`.

Only tasks 3, 4 and 15 are conditionally admissible.  They still require a
runner-supplied deterministic `constraint_validator`.  Missing or malformed
constraint results fail closed.

All other protected mutations are refused for this first benchmark version,
including mutations for read-only or underspecified tasks.

## Effect boundary

The underlying AgentDojo mutating callback is invoked only from
`AgentDojoBankingBindAdapter.apply`.

The adapter records `apply_attempted` and prohibits a second apply call on the
same instance.

No network endpoint, credential resolution, TrustLog append, production
authorization, customer system or real bank effect is introduced by this
module.

## Non-claims

This implementation is not:

- a completed AgentDojo benchmark run;
- independent validation;
- a production banking policy;
- proof of real banking authority;
- proof of Human Approval effectiveness;
- certification or regulatory approval.

The benchmark execution gate remains closed until the remaining TASK-022
preregistration fields are frozen.

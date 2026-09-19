# Human Approval Alternatives Evidence v1

This document describes a deterministic local/offline evidence supplement for
the SaaS permission-change Human Approval fixture.

The purpose is to test one narrow reconstructability question:

> Can a later reviewer determine which alternatives were technically available,
> which alternatives were actually presented in the review session, which path
> was selected, and when it was selected?

This is the third bounded human-oversight evidence iteration. It is not a
self-issued human-oversight rating.

## Evidence fields

`HumanApprovalReceipt` may optionally carry:

```text
review_alternatives: list[dict[str, Any]] | None
selected_alternative_id: str | None
selected_at: str | None
```

Each recorded alternative has this explicit shape:

```text
alternative_id
alternative_type
available
presented
presented_at
unavailable_reason
```

The bounded v1 alternative types are:

- `approve`
- `approve_narrower`
- `reject`
- `defer`
- `escalate`

## Critical distinction

```text
available != presented
```

An alternative may be technically actionable without being surfaced to the
reviewer. Conversely, an alternative can be shown in the review session while
being unavailable, for example as a disabled escalation path with an explicit
unavailability reason.

Those states are intentionally not collapsed.

The deterministic fixture includes both forms:

- `defer_review` is available but not presented;
- `escalate_for_secondary_review` is presented but unavailable;
- `reject_request` is both available and presented.

A separate evidence-only reject receipt demonstrates that the same recorded
alternative set can represent `reject_request` as the selected path. That
synthetic receipt is not reported as a runtime execution result.

## Prior timing result is preserved

The third evidence packet keeps the prior engagement-timing fixture unchanged:

- `ticket:AR-1001` opened/presented at 23:55 UTC;
- `manager_approval:MA-2002` opened/presented at 23:57 UTC;
- approval at 00:00 UTC.

The derived latest-basis-open-to-approval interval remains **180 seconds**.

The fixture is not lengthened merely to obtain a more favorable interpretation.

## Evidentiary boundary

The implementation intentionally preserves these distinctions:

```text
available != presented
presented != considered
selected != understood
recorded choice != proof of reviewer cognition
```

The artifact can preserve observable review-session state.

It does not prove:

- that the reviewer understood an alternative;
- that the reviewer mentally compared every presented option;
- that the reviewer believed the recorded rationale;
- that the reviewer exercised independent judgment;
- that sufficient review time was available;
- that the approval was substantively sound.

## Runtime boundary

Alternative-set evidence is **evidence-only in v1**.

`validate_human_approval_alternatives_evidence()` is separate from
`validate_human_approval_receipt()`.

Missing, partial, or invalid alternatives evidence does not by itself change:

- Authority validation;
- Human Approval runtime validity;
- scope validation;
- runtime admissibility;
- Bind behavior;
- refusal behavior;
- Outcome semantics.

A future decision to make any alternative evidence an execution prerequisite
would require a separate architecture and policy change.

## Deterministic packet

Generate the local/offline third data point with:

```bash
python3 scripts/demo/export_human_approval_alternatives_evidence.py
```

The packet preserves:

- the unchanged SaaS `valid_authority_and_approval` runtime outcome for context;
- the prior 180-second engagement-timing result;
- the alternative set;
- available/presented separation;
- the selected path and timestamp;
- an evidence-only reject-selection example;
- explicit evidence and runtime boundaries;
- a deterministic packet hash.

It performs no network calls and requires no credentials.

## Claim boundary

This local/offline artifact is not:

- proof of live human behavior;
- proof that alternatives were cognitively considered;
- production Human Approval assurance;
- third-party certification;
- regulatory approval;
- production deployment proof;
- evidence that Oversight Substance or Alternatives Considered has reached any
  particular external rating.

External re-evaluation should determine what, if anything, the additional
evidence changes.

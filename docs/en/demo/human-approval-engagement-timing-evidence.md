# Human Approval Engagement-Timing Evidence (Local/Offline)

This document describes a narrow, backward-compatible evidence signal for `HumanApprovalReceipt`.

## Purpose

`approval_basis_refs` can show which artifacts a human approval cites. By itself, that does not show when the referenced material was opened or presented relative to the approval decision.

The optional field:

```text
approval_basis_opened_at: dict[str, str] | None
```

records a deterministic mapping from an `approval_basis_ref` to the timezone-aware ISO/RFC3339 timestamp at which the referenced material was opened or presented in the human-review workflow.

Example:

```json
{
  "ticket:AR-1001": "2026-04-24T23:55:00+00:00",
  "manager_approval:MA-2002": "2026-04-24T23:57:00+00:00"
}
```

with an approval at:

```text
2026-04-25T00:00:00+00:00
```

The latest recorded basis-open event is therefore 180 seconds before approval.

## Evidentiary boundary

This signal records when a referenced approval-basis artifact was opened or presented.

It does **not** prove that the reviewer:

- read the material;
- understood it;
- independently evaluated it;
- agreed with it;
- compared it against another source; or
- exercised meaningful judgment.

A missing timing signal also does not prove that the reviewer failed to engage with the material. It means the timing evidence is unavailable.

## Backward compatibility

The field is optional.

When `approval_basis_opened_at` is `None`, it is omitted from the serialized/hash payload. Existing receipts therefore retain their previous canonical serialization and deterministic digest behavior.

When the field is present, the mapping is canonicalized by reference key and included in the receipt hash.

## Evidence validation

`validate_human_approval_engagement_timing()` validates the evidence signal separately from runtime approval/admissibility logic.

When timing evidence is present:

- each recorded key must match an existing `approval_basis_refs` entry;
- each timestamp must be timezone-aware ISO/RFC3339;
- an open/presentation timestamp may not be later than `approved_at`;
- partial mappings are permitted and are reported as incomplete rather than inferred as non-engagement.

This validation is intentionally separate from `validate_human_approval_receipt()`.

Malformed or incomplete engagement evidence does not, by itself, become a new runtime authorization, admissibility, scope, bind, or refusal predicate.

## Reviewer-facing summary

`summarize_human_approval_engagement_timing()` exposes:

- `approval_basis_opened_at`;
- `all_approval_basis_refs_have_open_signal`;
- `seconds_from_latest_basis_open_to_approval`;
- timing-evidence validation status and failure reasons.

The elapsed interval is derived from the latest recorded basis-open timestamp to `approved_at`; it is not stored as an independent source of truth in the receipt.

## SaaS permission-change evidence supplement

Generate the deterministic local/offline supplement with:

```bash
python3 scripts/demo/export_human_approval_engagement_timing_evidence.py
```

The supplement uses the existing `valid_authority_and_approval` SaaS permission-change case as context and binds these deterministic timing signals into a Human Approval Receipt:

- `ticket:AR-1001` opened/presented at `2026-04-24T23:55:00+00:00`;
- `manager_approval:MA-2002` opened/presented at `2026-04-24T23:57:00+00:00`;
- approval recorded at `2026-04-25T00:00:00+00:00`.

The resulting reviewer summary reports `180` seconds from the latest basis-open signal to approval.

## Non-goals

This change does not add:

- preservation of the substantive contents of the referenced ticket or manager approval;
- evidence that alternative actions were presented or weighed;
- production approval UI telemetry;
- live SaaS/IAM/IdP integration;
- a new fail-closed runtime rule based on engagement timing; or
- a claim that human oversight is substantively sufficient.

The evidence exists so an external reviewer can evaluate that question without VERITAS inferring a reviewer state of mind.

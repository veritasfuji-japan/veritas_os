# Material Change Semantics Consolidation Audit

Status: **DOCUMENTATION-ONLY / NON-ENFORCING**  
Audit date: 2026-09-16  
Audited `main`: `adf185a8b4318a3b14f13fd5c2a67303e46133b8`  
Frozen controlled-proof anchor: `ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc`

## 1. Purpose

This audit asks one narrow question:

> Does VERITAS need a new Material Change enforcement engine now, or are the
> relevant semantics already distributed across existing approval, intent,
> bind-context, revalidation, and drift mechanisms?

The audit is intentionally non-enforcing. It adds no runtime predicate, no new
authorization meaning, no new consumption meaning, and no external-effect path.

It also follows the current Company operating rule: if a gap does not block
External PoC #1 and no real partner or paid prospect currently requires Product
implementation, defer implementation by default.

## 2. Sources inspected

The audit treats current executable code and the frozen proof contract as the
source of truth. The relevant surfaces are:

1. `veritas_os/governance/human_approval_receipt.py`
2. `veritas_os/policy/canonical_execution_intent_formation.py`
3. `veritas_os/policy/execution_intent_pre_bind_validation.py`
4. `veritas_os/policy/real_bind_context.py`
5. `veritas_os/policy/native_bind_authorization_consumption.py`
6. `veritas_os/policy/bind_artifacts.py`
7. `veritas_os/policy/bind_revalidation.py`
8. `scripts/demo/generate_evaluation_drift_detection.py`
9. the Human Approval Workbench approval-edit invalidation path
10. `docs/en/architecture/controlled-execution-proof-architecture-freeze-v1.md`

## 3. Current semantic inventory

### 3.1 Human Approval context binding

`HumanApprovalReceipt` already carries and can validate exact governed-context
bindings including:

- `request_ref`;
- `ai_output_ref`;
- `execution_intent_id`;
- `decision_id`;
- `approved_action_class`;
- `policy_snapshot_id`;
- `authority_evidence_id`; and
- `bind_context_hash`.

`validate_human_approval_context_binding()` deterministically fails when a
provided expected binding differs from the receipt.

This is already an approval-to-context anti-substitution boundary. A new
Material Change engine must not duplicate or weaken it.

### 3.2 ExecutionIntent exactness

Canonical ExecutionIntent formation binds the complete mapped intent to an
`execution_intent_id` and `execution_intent_hash`.

Pre-bind validation independently reconstructs and verifies the exact intent,
its field mapping, source formation, required fields, lineage, and hash before
reporting readiness for bind preflight.

This is an integrity/exactness boundary, not a live-state or approval-validity
classifier.

### 3.3 Real Bind context

The canonical real bind context hash already binds a verified source gate to:

- source gate review hash;
- execution intent ID and hash;
- adapter contract ID and hash;
- endpoint identity binding digest;
- credential reference digest; and
- credential scope binding digest.

This means endpoint, credential-reference, credential-scope, adapter-contract,
or exact execution-intent substitution is already represented in a protected
context digest.

### 3.4 Native v2 current-context recheck

Before native v2 single-use consumption succeeds, current evidence is freshly
reverified. Current context must still match issuance-time authorization fields,
including bind context, action-contract digest, exact execution intent, intent
ID/hash, and source gate hash.

A mismatch fails closed as `NABC_CURRENT_CONTEXT_MISMATCH`.

This is already a pre-effect stale/substituted-context rejection mechanism.

### 3.5 Bind-time state drift and revalidation

`ExecutionIntent` carries `expected_state_fingerprint`. `BindReceipt` carries
live before/after fingerprints, `drift_check_result`, and a replayable
`revalidation_context`.

Bind replay/revalidation can compare expected and live state under the stored
admissibility configuration, including drift sensitivity and approval/TTL
freshness requirements.

This is the closest existing mechanism to runtime state drift, but it does not
provide one product-wide vocabulary for explaining every kind of material
change.

### 3.6 Evaluation Drift Detection

Evaluation Drift Detection v1 is an offline, non-enforcing reviewer/demo helper.
It classifies evaluation/outcome attribution signals such as policy identity,
rule version, evaluator version, refusal boundary, and material-context causes.

It explicitly does not participate in runtime admissibility or execution.
Therefore it should not be reused as pre-effect Material Change authority
without a separate architecture decision.

### 3.7 Human Approval edit invalidation in the Workbench

The frontend Human Approval Workbench invalidates an approved UI record when
reviewer/signature/reason metadata is edited and requires re-approval in that
workflow.

This is useful UX/audit behavior but is not a backend execution-authority source
of truth and must not be treated as one.

### 3.8 Human Approval engagement timing

`approval_basis_opened_at` is hash-bound reviewer evidence when present. It can
show when cited material was opened/presented relative to approval.

It remains evidence-only. It does not prove reading, understanding, independent
judgment, or whether alternatives were considered, and it does not alter
runtime authorization/admissibility semantics.

## 4. Consolidated matrix

| Change / condition | Existing detection or binding | Current enforcement meaning | Reviewer explanation quality |
|---|---|---|---|
| ExecutionIntent field substitution | intent hash + canonical pre-bind validation | fail closed | Strong technical evidence, limited business-level explanation |
| Action-class substitution | Human Approval binding / governance validation | fail closed | Good |
| Policy snapshot substitution | Human Approval binding / current governance checks | fail closed / revalidation | Good |
| Authority evidence substitution | Human Approval context + authority proof lineage | fail closed | Good |
| Endpoint identity change | bind-context digest | context mismatch / fail closed | Technically strong, field-level cause not unified |
| Credential reference change | bind-context digest | context mismatch / fail closed | Technically strong, field-level cause not unified |
| Credential scope change | bind-context digest | context mismatch / fail closed | Technically strong, field-level cause not unified |
| Adapter contract change | bind-context / action-contract digest | context mismatch / fail closed | Technically strong, field-level cause not unified |
| Live state fingerprint drift | bind admissibility / revalidation | block or escalate according to stored rules | Good within bind evidence |
| Approval expiry/freshness | approval validation / bind admissibility | fail closed / block or escalate | Good |
| Approval metadata edit in Workbench | frontend invalidation | UI re-approval required only | Good UX evidence; not backend authority |
| Post-outcome evaluator/policy drift | Evaluation Drift Detection helper | non-enforcing review signal | Good for offline review |
| Business parameter meaning, e.g. `amount 50000 -> 75000` | usually captured through exact intent/context hashes if modeled in the intent/contract | mismatch can fail closed | **Gap: no unified field-level materiality explanation** |
| Unknown/unavailable comparison input | mechanism-dependent | generally fail closed where required | **Gap: no unified `INDETERMINATE_MATERIAL_CHANGE` explanation vocabulary** |

## 5. Main finding

No evidence from this audit supports adding a second generic change-detection or
approval-invalidation engine to the frozen controlled proof path.

The existing mechanisms already provide substantial protection against stale,
substituted, or drifted execution context. They operate at different lifecycle
stages and are not merely duplicates:

- approval context protects what the human approved;
- ExecutionIntent protects the exact intended action representation;
- bind context protects exact target/credential/adapter context;
- native consumption rechecks current versus authorized context;
- bind revalidation handles live-state drift;
- Evaluation Drift Detection explains post-outcome evaluation drift.

The missing capability is primarily **unified reviewer-facing explanation**, not
another authorization primitive.

## 6. Identified explanation gap

Today a secure runtime path may correctly refuse execution with a coarse stable
reason such as `NABC_CURRENT_CONTEXT_MISMATCH`, while the reviewer still has to
reconstruct which protected dimension changed.

A future additive explanation artifact could make that difference explicit, for
example:

```json
{
  "changed_dimension": "business_parameter.amount",
  "approved_value_digest": "...",
  "current_value_digest": "...",
  "classification": "MATERIAL",
  "approval_effect": "REAPPROVAL_REQUIRED",
  "reason_code": "APPROVAL_SENSITIVE_PARAMETER_CHANGED"
}
```

That artifact must be derived from independently verified before/after evidence.
It must not turn caller-declared labels into execution authority.

## 7. Recommendation

### Now

1. Preserve the frozen controlled execution semantics.
2. Do not add a new generic Material Change enforcement engine.
3. Keep External PoC #1 as the immediate Product/Company priority when the real
   partner artifact arrives.
4. Use this audit as the semantic inventory for PoC-specific change-boundary
   documentation.
5. If a bounded PoC needs material-change evidence, define the relevant changed
   fields and invalidation conditions for that action class first.

### Later, only if pulled by external evidence

Consider a small **Material Change Explanation Boundary** that is:

- additive and reviewer-facing;
- side-effect free;
- derived from existing verified context and stable failure reasons;
- explicit about `UNCHANGED`, `MATERIAL`, and `INDETERMINATE` explanation states;
- incapable of issuing Authority, Human Approval, BindAuthorization, credentials,
  or execution permission; and
- unable to weaken any existing fail-closed decision.

Do not compose it into frozen authorization/consumption semantics without an
explicit architecture-reopen decision and human maintainer approval.

## 8. Exit criteria before Product implementation

A runtime or governance implementation should not begin solely because this
audit identifies an explanation gap. At least one of the following should be
true:

1. External PoC #1 or another real partner artifact demonstrates a concrete
   reviewer gap that cannot be handled by current evidence;
2. a qualified paid-PoC workflow requires explicit field-level change
   explanation or reapproval classification; or
3. a security/correctness defect shows that existing context binding can permit
   an unauthorized material substitution.

If none is true, documentation/runbook treatment remains the default.

## 9. Frozen-boundary statement

This audit changes no runtime behavior and makes no new production claim.

It does not change:

- authorization issuance or consumption;
- Human Approval admissibility;
- current governance rechecks;
- credential resolution;
- Bind dispatch;
- `EFFECT_UNKNOWN` or retry semantics;
- reconciliation;
- BindReceipt / Outcome semantics;
- confirmed-effect semantics; or
- any external-effect path.

The controlled-proof architecture remains frozen.
# Explicit approval for system resume

Status: proposed

In secure and prod, system resume should require both an authenticated caller
with `config_write` and verified human approval for the active halt. Today,
the HTTP route sets `system_resume_approved` after authenticating the operator.
The existing integration test supplies a negative authority result and confirms
that Bind preserves the halt and keeps decision admission closed.

## Approval and execution

1. Assign a fresh, opaque identifier to each halt, including a halt established
   at startup. Expose the identifier to the operator through the authenticated
   halt status API. A new halt invalidates approvals for the previous halt.
2. Define the resume approval request before issuing the
   [signed Human Approval Receipt](human-approval-receipt.md).
   Bind the signed context to the deployment, the active halt identifier,
   the `system_resume` action, the authenticated execution principal, and the
   governing policy snapshot. Use the same request and intent identifiers
   at issuance and execution.
3. In secure and prod, verify the signed receipt with the configured verifier
   and signer policy. Apply the existing production verifier policy in prod.
   Check the action, deployment, principal, policy, expiry and current halt
   before giving Bind a positive authority result. An unavailable verifier,
   stale approval or context mismatch leaves the system halted.
4. At the state transition, compare the expected halt identifier with the
   current identifier under the same lock or transaction that clears the halt.
   Recheck expiry at commit. A successful transition removes that halt
   identifier, so a duplicate request cannot clear a subsequent halt.
5. Record the verified approval reference, halt identifier, authenticated
   execution principal and outcome in the audit evidence. Keep the emergency
   halt available without a resume approval.

The current halt controller stores its state in process. A local lock can
protect the transition within one process. A deployment-wide guarantee across
workers needs shared authoritative halt state with an atomic conditional update.
Before enabling the strict policy, confirm how approvers prove their identity,
which signers may approve resumes, and how operators obtain signed approvals
after a startup halt.

## Acceptance checks

| Scenario | Expected result |
|---|---|
| Approval missing, invalid, expired or for another halt | Resume is refused and decision admission returns `503 HALTED` |
| Approval is valid for the active halt, action, principal and policy | Bind commits the resume and decision admission reopens |
| New halt occurs after approval verification and before commit | The new halt remains active and decision admission stays closed |
| Two requests try to resume the same halt | At most one transition commits |
| Approval verification is unavailable | Resume is refused and emergency halt remains available |

Exercise these cases through the mounted HTTP application using synthetic data.
Use a separate shared-state test with multiple workers before claiming
deployment-wide coverage.

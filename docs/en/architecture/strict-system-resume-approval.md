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
2. Prepare the resume request and issue the
   [signed Human Approval Receipt](human-approval-receipt.md) through the
   startup recovery flow below. Bind the signed context to the deployment,
   the active halt identifier, the `system_resume` action, the authenticated
   execution principal, and the governing policy snapshot. Reuse the prepared
   request and intent identifiers for Bind and audit correlation.
3. In secure and prod, verify the signed receipt with the configured verifier
   and signer policy. Apply the existing production verifier policy in prod.
   Check the action, deployment, principal, policy, expiry and current halt
   before giving Bind a positive authority result. An unavailable verifier,
   stale approval or context mismatch leaves the system halted.
4. At the state transition, compare the expected halt identifier with the
   current identifier under the same lock or transaction that clears the halt.
   Recheck expiry at commit. A successful transition removes that halt
   identifier, so a duplicate request cannot clear a subsequent halt.
5. Use the result of the conditional transition as the postcondition evidence
   for that resume. Record the cleared halt identifier, verified approval
   reference, authenticated execution principal and transition outcome. Report
   the current halt status separately. Keep the emergency halt available
   without a resume approval.

The current halt controller stores its state in process. A local lock can
protect the transition within one process. A deployment-wide guarantee across
workers needs shared authoritative halt state with an atomic conditional update.
## Startup recovery and approval issuance

`POST /v1/system/resume/prepare` implements the preparation step. Set
`VERITAS_DEPLOYMENT_ID` in the backend environment to a stable identifier
unique to the deployment. A caller with `config_write` can submit the request
without a body. The response includes the request and execution intent IDs,
active halt ID, authenticated execution principal, and SHA-256 digest of the
current canonical governance policy. Requests are kept in process memory.
Repeating preparation for the same principal and context returns the same
pending request. A new halt, policy, or deployment context supersedes older
requests. After a process restart, create a fresh request for the startup halt.

### Issue a signed approval during a halt

Provision a separate credential with `governance_write` for the human reviewer.
Set `VERITAS_SYSTEM_RESUME_APPROVER_ID` to its authenticated principal ID and
mount a dedicated Ed25519 private key at `VERITAS_SYSTEM_RESUME_SIGNING_KEY_FILE`
in the backend (URL-safe base64 raw key, mode 0600). Provision the verifier
separately with the public key, its SHA-256 raw-byte fingerprint as key ID,
the designated principal, and the role `system_resume_approver`. Assign the
executor and reviewer credentials to different people. The API distinguishes
authenticated key principals. When the governance policy lists
`approval_workflow.approver_identities`, include the reviewer there as well.

1. The executor gives the prepared request ID to the reviewer.
2. The reviewer authenticates and reads `GET /v1/system/resume/requests/{request_id}`.
   Review the displayed deployment, halt ID, execution principal and policy digest.
3. On acceptance, submit `{"decision":"approve","context_hash":"<reviewed hash>"}`
   to `POST /v1/system/resume/requests/{request_id}/approve` using the reviewer
   credential. The signed v1 receipt binds the complete prepared context.
   The reviewer can hand this artifact to the executor. Retries return the
   same receipt through its five-minute validity window. After expiry the
   executor prepares a new request, which requires a new review.

Issuance keeps the halt active. Runtime verification and enforcement at
`/v1/system/resume` are a subsequent implementation step.

Provision authorized human approvers and the approval verifier before enabling
strict resume. An operator with `config_write` can prepare a resume request via
an authenticated control-plane operation while decision admission is halted.
The server reads the active halt and policy, assigns the request and intent IDs,
and stores the pending request with the authenticated operator as the intended
executor. Preparation does not clear the halt.

An independently authenticated human approver reviews that pending request in
the configured approval workflow. A signing service authorized for
`system_resume` issues the receipt after the approver accepts the request.
The signer and verifier policies must establish the authorization and identity
of the signer and its association with the authenticated approver. The operator
submits the prepared request ID and signed receipt to the resume API. The server
loads the pending request and reconstructs the expected signed context from it
and current authoritative state. If the issuer or verifier is unavailable,
the halt remains active. The preparation, approval and submission steps must
all be usable during a startup halt without opening `/v1/decide`.

## Resume outcome and subsequent halts

Capture which halt was cleared as part of the successful conditional update.
Use that transition result to verify the resume even if a later status read
shows a new halt. If halt A was cleared before halt B was set, record the resume
of A as committed and report B as active. Keep decision admission closed under
B. If B replaced A before the conditional update, reject the resume of A and
leave B active. A status read alone cannot establish which transition occurred.

## Acceptance checks

| Scenario | Expected result |
|---|---|
| Approval missing, invalid, expired or for another halt | Resume is refused and decision admission returns `503 HALTED` |
| Approval is valid for the active halt, action, principal and policy | Bind commits the resume and decision admission reopens |
| New halt occurs after approval verification and before commit | The new halt remains active and decision admission stays closed |
| New halt occurs after the resume commits and before status is read | Record the first halt's resume as committed, report the new halt as active, and return `503 HALTED` from decision admission |
| Two requests try to resume the same halt | At most one transition commits |
| Authorized operator recovers from a startup halt | Prepare and approve while `/v1/decide` returns `503 HALTED`, then reopen admission through the approved resume |
| Approval verification is unavailable | Resume is refused and emergency halt remains available |

Exercise these cases through the mounted HTTP application using synthetic data.
Use a separate shared-state test with multiple workers before claiming
deployment-wide coverage.

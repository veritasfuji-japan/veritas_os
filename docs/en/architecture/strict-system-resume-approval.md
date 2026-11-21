# Explicit approval for system resume

Secure and production deployments require an independently signed approval before clearing the active halt.

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

## Shared deployment halt

For multiple API workers, apply Alembic revision `0013` and configure every
worker with `VERITAS_HALT_BACKEND=postgresql`, the same stable
`VERITAS_DEPLOYMENT_ID`, database, policy, approver and key configuration.
Use the primary PostgreSQL server for `VERITAS_DATABASE_URL`. The normal
shared authentication requirements still apply. Use a common protected
TrustLog directory on a filesystem that honors POSIX advisory locks across
all workers. Configure the same TrustLog encryption key or provider on every
worker so each can deliver queued records.
The default `memory` backend retains the single-worker strict startup guard.

Each shared worker startup preserves an existing halt or rearms the deployment
if it was running. Rolling restarts can therefore require a new approval.
Decision admission reads the authoritative row and refuses requests when it
cannot read it. Pending approvals are serialized under a deployment row lock.
The database clock gates the conditional release and checks approval expiry
again just before commit. The winning Bind receipt and encrypted audit
entries are saved in `deployment_resume_receipts` in the transaction that
clears the halt. A successful HTTP response confirms the database transition.
The TrustLog hash becomes available after file publication.

The API workers retry pending publication after startup and during operation.
A worker claims only a pending audit row while publishing, so slow file
writes and signed mirror delivery do not hold the emergency halt row.
Native JSONL writers serialize previous-hash lookup, rotation and append
across processes. The active and retained rotated logs use stable publication
identities to deduplicate retries. The authoritative receipt remains in
PostgreSQL, including after local log rotation. For a delayed audit record,
check `published_at` on the receipt row. Pending rows are retried after the
underlying error is resolved. Signed mirrors and transparency anchors retain
their destination-specific delivery guarantees.

## Startup recovery and approval issuance

`POST /v1/system/resume/prepare` implements the preparation step. Set
`VERITAS_DEPLOYMENT_ID` in the backend environment to a stable identifier
unique to the deployment. A caller with `config_write` can submit the request
without a body. The response includes the request and execution intent IDs,
active halt ID, authenticated execution principal, and SHA-256 digest of the
current canonical governance policy. Requests use the configured halt backend.
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
   same receipt while it is valid and the signing key is current. If the key is
   unavailable, retries fail closed. After key rotation or five-minute expiry the
   executor prepares a new request, which requires a new review.

Issuance keeps the halt active. Set `VERITAS_SYSTEM_RESUME_PUBLIC_KEY` to the
independently provisioned URL-safe base64 raw Ed25519 public key. The executor
posts `operator`, `request_id` and the complete signed `approval_artifact` to
`/v1/system/resume`. The authenticated credential determines the executor.
Configure the public key before startup and rotate it with the approval signer.
Development deployments continue to support operator-only resume. Providing
either approval field always selects the signed flow.

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
The PostgreSQL contention workflow exercises two API processes. It checks
rollback before commit, retry after file publication, a replacement halt
during stalled audit delivery, and native hash-chain integrity under
concurrent writes.

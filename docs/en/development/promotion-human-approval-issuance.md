# Promotion-bound Human Approval issuance

Call `issue_promotion_gate_bound_human_approval_artifact` in
`veritas_os.policy.gate_bound_human_approval_issuance` with the replay review,
runtime risk review, full final credential-scope source, trusted action
contract, actual human event, deployment-controlled signer, and aware `now`.
Only tests generate ephemeral signing keys; this API does not store keys or
create a human decision. The caller owns authentication and signer policy.

The source is independently verified. Approval cannot predate replay review;
signing cannot predate approval or be in the future; expiry must follow `now`
and cannot exceed the risk/replay deadline. Invalid input fails before signing.
Existing receipt construction enforces the intended action, scope, approver
identity, and approver role. Nonapproved results remain nonapproved.

The existing v1 signed receipt envelope is retained. Reserved receipt metadata
`promotion_approval_binding` binds review hashes, source projection, final
endpoint and credential-scope digests, intent, adapter, and Bind context under
the signature. Callers cannot override this namespace. Application metadata
outside it is not an authorization signal.

The result is an artifact, not a verified receipt or execution authorization.
Use the existing trusted Human Approval verifier and context-binding checks
as the next boundary. A downstream promotion consumer must also check the
signed promotion lineage against its independently verified current sources.
No automatic runtime integration, credential resolution, consumption, network
dispatch, or Bind invocation is added here. Approval does not replace authority
verification, revocation checks, or final runtime rechecks.

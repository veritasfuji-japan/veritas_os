# Independent Reviewer Reproduction Runner v1 — controlled proof

**Status: implementation candidate, not a completed third-party run.**
This procedure lets a reviewer operate the existing VERITAS controlled
Decision-to-Effect E2E on a disposable Docker host under their control. It does
not automatically establish a separately administered executor, independent
custodian, signed source authenticity, or certification.

## Reuse instead of reimplementing runtime logic

- Actual controlled test:
  veritas_os/tests/test_decision_to_effect_controlled_e2e.py
- Existing contract, identity and lineage verifier:
  scripts/validation/verify_reviewer_proof_contract_v1.py
- Existing required-artifact mutation cases:
  tests/validation/reviewer_proof_contract_e2e_checks.py
- New minimal orchestration:
  scripts/validation/run_reviewer_reproduction_v1.sh and
  scripts/validation/reviewer_proof_runner_v1.py
- Offline artifact verifier:
  scripts/validation/reviewer_reproduction_manifest_v1.py

No changes to production decision, native authorization, consumption, dispatch,
reconciliation, receipt or execution policy code are part of this runner.

## Requirements and trusted input

Use a fresh, clean checkout of the independently approved **40-character Git
commit SHA**. A reviewer must obtain that SHA through a trusted channel
*independent of the evidence bundle*. A PR-head SHA and a synthetic PR-merge SHA
are different; prefer an approved merged-main commit for a lasting checkpoint.

Requires Bash, Python 3 with the standard library, Git, Docker Engine and
Docker Compose v2. Docker builds need network access to fetch public package
dependencies. The controlled execution stage is isolated on an internal Docker
network and cannot use real provider credentials. The Docker daemon itself has
high privileges on the host; use a disposable reviewer-owned machine.

From a fresh detached checkout, run:

    git checkout --detach APPROVED_COMMIT_SHA
    bash scripts/validation/run_reviewer_reproduction_v1.sh \
      APPROVED_COMMIT_SHA /path/outside/checkout/new-evidence-directory

The target directory **must not already exist**, and its parent must exist.
The script rejects a dirty checkout, mismatched/malformed SHA, a target inside
the repository, or unavailable Docker. It creates an owner-only output
directory and does not alter Git source files or host DNS/port bindings.

Inside Docker:

1. Disposable PostgreSQL 16 holds execution and synthetic effect databases.
2. Temporary CA/server private keys are generated only inside the runner.
3. The pinned sandbox.example.invalid name resolves to container loopback.
4. The existing native v2 sandbox service listens on container port 443.
5. The existing normal/lost-response controlled E2E runs unchanged, including
   single-use consumption, read-only reconciliation and no blind retry.
6. Existing mandatory mutation tests run only **after** proof artifacts exist.
7. The original Reviewer Proof Contract validator runs against the same
   pinned checkout; missing/failed artifacts cause NO-GO.
8. The runner writes a hash/size manifest and validates it before finishing.

The internal network has **no host-published ports**, no Docker socket mount,
and the checkout is bind-mounted read-only. The proof container runs under the
reviewer's own host UID/GID, drops all Linux capabilities, and uses a
container-local unprivileged-port setting to bind TLS port 443. VERITAS runtime
data is redirected with VERITAS_RUNTIME_ROOT into disposable container tmpfs;
it never writes into the source checkout. A separate owner-only writable output
mount contains only the evidence bundle. Container
services and project-scoped DB
volume are removed on exit; generated private keys live only in container
temporary storage and are never part of the output bundle.

## Produced files

- report.json — existing controlled E2E PASS predicates, bounded claims
- evidence.json — existing synthetic decision/authorization/effect lineage
- reviewer-proof-validation.json — existing bounded consistency result
- reproduction-manifest.json — exact file sizes/digests, commit, runtime
  versions and explicit FALSE flags for independence/production claims

A successful command reports
PASS_BOUNDED_REVIEWER_OPERATED_REPRODUCTION_CONSISTENCY_ONLY.

**An artifact may exist after failure. A directory is only acceptable if both
the command exited zero and all verification stages passed.** Failed attempts
are NO-GO, never passing evidence.

## Independent offline inspection

The bundle verifier uses only Python standard library and takes an externally
pinned commit. No Docker, effect permission, HTTP connection or database is
needed for inspection:

    python3 -m scripts.validation.reviewer_reproduction_manifest_v1 verify \
      --bundle /path/to/copied-bundle \
      --expected-checkout-sha APPROVED_COMMIT_SHA

If a manifest digest was recorded separately by the reviewer, additionally
supply --expected-manifest-sha256 HEX64 to detect substitution of the entire
bundle. Without independently authenticated roots, matching self-hashes only
prove internal byte consistency, **not origin authenticity**. Even with the
expected SHA, the trust in the Git commit is an external assumption.

The manifest does not use a reviewer-held signing key and does not assert a
distinct administrative domain. To establish independent custody, a separate
host/administrator must hold and independently sign/attest observations, with a
public-key pin authenticated out of band and cross-host denial evidence.

## Explicit nonclaims and NO-GO boundaries

- Real TLS and PostgreSQL are used, but effects, decisions and credentials are
  synthetic. There are **no real provider API calls or IAM changes**.
- This is not production deployment, customer security assurance, evidence of
  universal bypass closure, Strict RC1 physical STOP timing, trusted UTC,
  TrustLog exactly-once publication, regulatory approval or certification.
- The reviewer Docker container owns the service, test and report; therefore
  independent effect observation and independent custody are **not proven**.
- Python/Docker images use pinned versions or major tags rather than verified
  immutable image digests. For supply-chain assurance, record trusted OCI
  digests and independently verify the dependency supply chain separately.
- A successful run on the developer's machine is NOT a third-party-run
  milestone. The independent-reproduction milestone requires an external
  operator to run from their own trusted checkout and provide their own
  signed, authenticated evidence with independent custody checks.

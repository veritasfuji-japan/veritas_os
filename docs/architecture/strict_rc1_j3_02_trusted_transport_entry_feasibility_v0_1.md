# TASK-J3-02 — Trusted Transport Entry Boundary: feasibility and proof obligations (v0.1)

**Status:** RESEARCH ONLY / NO-GO for Strict RC1 conformance  
**Date:** 2026-11-05  
**Source baseline:** VERITAS OS main after merged PR #2454, commit [`6f4efbda5dd4c4e84adb4a96afeedb4f7b3f7bdd`](https://github.com/veritasfuji-japan/veritas_os/commit/6f4efbda5dd4c4e84adb4a96afeedb4f7b3f7bdd)  
**Scope:** Sanction × VERITAS Strict RC1/J3 feasibility analysis, not a change to the agreed RC1 or Broker Admission draft2 contracts  
**Provenance:** VERITAS source paths and PR #2454 are repo-grounded. Strict RC1 thresholds and Sanction BA terminology are collaboration requirements under review; their current signed normative contract is not stored in this repository. No Eric approval or implementation is inferred.

## 1. Decision and precise question

**Current decision: J3 remains BLOCKED.** A successful final Python clock check followed by a separate `writer.write()` call is not a proof that an entry occurred while both issuer checks were fresh and their authorizations unexpired. PR #2454 establishes a deterministic synthetic counterexample at the application-call boundary. It does not show real kernel scheduling, actual network submission, peer receipt, or external effect.

Question for the next phase:

> Can a trusted component establish a defensible, observable *entry linearization point* at which all required time, authority, ownership and STOP conditions are checked and a single immutable dispatch is admitted, without a subsequent unguarded gap before the specifically defined transport-entry event?

A positive answer must be tied to a named execution platform and a concrete definition of entry. An abstract Python interface or one more clock read is not enough.

## 2. Evidence from current native implementation

| Source | What exists | What is NOT established |
| --- | --- | --- |
| `veritas_os/policy/sandbox_bind_execution.py:203-215` | `check_send_window()` checks trusted clock, authorization window, <=1 s elapsed on wall and monotonic clocks, and credential metadata | No check bound atomically to kernel submission |
| `veritas_os/policy/sandbox_bind_execution.py:217-243` | Checks before/after durable intent, then one-shot `take_material()` repeats checks | No protection against arbitrary pause after callback return |
| `veritas_os/policy/sandbox_https_transport.py:116-130` | TLS setup; callback; secret extraction; byte construction; `writer.write(wire)`; `drain()` | No time/STOP recheck at write; write may only enqueue in user-space transport buffer |
| `veritas_os/policy/sandbox_pre_effect.py:131-143,173-196` | Clock health, uncertainty and authorization-window checks; monotonic is elapsed-time evidence only | No independently authenticated UTC truth or globally ordered revocation stream |
| `veritas_os/tests/test_strict_rc1_j3_preemption_boundary.py` | Four deterministic post-check/pre-write clock advances: 1000/1001/2000/2001 ms | Synthetic observations are not proof of kernel or peer effects |
| PR #2454 CI | Run `41821266612`: all 38 workflows succeeded; J3's four parametrized observations executed | Not a Strict RC1 conformance certificate |

**Boundary distinction:** The native <=1 s executor-local budget is not the Sanction × VERITAS Strict RC1 requirement that each issuer's last validation be no older than 2000 ms at the actual entry event. Both may be relevant, but they are separate predicates.

## 3. Candidate definitions of transport entry

These are **alternatives to be agreed with Eric**, not synonyms:

- **E0 — Python call:** `writer.write(wire)` invoked. Testable today; may buffer. Insufficient to claim physical or kernel entry.
- **E1 — Kernel acceptance:** trusted kernel component accepts an immutable, authorized message into a transport queue at an explicitly specified linearization point. A syscall's return alone does not prove where its internal acceptance point lies. Needs instrumented, reviewed implementation and proof.
- **E2 — Network transmission:** bytes actually emitted by the network stack/device. Scheduling, buffering, retransmission and partial sends create further delays; E1 evidence does not imply E2 freshness.
- **E3 — Receiver admission:** authenticated receiver admits the exact operation at its own trusted decision boundary. This can be a useful *different* guarantee, but does not retroactively prove E1/E2 timing.
- **E4 — External effect commit:** downstream effect is durably applied. This is a distinct outcome/effect property, not transport entry.

**Required joint decision:** select E1/E2/E3 (or another precisely instrumentable point), document which system owns it, and explicitly state whether the deadline applies to entry, transmission, admission, or effect. Do not move the reference point after observing results.

## 4. Timing and authority predicates (proposed model)

Let `T_entry` be the trusted timestamp at the selected linearization point. For issuers `i in {Sanction, VERITAS}`, let `T_check_i` be the authenticated final validation time and `T_expiry_i` the effective expiry, as interpreted under the agreed clock/uncertainty model.

At entry require, at minimum:

1. `0 <= T_entry - T_check_i <= 2000 ms` for **each** issuer, with 2000 accepted and 2001 rejected, assuming exact time measurement.
2. `T_entry < T_expiry_i` for **each** issuer; equality rejects.
3. The canonical action, target, attempt, issuer evidence and original owner incarnation remain exactly bound.
4. The one-use dispatch right has not previously been spent and cannot be reconstructed by restart/recovery.
5. STOP/disable has not become effective *before the agreed entry linearization point*. If STOP and entry race, a total ordering and a verifiable tie-breaking rule are required.
6. Unknown or untrusted time, missing issuer proof, ambiguous STOP order, identity drift or unverified commit must fail closed, retaining durable uncertainty without redispatch.

**Unresolved semantics:** Does Strict RC1 also require instantaneous awareness of remote issuer revocations not yet delivered to the owner? If yes, no isolated local gate can guarantee that without an agreed synchronous/linearizable issuer check or equivalent shared authority. Clarify the revocation knowledge and clock-trust model before implementation.

Clock uncertainty must be incorporated conservatively: with a reading interval `[L,U]`, use the latest plausible entry time `U` for freshness upper bounds and expiry checks, and the earliest plausible time `L` for nonnegative age checks. Exact equality or threshold cases are meaningful only under a stated resolution and uncertainty model.

## 5. Conditional impossibility result (not an unconditional theorem)

Assume all of the following:

A. The only authorization decision is a user-space check at time `t0`.  
B. The scheduler can pause that process for an unbounded duration immediately after the check.  
C. The transport later accepts a write without another trusted gate that atomically binds the acceptance event to fresh authority/time.  
D. The authorization has a finite expiry or final-validation age limit.

Then an execution exists in which the check passes at `t0`, the process pauses past the relevant deadline, resumes, and the write is accepted. Therefore **this architecture cannot guarantee the Strict RC1 entry-time predicate under those assumptions**.

This argument does **not** prove that all systems are incapable of meeting RC1. It identifies a missing trusted linearization mechanism or a missing bounded-scheduling assumption. Moving a Python check closer to `write()`, disabling `await`, or holding a user-space mutex does not remove an arbitrary preemption point.

Even if a native gate can atomically admit at E1, the claim must not silently extend to E2/E3/E4.

## 6. Feasibility options and verdicts

| Option | Proposed mechanism | Verdict | Main gap |
| --- | --- | --- | --- |
| A | Another Python `trusted_clock()` immediately before `writer.write()` | **REJECT as Strict RC1 proof** | Check-to-call preemption remains; E0 != E1/E2 |
| B | Bounded timeout, `asyncio.timeout`, scheduling priority or process lock | **INSUFFICIENT alone** | Timeout cancellation and lock ownership are not atomic send authorization |
| C | Native/kernel-owned entry gate that serializes one-use dispatch, STOP and time checks with the defined E1 event | **RESEARCH CANDIDATE** | Need a concrete trusted primitive, kernel trust boundary, revocation semantics and proof of linearization |
| D | Time-aware socket scheduling / kernel queue deadlines | **RESEARCH CANDIDATE, NOT CLAIMED** | Queue/deadline APIs may control scheduling, not verify dual issuer authority or prove actual transmission |
| E | Trusted receiver admission that checks issuer evidence, STOP and deadline before accepting exact operation | **ALTERNATIVE CONTRACT** | E3 is not necessarily sender-side E1/E2; remote revocation and effects still need definitions |
| F | Broker Admission draft2: commit logical admission, permit later physical write under its specified local disable rules | **SEPARATE, WEAKER PROFILE** | Cannot relabel admission as Strict RC1 transport entry |
| G | Proved finite maximum delay from final check to selected entry on a restricted real-time platform | **CONDITIONAL CANDIDATE** | Requires verified end-to-end WCET/scheduler/clock assumptions; arbitrary preemption contradicts premise |

Do not implement options C/D/E/G as a production enforcement path without partner agreement on the event, trust root and proof obligations.

## 7. Candidate trusted gate contract (conceptual only)

A possible future `attempt_entry` primitive would take a **frozen** request digest, exact destination, two issuer evidence objects, original owner-incarnation identity, durable one-use claim, and STOP epoch. It would return an authenticated, non-replayable receipt describing either `DENIED`, `ENTRY_COMMITTED`, or `UNKNOWN` (never infer external effect).

**Critical obligation:** the primitive's time/STOP/authority checks and its claimed E1 admission event must share one defined atomic ordering. A primitive that checks then calls an unguarded send later is just the original gap moved into another component.

Required invariants:

- One canonical attempt/target/body; no substitute or drift.
- Single-use admission despite 32 concurrent attempts, process crashes, retries and restart.
- STOP-before-entry wins; entry-before-STOP is classified per agreed semantics; tie and uncertain order fail closed.
- Both issuer check ages and effective expiries hold at the chosen entry point, using a reviewed clock-trust model.
- Uncertainty, lost acknowledgement and partial send never authorize replay.
- Receipt proves only the chosen entry event, not delivery or external effect.
- Any independently mutable revocation source has an explicitly stated synchronization/knowledge guarantee.

This is a **design target**, not an API proposal accepted by Sanction, and not implemented.

## 8. Research gates and stop conditions

- **G0 — Definition:** Eric and VERITAS agree on exact `T_entry` and whether RC1 means E1, E2 or E3; specify expiry, freshness, STOP ordering and revocation visibility.
- **G1 — Trust root:** Identify who authenticates UTC/monotonic samples, issuer evidence, owner incarnation, STOP epoch and gate implementation; state failure model.
- **G2 — Feasibility prototype:** Isolated, inert, platform-pinned experiment with an instrumented candidate entry point; no real provider, no network effect, no live credentials.
- **G3 — Adversarial oracles:** Run the matrix in `strict_rc1_j3_02_oracle_matrix_v0_1.md`, including pause after last check, expiry equality, STOP race, crash and 32-way contention.
- **G4 — Independent replay:** Capture source commit, compiler/kernel/runtime version, executable hash, test harness, monotonic trace, receipt, and reviewer reproduction.
- **G5 — Contract review:** Eric explicitly accepts the event definition and evidence before any change to J3 status.

**Stop immediately** if the proposed gate merely shifts the check-to-entry gap, if an E1 receipt is presented as E2/E4 evidence, or if remote revocation semantics cannot be made explicit.

## 9. Decision record

- PR #2454: merged; synthetic limitation reproduced.
- J3-02: feasibility analysis only, no implementation or production effects.
- Strict RC1/J3: **BLOCKED**.
- J5–J7: **OPEN**.
- BA6: **PENDING partner review**.
- Broker Admission draft2 and original RC1/schema draft2: **UNCHANGED**.
- No external send, issuer approval, contract freeze, or conformance claim.

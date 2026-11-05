# TASK-J3-07 — conditional temporal envelope, impossibility boundary and trust-root selection

**Status:** RESEARCH-ONLY / NOT AN ENTRY GATE / NOT STRICT RC1 CONFORMANCE  
**Predecessor:** merged #2459 (J3-06), J3-05 ADR and partner questions Q01/Q04/Q05.  
**Code:** `veritas_os/tests/research_j3_07_temporal_envelope.py`  
**Tests:** `veritas_os/tests/test_research_j3_07_temporal_envelope.py`

## 1. Research result: time margin is conditional, not a gate

For a selected hypothetical entry event `E ∈ {E1,E2,E3}`, let an authenticated clock snapshot be an **interval** `[L,U]` in UTC milliseconds, with monotonic sample `M`. Let `B ≥ 0` be an **independently certified** maximum physical delay from the snapshot to that *specific* entry event. For each issuer `i`, with checked times `Cᵢ_UTC`, `Cᵢ_mono`, and strict expiry `Xᵢ`, a sufficient **arithmetic** condition for all hypothetical entries within the envelope is:

- No future check at the earliest possible entry: `L ≥ Cᵢ_UTC` and `M ≥ Cᵢ_mono`.
- Worst-case freshness: `U + B − Cᵢ_UTC ≤ 2000 ms` and `M + B − Cᵢ_mono ≤ 2000 ms`.
- Strict expiry: `U + B < Xᵢ` (**equality fails**).
- Both distinct issuer records must satisfy every predicate. The 2000 ms limit is a **J3-02 research proposal**, not a jointly accepted Strict RC1 value. The existing separate native 1-second local budget is **not** replaced or proved by this envelope.

The model returns `CONDITIONAL_TIME_ENVELOPE` only when all externally asserted prerequisites are TRUE. That output means **arithmetic feasibility under assumed premises**, never execution permission, proof that the premises are true, or evidence that an entry occurred. The model performs no I/O.

**No finite `B` without a trusted runtime:** under an adversarial/unbounded pause after the final clock read, any finite freshness/expiry margin can be exhausted before a later commit, send or receive. A process lock, SQLite transaction, ordinary scheduler priority, syscall wrapper, or test-observed low latency is not a certified worst-case bound. J3-06 demonstrated this physically with a >2000 ms pause inside its SQLite transaction. J3-07 makes the necessary assumption and the counterexample explicit.

## 2. Three distinct ordering and authority problems

| Requirement | Can a time envelope alone prove it? | Required external evidence |
| --- | --- | --- |
| Two-issuer freshness/strict expiry **at E** | **Conditionally**, only if `B` is a real enforced upper bound and time is trusted | Selected E event, clock calibration/error, independent upper-bound certificate, adversarial preemption proof |
| STOP effective before E implies rejection | **No** | One named linearization/total-order mechanism for STOP and E, including acknowledgment semantics |
| Remote revocation visible before E | **No** | Shared authoritative revocation state, synchronous validation or a jointly accepted bounded-staleness contract |
| One-use despite crash/restart | **No** | Durable, trusted, exclusive consumption and recovery evidence |
| Real E1/E2/E3/E4 occurrence | **No** | Independent instrumentation at each selected physical/receiver/effect boundary |

An implementation cannot fix STOP ordering by subtracting a few milliseconds from expiry. It also cannot claim remote issuer revocation visibility merely because the local STOP table is locked.

## 3. Platform/architecture candidate decision matrix

| Candidate | Possible time trust | Event boundary | Outstanding proof | J3-07 decision |
| --- | --- | --- | --- | --- |
| Python/SQLite E3-model from #2459 | Caller fixture only | Logical DB commit | Arbitrary preemption after clock read | **COUNTEREXAMPLE OBSERVED; NOT ELIGIBLE** |
| Bounded real-time receiver | Calibrated trusted clock with quantified uncertainty | Instrumented receiver-owned E3 | WCET/latency certificate, STOP+commit linearization, remote revocation | **CONDITIONAL RESEARCH ONLY** |
| Kernel/transport E1 admission | Platform/kernel time root | Instrumented actual kernel queue acceptance | Precise hook semantics, issuer trust, STOP ordering, one-use recovery, bypass resistance | **CONDITIONAL RESEARCH ONLY** |
| Sender deadline/scheduler | OS clock | E1/E2 not automatically defined | Worst-case scheduling and actual entry, not merely syscall return | **INSUFFICIENT ALONE** |
| Remote synchronized authority | Authority's trust root | Must explicitly choose E1/E3 | Cross-host ordering, latency, partition and failure semantics | **CONDITIONAL RESEARCH ONLY** |
| Broker Admission draft2 | Separate local broker assumptions | Logical broker admission | Cannot infer later physical transport entry | **SEPARATE PROFILE; UNCHANGED** |

**No architecture is selected for production.** The E3 research track is a conditional candidate, not a way to rename E3 as E1.

## 4. Evidence required before any implementation or conformance claim

1. **Partner agreement:** Eric and VERITAS must explicitly resolve J3-05 Q01 (E1/E2/E3 event), Q04 (STOP-effective point) and Q05 (remote revocation visibility); Q02/Q03 and trust roots must also be frozen.
2. **Pinned platform:** kernel/runtime/build hash, CPU/scheduler/isolation, resource ceilings, clock source and uncertainty, target event instrumentation. Linux scheduling configuration alone is not a WCET proof.
3. **Certified `B`:** measurement-based maximums are observations, not adversarial upper bounds; bound must account for preemption, GC, I/O, power management, interrupt, pause, crash and scheduling assumptions.
4. **One linearization point:** checks, STOP visibility, one-use and selected E must be ordered by a reviewed trust root; if time sampling is earlier, a certified `B` must cover the whole interval.
5. **Independent revocation trust:** authoritative issuer/key/revocation freshness and failure/partition semantics, not fixture HMAC flags.
6. **Independent evidence:** time/error trace, actual E event, exact bytes/destination/owner, STOP epoch, one-use record, runtime hash, crash/receipt-loss oracles, third-party replay.
7. **Full oracle coverage:** J3-02 38 cases and J3-05 P01–P12 remain separately tracked. These new arithmetic unit tests do **not** mark them all passed.

## 5. What the tests establish and what they do not

Tests exercise arithmetic boundaries: 0/1999/2000/2001 ms age, strict expiry equality, UTC uncertainty, either issuer stale, clock rollback, absent/unverified delay bound, untrusted root, STOP/revocation/one-use missing, and a counterexample where an assumed 500ms margin is violated by a 2500ms pause.

They **do not** certify a real maximum delay, authenticate an actual clock or issuer, perform a syscall, verify remote STOP, prove any E event or close the physical time gap. Boolean fields named `*_proven` are **fixture assertions**, not self-verifying certificates.

## 6. Next action and hard stop

**Do not promote J3-07 to a production authorization gate.** Next is a partner-facing decision package (Q01/Q04/Q05 and candidate event-specific evidence), or a separately scoped platform-pinned feasibility study after the event and trust root are chosen. Do not build a kernel hook based on this arithmetic model alone.

**Strict RC1/J3 BLOCKED; J5–J7 OPEN; BA6 PENDING partner review.** No Sanction approval, real external send, actual E1/E2/E3/E4, or production conformance is claimed.

# TASK-J3-05 — Partner decision questions and inert E3 experiment acceptance plan

**Status:** DRAFT FOR TECHNICAL REVIEW / NOT SENT TO SANCTION  
**Companion:** `strict_rc1_j3_05_trusted_entry_architecture_decision_v0_1.md`  
**Evidence base:** PR #2454–#2457, J3-02 38-row oracle matrix. These documents do not assert any partner's acceptance.

## A. Decisions required before a conformance claim

| ID | Question for joint Sanction × VERITAS review | Why it changes the architecture | Current disposition |
| --- | --- | --- | --- |
| Q01 | Does Strict RC1 define entry as E1 kernel queue admission, E2 network transmission, E3 receiver admission, or multiple events? | E3 cannot satisfy a sender-side E1/E2 predicate | **OPEN** |
| Q02 | Must both issuer final validations be within 2000ms **at that event**, with equality accepted only under exact-time measurement? | Defines temporal oracle and time trust | **PROPOSED / NOT FROZEN** |
| Q03 | Must `T_entry < T_expiry_i` hold for each issuer, with equality rejected? | Strict expiry boundary | **PROPOSED / NOT FROZEN** |
| Q04 | What is the authoritative STOP-effective point, and who can observe/acknowledge it? | Determines S01–S03/S08 ordering | **OPEN** |
| Q05 | Are remote issuer revocations required to be visible instantaneously, synchronously, or within a bounded propagation delay? | Determines whether an isolated E3/E1 gate is feasible | **OPEN** |
| Q06 | Which trust roots authenticate issuer signatures, UTC/monotonic clock, uncertainty, owner incarnation, code identity and one-use storage? | Defines G1 and attack surface | **OPEN** |
| Q07 | What is the authorized outcome after lost E3 receipt, partial send, crash and restart? | Determines F02–F07/F11 no-retry and reconciliation | **PROPOSED UNKNOWN_NO_RETRY / NOT FROZEN** |
| Q08 | May a receiver-owned E3-only profile be evaluated separately from Strict RC1 E1, without renaming it as conformance? | Enables a tractable isolated prototype | **PROPOSED** |

**Do not collapse Q01/Q04/Q05 into an assumed answer.** If the agreement requires E1, an E3 proof is relevant complementary research but not RC1 acceptance.

## B. Isolated E3 candidate — implementation boundary

Proposed next experiment, contingent on scope agreement:

- **No external network/provider/credentials:** synthetic frozen operation, local-only harness, fixture keys and isolated receiver.
- **Receiver-owned authority:** parse exact canonical payload and compute a real cryptographic digest in the receiver, not merely compare opaque fixture labels. Signatures in a prototype are test keys only; production issuer trust is not inferred.
- **Receiver-owned event:** a named local transaction that checks issuer evidence, local STOP epoch, conservative clock interval, owner and replay state, then commits a durable one-use E3 admission record. If using SQLite/PostgreSQL, describe the *database logical commit* as E3-model admission only; it is not a remote effect.
- **No hidden second execution:** record `UNKNOWN_NO_RETRY` on uncertain commit; read-only reconciliation only. Do not automatically redispatch after a timeout.
- **Fault injection:** pause after initial validation, just before transaction/commit, after commit before receipt, during STOP race, and across restart. If STOP is in another independent store, explicitly mark atomicity unproven.
- **Independent observation:** capture signed evidence references, source hash, runtime/OS versions, receiver clock interval, STOP epoch, committed row, crash/restart recovery and negative tests.

### Mandatory local acceptance conditions (research, not conformance)

| Gate | Inert test | Expected | Boundary of claim |
| --- | --- | --- | --- |
| P01 | Both issuer ages 0, 1999, 2000ms at receiver E3-model commit | Accept once with trusted exact clock | Local modeled E3 only |
| P02 | Either issuer 2001ms old; expiry equality; missing issuer | Deny, no E3-model row | Fixture issuer authenticity only unless cryptographic verification added |
| P03 | Sender pauses >2000ms after earlier approval | Receiver must deny at its own admission check | Does not prove sender E1 |
| P04 | STOP effective before E3-model commit | Deny with auditable ordering | Only STOP in same trust domain |
| P05 | E3-model commit before STOP | At most one admission; no retrospective undo | Downstream effect remains unknown |
| P06 | STOP and E3 race with independently ordered durable state | One documented order, or fail closed | Not global STOP propagation |
| P07 | 32 contenders + restart + replay | At most one durable commit; no re-arm | Depends on actual database durability and configuration |
| P08 | Lost receipt after durable commit | `UNKNOWN_NO_RETRY`, read-only reconcile | Not proof of external effect |
| P09 | Payload/target/owner substitution and key mismatch | Deny | Cryptographic identity scope limited to test trust root |
| P10 | Clock uncertainty, rollback, issuer revocation stale view | Deny or `NOT_SCORED` according to explicit contract | Never silently assume globally fresh revocation |
| P11 | Pause **inside** alleged atomic boundary | Demonstrate invariant under real scheduling, or report a counterexample | Python mutex alone cannot prove physical-time atomicity |
| P12 | Source/runtime hash mismatch, unreviewed environment | `NOT_SCORED` / deny operationally | Independent replay required |

P01–P12 are **planned**, not executed by this ADR. The full J3-02 38-row matrix remains the required eventual adversarial suite. A local database's transaction boundary may serialize STOP and admission, but cannot make physical time stand still; P11 is deliberately a hard stop condition for any claim that timestamp sampling and commit are physically simultaneous.

## C. Stop conditions and decision rule

1. **Stop** if an implementation calls a precheck + later write/commit “atomic entry” without bounding or eliminating intervening physical-time advance.
2. **Stop** if a receipt claims E1/E2/E4 from E3-only evidence, or global revocation visibility from a cached local STOP flag.
3. **Stop** if a synthetic fixture's `authenticated_in_fixture` flag is described as verified cryptographic issuer evidence.
4. **Stop** if a successful test result is used to amend the partner contract without explicit review.
5. **Stop** if a local database commit is conflated with downstream effect or a receiver's authenticated acceptance.

**Next choice:** ask the partner to settle Q01, Q04 and Q05 first. If E3 is accepted as an independent experiment, implement the P01–P12 inert receiver candidate as a separate research task. If Strict RC1 mandates E1, open a platform-pinned kernel feasibility task and keep E3 in a distinct profile.

**Current statuses:** J3 BLOCKED, J5–J7 OPEN, BA6 PENDING; Broker Admission draft2 unchanged.

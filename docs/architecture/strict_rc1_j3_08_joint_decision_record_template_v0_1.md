# TASK-J3-08 — joint decision record template and evidence gate (v0.1)

**State: BLANK WORKSHEET / ALL JOINT DECISIONS UNRESOLVED**  
**Owner:** proposed joint Sanction × VERITAS technical review  
**Companion:** `strict_rc1_j3_08_sanction_veritas_boundary_decision_package_v0_1.md`  
**This is not a signed decision, partner communication, contract amendment or approval.**

## A. Mandatory provenance before any decision is marked agreed

| Field | Required entry | Current value |
| --- | --- | --- |
| Review identifier and version | Stable ID; record revision | UNSET |
| Sanction reviewer/authority | Named person and authority scope | UNSET |
| VERITAS reviewer/authority | Named person and authority scope | UNSET |
| Source of each answer | Explicit message, issue or signed record URL + date | UNSET |
| Scope | Exact Strict RC1 contract version and applicable operation | UNSET |
| Agreement evidence | Both parties explicitly confirm same wording | UNSET |
| Disagreements/qualifications | Preserve exact objections and alternatives | UNSET |
| Decision timestamp and immutable digest | Record after both confirmations | UNSET |

Do not interpret a GitHub merge, passing test, lack of objection, or receipt of a draft as partner consent. Retain superseded proposals with provenance; do not overwrite history.

## B. Decision rows (fill only from explicit partner evidence)

| ID | Selected answer | Exact agreed predicate | Authority / trust root | Failure/partition policy | Evidence URL / digest | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Q01 entry event(s) | UNRESOLVED | UNSET | UNSET | UNSET | UNSET | OPEN |
| Q02 final-check freshness and uncertainty | UNRESOLVED | UNSET | UNSET | UNSET | UNSET | OPEN |
| Q03 strict expiry | UNRESOLVED | UNSET | UNSET | UNSET | UNSET | OPEN |
| Q04 STOP-effective ordering and acknowledgment | UNRESOLVED | UNSET | UNSET | UNSET | UNSET | OPEN |
| Q05 remote revocation visibility | UNRESOLVED | UNSET | UNSET | UNSET | UNSET | OPEN |
| Q06 issuer/time/owner/one-use trust roots | UNRESOLVED | UNSET | UNSET | UNSET | UNSET | OPEN |
| Q07 lost receipt/crash/partial send | UNRESOLVED | UNSET | UNSET | UNSET | UNSET | OPEN |
| Q08 E3 research as separate profile | UNRESOLVED | UNSET | UNSET | UNSET | UNSET | OPEN |

### Recording rule

Each row must contain a **precise, falsifiable event predicate** and an evidence source. If a party chooses `OTHER_DEFINED`, transcribe its definition; do not normalize it to the nearest predefined option. If either party disagrees or has not answered, retain `OPEN`. An answer to Q01 does not automatically resolve Q04/Q05.

## C. Event-specific acceptance evidence checklist

These are future gates, not claims that they have passed.

| Gate | Evidence to attach | Status |
| --- | --- | --- |
| C0 | Explicit bilateral Q01/Q04/Q05 agreement, with Q02/Q03/Q06–Q08 as required | NOT_SCORED |
| C1 | Pinned selected E event and independently reviewable instrumentation | NOT_SCORED |
| C2 | Two independently authenticated issuer evidences and exact immutable binding | NOT_SCORED |
| C3 | Trusted clock interval, uncertainty, and either a certified worst-case sample-to-E bound or reviewed atomic trusted mechanism | NOT_SCORED |
| C4 | STOP-effective versus E linearization, including STOP racing with entry | NOT_SCORED |
| C5 | Remote revocation authority, partition behavior and visibility proof | NOT_SCORED |
| C6 | Durable single-use consumption, crash/restart, unknown outcome, read-only reconciliation | NOT_SCORED |
| C7 | J3-02 38-oracle matrix and J3-05 P01–P12 execution evidence on selected pinned platform | NOT_SCORED |
| C8 | Independent replay, provenance, source/runtime digest and partner review | NOT_SCORED |

**Do not promote status on the basis of synthetic arithmetic fixtures.** J3-06 and J3-07 establish negative limitations and conditional models; they do not satisfy C1–C8.

## D. Decision meeting / asynchronous review protocol

1. Share the companion packet **only after human review**. Ask for independent answers to Q01, Q04, Q05 first, including explicit `UNRESOLVED` where appropriate.
2. Preserve exact reply text, date and source; distinguish each party's proposal from joint agreement.
3. Draft a proposed canonical predicate for each resolved row and send it to both parties for confirmation.
4. Record both confirmations with versioned provenance. If there is a conflict, keep the row `OPEN` and state the competing definitions.
5. Only after C0 is satisfied, open a **separate** platform-specific feasibility task; do not infer that C1–C8 have passed.
6. Amend any normative contract only in a distinct, explicitly approved change; do not modify production execution from this worksheet.

## E. No-go guardrails

- No E3-only model can be used as proof of E1/E2.
- No local STOP lock proves global STOP effectiveness.
- No remote cached revocation flag proves globally current revocation.
- No observed test duration is a certified adversarial worst-case bound.
- No `CONDITIONAL_TIME_ENVELOPE` is execution permission.
- No partner decision is invented from prior research or implied by PR approval.

**Current project statuses: Strict RC1/J3 BLOCKED; J5–J7 OPEN; BA6 PENDING partner review.**

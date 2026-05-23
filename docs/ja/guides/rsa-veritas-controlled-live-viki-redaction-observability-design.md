# RSA ↔ VERITAS Controlled Live V.I.K.I. Redaction and Observability Design

## 英語正本

- [RSA ↔ VERITAS Controlled Live V.I.K.I. Redaction and Observability Design](../../en/guides/rsa-veritas-controlled-live-viki-redaction-observability-design.md)

## 1. 目的

本書は、将来の controlled live V.I.K.I. integration に向けた redaction と observability の要件を定義する documentation-only 設計です。

- これは documentation-only です。
- これは live integration ではありません。
- これは runtime implementation ではありません。
- これは logging implementation ではありません。
- これは observability implementation ではありません。
- これは production API endpoint ではありません。
- これは production use を許可しません。
- これは network calls を追加しません。
- これは secrets / credentials を追加しません。
- これは実データの KYC 処理を行いません。
- これは法的・規制上の承認を提供しません。
- この設計は、live logging / telemetry / audit pipeline / endpoint / live middleware 実装開始前にレビューされる必要があります。

関連する pre-live artifact:
- [Controlled live V.I.K.I. observability event taxonomy fixture plan](./rsa-veritas-controlled-live-viki-observability-event-taxonomy-fixture-plan.md)（documentation-only / runtime・tests・fixtures・live integration 追加なし）。

## 2. Current baseline

以下の pre-live gate は既存として整備済みです。

- local mock ingestion receiver design
- local mock receiver test fixture plan
- local mock receiver implementation
- local mock receiver validation snapshot
- static synthetic JSON fixture-driven E2E harness
- E2E harness validation snapshot
- controlled live integration threat model
- controlled live payload schema draft
- controlled live transport/authentication design
- controlled live replay protection and correlation-id design

現在の検証済みパスは次のとおりです。

`static synthetic JSON fixture`
→ `ingest_local_viki_mock_payload()`
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ `VERITAS decision`
→ `redacted audit output`

このパスは引き続き local-only / synthetic-data-only / no-network です。

## 3. Future observability boundary

将来の observability boundary:

`V.I.K.I. live middleware`
→ `RSA-compatible payload`
→ `transport/authentication event`
→ `message integrity event`
→ `replay/correlation event`
→ `schema validation event`
→ `RSASandboxPayload construction event`
→ `evaluate_rsa_sandbox_signal() result event`
→ `VERITAS decision event`
→ `redacted audit entry`
→ `optional human review event`

- Observability は data leakage channel になってはいけません。
- Audit usefulness は、raw reasoning / raw LLM text / raw KYC records / secrets / credentials / customer PII を保存せずに維持される必要があります。
- すべての observability event は deterministic・minimal・redacted である必要があります。
- Logging success は payload validity を意味しません。
- Payload validity は final commit approval を意味しません。
- SAFE_PROCEED は final commit approval と同義ではありません。
- VERITAS commit gate が引き続き authoritative です。

## 4. Redaction principles

- 最小限必要な field のみ収集する。
- free-form text より deterministic state labels を優先する。
- raw explanations より reason codes を優先する。
- raw upstream intent/action は明示レビューがない限りデフォルトで redact する。
- chain-of-thought と hidden model state は reject する。
- secrets / credentials は persistence 前に reject または strip する。
- raw Authorization headers は記録しない。
- sensitive data を含み得る raw payload は記録しない。
- raw KYC records は記録しない。
- live LLM text は記録しない。
- raw V.I.K.I. internal reasoning は保存しない。
- logs は reviewer inspection に安全でなければなりません。

## 5. Fields allowed in observability events

| Field | Allowed | Notes |
| --- | --- | --- |
| event_type | Yes | deterministic event taxonomy value のみ。 |
| event_version | Yes | versioned event contract metadata。 |
| schema_version | Yes | payload schema contract version metadata。 |
| request_id | Yes | primary safe per-request correlation key。 |
| correlation_id | Yes | controlled live checks を横断する correlation key。 |
| rsa_status | Yes | v1 compatibility naming を維持。 |
| trigger_source | Yes | raw reasoning / PII を含めない。 |
| timestamp | Yes | deterministic event emission timestamp。 |
| payload_issued_at | Yes | deterministic upstream-issued timestamp metadata。 |
| source_environment | Yes | non-sensitive environment class のみ。 |
| source_instance_id | Yes, constrained | host credentials / secrets / PII を含めない。 |
| authentication_result_class | Yes | class label のみ。 |
| integrity_result_class | Yes | class label のみ。 |
| replay_result_class | Yes | class label のみ。 |
| schema_validation_result_class | Yes | class label のみ。 |
| veritas_continuation_decision | Yes | deterministic VERITAS continuation state。 |
| veritas_reason_code | Yes | deterministic reason code のみ。 |
| veritas_sandbox_commit_state | Yes | deterministic commit-state label のみ。 |
| required_next_action | Yes | deterministic action guidance class のみ。 |
| latency_ms | Yes | 数値メトリクスのみ。 |
| body_hash_prefix | Yes, constrained | non-reversible であり raw payload を露出しない。 |

## 6. Fields forbidden in observability events

禁止クラスは persistence 前に reject / redact / deterministic class label への置換を必須とし、検知時は fail closed とします。

- chain-of-thought
- hidden model state
- raw V.I.K.I. reasoning
- raw LLM text
- raw KYC records
- customer PII
- secrets
- credentials
- access tokens
- refresh tokens
- private keys
- webhook secrets
- raw Authorization header
- full signed secret material
- unredacted regulated data
- raw payload body
- raw upstream free-form explanation
- stack traces containing secrets

## 7. Event taxonomy

Draft event types:

- `viki_payload_received`
- `transport_authentication_checked`
- `message_integrity_checked`
- `replay_window_checked`
- `replay_cache_checked`
- `schema_validation_checked`
- `rsa_sandbox_payload_constructed`
- `rsa_sandbox_signal_evaluated`
- `veritas_decision_emitted`
- `human_review_required`
- `upstream_unavailable`
- `fail_closed_emitted`

- event 名は draft のみです。
- final event taxonomy は実装前レビュー必須です。
- events は versioning 必須です。
- raw reasoning / raw LLM text / raw KYC records / secrets / credentials を含めてはいけません。

## 8. Example safe observability event

```json
{
  "event_type": "veritas_decision_emitted",
  "event_version": "v1alpha1",
  "schema_version": "v1alpha1",
  "request_id": "req_viki_000001",
  "correlation_id": "corr_viki_veritas_000001",
  "rsa_status": "SAFE_PROCEED",
  "trigger_source": "SRC_Normal_State",
  "timestamp": "2026-05-20T23:01:35.876Z",
  "payload_issued_at": "2026-05-20T23:01:35.876Z",
  "authentication_result_class": "AUTHENTICATED",
  "integrity_result_class": "INTEGRITY_VALID",
  "replay_result_class": "NO_REPLAY_DETECTED",
  "schema_validation_result_class": "SCHEMA_VALID",
  "veritas_continuation_decision": "CONTINUE_TO_BIND_BOUNDARY",
  "veritas_reason_code": "UPSTREAM_SAFE_PROCEED_SIGNAL",
  "veritas_sandbox_commit_state": "SUSPENDED_NOT_COMMITTED",
  "required_next_action": "CONTINUE_BOUNDARY_EVALUATION",
  "latency_ms": 42
}
```

- この例は synthetic です。
- この例は production logging を許可しません。
- SAFE_PROCEED は final commit approval ではありません。

## 9. Example forbidden observability event

```json
{
  "event_type": "veritas_decision_emitted",
  "request_id": "req_viki_invalid_001",
  "correlation_id": "corr_viki_veritas_invalid_001",
  "chain_of_thought": "FORBIDDEN",
  "raw_kyc_record": "FORBIDDEN",
  "access_token": "FORBIDDEN"
}
```

Expected behavior:

- reject before persistence or redact before persistence
- fail closed
- do not infer SAFE_PROCEED
- never store chain-of-thought
- never store raw KYC records
- never store access tokens

## 10. Redacted audit entry relationship

将来の VERITAS audit entries は次を保持し得ます。

- upstream_signal_source
- event_type
- event_version
- schema_version
- request_id
- correlation_id
- rsa_status
- trigger_source
- timestamp
- payload_issued_at
- source_environment
- source_instance_id（non-sensitive の場合のみ）
- authentication_result_class
- integrity_result_class
- replay_result_class
- schema_validation_result_class
- VERITAS continuation_decision
- VERITAS reason_code
- VERITAS sandbox_commit_state
- required_next_action

将来の VERITAS audit entries は次を保持してはいけません。

- raw V.I.K.I. reasoning
- raw LLM text
- chain-of-thought
- hidden model state
- raw KYC records
- customer PII
- secrets
- credentials
- tokens
- private keys
- raw Authorization header
- full signed secret material
- unredacted regulated data
- raw payload body

## 11. Failure observability

失敗は、sensitive data を漏えいせずに observable である必要があります。

各 failure で記録するのは deterministic classes のみ:

- authentication failed
- integrity failed
- replay detected
- replay cache unavailable
- schema validation failed
- forbidden field detected
- upstream unavailable
- timeout
- fail-closed emitted

記録してはいけないもの:

- raw payload
- raw secret
- raw Authorization header
- raw KYC record
- raw reasoning
- stack trace with credentials

## 12. Interaction with replay/correlation design

- request_id と correlation_id は primary safe correlation fields です。
- correlation_id は transport / replay / schema validation / VERITAS decision / human review events を接続します。
- request_id は単一 payload emission を識別します。
- 重複 request_id は replay risk として fail closed 必須です。
- correlation_id は PII / secrets を含めてはいけません。
- Observability は raw payload data を保存せずに correlation を保持する必要があります。

## 13. Interaction with transport/authentication design

- Authentication result は credential material ではなく class として記録します。
- Signature verification result は signature secret material ではなく class として記録します。
- mTLS result は raw certificate secrets ではなく class として記録します。
- Body hash は safe digest または safe prefix のみ許可し、raw payload は不可です。
- raw Authorization headers は記録禁止です。
- Authentication failure 時も secret material を logs に露出してはいけません。

## 14. Interaction with payload schema draft

- payload schema draft は required / optional / forbidden fields を定義します。
- Observability は schema validation result を反映し、forbidden fields を保存してはいけません。
- optional な raw-intent/action fields はデフォルトで redact 必須です。
- chain_of_thought や hidden_model_state など forbidden fields は fail closed または persistence 前 reject が必須です。
- schema_version は deterministic metadata として保持します。

## 15. Log retention and access assumptions

- 本書は production retention period を定義しません。
- retention period は production 前レビュー必須です。
- log access は制限される必要があります。
- regulated metadata を含む logs は compliance review が必要となる場合があります。
- logs は raw payload の dumping ground にしてはいけません。
- logs の export は redaction を維持する必要があります。
- 将来の retention policy は deletion/expiry behavior を含む必要があります。

## 16. Fail-closed matrix

すべての failure class に対する VERITAS behavior は共通です。

- fail closed
- PAUSE_FOR_HUMAN_REVIEW
- SUSPENDED_NOT_COMMITTED
- no SAFE_PROCEED inference

Failure class:

- Forbidden field detected
- Secret detected in payload
- Raw KYC detected
- Raw reasoning detected
- Chain-of-thought detected
- Hidden model state detected
- Authorization header logging attempted
- Replay cache unavailable
- Authentication failed
- Integrity failed
- Schema validation failed
- Upstream unavailable
- Timeout

## 17. Required implementation gates

redaction/observability implementation 前チェックリスト:

- [ ] threat model merged
- [ ] payload schema draft merged
- [ ] transport/auth design merged
- [ ] replay/correlation design merged
- [ ] redaction/observability design merged
- [ ] event taxonomy finalized
- [ ] forbidden field detector plan drafted
- [ ] logging sink selected
- [ ] log retention policy drafted
- [ ] access control policy drafted
- [ ] redaction tests drafted
- [ ] failure-mode test plan drafted
- [ ] staging-only feature flag defined
- [ ] synthetic-data-only test plan drafted
- [ ] rollback plan documented
- [ ] security review completed

## 18. Non-goals

この設計が許可しないもの:

- production live V.I.K.I. integration
- production logging pipeline
- production API endpoint
- public unauthenticated endpoint
- real KYC data processing
- live customer data processing
- live LLM text ingestion
- raw V.I.K.I. reasoning ingestion
- chain-of-thought storage
- hidden model state storage
- raw KYC logging
- final commit automation based only on V.I.K.I.
- bypass of VERITAS commit gate
- secrets in repository
- production AML/KYC compliance claims
- regulatory approval claims
- legal advice claims

## 19. Compatibility preservation

- rsa_status は v1 payload field のまま維持します。
- RSASandboxPayload は downstream payload container として維持します。
- evaluate_rsa_sandbox_signal() は downstream evaluator として維持します。
- upstream_signal_source は `"RSA"` を維持します。
- request_id / correlation_id は observability/correlation fields であり、rsa_status の置換ではありません。
- viki_status はこの phase で導入しません。
- VIKIPayload はこの phase で導入しません。
- naming migration は v2 として別途扱います。

## 20. What this design validates

- implementation 前に observability risks が文書化されること
- allowed observability fields が定義されること
- forbidden observability fields が定義されること
- redaction expectations が文書化されること
- failure observability が文書化されること
- audit relationship が文書化されること
- log retention assumptions が文書化されること
- live implementation を導入しないこと

## 21. What this design does not validate

- it does not implement logging
- it does not implement telemetry
- it does not implement redaction
- it does not implement forbidden field detection
- it does not implement transport
- it does not implement authentication
- it does not implement replay protection
- it does not validate production AML/KYC compliance
- it does not validate regulatory approval
- it does not provide legal advice
- it does not authorize production deployment
- it does not make VERITAS production-ready for live V.I.K.I.

## 22. この設計後の推奨 PR

次の safe PR 候補:

- live payload schema fixture examples
- controlled live failure-mode test plan
- redaction fixture examples
- controlled live integration implementation plan
- observability event taxonomy fixture plan

最も安全な次 PR は、live payload schema fixture examples（documentation-only または fixture-only、synthetic data 限定）です。schema / transport-auth / replay-correlation / redaction-observability の各 gate を runtime 実装前に具体的な synthetic examples で固定化できるためです。


## Related pre-live artifact

- [Controlled live V.I.K.I. payload schema fixture examples（documentation-and-fixture-only の pre-live artifact。runtime changes / tests / live integration は追加しない）。](./rsa-veritas-controlled-live-viki-payload-schema-fixture-examples.md)

## 関連フィクスチャ成果物

関連資料: [Controlled live V.I.K.I. observability event fixture examples](./rsa-veritas-controlled-live-viki-observability-event-fixture-examples.md)。

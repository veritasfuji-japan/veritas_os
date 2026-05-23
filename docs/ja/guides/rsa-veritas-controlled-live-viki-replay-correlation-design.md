# RSA ↔ VERITAS Controlled Live V.I.K.I. Replay Protection and Correlation-ID Design

## 英語正本

- [RSA ↔ VERITAS Controlled Live V.I.K.I. Replay Protection and Correlation-ID Design](../../en/guides/rsa-veritas-controlled-live-viki-replay-correlation-design.md)

## 1. 目的

本ドキュメントは、将来の controlled live V.I.K.I. integration に向けた replay protection と correlation-id 設計を定義します。

本成果物は documentation-only です。

本成果物は live integration ではありません。

本成果物は runtime implementation ではありません。

本成果物は replay cache implementation ではありません。

本成果物は production API endpoint ではありません。

本成果物は production use を許可しません。

本成果物は network calls を追加しません。

本成果物は secrets / credentials を追加しません。

本成果物は実データの KYC を処理しません。

本成果物は法的助言・規制承認を提供しません。

replay cache、request tracking、endpoint、live middleware のいずれの実装に着手する前にも、この設計のレビュー完了が必須です。

## 2. 現在の baseline

以下の pre-live gate は既に存在します。

- local mock ingestion receiver design
- local mock receiver test fixture plan
- local mock receiver implementation
- local mock receiver validation snapshot
- static synthetic JSON fixture-driven E2E harness
- E2E harness validation snapshot
- controlled live integration threat model
- controlled live payload schema draft
- controlled live transport/authentication design

現在の検証済みパスは次のままです。

static synthetic JSON fixture
→ ingest_local_viki_mock_payload()
→ RSASandboxPayload
→ evaluate_rsa_sandbox_signal()
→ VERITAS decision
→ redacted audit output

この経路は現在も local-only / synthetic-data-only / no-network です。

## 3. Future replay and correlation boundary

将来の replay/correlation boundary:

V.I.K.I. live middleware
→ request_id と correlation_id を含む RSA-compatible payload
→ transport authentication layer
→ message integrity verification
→ timestamp / payload_issued_at validation
→ replay window check
→ replay cache duplicate check
→ VERITAS live ingestion boundary
→ schema validation
→ RSASandboxPayload
→ evaluate_rsa_sandbox_signal()
→ VERITAS decision
→ redacted audit entry
→ commit gate

方針:

- VERITAS は transport / integrity / replay / schema validation が完了するまで、request_id と correlation_id を untrusted として扱う必要があります。
- request_id の uniqueness は payload validity を意味しません。
- correlation_id の traceability は final commit approval を意味しません。
- SAFE_PROCEED は final commit approval と同義ではありません。
- VERITAS commit gate は引き続き authoritative です。
- replay suspicion、重複 request_id、stale timestamp、許容 skew 超過 future timestamp、ID 欠落、ID malformed、replay cache failure は fail closed 必須です。

## 4. Identifier definitions

### request_id

- 単一の V.I.K.I. payload emission / upstream request を表す一意識別子。
- non-empty 必須。
- PII を含めてはいけません。
- secrets を含めてはいけません。
- raw reasoning を含めてはいけません。
- replay window 内で一意である必要があります。
- replay window 内で duplicate request_id は fail closed 必須です。

### correlation_id

- V.I.K.I. emission、VERITAS ingestion、audit entry、human review event を関連付ける trace identifier。
- 同一 review flow の関連イベント間で共有される場合があります。
- non-empty 必須。
- PII を含めてはいけません。
- secrets を含めてはいけません。
- raw reasoning を含めてはいけません。
- non-sensitive の場合、redacted audit output へ保持されるべきです。

### payload_issued_at

- V.I.K.I. が payload を発行した時刻。
- RFC 3339 UTC または timezone-aware ISO-8601 を UTC 正規化した形式である必要があります。
- accepted skew と replay window の両方で検証する必要があります。

### timestamp

- 主イベントの timestamp。
- RFC 3339 UTC または timezone-aware ISO-8601 を UTC 正規化した形式である必要があります。
- naive timestamp は不可です。
- invalid timestamp は不可です。

## 5. Identifier format requirements

将来実装では strict identifier format rule を事前定義すべきです。

推奨ドラフト制約:

- request_id should be an opaque string.
- correlation_id should be an opaque string.
- Minimum length should be defined before implementation.
- Maximum length should be defined before implementation.
- Allowed character set should be defined before implementation.
- IDs should not encode user identity, customer identity, KYC fields, regulated data, secrets, or raw reasoning.
- IDs should not be derived from raw PII.
- IDs should be safe for logs after redaction review.

推奨例:

- req_viki_000001
- corr_viki_veritas_000001

これらは draft examples のみです。

最終 ID format は実装前レビューが必須です。

invalid identifier format は fail closed 必須です。

## 6. Replay window design

replay window は実装前に明示定義が必要です。

ドラフト設計:

- replay window は request_id を記憶する期間を定義します。
- replay window 内 duplicate request_id は fail closed 必須です。
- replay window 外 request_id であっても、timestamp/integrity check が失敗した場合は自動受理してはいけません。
- replay window は payload_issued_at / timestamp validation と連携する必要があります。
- replay window duration は実装前レビューが必要です。
- replay cache TTL は accepted replay window 以上である必要があります。
- clock skew threshold は定義とテストが必要です。

現在の local mock rule 参照:

- skew > 300 seconds fails closed
- skew = 300 seconds is accepted

controlled live integration でも、別途レビュー済み設計で変更されない限り、同じ 300 秒の exclusive threshold を採用し得ます。

異なる live threshold を採用する場合は、実装前に文書化が必須です。

## 7. Replay cache behavior

ドラフト replay cache requirements:

- Store request_id for the replay window.
- Store associated correlation_id.
- Store payload_issued_at.
- Store schema_version.
- Store a safe payload hash or body digest, not raw body.
- Do not store raw payload with sensitive fields.
- Do not store raw V.I.K.I. reasoning.
- Do not store chain-of-thought.
- Do not store hidden model state.
- Do not store raw KYC records.
- Do not store secrets or credentials.

replay cache 必須機能:

- lookup by request_id
- duplicate detection
- TTL expiration
- redacted audit correlation
- bounded storage behavior

replay cache failure は、別途レビュー済み degradation policy がない限り fail closed とすべきです。

replay cache を sensitive data store 化してはいけません。

replay cache implementation は本 PR の scope 外です。

## 8. Timestamp validation

- timestamp と payload_issued_at は RFC 3339 UTC もしくは timezone-aware ISO-8601 の UTC 正規化として parse する必要があります。
- Naive timestamps は fail closed。
- Invalid timestamps は fail closed。
- Missing timestamp は fail closed。
- Missing payload_issued_at は fail closed。
- accepted skew を超える future timestamp は fail closed。
- accepted replay window を超える stale timestamp は fail closed。
- timestamp / payload_issued_at mismatch policy は実装前に定義必須です。

ドラフト rule:

- timestamp と payload_issued_at が material に乖離する場合、レビュー済み tolerance がない限り fail closed。
- material difference threshold は実装前定義が必須。

## 9. Duplicate and replay failure behavior

以下は fail closed 必須です。

- missing request_id
- empty request_id
- malformed request_id
- request_id containing PII
- request_id containing secret material
- duplicate request_id within replay window
- missing correlation_id
- empty correlation_id
- malformed correlation_id
- correlation_id containing PII
- correlation_id containing secret material
- missing payload_issued_at
- invalid payload_issued_at
- stale payload_issued_at
- future payload_issued_at beyond skew
- replay cache unavailable
- replay cache write failure
- replay cache read failure
- body hash mismatch for same request_id
- correlation mismatch for same request_id

期待される generic behavior:

- continuation_decision: PAUSE_FOR_HUMAN_REVIEW
- sandbox_commit_state: SUSPENDED_NOT_COMMITTED
- required_next_action: REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE
- SAFE_PROCEED を推論しない

## 10. Correlation across audit and review

correlation_id は以下を連結するべきです。

- V.I.K.I. payload emission
- transport authentication event
- message integrity event
- replay check event
- VERITAS schema validation event
- RSASandboxPayload construction
- evaluate_rsa_sandbox_signal() result
- VERITAS audit entry
- 必要時の human review event

audit で保持してよい項目:

- request_id
- correlation_id
- schema_version
- rsa_status
- trigger_source
- timestamp
- payload_issued_at
- replay result class
- integrity result class
- authentication result class
- VERITAS continuation_decision
- VERITAS reason_code
- VERITAS sandbox_commit_state

audit で保持してはいけない項目:

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

## 11. Interaction with transport/authentication design

- replay protection は transport authentication と message integrity に依存します。
- replay protection を欠く authentication は不十分です。
- message integrity を欠く replay protection は不十分です。
- message integrity は request_id / correlation_id / payload_issued_at / schema_version / body hash を束縛する必要があります。
- signed request canonicalization には request_id と correlation_id を含める必要があります。
- mTLS identity 単独では request uniqueness を強制しない限り replay 防止になりません。
- transport validation は schema validation より前に行う必要があります。
- schema validation は transport/replay validation 後にも必須です。

## 12. Interaction with payload schema draft

payload schema draft は既に以下を要求しています。

- schema_version
- rsa_status
- trigger_source
- timestamp
- request_id
- correlation_id
- payload_issued_at

方針:

- replay design はこれら項目の検証方式を制約します。
- request_id / correlation_id は traceability と replay protection に必須です。
- payload_issued_at は replay/freshness check に必須です。
- schema_version は signed/integrity-protected material に含める必要があります。
- Unknown schema_version は fail closed。
- Unsupported schema_version は fail closed。

## 13. Fail-closed matrix

| Failure class | Example | Expected behavior |
| --- | --- | --- |
| Missing request_id | request_id omitted from payload | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Empty request_id | request_id = "" | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Malformed request_id | request_id has disallowed format | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Duplicate request_id | same request_id observed inside replay window | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Missing correlation_id | correlation_id omitted from payload | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Malformed correlation_id | correlation_id has disallowed format | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| request_id contains PII | request_id embeds customer name/email | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| correlation_id contains PII | correlation_id embeds customer account data | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Stale payload_issued_at | issued time older than replay window | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Future payload_issued_at beyond skew | issued time exceeds allowed forward skew | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| timestamp / payload_issued_at mismatch | materially different event times | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Replay cache unavailable | replay cache service not reachable | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Replay cache read failure | replay cache lookup error | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Replay cache write failure | replay cache persistence error | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Body hash mismatch for same request_id | same request_id with different body hash | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Correlation mismatch for same request_id | same request_id with different correlation_id | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Replay window not configured | replay window unset at startup | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |
| Clock skew policy not configured | skew threshold unset at startup | fail closed; PAUSE_FOR_HUMAN_REVIEW; SUSPENDED_NOT_COMMITTED; no SAFE_PROCEED inference |

## 14. Required implementation gates

replay/correlation 実装前チェックリスト:

- threat model merged
- payload schema draft merged
- transport/auth design merged
- replay/correlation design merged
- identifier format finalized
- replay window finalized
- replay cache TTL finalized
- replay cache storage selected
- replay cache failure policy finalized
- timestamp mismatch policy finalized
- correlation audit policy finalized
- security review completed
- staging-only feature flag defined
- synthetic-data-only test plan drafted
- rollback plan documented

## 15. Non-goals

この設計は以下を許可しません。

- production live V.I.K.I. integration
- production replay cache
- production API endpoint
- public unauthenticated endpoint
- real KYC data processing
- live customer data processing
- live LLM text ingestion
- raw V.I.K.I. reasoning ingestion
- final commit automation based only on V.I.K.I.
- bypass of VERITAS commit gate
- secrets in repository
- production AML/KYC compliance claims
- regulatory approval claims
- legal advice claims

## 16. Compatibility preservation

- rsa_status は v1 payload field のまま維持します。
- RSASandboxPayload は downstream payload container のまま維持します。
- evaluate_rsa_sandbox_signal() は downstream evaluator のまま維持します。
- upstream_signal_source は "RSA" のまま維持します。
- request_id / correlation_id は pre-live schema additions であり、rsa_status の置き換えではありません。
- このフェーズでは viki_status を導入しません。
- このフェーズでは VIKIPayload を導入しません。
- naming migration が必要な場合は v2 として別途扱います。

## 17. What this design validates

- replay risks are documented before implementation
- request_id role is defined
- correlation_id role is defined
- replay window expectations are documented
- replay cache behavior is constrained
- timestamp validation expectations are documented
- duplicate request_id must fail closed
- replay cache failure must fail closed
- audit correlation expectations are defined
- no live implementation is introduced

## 18. What this design does not validate

- it does not implement replay cache
- it does not implement request tracking
- it does not implement transport
- it does not implement authentication
- it does not implement authorization
- it does not validate production AML/KYC compliance
- it does not validate regulatory approval
- it does not provide legal advice
- it does not authorize production deployment
- it does not make VERITAS production-ready for live V.I.K.I.

## 19. Recommended next PR after this design

次の safe PR 候補:

- redaction and observability design
- live payload schema fixture examples
- controlled live failure-mode test plan
- controlled live integration implementation plan
- replay/correlation fixture examples

最も安全な次 PR は、引き続き documentation-only の redaction and observability design です。replay/correlation fields を安全に監査記録へ残しつつ、sensitive payload leakage を防ぐ設計が先行して必要なためです。

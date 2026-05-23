# RSA ↔ VERITAS Controlled Live V.I.K.I. Transport Authentication Design

- [Controlled live V.I.K.I. replay protection and correlation-id design（pre-live 必須 replay/correlation gate、documentation-only、runtime 変更なし、live integration なし）](./rsa-veritas-controlled-live-viki-replay-correlation-design.md)
## 英語正本

- [RSA ↔ VERITAS Controlled Live V.I.K.I. Transport Authentication Design](../../en/guides/rsa-veritas-controlled-live-viki-transport-authentication-design.md)

## 1. 目的

この文書は、将来の controlled live V.I.K.I. integration に向けた transport と authentication の設計方針を定義します。

- 本文書は documentation-only です。
- 本文書は live integration ではありません。
- 本文書は runtime implementation ではありません。
- 本文書は production API endpoint ではありません。
- 本文書は production use を承認しません。
- 本文書は network calls を追加しません。
- 本文書は secrets / credentials を追加しません。
- 本文書は実データの KYC 処理を行いません。
- 本文書は法規制承認や法的助言を提供しません。
- transport / endpoint / credential / live middleware 実装に着手する前に、必ず本設計レビューを完了させる必要があります。

## 2. 現在の baseline

以下の pre-live gates は既に存在します。

- local mock ingestion receiver design
- local mock receiver test fixture plan
- local mock receiver implementation
- local mock receiver validation snapshot
- static synthetic JSON fixture-driven E2E harness
- E2E harness validation snapshot
- controlled live integration threat model
- controlled live payload schema draft

現在の検証済み経路:

static synthetic JSON fixture
→ `ingest_local_viki_mock_payload()`
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ VERITAS decision
→ redacted audit output

この経路は引き続き local-only / synthetic-data-only / no-network です。

## 3. 将来の controlled transport boundary

将来の controlled transport boundary:

V.I.K.I. live middleware
→ RSA-compatible payload
→ transport authentication layer
→ message integrity verification
→ replay protection check
→ VERITAS live ingestion boundary
→ schema validation
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ VERITAS decision
→ redacted audit entry
→ commit gate

- VERITAS は、transport・integrity・replay・schema validation を通過するまで、すべての payload を untrusted として扱う必要があります。
- Transport success は payload validity を意味しません。
- Payload validity は final commit approval を意味しません。
- `SAFE_PROCEED` は final commit approval と同義ではありません。
- VERITAS commit gate は引き続き authoritative です。
- timeout / failed authentication / failed integrity verification / replay suspicion / malformed payload / missing payload は fail closed にする必要があります。

## 4. Proposed controlled transport assumptions

初期の controlled live transport は次を前提とします。

- staging-only
- synthetic-data-only
- default-off
- feature-flag gated
- no production endpoint
- no public unauthenticated endpoint
- no real KYC data
- no live customer data
- no raw LLM text
- no raw V.I.K.I. reasoning

Transport assumptions:

- HTTPS は必須です。
- TLS 1.2 または TLS 1.3 を必須化すべきです。
- 可能であれば、service-to-service 認証には mTLS を優先します。
- mTLS が使えない場合は、repository 外に保管した secret による署名付き request を controlled testing に限り利用できます。
- secrets は repository にコミットしてはいけません。
- endpoint URL は安全性が明示できる場合を除き public docs に掲載してはいけません。
- 将来 endpoint を導入する場合も、別途 production readiness review 完了までは staging-only とします。

## 5. Authentication design

将来許容される authentication option は2つです。

### Option A: mTLS preferred

- V.I.K.I. と VERITAS は certificate で相互認証します。
- certificate は repository 外で払い出します。
- production consideration 前に certificate rotation が必要です。
- 実装前に certificate subject / SAN allowlisting を定義すべきです。
- certificate validation failure は fail closed 必須です。

### Option B: signed request fallback

- V.I.K.I. は repository 外に保管した secret または private key で request を署名します。
- VERITAS は schema validation 前に署名検証を行います。
- metadata または headers に key id を含める必要があります。
- 実装前に secret rotation 設計が必要です。
- signature verification failure は fail closed 必須です。

- 本設計は production authentication mechanism を選定しません。
- 初期 controlled implementation では採用 option を必ず明記する必要があります。
- authentication bypass は禁止です。
- missing authentication は fail closed 必須です。

## 6. Draft transport metadata

将来 transport で使用し得る draft metadata:

- `X-VERITAS-Schema-Version`
- `X-VERITAS-Request-Id`
- `X-VERITAS-Correlation-Id`
- `X-VERITAS-Payload-Issued-At`
- `X-VERITAS-Signature`
- `X-VERITAS-Key-Id`
- `X-VERITAS-Body-SHA256`
- `X-VERITAS-Source-Environment`
- `X-VERITAS-Source-Instance-Id`

- header 名は draft 名です。
- final 名称は実装前にレビュー必須です。
- headers に PII / raw reasoning / secrets / tokens / regulated data を含めてはいけません。
- 該当する場合、`request_id` と `correlation_id` は payload と一致する必要があります。
- signature または integrity checks は body と関連 metadata を対象化する必要があります。

## 7. Message integrity design

将来の controlled live transport は message integrity を必須とします。

最小要件:

- payload の body hash を検証する。
- signature または mTLS identity を検証する。
- `request_id` を検証する。
- `correlation_id` を検証する。
- timestamp / `payload_issued_at` を検証する。
- `schema_version` を検証する。
- tampered payload を拒否する。
- 改ざんされた `rsa_status` を拒否する。
- 改ざんされた `trigger_source` を拒否する。
- body/header mismatch を拒否する。

signed request 設計では、署名対象に以下を含めるべきです。

- HTTP method または transport operation name
- request path または operation target
- timestamp または `payload_issued_at`
- `request_id`
- `correlation_id`
- body hash
- `schema_version`

- canonicalization rules は実装前に厳密定義が必要です。
- canonicalization が曖昧な場合、実装を進めてはいけません。
- integrity verification failure は fail closed 必須です。

## 8. Replay protection design

live implementation 前に replay protection の設計が必須です。

最小期待:

- `request_id` は定義済み replay window 内で一意であること。
- `payload_issued_at` は許容 clock skew 内であること。
- replay window 内の duplicate `request_id` は fail closed。
- stale payload は fail closed。
- 許容 skew を超える未来 timestamp は fail closed。
- replay cache storage の定義が実装前に必要。
- replay cache TTL の定義が実装前に必要。
- replay cache failure は、別途レビュー済み degradation policy がない限り fail closed。

既存 local mock ルール参照:

- local mock threshold: skew > 300 seconds は fail closed
- skew = 300 seconds は許容

- controlled live integration でも、別設計で変更されない限り同閾値採用を検討できます。
- replay protection は実 live transport 前の必須条件です。

## 9. Timeout and availability design

- V.I.K.I. timeout は fail closed。
- V.I.K.I. unreachable は fail closed。
- connection refused は fail closed。
- partial response は fail closed。
- しきい値超過の遅延応答は fail closed。
- missing payload は fail closed。
- transport error は fail closed。

期待される汎用挙動:

- `continuation_decision`: `PAUSE_FOR_HUMAN_REVIEW`
- `sandbox_commit_state`: `SUSPENDED_NOT_COMMITTED`
- `required_next_action`: `REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE`

- VERITAS は timeout / unavailability から `SAFE_PROCEED` を推論してはいけません。
- availability failure を通常承認に変換してはいけません。
- retry behavior は実装前に bounded かつレビュー済みである必要があります。

## 10. Payload schema relationship

この transport 設計は controlled live payload schema draft に依存します。

required payload fields:

- `schema_version`
- `rsa_status`
- `trigger_source`
- `timestamp`
- `request_id`
- `correlation_id`
- `payload_issued_at`

- transport metadata は payload fields と整合している必要があります。
- schema validation は transport validation の後にも必ず実行されます。
- transport authentication は schema validation を置換しません。
- schema validation は transport authentication を置換しません。
- payload 受理には両方が必要です。

## 11. Redaction and logging policy

将来の transport logs に含めてもよい項目:

- `request_id`
- `correlation_id`
- `schema_version`
- `source_environment`
- 非機微の場合の `source_instance_id`
- authentication result class
- integrity result class
- replay result class
- timeout result class
- VERITAS `continuation_decision`
- VERITAS `sandbox_commit_state`

将来の transport logs に含めてはいけない項目:

- secrets
- credentials
- access tokens
- refresh tokens
- private keys
- webhook secrets
- raw V.I.K.I. reasoning
- raw LLM text
- chain-of-thought
- hidden model state
- raw KYC records
- customer PII
- unredacted regulated data
- full signed secret material
- raw Authorization header

- logging は deterministic かつ redacted である必要があります。
- observability を data leakage channel にしてはいけません。
- failed authentication logs は secret material を露出してはいけません。

## 12. Credential and secret handling

- secrets を repository に保存してはいけません。
- secrets を fixtures に保存してはいけません。
- secrets を logs に出力してはいけません。
- secrets を docs に記載してはいけません。
- secrets を raw payload fields で受け渡してはいけません。
- 将来実装では secret manager または platform-provided secret storage を使用する必要があります。
- production consideration 前に rotation plan を文書化する必要があります。
- production consideration 前に revocation plan を文書化する必要があります。
- test credentials を使う場合も synthetic かつ staging-only に限定する必要があります。

## 13. Environment separation

controlled live integration は以下の環境分離を必須とします。

- local
- CI
- staging
- controlled-test
- production

Rules:

- local mock receiver は local-only / test-only のまま維持します。
- controlled live transport は初期段階で staging-only とします。
- 本設計で production を有効化してはいけません。
- `source_environment` を authorization mechanism として使ってはいけません。
- feature flags は default-off にします。
- production deployment には別途 production readiness review が必要です。

## 14. Fail-closed matrix

| Failure class | Example | Expected behavior |
| --- | --- | --- |
| Missing authentication | certificate または signature metadata が欠落 | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Failed authentication | mTLS certificate reject | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Failed signature verification | payload body の署名検証が不一致 | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Body hash mismatch | `X-VERITAS-Body-SHA256` と body hash が不一致 | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Replay detected | 既知 payload の再送検知 | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Duplicate request_id | replay window 内で同一 `request_id` 再出現 | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Stale timestamp | `payload_issued_at` が許容 replay window 外で過去 | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Future timestamp beyond skew | `payload_issued_at` が許容 skew を超えて未来 | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Timeout | upstream timeout 超過 | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| V.I.K.I. unreachable | DNS/network/connectivity failure | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Malformed payload | JSON 破損または required fields 欠落 | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Unknown rsa_status | 契約外 `rsa_status` 値 | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Forbidden raw reasoning field | raw reasoning field を payload が含む | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Secret detected in payload | secret/token/key material 検出 | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |
| Raw KYC data detected | unredacted regulated KYC record 検出 | fail closed; `PAUSE_FOR_HUMAN_REVIEW`; `SUSPENDED_NOT_COMMITTED`; no `SAFE_PROCEED` inference |

## 15. Required implementation gates

transport implementation 前のチェックリスト:

- threat model merged
- payload schema draft merged
- transport/auth design merged
- authentication option selected
- message integrity design finalized
- replay protection design finalized
- timeout policy finalized
- redaction/logging policy finalized
- secret storage approach approved
- staging-only feature flag defined
- synthetic-data-only test plan drafted
- rollback plan documented
- security review completed

## 16. Non-goals

本設計で許可しない項目:

- production live V.I.K.I. integration
- production API endpoint
- public unauthenticated endpoint
- real KYC data processing
- live customer data processing
- live LLM text ingestion
- raw V.I.K.I. reasoning ingestion
- final commit automation based only on V.I.K.I.
- VERITAS commit gate の bypass
- repository への secrets 保存
- production AML/KYC compliance claims
- regulatory approval claims
- legal advice claims

## 17. Compatibility preservation

- `rsa_status` は v1 payload field のまま維持します。
- `RSASandboxPayload` は downstream payload container のまま維持します。
- `evaluate_rsa_sandbox_signal()` は downstream evaluator のまま維持します。
- `upstream_signal_source` は `"RSA"` のまま維持します。
- `viki_status` はこの phase では導入しません。
- `VIKIPayload` はこの phase では導入しません。
- naming migration が必要な場合は v2 として別管理します。

## 18. この設計が検証すること

- transport risks を実装前に文書化済み
- authentication options を定義済み
- message integrity を必須化
- replay protection を必須化
- timeout の fail closed を必須化
- secrets の repository 外管理を必須化
- logs の redaction を必須化
- schema validation 必須を維持
- live implementation を導入しない

## 19. この設計が検証しないこと

- transport を実装しない
- authentication を実装しない
- authorization を実装しない
- replay protection を実装しない
- production AML/KYC compliance を検証しない
- regulatory approval を検証しない
- legal advice を提供しない
- production deployment を承認しない
- live V.I.K.I. 向けに VERITAS を production-ready と見なさない

## 20. この設計の次に推奨される PR

次の安全な PR 候補:

- replay protection and correlation-id design
- redaction and observability design
- live payload schema fixture examples
- controlled live failure-mode test plan
- controlled live integration implementation plan

最も安全な次 PR は、documentation-only のまま進める replay protection and correlation-id design です。transport authentication は runtime implementation 前に replay protection と対でレビューされる必要があります。


## Related pre-live artifact

- [Controlled live V.I.K.I. payload schema fixture examples（documentation-and-fixture-only の pre-live artifact。runtime changes / tests / live integration は追加しない）。](./rsa-veritas-controlled-live-viki-payload-schema-fixture-examples.md)

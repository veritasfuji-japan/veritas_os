# RSA ↔ VERITAS Controlled Live V.I.K.I. Integration Implementation Plan

## 英語正本

- [RSA ↔ VERITAS Controlled Live V.I.K.I. Integration Implementation Plan](../../en/guides/rsa-veritas-controlled-live-viki-integration-implementation-plan.md)

## 1. 目的

この文書は、RSA ↔ VERITAS sandbox stack における controlled live V.I.K.I. integration の**将来実装順序**を定義します。

本ページは documentation-only であり、以下は実施しません。

- runtime implementation
- transport implementation
- authentication implementation
- replay cache implementation
- logging / telemetry implementation
- observability runtime implementation
- live integration
- production API endpoint

また本計画は、network call、secrets / credentials、real KYC data processing を追加せず、production use を許可しません。

runtime integration PR を作成する前に、本計画のレビューを必須とします。

## 2. 現在の baseline

以下の controlled live pre-live gates は既に存在します。

- controlled live integration threat model
- controlled live payload schema draft
- controlled live transport/authentication design
- controlled live replay protection and correlation-id design
- controlled live redaction and observability design
- controlled live payload schema fixture examples
- controlled live failure-mode test plan
- controlled live fixture validation plan
- controlled live fixture validation test skeleton
- controlled live failure-mode test skeleton
- controlled live observability event taxonomy fixture plan
- controlled live observability event fixture examples
- controlled live observability event fixture validation test skeleton
- controlled live runtime interface skeleton plan

現在の検証経路は offline・synthetic-fixture-only・no-network です。

この phase では live V.I.K.I. integration は存在しません。

この phase では runtime controlled live transport は存在しません。

この phase では production observability / telemetry pipeline は存在しません。

## 3. Implementation boundary

将来の implementation boundary:

controlled live V.I.K.I. response  
→ transport/authentication verification  
→ message integrity verification  
→ replay/correlation verification  
→ schema validation  
→ redaction/forbidden-content validation  
→ RSASandboxPayload construction  
→ evaluate_rsa_sandbox_signal()  
→ VERITAS decision  
→ redacted audit / observability event emission  
→ sandbox commit gate remains enforced

安全制約:

- SAFE_PROCEED は upstream signal のみです。
- SAFE_PROCEED は final commit approval を決して付与してはいけません。
- 別系統の VERITAS commit gate が承認しない限り、final_commit_approved は false のまま維持します。
- controlled live V.I.K.I. は VERITAS commit gate を bypass してはいけません。
- raw V.I.K.I. reasoning は ingest してはいけません。
- chain-of-thought は ingest してはいけません。
- raw KYC records は ingest してはいけません。

## 4. Phased implementation sequence

### Phase 0 — Planning complete

- 既存の docs / fixtures / offline tests はマージ済み。
- runtime behavior なし。
- live integration なし。

### Phase 1 — Runtime interface skeleton

- disabled-by-default の controlled live receiver interface を追加。
- network call なし。
- real credentials なし。
- endpoint なし。
- live V.I.K.I. なし。
- feature flag の default は disabled。
- disabled 時の挙動は fail closed。

### Phase 2 — Schema validation runtime adapter

- controlled live synthetic payloads を内部の validated form へ変換。
- rsa_status compatibility を維持。
- RSASandboxPayload downstream contract を維持。
- unsupported schema_version は reject。
- unknown rsa_status は reject。
- request_id / correlation_id 欠落は reject。
- naive timestamp は reject。
- forbidden fields は reject。
- secret-like fields は reject。
- regulated-data fields は reject。

### Phase 3 — Replay/correlation adapter

- disabled-by-default guard 配下で replay/correlation validation を追加。
- request_id duplicate detection は fail closed。
- correlation_id mismatch は fail closed。
- replay cache unavailable は fail closed。
- 初回 runtime PR での production replay cache 導入は、別途レビューがない限り不可。

### Phase 4 — Transport/authentication adapter

- disabled-by-default guard 配下で transport/authentication verification を追加。
- authentication failure は fail closed。
- message integrity failure は fail closed。
- repository に real credentials を置かない。
- repository に production endpoint を置かない。
- レビューなしの自動 retry loop は不可。

### Phase 5 — Redacted audit and observability adapter

- fixture examples と validation tests が揃った後に限り redacted event construction を追加。
- raw payload bodies を log しない。
- chain-of-thought を log しない。
- hidden model state を log しない。
- raw KYC records を log しない。
- secrets / credentials を log しない。
- observability output は fixture taxonomy と一致させる。

### Phase 6 — Controlled live dry-run

- non-production controlled environment を使用。
- synthetic または承認済み test data のみ使用。
- real customer KYC data は使用しない。
- production AML/KYC claims は行わない。
- すべての結果は SUSPENDED_NOT_COMMITTED のまま維持。
- fail-closed case では human review を必須とする。

### Phase 7 — Reviewed limited live pilot

- 別途承認後のみ。
- security review 必須。
- data-handling review 必須。
- rollback plan 必須。
- 明示的な operational owner 必須。
- audit review 必須。
- repository に secrets を置かない。
- logs に raw KYC / raw reasoning を置かない。

## 5. Required feature flags and default state

想定 feature flags:

- VERITAS_CONTROLLED_LIVE_VIKI_ENABLE
- VERITAS_CONTROLLED_LIVE_VIKI_TRANSPORT_ENABLE
- VERITAS_CONTROLLED_LIVE_VIKI_OBSERVABILITY_ENABLE
- VERITAS_CONTROLLED_LIVE_VIKI_REPLAY_CACHE_ENABLE

ルール:

- すべて default disabled。
- disabled state は fail closed。
- live behavior より先に default-disabled behavior の tests で検証。
- flags が default で production behavior を有効化してはいけない。
- flags に credentials を保存してはいけない。
- flags に endpoint URLs を含めてはいけない。

## 6. Fail-closed requirements

以下の条件は fail closed 必須:

- disabled feature flag
- unsupported schema_version
- unknown rsa_status
- missing request_id
- missing correlation_id
- invalid timestamp
- future payload_issued_at beyond reviewed skew
- stale payload_issued_at beyond replay window
- duplicate request_id
- correlation_id mismatch
- replay cache unavailable
- authentication failure
- message integrity failure
- upstream timeout
- upstream unavailable
- forbidden field detected
- secret-like value detected
- regulated data detected
- raw reasoning detected
- raw KYC detected
- malformed payload
- invalid JSON
- unexpected exception

Fail-closed output:

- veritas_continuation_decision: PAUSE_FOR_HUMAN_REVIEW
- veritas_sandbox_commit_state: SUSPENDED_NOT_COMMITTED
- final_commit_approved: false
- required_next_action: REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE or REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW

## 7. Compatibility preservation

- rsa_status は v1 payload field として維持。
- RSASandboxPayload は downstream payload container として維持。
- evaluate_rsa_sandbox_signal() は downstream evaluator として維持。
- upstream_signal_source = "RSA" を維持。
- request_id / correlation_id は controlled-live schema/correlation fields であり、rsa_status の置換ではない。
- この phase では viki_status を導入しない。
- この phase では VIKIPayload を導入しない。
- 命名 migration は v2 として別途実施。

## 8. Data handling constraints

禁止:

- real KYC data
- real customer PII
- regulated financial records
- raw V.I.K.I. reasoning
- raw LLM text
- chain-of-thought
- hidden model state
- secrets
- credentials
- API keys
- access tokens
- refresh tokens
- private keys
- webhook secrets
- authorization headers
- bearer tokens
- raw payload bodies in logs
- raw request bodies in logs
- raw response bodies in logs

この phase で許可:

- static synthetic fixtures
- redacted metadata
- deterministic reason codes
- synthetic request_id
- synthetic correlation_id
- synthetic fixture names
- non-reversible body_hash_prefix

## 9. Observability implementation constraints

- observability は default で redacted 必須。
- observability は raw payload bodies を emit してはいけない。
- observability は raw reasoning を emit してはいけない。
- observability は KYC data を emit してはいけない。
- observability は secrets を emit してはいけない。
- first runtime skeleton では telemetry SDKs 必須にしてはいけない。
- observability event names は taxonomy fixture plan に準拠。
- pre-live observability examples では final_commit_approved は false のまま維持。

## 10. Runtime implementation 前の test requirements

runtime implementation PR 前に必須:

- fixture validation tests が pass
- failure-mode tests が pass
- observability event fixture validation tests が pass
- default-disabled behavior が計画化済み
- fail-closed behavior が計画化済み
- no-network tests が green 維持
- fixtures に secrets がないことを確認
- reviewer index がすべての pre-live artifacts を指していること

## 11. この計画後に必要な PR sequence

推奨される安全な PR sequence:

1. docs: controlled live runtime interface skeleton plan を追加
2. tests: controlled live default-disabled behavior test skeleton を追加
3. runtime: disabled-by-default controlled live receiver interface を追加
4. tests: synthetic fixtures を使う controlled live schema adapter unit tests を追加
5. runtime: disabled feature flag 配下で schema adapter を追加
6. tests: replay/correlation adapter unit tests を追加
7. runtime: disabled feature flag 配下で replay/correlation adapter を追加
8. tests: synthetic inputs を使う transport/authentication adapter unit tests を追加
9. runtime: disabled feature flag 配下で transport/authentication adapter を追加
10. tests: redacted observability event construction tests を追加
11. runtime: disabled feature flag 配下で redacted observability event construction を追加
12. docs: controlled live dry-run runbook を追加
13. tests: dry-run guard tests を追加
14. runtime: レビュー後に限り controlled live dry-run mode を追加

- live integration へ直接ジャンプしない。
- interface / schema / fail-closed / replay / observability gates の検証前に network call を追加しない。
- いかなる段階でも production credentials を追加しない。

## 12. Runtime implementation acceptance criteria

将来の runtime implementation PR が証明すべき事項:

- default disabled
- production endpoint 未コミット
- credentials 未コミット
- raw payload logging なし
- raw reasoning logging なし
- KYC logging なし
- すべての invalid states で fail closed
- SAFE_PROCEED が final commit を承認しない
- replay/correlation failures は pause
- transport/auth failures は pause
- observability output は redacted
- tests は offline で pass
- runtime behavior を targeted tests でカバー
- rollback path が存在

## 13. Rollback と kill switch の期待値

- live dry-run 前に kill switch を必須化。
- disable flag は fail-closed を強制。
- runtime は upstream unavailability に耐える。
- replay cache unavailable は fail closed。
- transport/authentication unavailable は fail closed。
- V.I.K.I. が SAFE_PROCEED を返しても、それのみで state を commit してはいけない。

## 14. Security review checklist

- repository に credentials がない
- repository に production endpoint がない
- fixtures/logs に raw KYC がない
- fixtures/logs に raw reasoning がない
- chain-of-thought ingestion がない
- hidden model state ingestion がない
- unauthenticated transport がない
- replay bypass がない
- upstream signal 単独による final commit automation がない
- telemetry leakage がない
- environment secret の出力がない
- secrets を含む exception stack trace がない
- dependency audit weakening がない

## 15. Non-goals

この計画で許可しない事項:

- production live V.I.K.I. integration
- production API endpoint
- live transport implementation
- authentication implementation
- replay cache implementation
- logging implementation
- telemetry implementation
- observability implementation
- real KYC data processing
- live customer data processing
- live LLM text ingestion
- raw V.I.K.I. reasoning ingestion
- chain-of-thought storage
- hidden model state storage
- V.I.K.I. 単独信号に基づく final commit automation
- VERITAS commit gate の bypass
- repository 内 secrets
- production AML/KYC compliance claims
- regulatory approval claims
- legal advice claims

## 16. この計画が検証すること

- runtime implementation 前に implementation sequence が定義されること
- default-disabled behavior が必須であること
- fail-closed behavior が必須であること
- compatibility contract が維持されること
- data-handling constraints が定義されること
- observability constraints が定義されること
- runtime PR sequence が定義されること
- rollback と kill switch 期待値が定義されること
- live implementation が導入されないこと

## 17. この計画が検証しないこと

- runtime code は実装しない
- tests は実装しない
- transport は実装しない
- authentication は実装しない
- replay cache は実装しない
- logging は実装しない
- telemetry は実装しない
- observability runtime は実装しない
- live V.I.K.I. を接続しない
- real KYC data は処理しない
- production deployment は承認しない

## 18. この計画後の推奨 next PR

最も安全な next PR は、documentation-only の controlled live runtime interface skeleton plan であり、その次に test-only の default-disabled behavior test skeleton を追加する PR です。

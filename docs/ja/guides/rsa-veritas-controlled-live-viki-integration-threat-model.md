# RSA ↔ VERITAS Controlled Live V.I.K.I. Integration Threat Model

## 英語正本

- [RSA ↔ VERITAS Controlled Live V.I.K.I. Integration Threat Model](../../en/guides/rsa-veritas-controlled-live-viki-integration-threat-model.md)

## 1. 目的

本書は、将来の controlled live V.I.K.I. integration に向けた threat model を定義する文書です。

- これは documentation-only です。
- これは live integration ではありません。
- これは runtime implementation ではありません。
- これは production API endpoint ではありません。
- これは production use を承認しません。
- これは real KYC data を処理しません。
- これは legal/regulatory approval を提供しません。
- これは controlled live integration 実装前の review gate を定義するための文書です。

## 2. 現在のベースライン

local mock phase には既に次が含まれます。

- local mock ingestion receiver design
- local mock receiver test fixture plan
- local mock receiver implementation
- local mock receiver validation snapshot
- static synthetic JSON fixture-driven E2E harness
- E2E harness validation snapshot

現在の検証済みパス:

static synthetic JSON fixture
→ `ingest_local_viki_mock_payload()`
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ VERITAS decision
→ redacted audit output

このパスは local-only / synthetic-data-only / no-network を維持します。

## 3. 将来の controlled live integration boundary

将来境界:

V.I.K.I. live middleware
→ RSA-compatible payload emission
→ controlled transport boundary
→ VERITAS live ingestion boundary
→ schema validation
→ `RSASandboxPayload`
→ `evaluate_rsa_sandbox_signal()`
→ VERITAS decision
→ audit entry
→ commit gate

要件:

- V.I.K.I. は RSA-compatible payload のみ emit できる。
- VERITAS は validation 成功まで live payload を untrusted として扱う。
- VERITAS は V.I.K.I. internal reasoning を consume しない。
- VERITAS は hidden V.I.K.I. logic を実行しない。
- timeout / missing payload / malformed payload / middleware unavailable から `SAFE_PROCEED` を推定しない。

## 4. 保護対象アセット

| Asset | Risk | Required protection |
| --- | --- | --- |
| VERITAS commit authority | untrusted state による unsafe commit。 | fail-closed behavior、人手レビュー、commit gate 権限維持。 |
| Audit trail integrity | 監査ログの汚染・非決定化。 | deterministic fields、redaction、制御済み reason codes。 |
| Human review gate | 自動化バイパス。 | fail-closed、人手レビュー必須。 |
| rsa_status contract | enum drift / 不正 status。 | schema validation、許可値の厳格化。 |
| RSASandboxPayload compatibility | payload shape drift。 | 構築前 validation、互換性確認。 |
| Redaction boundary | raw data 漏えい。 | redaction、no raw reasoning ingestion。 |
| Runtime secrets | secret 漏えい。 | credentials isolation、repo への secret 禁止。 |
| Transport credentials | credential 盗用。 | credentials isolation、test/staging/prod separation。 |
| Customer / KYC / regulated data | 規制データ露出。 | 早期段階は synthetic-only、redaction 必須。 |
| Live LLM text | モデル出力の永続漏えい。 | raw text の reject/redact。 |
| V.I.K.I. internal reasoning | chain-of-thought / hidden model state の漏えい。 | no ingestion、interface-only 契約。 |
| Dependency audit posture | 脆弱性例外の放置。 | `PYSEC-2026-161` 例外の狭域維持、分離レビュー。 |

## 5. Trust boundaries

### Boundary A: V.I.K.I. internal logic → emitted RSA-compatible payload

- 境界を越えるもの: 外部公開用 RSA-compatible fields。
- 越えてはいけないもの: chain-of-thought、hidden model state、raw KYC narrative。
- 期待 failure: 契約不成立時は fail closed。

### Boundary B: Payload emission → transport layer

- 境界を越えるもの: serialized payload と最小 metadata。
- 越えてはいけないもの: debug dump、secrets、raw reasoning。
- 期待 failure: emission failure は fail closed、`SAFE_PROCEED` 不可。

### Boundary C: Transport layer → VERITAS ingestion boundary

- 境界を越えるもの: payload bytes、transport metadata。
- 越えてはいけないもの: 認証なし信頼、hidden execution。
- 期待 failure: timeout/unreachable/partial は fail closed。

### Boundary D: VERITAS schema validation → RSASandboxPayload construction

- 境界を越えるもの: `RSASandboxPayload` 化可能な validated fields。
- 越えてはいけないもの: malformed JSON、unknown enum、invalid timestamp。
- 期待 failure: schema violation は fail closed と redacted audit。

### Boundary E: RSASandboxPayload → evaluate_rsa_sandbox_signal()

- 境界を越えるもの: contract-compliant `RSASandboxPayload`。
- 越えてはいけないもの: hidden reasoning、unvalidated alias。
- 期待 failure: 不確実性は fail closed + human review。

### Boundary F: VERITAS decision → audit entry / commit gate

- 境界を越えるもの: deterministic decision fields、reason codes。
- 越えてはいけないもの: raw reasoning、unredacted regulated data。
- 期待 failure: commit gate 維持、`PAUSE_FOR_HUMAN_REVIEW` へ退避。

## 6. 脅威カテゴリ

### 6.1 Malformed payloads

Threat:
- invalid JSON
- missing required fields
- null required fields
- unknown rsa_status
- invalid timestamp
- payload shape mismatch

Required behavior:
- fail closed
- `SAFE_PROCEED` を推定しない
- `PAUSE_FOR_HUMAN_REVIEW` を出力
- redacted audit entry を記録

### 6.2 Middleware unavailability

Threat:
- V.I.K.I. unreachable
- timeout
- connection refused
- delayed response
- partial response

Required behavior:
- fail closed
- `reason_code` は `UPSTREAM_MIDDLEWARE_OFFLINE` または将来の canonical code
- no payload を `SAFE_PROCEED` と扱わない

### 6.3 Replay and stale payloads

Threat:
- replayed old payload
- timestamp drift
- clock skew
- duplicated nonce / request id

Required behavior:
- timestamp validation
- clock skew limits
- live 前に nonce / request-id replay protection
- stale / replay-suspect は fail closed

### 6.4 Payload tampering

Threat:
- modified rsa_status
- modified trigger_source
- altered timestamp
- modified transport payload

Required behavior:
- future transport authentication
- live 前に message integrity control
- verification failure は fail closed
- redacted deterministic audit のみ保存

### 6.5 Status escalation abuse

Threat:
- unsafe promotion to `SAFE_PROCEED`
- middleware bug による誤 `SAFE_PROCEED`
- upstream intervention state のバイパス

Required behavior:
- VERITAS は status を検証し、intent を信頼しない
- high-risk state は常に gated
- `SAFE_PROCEED` は最終 commit 承認を意味しない
- VERITAS commit gate が最終権限

### 6.6 Raw reasoning leakage

Threat:
- internal reasoning downstream 流出
- live LLM text 混入
- chain-of-thought / hidden model state 混入
- raw KYC explanation 混入

Required behavior:
- unsupported fields は reject/redact
- chain-of-thought を保存しない
- hidden model state を保存しない
- audit は deterministic state のみ

### 6.7 Secret and credential exposure

Threat:
- API keys が docs/tests/fixtures/logs/payloads/PRs に混入
- credentials の誤コミット
- webhook secrets 露出

Required behavior:
- repo に secrets を置かない
- secret manager / environment で管理
- fixture に live credential を入れない
- 公開 docs に安全確認なし endpoint URL を記載しない

### 6.8 Production data exposure

Threat:
- real KYC data の使用
- customer records を fixture 化
- regulated financial data を test 混入

Required behavior:
- controlled integration は synthetic-only
- repo に real KYC data 禁止
- regulated data test は明示承認必須
- data minimization と redaction 必須

### 6.9 Audit poisoning

Threat:
- trigger_source / reason text の偽装
- raw text による audit 汚染
- audit 非決定化

Required behavior:
- deterministic audit fields
- raw text redaction
- controlled reason codes
- raw model reasoning を監査保存しない

### 6.10 Dependency and supply-chain drift

Threat:
- vulnerable dependencies
- temporary audit exception の放置
- dependency resolution によるリスク隠蔽

Required behavior:
- `PYSEC-2026-161` 例外は narrow に維持
- FastAPI / Starlette 互換改善時に削除
- audit ignore を拡大しない
- dependency change は別レビュー

## 7. 実装前に必須の live integration controls

- controlled live integration 用 feature flag
- default-off
- staging-only 初期環境
- synthetic-data-only 初期 live transport test
- `RSASandboxPayload` 前の schema validation
- fail-closed timeout behavior
- transport authentication design
- message integrity design
- replay protection design
- request id / correlation id design
- audit redaction design
- no raw reasoning ingestion
- no chain-of-thought storage
- no hidden state storage
- explicit human review gate
- rollback plan
- sensitive payload を記録しない observability
- merge 前 security review

## 8. Required non-goals

本 threat model は次を許可しません。

- production live V.I.K.I. integration
- production API endpoint
- real KYC data processing
- live customer data processing
- live LLM text ingestion
- V.I.K.I. 単独判断による final commit automation
- VERITAS commit gate の bypass
- `rsa_status` を `viki_status` へ rename
- `RSASandboxPayload` を `VIKIPayload` へ rename
- `evaluate_rsa_sandbox_signal()` の置換
- production AML/KYC compliance claim
- regulatory approval claim
- legal advice claim

## 9. Fail-closed policy

以下は必ず fail closed:

- timeout
- middleware unreachable
- malformed payload
- unknown rsa_status
- invalid timestamp
- replay-suspect payload
- transport integrity check failure
- authentication failure

期待する安全側 failure:

- `continuation_decision`: `PAUSE_FOR_HUMAN_REVIEW`
- `sandbox_commit_state`: `SUSPENDED_NOT_COMMITTED`
- `required_next_action`: `REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE` または `REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW`

## 10. Audit and redaction policy

将来の live integration audit で保持すべき項目:

- `upstream_signal_source`
- `rsa_status`
- `trigger_source`
- `timestamp`
- VERITAS `continuation_decision`
- VERITAS `reason_code`
- VERITAS `sandbox_commit_state`
- 定義後の correlation id / request id

保存してはいけない項目:

- V.I.K.I. internal reasoning
- chain-of-thought
- hidden model state
- raw live LLM text
- raw KYC records
- secrets
- credentials
- unredacted regulated data

## 11. Approval gates

### 実装前

- [ ] threat model merged
- [ ] live payload schema draft merged
- [ ] transport/auth design merged
- [ ] replay protection design merged
- [ ] redaction policy reviewed
- [ ] rollback plan documented
- [ ] human review gate documented

### controlled live test 前

- [ ] feature flag default-off
- [ ] staging-only
- [ ] synthetic-data-only
- [ ] no production endpoint
- [ ] no real KYC data
- [ ] no secrets in repo
- [ ] security review completed
- [ ] test plan approved

### production 前

- [ ] not approved by this document
- [ ] separate production readiness review required
- [ ] regulatory/legal/compliance review required where applicable
- [ ] operational runbook required
- [ ] incident response plan required
- [ ] audit retention policy required

## 12. Compatibility preservation

- `rsa_status` は v1 payload field として維持。
- `RSASandboxPayload` は payload container として維持。
- `evaluate_rsa_sandbox_signal()` は downstream evaluator として維持。
- `upstream_signal_source` は `"RSA"` を維持。
- naming migration は本スコープ外。
- V.I.K.I.-specific naming migration は別 v2 で扱う。

## 13. この threat model が検証すること

- 実装前に live integration risk が文書化される
- trust boundary が明示される
- fail-closed behavior が必須化される
- no raw reasoning ingestion が必須
- no production data が必須
- no production endpoint が必須
- audit redaction が必須
- human review gate が維持される

## 14. この threat model が検証しないこと

- live V.I.K.I. は実装しない
- transport は検証しない
- authentication は検証しない
- authorization は検証しない
- production AML/KYC compliance は検証しない
- regulatory approval は検証しない
- legal advice は提供しない
- live middleware 向け production-ready 化を保証しない
- production deployment を承認しない

## 15. この threat model 後の推奨 PR

次の安全な PR 候補:

- live payload schema draft
- controlled transport/authentication design
- replay protection and correlation-id design
- redaction and observability design
- controlled live integration implementation plan

最も安全な次 PR は、**live payload schema draft（documentation-only）**です。threat model の直後に精密な schema contract を先行させ、transport/runtime 実装より前に境界を固定するためです。

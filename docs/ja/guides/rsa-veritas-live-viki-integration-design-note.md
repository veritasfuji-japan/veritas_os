# RSA ↔ VERITAS Live V.I.K.I. Integration Design Note

## 英語正本

- [RSA ↔ VERITAS Live V.I.K.I. Integration Design Note](../../en/guides/rsa-veritas-live-viki-integration-design-note.md)

## 1. 目的

この文書は、将来の live V.I.K.I. integration に向けた設計メモ（design note）です。

- これは runtime implementation ではありません。
- これは live middleware connection ではありません。
- これは production AML/KYC compliance ではありません。
- これは将来レビューのための boundary と validation の設計メモです。
- この design note は reviewer checklist と併読してレビューします。

関連する文書アーティファクト:

- [Local V.I.K.I. mock ingestion receiver design（Phase 2 local mock artifact / documentation-only）](./rsa-veritas-local-viki-mock-ingestion-receiver-design.md)
- [Live V.I.K.I. integration reviewer checklist](./rsa-veritas-live-viki-integration-reviewer-checklist.md)
- [Controlled live V.I.K.I. integration threat model (documentation-only pre-live gate)](./rsa-veritas-controlled-live-viki-integration-threat-model.md)
- [Controlled live V.I.K.I. payload schema draft（pre-live 必須 schema gate、documentation-only）](./rsa-veritas-controlled-live-viki-payload-schema-draft.md)

## 2. 現在の静的ベースライン

静的 sandbox 文書セットには、すでに以下が含まれています。

- AML/KYC scenario map
- E2E sandbox demo plan
- E2E sandbox validation snapshot
- Static fixture matrix
- Sandbox reviewer index
- SAFE_PROCEED validation snapshot
- DENSITY_THROTTLED validation snapshot
- ALGORITHMIC_HUMILITY_ENGAGED validation snapshot
- DEFERRAL_ENGAGED validation snapshot
- Live V.I.K.I. integration reviewer checklist（documentation-only の review-gate artifact）

static fixture ladder は現在、対称的にそろっています。

- SAFE_PROCEED
- DENSITY_THROTTLED
- ALGORITHMIC_HUMILITY_ENGAGED
- DEFERRAL_ENGAGED

## 3. Boundary model

RSA:

- theoretical framework と underlying rule set。

V.I.K.I.:

- operational middleware。
- upstream behavioral/context checks を実行。
- RSA-compatible な upstream payloads を emit。
- VERITAS の外部コンポーネントとして存在。

VERITAS:

- emit された payload のみを consume。
- V.I.K.I. internal reasoning は consume しない。
- emit された payload を continuation decision に map。
- audit entries を emit。
- 必要に応じ unsafe final commit を防止。

## 4. Compatibility contract

v1 sandbox contract では、次の名称を安定維持します。

- rsa_status
- RSASandboxPayload
- evaluate_rsa_sandbox_signal()
- upstream_signal_source = "RSA"

補足:

- upstream_signal_source = "RSA" は、v1 compatibility fixture/source label として維持します。
- この label は、VERITAS が V.I.K.I. internal reasoning を consume することを意味しません。
- 将来の live V.I.K.I. integration では、同じ receiver contract に RSA-compatible payloads を emit できます。
- viki_status や VIKIPayload などの rename は、別の v2 migration として扱い、v1 live integration design に混在させません。

## 5. 提案される live integration flow

V.I.K.I. runtime check
→ RSA-compatible upstream payload emitted
→ VERITAS boundary で RSASandboxPayload validation
→ evaluate_rsa_sandbox_signal(payload)
→ VERITAS continuation decision
→ audit entry
→ commit state decision

追加制約:

- VERITAS は schema validation 後の emitted payload のみを trust する必要があります。
- VERITAS は V.I.K.I. の hidden reasoning、chain-of-thought、raw internal model state を ingest してはいけません。
- sensitive intent/action data を含みうる raw upstream fields は、audit output でデフォルト redacted を維持する必要があります。

## 6. live connection 前の phase gate

Phase 0: Current static sandbox

- Static fixtures only
- No network connection
- No live middleware
- No real regulated data

Phase 1: Contract-only live adapter design

- payload schema boundaries を定義
- allowed enum values を定義
- redaction expectations を定義
- error handling と reject behavior を定義
- まだ runtime connection は行わない

Phase 2: Local mock adapter

- local mock V.I.K.I. emitter
- deterministic test payloads
- no external network
- no secrets
- no real data

Phase 3: Controlled integration test

- 明示的 gate を必須化
- test-only environment
- synthetic data only
- no production commit authority
- full audit output review

Phase 4: Future production-readiness review

- separate review
- separate security model
- separate compliance review
- separate operational approval
- この design note の対象外

## 7. Failure と reject behavior

- 未知の rsa_status は reject するか safe failure behavior に map する必要があります。
- malformed payloads は proceed してはいけません。
- required fields 欠落時は proceed してはいけません。
- invalid timestamps は将来 schema rules に従って記録または reject します。
- untrusted raw upstream content は、redaction なしで audit output に含めてはいけません。
- payload validity を確立できない場合、live integration は fail closed で動作する必要があります。
- unvalidated live signal から final commit を行ってはいけません。

## 8. Audit と redaction の期待値

- audit entries は VERITAS decision と reason code を保持する必要があります。
- raw upstream intent/action fields はデフォルトで redacted を維持する必要があります。
- audit entry は、V.I.K.I. internal reasoning を露出せずに review 可能な情報量を示す必要があります。
- boundary は external auditors から reviewable な状態を維持する必要があります。

## 9. Security と privacy の制約

- No secrets in docs
- No API keys
- No webhook URLs
- No production endpoints
- No real customer data
- No financial account data
- No medical data
- No KYC documents
- No regulated data
- No live production workflow authority

## 10. この design note が検証すること

- 意図した live integration boundary が文書化されていること。
- static sandbox artifacts から将来 live adapter へ進む経路が示されていること。
- v1 compatibility contract が安定維持されること。
- VERITAS が downstream-only であること。
- V.I.K.I. が external component であること。
- live integration が明示的に gate され、暗黙導入されないこと。

## 11. この design note が検証しないこと

- live V.I.K.I. middleware を接続しません。
- V.I.K.I. internal reasoning を検証しません。
- network transport を検証しません。
- authentication / authorization を検証しません。
- production compliance を検証しません。
- real AML/KYC use を検証しません。
- regulatory approval を提供しません。
- legal advice を提供しません。
- production runtime behavior を変更しません。

## 12. 実装前の open questions

- 実際の live payload transport は何を使うべきか？
- payload authenticity をどのように検証するか？
- replay protection をどう設計するか？
- schema versioning をどう扱うか？
- v1 で rsa_status を恒久維持するか、将来 v2 で viki_status を導入するか？
- live review のために必須となる audit fields は何か？
- malformed payload のクラスごとに必要な failure mode は何か？
- controlled integration tests 前に必要な environment gating は何か？
- local mock adapter から controlled integration test への移行は誰が承認するか？

## 13. このノート後の推奨 PR

この design note のマージ後、次の安全な PR は次のいずれかに限定します。

- live integration design 向け reviewer checklist
- local mock adapter design note

design note と checklist のレビュー完了までは、live V.I.K.I. integration を実装してはいけません。

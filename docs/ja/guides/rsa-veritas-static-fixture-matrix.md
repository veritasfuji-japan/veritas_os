# RSA ↔ VERITAS Static Fixture Matrix

## 英語正本

- [RSA ↔ VERITAS Static Fixture Matrix](../../en/guides/rsa-veritas-static-fixture-matrix.md)

## 1. 目的

本ドキュメントは、V.I.K.I. ↔ VERITAS の sandbox validation flow で使われる static な RSA-compatible fixture variants を一か所に集約して要約するものです。

目的は、upstream の RSA-compatible status から、VERITAS の continuation decision・reason code・audit posture・commit state への決定論的マッピングを、コンパクトに確認できるようにすることです。

## 2. 現在のベースライン

現在のマージ済みベースラインには以下が含まれます。

- RSA / V.I.K.I. / VERITAS の terminology synchronization。
- 既存の RSASandboxPayload receiver contract。
- 既存の evaluate_rsa_sandbox_signal(payload) mapping。
- 既存の E2E sandbox harness。
- 既存の governance-backend-fast CI coverage。
- 既存の ALGORITHMIC_HUMILITY_ENGAGED validation snapshot。
- 既存の DENSITY_THROTTLED validation snapshot。
- 既存の DEFERRAL_ENGAGED validation snapshot。
- 既存の SAFE_PROCEED validation snapshot。

## 3. 用語互換性ノート

- RSA は theoretical framework / underlying rule set のままです。
- V.I.K.I. は RSA-compatible upstream payloads の operational producer です。
- VERITAS は downstream commit governance boundary です。
- 互換性のため rsa_status は変更しません。
- RSASandboxPayload は VERITAS 側 receiver contract 名として維持します。
- upstream_signal_source = "RSA" は v1 compatibility fixture/source label として維持します。
- この compatibility label は、VERITAS が V.I.K.I. の internal reasoning を消費することを意味しません。
- VERITAS が消費するのは emitted payload のみです。

## 4. Static fixture matrix

| rsa_status | upstream meaning | VERITAS continuation_decision | reason_code | sandbox_commit_state | review posture |
| --- | --- | --- | --- | --- | --- |
| SAFE_PROCEED | Upstream signal indicates the workflow may continue toward normal bind-boundary evaluation. | CONTINUE_TO_BIND_BOUNDARY | UPSTREAM_SAFE_PROCEED_SIGNAL | SUSPENDED_NOT_COMMITTED | continue to normal sandbox bind-boundary evaluation |
| DENSITY_THROTTLED | Upstream output was modified for cognitive-density control. | CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED | UPSTREAM_INTERVENTION_DENSITY_THROTTLE | SUSPENDED_NOT_COMMITTED | continue with upstream intervention logged |
| ALGORITHMIC_HUMILITY_ENGAGED | Required context or authority evidence is incomplete. | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_INCOMPLETE_KYC_CONTEXT | SUSPENDED_NOT_COMMITTED | pause for human review or additional evidence |
| DEFERRAL_ENGAGED | Critical upstream deferral condition reported before final commit. | BLOCK_FINAL_COMMIT | UPSTREAM_CRITICAL_DEFERRAL_SIGNAL | BLOCKED_NOT_COMMITTED | hard block final commit until review or remediation |

## 5. Escalation ladder

SAFE_PROCEED  
→ normal continuation

DENSITY_THROTTLED  
→ soft intervention logged

ALGORITHMIC_HUMILITY_ENGAGED  
→ pause for human review

DEFERRAL_ENGAGED  
→ block final commit

この ladder により、live V.I.K.I. middleware を接続しなくても、sandbox governance behavior の段階的エスカレーションをレビューできます。

## 6. スナップショットとの関係

本マトリクスは、既存の snapshot pages と合わせて参照する想定です。

- [RSA ↔ VERITAS E2E Sandbox Validation Snapshot](../../en/guides/rsa-veritas-e2e-sandbox-validation-snapshot.md)
- [SAFE_PROCEED validation snapshot](./rsa-veritas-safe-proceed-validation-snapshot.md)
- [RSA ↔ VERITAS DENSITY_THROTTLED Validation Snapshot](../../en/guides/rsa-veritas-density-throttled-validation-snapshot.md)
- [ALGORITHMIC_HUMILITY_ENGAGED validation snapshot](./rsa-veritas-algorithmic-humility-engaged-validation-snapshot.md)
- [RSA ↔ VERITAS DEFERRAL_ENGAGED Validation Snapshot](../../en/guides/rsa-veritas-deferral-engaged-validation-snapshot.md)

## 7. この文書で検証できること

- 現行の static RSA-compatible statuses を 1 つのレビュー可能な matrix で俯瞰できること。
- VERITAS が static fixture variants に対して deterministic な continuation decision mappings を持つこと。
- matrix が safe continuation / soft intervention / pause / hard commit block の全レンジを示すこと。
- 既存の compatibility labels と receiver contracts が安定維持されていること。
- live V.I.K.I. logic 接続なしで current sandbox validation flow をレビューできること。

## 8. この文書で検証しないこと

- live V.I.K.I. middleware の接続は行いません。
- V.I.K.I. internal reasoning の妥当性は検証しません。
- 現実世界での compliance status を判定しません。
- production AML/KYC compliance を実装しません。
- regulatory approval を提供しません。
- third-party certification を提供しません。
- legal advice を提供しません。
- real customer, financial, medical, KYC, regulated data は使用しません。
- production runtime governance は変更しません。

## 9. 次の sandbox ステップ

現行の 4 つの static fixture variants は、すべて個別の validation snapshots を持つ状態になりました。

次の安全な sandbox ステップは、E2E sandbox validation snapshot、4 つの個別 fixture snapshots、static fixture matrix、AML/KYC scenario map、E2E sandbox demo plan をリンクする lightweight reviewer index page の追加です。

reviewer index page が文書化・レビューされる前に、live V.I.K.I. connection を追加すべきではありません。

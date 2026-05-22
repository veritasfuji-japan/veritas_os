# RSA ↔ VERITAS Sandbox Reviewer Index

このページは、RSA-compatible な V.I.K.I. ↔ VERITAS サンドボックス文書群をレビューするための索引（review entrypoint）です。レビュー担当者が、各資料の役割と読み順を短時間で把握できるように整理しています。

## 英語正本

- [RSA ↔ VERITAS Sandbox Reviewer Index](../../en/guides/rsa-veritas-sandbox-reviewer-index.md)

## 1. 目的

この索引は、V.I.K.I. ↔ VERITAS / RSA-compatible サンドボックス文書セットのレビュー入口です。

シナリオマップ、デモ計画、検証スナップショット、静的フィクスチャ・マトリクスを1ページに集約し、live V.I.K.I. middleware へ接続せずにサンドボックスの流れを確認できるようにします。

## 2. 現在の taxonomy

- RSA は理論フレームワークおよび基礎ルールセットとして位置づけられます。
- V.I.K.I. は RSA-compatible な upstream payload を発行する運用 middleware です。
- VERITAS は downstream の commit governance boundary です。
- VERITAS は発行された payload のみを消費します。
- VERITAS は V.I.K.I. の internal reasoning を消費しません。
- `rsa_status`、`RSASandboxPayload`、`upstream_signal_source = "RSA"` といった既存の互換名は、v1 sandbox compatibility のため変更しません。

## 3. 推奨読了順

1. [AML/KYC シナリオマップ](./rsa-veritas-aml-kyc-scenario-map.md)
2. [E2E サンドボックス・デモ計画](./rsa-veritas-e2e-sandbox-demo-plan.md)
3. [E2E サンドボックス検証スナップショット](./rsa-veritas-e2e-sandbox-validation-snapshot.md)
4. [静的フィクスチャ・マトリクス](./rsa-veritas-static-fixture-matrix.md)
5. [SAFE_PROCEED 検証スナップショット](./rsa-veritas-safe-proceed-validation-snapshot.md)
6. [DENSITY_THROTTLED 検証スナップショット](./rsa-veritas-density-throttled-validation-snapshot.md)
7. [ALGORITHMIC_HUMILITY_ENGAGED 検証スナップショット](./rsa-veritas-algorithmic-humility-engaged-validation-snapshot.md)
8. [DEFERRAL_ENGAGED 検証スナップショット](./rsa-veritas-deferral-engaged-validation-snapshot.md)
9. [Local V.I.K.I. mock ingestion receiver design（Phase 2 local mock artifact / documentation-only）](./rsa-veritas-local-viki-mock-ingestion-receiver-design.md)
10. [Live V.I.K.I. integration design note（将来設計アーティファクト / documentation-only）](./rsa-veritas-live-viki-integration-design-note.md)
11. [Live V.I.K.I. integration reviewer checklist（review-gate artifact / documentation-only）](./rsa-veritas-live-viki-integration-reviewer-checklist.md)
12. [Local V.I.K.I. mock receiver test fixture plan（Phase 2 local mock artifact / documentation-only）](./rsa-veritas-local-viki-mock-receiver-test-fixture-plan.md)

4つの static fixture variants はすべて dedicated per-variant validation snapshots を持つ状態です。

## 4. Artifact map

| Artifact | Purpose | Primary reviewer question answered |
| --- | --- | --- |
| AML/KYC scenario map | node-by-node の upstream/downstream boundary を示します。 | V.I.K.I. はどこまでで、VERITAS はどこから始まるか？ |
| E2E sandbox demo plan | 静的サンドボックスのデモフローを説明します。 | 想定されたデモ経路は何か？ |
| E2E sandbox validation snapshot | 現在の静的 E2E 出力形状を記録します。 | 現行ハーネスの出力はどのような形か？ |
| Static fixture matrix | サポートされる静的フィクスチャ status を比較します。 | VERITAS は各 upstream status をどうマップするか？ |
| SAFE_PROCEED validation snapshot | 通常継続のケースを文書化します。 | upstream signal が proceed のとき何が起こるか？ |
| DENSITY_THROTTLED validation snapshot | soft な upstream 介入を文書化します。 | upstream output が修正されたが hard-block ではない場合、何が起こるか？ |
| ALGORITHMIC_HUMILITY_ENGAGED validation snapshot | required context 不足・authority evidence 不足時の pause / human-review gating を文書化します。 | required KYC context が incomplete の場合、何が起こるか？ |
| DEFERRAL_ENGAGED validation snapshot | hard な final-commit block を文書化します。 | 重大な upstream deferral signal が発行された場合、何が起こるか？ |
| Local V.I.K.I. mock ingestion receiver design | VERITAS 側 local mock receiver の受信・検証・fail-closed ルールを実装前に定義します。 | runtime integration を導入せず、synthetic local mock payload を VERITAS がどう受信・検証すべきか？ |
| Local V.I.K.I. mock receiver test fixture plan | receiver 実装前・テスト実装前に positive/negative/timeout/audit の fixture coverage を定義します。 | 将来の receiver tests で fail-closed 挙動を検証するために、どの fixture セットを実装すべきか？ |

## 5. Static fixture ladder

現在の static fixture ladder は次の通りです。

- `SAFE_PROCEED`
  - → `CONTINUE_TO_BIND_BOUNDARY`
  - → normal continuation
- `DENSITY_THROTTLED`
  - → `CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED`
  - → soft intervention logged
- `ALGORITHMIC_HUMILITY_ENGAGED`
  - → `PAUSE_FOR_HUMAN_REVIEW`
  - → pause / human review
- `DEFERRAL_ENGAGED`
  - → `BLOCK_FINAL_COMMIT`
  - → hard final-commit block

補足:

- `SAFE_PROCEED`、`DENSITY_THROTTLED`、`ALGORITHMIC_HUMILITY_ENGAGED`、`DEFERRAL_ENGAGED` はすべて専用の per-variant snapshot ページがあります。
- E2E sandbox validation snapshot は、別個の general E2E artifact として維持されます。

## 6. この文書セットが検証すること

- サンドボックスには RSA / V.I.K.I. / VERITAS の terminology boundary が文書化されています。
- サンドボックスには AML/KYC scenario map が文書化されています。
- サンドボックスには E2E demo plan が文書化されています。
- サンドボックスには current static E2E path の validation snapshot が文書化されています。
- サンドボックスには `SAFE_PROCEED`、`DENSITY_THROTTLED`、`ALGORITHMIC_HUMILITY_ENGAGED`、`DEFERRAL_ENGAGED` を含む static fixture matrix があります。
- サンドボックスは RSA-compatible upstream status から VERITAS continuation decision への deterministic mapping を示します。
- サンドボックスは監査エントリが raw upstream intent/action fields をデフォルトで redact する挙動を示します。
- サンドボックスは live V.I.K.I. logic へ接続せずにレビュー可能です。

## 7. この文書セットが検証しないこと

- live V.I.K.I. middleware への接続は行いません。
- V.I.K.I. の internal reasoning は検証しません。
- 実際の取引やワークフローが安全であることを証明しません。
- 現実世界の compliance status を判定しません。
- 本番の AML/KYC compliance を実装しません。
- 規制当局の承認を提供しません。
- 第三者認証を提供しません。
- 法的助言を提供しません。
- 実在の顧客・金融・医療・KYC・規制対象データは使用しません。
- 本番 runtime governance は変更しません。

## 8. 次の安全な sandbox ステップ

1. general E2E artifact と4つの per-variant snapshots の導線として、static fixture matrix と reviewer index のリンク整合を維持する。
2. maintainers がコミット済み出力 artifact を望む場合、`examples/sandbox/rsa_veritas_e2e_harness.py` から小さな生成サンプル出力ファイルを追加する。
3. live adapter 提案時の review gate として reviewer checklist を利用する。
4. 静的ドキュメントセットのレビュー完了後に限り、live V.I.K.I. integration 用の別 design / contract artifact を検討する。

この PR で live V.I.K.I. connection を追加してはいけません。

live integration は後続の design phase とし、静的 sandbox documentation pass には含めません。

本索引に追加された live V.I.K.I. integration ページは将来設計アーティファクトのみであり、runtime integration は導入しません。

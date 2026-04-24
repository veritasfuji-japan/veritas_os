# AML/KYC PoC クイックスタート

## 位置づけ
この文書は、英語正本の要点を日本語で把握するための説明ページです。対象読者は、運用責任者・監査担当・技術評価者です。

## 要点
- VERITAS OS は Decision Governance / 意思決定ガバナンス と Bind-Boundary / bind境界 の統制を実装する beta 段階のシステムです。
- 本ページは実装済み事実と運用上の確認観点を整理するもので、認証取得・規制承認・本番適合を主張するものではありません。
- 詳細仕様は英語正本が canonical であり、差分がある場合は英語正本を優先します。

## VERITASにおける意味
- Decision Governance / 意思決定ガバナンス: `gate_decision` と `business_decision` の境界を明示します。
- Bind-Boundary / bind境界: 承認後の副作用を bind 時に再評価し、fail-closed / 安全側停止 を優先します。
- FUJI Gate と TrustLog: 実行判断と監査系譜を接続し、Mission Control で operator-facing governance surface / 運用者向けガバナンス面 を確認できます。
- Replay / 再現実行: 再実行時の差分確認により、ガバナンス適用状況を検証します。
- governance_identity / ガバナンス識別子、bind_summary / bind概要、BindReceipt / bind証跡: 監査・レビュー向けの成果物連携キーです。

## 実装上の確認ポイント
- API 境界: `/v1/decide`、`/v1/governance/*`、`/v1/compliance/config`、`/v1/system/halt`、`/v1/system/resume` の現行契約を確認します。
- 成果物: TrustLog、BindReceipt、bind_summary、governance_identity の保存/表示経路を確認します。
- UI: Mission Control の Governance / Audit / Replay 画面で表示契約を確認します。
- テスト・スキーマ: 英語正本または実装ファイルを確認してください。

## 現時点の制限
- 本リポジトリは、実装済みの統制境界と検証可能な証跡を示すbeta段階のシステムです。
- 現時点で全ての副作用経路がbind-governedであると主張するものではありません。
- 本番環境での利用には、環境ごとのハードニング、鍵管理、監査設計、運用手順の確立が必要です。
- 外部監査や第三者検証は、実施範囲と証拠提出範囲を個別に定義する必要があります。

## 英語正本
- [../../en/guides/poc-pack-financial-quickstart.md](../../en/guides/poc-pack-financial-quickstart.md)

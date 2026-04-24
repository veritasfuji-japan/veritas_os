# ポリシーバンドル昇格（日本語解説）

## 位置づけ
`POST /v1/governance/policy-bundles/promote` を中心とした昇格運用の日本語解説です。

## 要点
- 昇格は「作成済みポリシーを運用有効化する統制イベント」です。
- 署名検証、承認履歴、rollback 経路をセットで管理します。
- bind-governed effect path として監査対象になるため、証跡保全が必須です。

## VERITASにおける意味
- Decision Governance と Bind-Boundary / bind境界 の接続点です。
- FUJI Gate・TrustLog・Mission Control で同一昇格イベントを追跡できます。

## 実装上の確認ポイント
- promotion API の入力条件と失敗コードを確認する。
- 昇格後に `governance_identity` と bind結果が期待通りか確認する。
- 詳細は英語正本または実装ファイルを確認してください。

## 現時点の制限
- 組織固有の承認ワークフローは追加設計が必要です。
- 本文書は全環境での自動昇格安全性を保証しません。

## 英語正本
- [docs/en/guides/governance-policy-bundle-promotion.md](../../en/guides/governance-policy-bundle-promotion.md)

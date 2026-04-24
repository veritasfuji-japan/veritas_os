# Governance Artifact Lifecycle（日本語解説）

## 位置づけ
ガバナンス成果物の生成・昇格・保管・廃止のライフサイクルを説明する日本語解説です。

## 要点
- 成果物は作成、レビュー、署名、昇格、失効の段階で管理します。
- policy bundle promotion と署名検証を分離せず運用します。
- 監査時は lifecycle 上の責任分界と変更履歴を提示します。

## VERITASにおける意味
- governance_identity と bind証跡の整合を保つ運用設計の核です。
- Mission Control から追跡可能な状態遷移を維持することで、外部レビュー対応力を高めます。

## 実装上の確認ポイント
- ポリシーバンドル昇格 API と署名検証手順の紐付け。
- 失効・ロールバック時の Replay 影響確認。
- 詳細は英語正本または実装ファイルを確認してください。

## 現時点の制限
- lifecycle の承認フローは組織ごとに追加実装が必要です。
- 本文書は外部認証取得を意味しません。

## 英語正本
- [docs/en/governance/governance-artifact-lifecycle.md](../../en/governance/governance-artifact-lifecycle.md)

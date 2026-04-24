# バックエンドパリティカバレッジ（日本語解説）

## 位置づけ
Memory / TrustLog バックエンド間の実装差分と検証範囲を確認する日本語解説です。

## 要点
- PostgreSQL を本番パスとし、JSON/JSONL は軽量開発用途として扱います。
- パリティは API 契約・整合性・失敗時挙動の観点で確認します。
- fail-closed での挙動差異は監査向けに明示する必要があります。

## VERITASにおける意味
- Bind-Boundary の結果がストレージ差異で変わらないことは、監査と運用信頼性の基礎です。
- Mission Control と Replay の整合にも直結します。

## 実装上の確認ポイント
- `/health` の `storage_backends` で有効バックエンドを確認する。
- parity テストと production/smoke 検証の結果を証跡化する。
- 詳細は英語正本または実装ファイルを確認してください。

## 現時点の制限
- 本ページは全構成での性能同等性を保証するものではありません。
- 本番導入時はDB設定、監視、復旧訓練を環境別に実施してください。

## 英語正本
- [docs/en/validation/backend-parity-coverage.md](../../en/validation/backend-parity-coverage.md)

# 技術証明パック（Technical Proof Pack）

## 位置づけ
レビュー、PoC、監査前審査で「何を技術的に証明するか」を整理する日本語解説です。

## 要点
- 技術証明パックは、実装済み事実と未保証範囲を分離して示します。
- bind境界、Replay、TrustLog、運用Runbook の証拠セットを束ねます。
- 過大主張を避け、beta段階の制限を明記します。

## VERITASにおける意味
- Decision Governance を「説明可能」から「検証可能」へ進めるための提出単位です。
- `bind_summary` と `BindReceipt` を接続し、監査・投資家・顧客の確認負担を下げます。

## 実装上の確認ポイント
- 技術証明に含めるテスト、API出力、ログ、Runbook の版を固定する。
- production validation / backend parity と整合した証拠を使う。
- 詳細は英語正本または実装ファイルを確認してください。

## 現時点の制限
- 本資料のみで本番適合を保証しません。
- 環境依存の性能・可用性・運用成熟度は別途検証が必要です。

## 英語正本
- [docs/en/validation/technical-proof-pack.md](../../en/validation/technical-proof-pack.md)

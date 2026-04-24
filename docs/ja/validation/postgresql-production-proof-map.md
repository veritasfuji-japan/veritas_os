# PostgreSQL Production Proof Map（日本語解説）

## 位置づけ
PostgreSQL を本番パスとして説明する際に、参照すべき証拠と文書を整理する日本語案内です。

## 要点
- Docker Compose 既定、runtime 確認点、検証ジョブの三点で本番パスを示します。
- proof map は提出用リンク集であり、単独で保証を与える文書ではありません。
- backend parity / production validation / operations guide と併読します。

## VERITASにおける意味
- Bind-Boundary と TrustLog の証跡保存を、運用現場で再現可能にします。
- Mission Control・監査・運用担当が同じ証拠源を参照するための索引です。

## 実装上の確認ポイント
- `/health` の backend 表示、検証ジョブ結果、Runbook を同一リリースで紐づける。
- 監査提出時に参照URLとコミットSHAを固定する。
- 詳細は英語正本または実装ファイルを確認してください。

## 現時点の制限
- 環境別の HA/DR や運用成熟度は別資料で評価が必要です。
- 第三者監査完了・認証取得を示す文書ではありません。

## 英語正本
- [docs/en/validation/postgresql-production-proof-map.md](../../en/validation/postgresql-production-proof-map.md)

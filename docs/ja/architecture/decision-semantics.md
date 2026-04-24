# Decision Semantics（日本語解説）

## 位置づけ
本ページは `docs/en/architecture/decision-semantics.md` の日本語解説です。
Decision Governance を評価・監査・実装する担当者が、意思決定契約の読みどころを短時間で共有するために使います。

## 要点
- decision 結果と bind 結果は別フェーズで管理されます。
- 公開契約では `bind_summary` と `BindReceipt` により、運用者が最小情報で triage しつつ詳細追跡できます。
- fail-closed を前提に、未定義・不整合経路では安全側に倒れる設計です。

## VERITASにおける意味
Decision Semantics は、FUJI Gate・TrustLog・Mission Control を横断する共通語彙です。
`governance_identity` と bind 系譜を揃えることで、Replay 時に「なぜその判断になったか」を再検証可能にします。

## 実装上の確認ポイント
- `/v1/decide` とガバナンス mutation API のレスポンス契約が整合していること。
- `bind_summary` が mutation/export で再利用されていること。
- BindReceipt detail API で canonical target metadata が取得できること。

## 英語正本
- [docs/en/architecture/decision-semantics.md](../../en/architecture/decision-semantics.md)

## 注意
- このページは英語正本の補助であり、仕様の最終判断は英語正本で行います。
- 現在の実装事実と将来方向を混同しないでください。
- 本番適用には環境ごとのハードニング・統合・運用審査が必要です。

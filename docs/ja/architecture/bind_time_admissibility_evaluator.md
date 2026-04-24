# Bind-Time Admissibility Evaluator（日本語解説）

## 位置づけ
この文書は、bind 時点で副作用を許可できるかを判定する evaluator の観点を日本語で整理したものです。設計レビューと運用審査の入口として利用します。

## 要点
- 承認済み decision でも、bind 時点の条件不一致で `BLOCKED` / `ESCALATED` になり得ます。
- 判定には policy bundle、`governance_identity`、要求証拠、環境条件を使います。
- 判定結果は `bind_summary` と `BindReceipt` に残り、Replay / 再現実行で追跡可能です。

## VERITASにおける意味
- Bind-Boundary / bind境界 は「承認」と「副作用コミット」の安全分離点です。
- FUJI Gate と evaluator の組み合わせで fail-closed / 安全側停止 を担保します。
- Mission Control では operator-facing governance surface として判定理由を確認できます。

## 実装上の確認ポイント
- bind 判定が接続された effect path（policy 更新・ポリシーバンドル昇格・halt/resume 等）を確認する。
- 判定失敗時の reason code と `bind_failure_reason` の整合を確認する。
- Replay 実行で同一条件時に同じ admissibility 判定になるか確認する。
- 詳細は英語正本または実装ファイルを確認してください。

## 現時点の制限
- 現時点で全副作用経路が bind-governed / bind統制対象 であるとは主張しません。
- 本番適用には環境ごとのハードニング、統合、監査設計、運用審査が必要です。

## 英語正本
- [docs/en/architecture/bind_time_admissibility_evaluator.md](../../en/architecture/bind_time_admissibility_evaluator.md)

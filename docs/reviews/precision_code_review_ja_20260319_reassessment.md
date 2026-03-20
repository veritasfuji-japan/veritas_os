# VERITAS OS 再評価レビュー

作成日: 2026-03-19
対象文書: `docs/reviews/precision_code_review_ja_20260319.md`

## 要約

`precision_code_review_ja_20260319.md` を全文再読し、関連実装とテストを照合した結果、
文書前半で High として挙げられている懸念のうち、
TrustLog / Memory API / auth fail-open に関する項目は、
同一文書の後半に記載された 2026-03-19 改善で概ね解消済みであることを確認しました。

一方で、`kernel.py` / `pipeline.py` / `fuji.py` / `memory.py` などの
中核モジュールに複雑度が集中しているという指摘は、
現時点でも有効です。

**再評価の結論**:

- 完成度: 高い
- 整合性: 高い
- 一貫性: 高い
- コード品質: 高いが、中核モジュールの複雑度集中が継続課題
- セキュリティ: 強いが、fail-open 設定の運用統制は継続必須

## 再評価結果

### 1. 文書前半の High 指摘の扱い

#### H1. 中核モジュールへの複雑度集中
これは現在も有効です。
今回確認した改善は主に API 安全性・観測性・設定防御に関するものであり、
中核アーキテクチャそのものの分割や責務再整理を完了させたものではありません。

#### H2. API 層の broad exception と observability 不足
この点は、現状では「過去の主要懸念」寄りです。
以下の改善がすでに反映されていました。

- TrustLog aggregate JSON の状態を `missing / ok / invalid / unreadable / too_large` で区別
- unreadable な aggregate JSON を append 時に上書きしない
- Memory API が `status: ok | partial_failure | failed` と `errors[]` を返す
- auth fail-open を explicit local/test profile に限定
- `/v1/metrics` で TrustLog aggregate の状態を露出

したがって、文書前半の問題提起自体は妥当ですが、
**現在の実装評価としては「すでに大きく改善済み」** と整理するのが正確です。

### 2. 現在の最重要課題

現時点で最も重い論点は、次の一点です。

- `pipeline.py` / `kernel.py` / `fuji.py` / `memory.py` に集中した構造的複雑度

これは単なる行数の多さではなく、以下の実務リスクにつながります。

- 変更影響範囲の読解コスト上昇
- backward compatibility layer と正規経路の判別難化
- monkeypatch 前提テストの増加
- Planner / Kernel / Fuji / MemoryOS の責務境界の将来的侵食

## 実装照合メモ

### TrustLog

`veritas_os/api/trust_log_io.py` では、`TrustLogLoadResult` と
`load_logs_json_result()` が導入されており、aggregate JSON の異常状態を
空配列へ丸めずに扱えるようになっています。
また append 処理では、aggregate JSON が unreadable な場合に
`trust_log.json` の再保存をスキップし、JSONL 側のみ維持します。

### Memory API

`veritas_os/api/routes_memory.py` の `memory_put()` は、
legacy 保存と vector 保存を分離して評価し、
部分成功を `partial_failure` として返します。
これにより「成功に見える部分失敗」はかなり緩和されています。

### auth fail-open

`veritas_os/api/auth.py` では、`VERITAS_AUTH_STORE_FAILURE_MODE=open` を使うには
`VERITAS_AUTH_ALLOW_FAIL_OPEN=true` に加えて、
`VERITAS_ENV=dev|development|local|test` が必要です。
`VERITAS_ENV` 未設定や staging などでは `closed` に戻されます。

さらに `veritas_os/api/startup_health.py` では、
unsupported profile で `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` が残っている場合に
警告が出るようになっています。

### metrics observability

`veritas_os/api/routes_system.py` の `/v1/metrics` は、
`trust_json_status` と `trust_json_error` を返します。
これにより、TrustLog aggregate JSON の破損や unreadable 状態を
運用から検知しやすくなっています。

## セキュリティ警告

1. `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` は、非本番でも認証保護を弱めます。
   shared staging / preview では原則として残さないでください。
2. TrustLog aggregate JSON が unreadable の場合、
   いまの実装は「壊れた上書き」を防ぐだけで、根本原因を自動修復するものではありません。
   warning を検知したら速やかに復旧が必要です。
3. Memory API は改善済みですが、例外種別の細分化余地は残っています。
   監査要件がさらに厳しくなる場合は、段階別に例外契約を明確化する価値があります。

## 推奨アクション

### Priority 1

- 中核モジュールの public contract と internal helper の境界をさらに明文化する
- backward compatibility export と正規拡張ポイントを architecture docs に固定する
- 新規コントリビュータ向けに「正規経路」と「互換レイヤ」を区別した案内を追加する

### Priority 2

- TrustLog degraded 状態の運用手順を runbook 化する
- fail-open 警告を shared 環境で CI / startup policy によりさらに検知しやすくする

## 2026-03-19 実施改善

再評価で残課題だった「public contract / compatibility layer / 正規拡張ポイントの見えにくさ」に対して、
責務境界を越えない最小改善を実施しました。

- `docs/architecture/core_responsibility_boundaries.md` を追加し、Planner / Kernel / FUJI / MemoryOS それぞれについて
  public contract・責務・正規拡張ポイント・互換レイヤの扱いを明文化
- `scripts/architecture/check_responsibility_boundaries.py` の remediation guide を拡張し、
  CI 上で「禁止依存を直すならどこへ実装すべきか」を extension point 付きで案内
- さらに boundary checker の JSON レポートにも
  `allowed_dependencies` / `recommended_extension_points` / `remediation_link` を追加し、
  CI や自動解析が text 出力を再解釈しなくても同じ修正ガイダンスを扱えるようにした
- 対応テストを更新し、boundary checker のガイダンス退行を防止

この改善は、`kernel.py` / `pipeline.py` / `fuji.py` / `memory.py` の責務を移動せず、
既存 API 契約も変えずに、構造的複雑度の運用コストだけを下げることを目的としています。

## 2026-03-19 追加改善（最小差分）

上記の改善内容を実装と再照合したところ、
`docs/architecture/core_responsibility_boundaries.md` と
`scripts/architecture/check_responsibility_boundaries.py` の
正規拡張ポイント一覧に一部ずれが残っていました。

無駄な責務変更を避けるため、今回は中核モジュール本体には触れず、
**boundary checker の修正ガイダンスだけを文書と一致させる最小改善**を実施しました。

- FUJI の推奨拡張ポイントに `veritas_os.core.fuji_safety_head` を追加
- MemoryOS の推奨拡張ポイントに
  `veritas_os.core.memory_helpers` / `veritas_os.core.memory_lifecycle` /
  `veritas_os.core.memory_security` を追加
- JSON machine report にも同じ一覧が載ることをテストで固定し、
  CI 上の修正ガイダンス退行を防止

この対応は Planner / Kernel / FUJI / MemoryOS の責務境界や既存 API 契約を変更せず、
レビューで重視された「正規拡張ポイントの明確化」をより正確にするものです。

## 2026-03-20 追加改善（ドキュメント整合性の自動検証）

再評価文書を踏まえて現状を再点検したところ、
残っている実務リスクは「boundary checker の修正ガイダンスと
アーキテクチャ文書が将来また乖離すること」でした。

責務境界を動かしたり中核モジュールを再分割したりするのは今回の目的から外れるため、
**既存の責務を一切変えずに、ガイダンスの整合性だけを自動検証する最小改善**を実施しました。

- `scripts/architecture/check_responsibility_boundaries.py` に
  `docs/architecture/core_responsibility_boundaries.md` から
  Preferred extension points を抽出する補助関数を追加
- checker 定義の `RECOMMENDED_EXTENSION_POINTS` と
  文書記載の一覧との差分を検出する整合性チェック関数を追加
- `veritas_os/tests/test_responsibility_boundary_checker.py` に
  実文書を直接読む回帰テストを追加し、文書と checker の再乖離を防止

この改善は Planner / Kernel / FUJI / MemoryOS の public contract や
互換レイヤの振る舞いを変えず、レビューで継続課題とされた
「拡張境界の見えにくさ」を運用面で再発しにくくするものです。

## 2026-03-20 追加改善（CI 失敗条件への統合）

上記の「自動検証」を再確認したところ、整合性チェック関数自体は存在していたものの、
boundary checker の CLI / JSON レポートには未統合で、
**文書と checker が再乖離しても CI 失敗条件にならない**状態が残っていました。

そこで今回は、中核責務や API 契約を一切変えず、
**既存の doc alignment check を boundary checker の正式な失敗要因として扱う最小改善**を実施しました。

- `scripts/architecture/check_responsibility_boundaries.py` で
  architecture 文書との不整合を `doc_alignment_error` として収集するよう修正
- CLI 実行時にも JSON machine report にも同エラーを含め、
  文書と checker の乖離を CI から自動検知できるように変更
- 回帰テストを追加し、drift が human-readable / machine-readable の両経路で
  失敗として観測されることを固定

この対応はレビューで重視された「正規拡張ポイントの明確化」を維持するための
運用改善であり、Planner / Kernel / FUJI / MemoryOS の責務分割そのものには触れていません。

## 2026-03-20 追加改善（Markdown 整形差分への耐性強化）

上記の運用改善を踏まえてさらに確認したところ、
boundary checker の文書抽出は `**Preferred extension points**:` の直後に
空行が入るだけでも箇条書きを読めなくなり、
**文書の意味は変わっていないのに cosmetic な Markdown 整形だけで
doc alignment error が発生しうる** 状態でした。

これは責務境界そのものの問題ではなく、整合性検証の安定性の問題であるため、
今回は checker の文書パーサだけを最小修正しました。

- `scripts/architecture/check_responsibility_boundaries.py` の
  `extract_doc_extension_points()` を修正し、
  marker 直後の空行や行頭インデントを無視して
  Preferred extension points の箇条書きを抽出できるように改善
- `veritas_os/tests/test_responsibility_boundary_checker.py` に
  空行入り Markdown を直接与える回帰テストを追加し、
  今後の整形差分で CI が誤検知しないことを固定

この改善も Planner / Kernel / FUJI / MemoryOS の public contract や責務境界を変えず、
レビューで継続課題とされた「拡張境界の見えにくさ」を支える
文書整合性チェックの信頼性だけを上げるものです。

## 最終結論

このコードベースは、監査性・安全性・再現性を強く意識して作られた高品質な基盤です。
ただし、今後の品質向上効果が最も大きいのは、機能追加ではなく
**中核モジュールの複雑度削減と拡張境界の明確化**です。

つまり、今回の再評価を一言でまとめると次の通りです。

> 思想と安全設計は非常に強く、API レベルの高優先度懸念はかなり改善済み。
> これからの主戦場は、構造的複雑度の制御である。

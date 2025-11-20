# VERITAS AGI Research Roadmap (6 months)

Version: 1.0  
Scope: VERITAS Self-Hosting / Proto-AGI OS の6ヶ月ロードマップ  
Owner: 藤下 + VERITAS OS  
Status: Draft (to be evolved by Self-Improve loop)

---

## 0. ゴールイメージ（6ヶ月後）

6ヶ月後に VERITAS を以下の状態に持っていくことを目標とする。

- Self-Improve ループ  
  （観測 → 解釈 → 設計 → 実装 → 検証 → 採用/rollback）  
  が **週1〜2回ペースで安定して回っている**
- /v1/decide の品質・安定性に関する主要メトリクスが、初期比で明確に改善している  
  - `decision_latency_ms_median`: **30%以上の改善（短縮）**
  - `error_rate`: **50%以上の低下**
  - `value_ema`: **ベースライン +0.05 以上で安定**
  - `crash_free_rate`: **99%以上**
- AGI 研究OSとして第三者に説明できるだけのドキュメント・図・ログ構造が揃っている  
  - world_model, FUJI Gate, module responsibilities, decide pipeline, self-improve loop, metrics, roadmap, fail-safe など

---

## 1. 月次マイルストーン

### Month 1 ― 「骨格ドキュメント & Self-Improve v1」

**フォーカス**

- 世界モデル / 安全境界 / モジュール責務 / パイプラインを  
  「言語化された設計」として固める
- Self-Improve ループを **1サイクルでもいいから実際に回す**

**ターゲット成果物**

- `docs/world_model.md`（完成版）
- `docs/fuji_gate_safety.md`（完成版）
- `docs/module_responsibilities.md`（完成版）
- `docs/decide_pipeline_flow.md`（完成版）
- `docs/self_improvement_loop.md`（β版）
- `docs/self_improvement_commands.md`（CLI / スクリプト一覧）
- `veritas_os/scripts/bench_plan.py`（bench → code_tasks 生成）
- `veritas_os/scripts/generate_doctor_report.py`（最低限動く形）

**成功条件（Done の定義）**

- 上記ドキュメントが Git 管理下に入り、常に最新に近い状態である
- Self-Improve ループを **1回以上** 実行し、以下のアーティファクトが実際に生成されている
  - `scripts/logs/bench_*.json`
  - `scripts/logs/doctor_report.json`
  - `scripts/logs/plan_*.json`
  - `docs/plan_*.md`
- `world_state.json` に `projects.veritas_agi` が存在し、`progress` が 0 → 0.5 付近まで進んでいる

---

### Month 2 ― 「計測と評価軸の固定」

**フォーカス**

- 「何が良くなったと言えるのか？」を数値で定義する
- ベンチ・doctor・world_state からメトリクスを自動抽出できるようにする

**ターゲット成果物**

- `docs/metrics.md`（メトリクス仕様書）
- `veritas_os/scripts/metrics_snapshot.py`（メトリクスを1枚の JSON に集約）
- `world_state.json` に `metrics.*` を持たせる実装
- `scripts/logs/metrics_*.json`（スナップショットログ）
- `scripts/logs/bench_summary_*.md`（Before/After 比較の Markdown）

**成功条件**

- 以下の値が **毎回同じ形式で** 記録されるようになっている  
  - `decision_latency_ms_median`
  - `error_rate`
  - `value_ema`
  - `risk_effective`
  - `crash_free_rate`
- Month1 のベースラインと比較して、「何がどれくらい変わったか」を  
  1枚の Markdown（bench_summary）で説明できる

---

### Month 3 ― 「Self-Improve ループの標準運用化」

**フォーカス**

- 週次で Self-Improve サイクルを回すことを “運用のデフォルト” にする
- ロールバック戦略（Git / world_state への記録）を設計

**ターゲット成果物**

- `docs/self_improvement_loop.md`（正式版）
- `docs/self_improvement_commands.md`（更新）
- `docs/rollback_strategy.md`（ドラフト版）
- `docs/weekly_routine.md`（週次ルーチン・チェックリスト）
- Git ブランチ運用ルール（feature/*, hotfix/* 等の方針）

**成功条件**

- 3〜4週連続で  
  `観測 → 解釈 → 設計 → 実装（小さめ変更） → 検証 → 採用/rollback`  
  が実行されている
- Git の実験ブランチ（feature/*）が少なくとも 3 本以上存在し、  
  それぞれの目的と結果が簡単なメモとして残っている
- `world_state.json` に「どのサイクルが採用/rollback されたか」の痕跡が残っている

---

### Month 4 ― 「安全性・FUJI Gate の強化」

**フォーカス**

- FUJI Gate のルールを体系化し、危険な自己改善を事前にブロックする
- 倫理・法的・セキュリティリスクに関するルールセットを整備

**ターゲット成果物**

- `docs/fuji_gate_safety.md`（拡張版：ルール一覧＋事例付き）
- `config/fuji_rules.json`（仮称：FUJI Gate 用ルール定義ファイル）
- `veritas_os/scripts/fuji_dry_run.py`  
  （ある決定案を FUJI Gate だけに通して評価するためのツール）

**成功条件**

- 危険 / 不適切な決定案に対して FUJI Gate が  
  `decision_status = "reject"` を返すテストケースが存在する
- Self-Improve 用の /v1/decide 呼び出しも、必ず FUJI Gate を経由している（コード上保証）
- `risk_effective` が安定して 0.1 以下のレンジに収まっている

---

### Month 5 ― 「外部レビュー可能な形に整える」

**フォーカス**

- エンジニア / 研究者 / 投資家など第三者に見せられる形に整理
- デモシナリオを用意し、「何が新しいのか」「何が出来るのか」を示す

**ターゲット成果物**

- `docs/veritas_agi_research_overview.md`  
  （VERITAS AGI 研究OSの全体像）
- `docs/demo_script_self_improve_loop.md`  
  （Self-Improve 1サイクルのデモ台本）
- 簡易スライド or PDF（研究者・友人向け説明資料）
- GitHub 公開時の README ドラフト（公開範囲は別途検討）

**成功条件**

- 第三者に対して、
  1. 世界モデル  
  2. Decide パイプライン  
  3. Self-Improve ループ  
  4. メトリクス  
  5. フェイルセーフ  
  を 30〜60分で説明できる
- 少なくとも 1人以上からフィードバックを受け、その内容を world_state.notes に記録

---

### Month 6 ― 「総仕上げ & 安定運用モード」

**フォーカス**

- ロールバック戦略・バックアップ・Drive 同期まで含めた「運用OS」としての完成度を上げる
- 6ヶ月分のメトリクスとログを振り返り、「何が変わったか」を総括

**ターゲット成果物**

- `docs/fail_safe.md`（フェイルセーフ / ロールバック / バックアップ仕様）
- `docs/rollback_strategy.md`（正式版）
- `docs/roadmap_review_6m.md`（6ヶ月の振り返りレポート）
- `veritas_os/scripts/backup_logs.sh` / `sync_to_drive.sh` の運用ルール記述

**成功条件**

- 6ヶ月分の `world_state.json` / `doctor_report` / `bench_summary_*` をもとに、
  「VERITAS がどう変化したか」を時系列で説明できる
- 重大な事故（ログ喪失 / Git 破壊など）が起きていない
- Self-Improve サイクルを「半自動で」「安全に」回せているという手応えがある

---

## 2. 週次スプリント テンプレ

**Week X の基本サイクル（目安: 週10〜15時間）**

1. 観測（1〜2h）
   - ベンチ実行（bench.py / run_benchmarks.py）
   - doctor_report 再生成
   - world_state / metrics スナップショット保存

2. 解釈（1〜2h）
   - doctor_report / bench_summary を読む
   - decide.py で「弱点リスト＋Next Actions」を生成
   - 今週触るテーマを1つ決める（例: world_model / fuji / planner / scripts 等）

3. 設計（1〜2h）
   - テーマ別プランを /v1/decide で生成
   - `plan_*.md` / `plan_*.json` を保存
   - やり過ぎ / 物足りなさを人間側で微調整

4. 実装（4〜6h）
   - Git ブランチを切る（feature/*）
   - 小さめの実装タスク 2〜3 個に分割
   - テスト & コミットを積み重ねる

5. 検証（1〜2h）
   - ベンチ / doctor / bench_summary を再実行
   - Before/After メトリクスを比較
   - 良ければ採用、微妙ならロールバック or 保留

6. ログ・同期・振り返り（1h）
   - world_state 更新（採用/rollback のメモを残す）
   - `backup_logs.sh` / `sync_to_drive.sh` の実行（必要に応じて）
   - 「今週やったこと」「来週やること」を1〜2行メモで記録

---

## 3. このロードマップの扱い

- 本ドキュメント自体も Self-Improve ループの対象とする  
  - 必要に応じて /v1/decide 経由で改訂案を生成し、バージョンを上げていく
- 現実とのズレが大きくなった場合は、  
  「現実に合わせてロードマップを更新する」ことを優先する  
  （計画を守るために開発を歪めない）

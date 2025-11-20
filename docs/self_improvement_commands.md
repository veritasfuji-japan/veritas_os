# VERITAS Self-Improvement Loop コマンド集  
(self_improvement_commands.md)

Version: 1.0  
Author: VERITAS OS (藤下 + LLM Co-evolution)  
Scope: Self-Improve ループの各フェーズで「実際に叩くコマンド」の一覧

---

## 0. 共通セットアップ

**前提ディレクトリ構成（想定）**

- プロジェクトルート: `~/veritas_clean_test2`
- VERITAS 本体: `~/veritas_clean_test2/veritas_os`
- スクリプト群: `~/veritas_clean_test2/veritas_os/scripts/`
- 仮想環境: `.venv`（ある場合）

**セットアップ**

```bash
cd ~/veritas_clean_test2

# (必要なら) 仮想環境
source .venv/bin/activate

# API 呼び出し用の環境変数（実際の値に置き換える）
export VERITAS_API_URL="http://localhost:8000/v1/decide"
export VERITAS_API_KEY="your_api_key"
export VERITAS_API_SECRET="your_api_secret"

FastAPI サーバー起動（別ターミナル）

cd ~/veritas_clean_test2
uvicorn veritas_os.api.server:app --reload --port 8000

1. 観測 (Observation) フェーズ

1-1. 単一ベンチを叩く
	•	用途: 特定の bench（例: agi_veritas_self_hosting）を 1 回実行
	•	スクリプト: veritas_os/benchmarks/bench.py

cd ~/veritas_clean_test2

python veritas_os/benchmarks/bench.py \
  --bench-id agi_veritas_self_hosting \
  --api-url "$VERITAS_API_URL" \
  --api-key "$VERITAS_API_KEY" \
  --api-secret "$VERITAS_API_SECRET"

1-2. 複数ベンチをまとめて回す（あれば）
	•	用途: 複数 YAML ベンチを一括実行
	•	スクリプト（想定）: veritas_os/scripts/run_benchmarks.py
※ まだ無ければ今後作成する対象。

cd ~/veritas_clean_test2

python veritas_os/scripts/run_benchmarks.py \
  --api-url "$VERITAS_API_URL" \
  --api-key "$VERITAS_API_KEY" \
  --api-secret "$VERITAS_API_SECRET"

1-3. doctor_report（自己診断レポート）の生成
	•	用途: decision_log.jsonl / bench_*.json から集計してヘルスチェック
	•	スクリプト（想定名）: veritas_os/scripts/generate_doctor_report.py

cd ~/veritas_clean_test2

python veritas_os/scripts/generate_doctor_report.py \
  --logs-dir veritas_os/scripts/logs \
  --out veritas_os/scripts/logs/doctor_report.json

※ このとき world_state.json や簡易メトリクスのスナップショットも一緒に吐くと、Self-Improve ループが回しやすい。

⸻

2. 解釈 (Interpretation) フェーズ

2-1. doctor_report から弱点リストを抽出
	•	用途: 「弱点の整理」と「次にやるべきテーマ」を LLM にまとめさせる
	•	スクリプト: veritas_os/scripts/decide.py（CLI ラッパー）

cd ~/veritas_clean_test2

python veritas_os/scripts/decide.py \
  --query-file veritas_os/prompts/weakpoints_from_doctor.txt \
  --input veritas_os/scripts/logs/doctor_report.json \
  --out veritas_os/scripts/logs/agi_weakpoints.json

weakpoints_from_doctor.txt には例えば：

最新の doctor_report.json を読み、
VERITAS OS の弱点を箇条書きで整理し、
それぞれの弱点に対して「なぜ問題か」「どのモジュールに関係するか」をコメントしてください。

のようなプロンプトを書く。

⸻

3. 設計 (Design) フェーズ

3-1. 弱点リストから具体的なプランを生成
	•	用途: planner.steps を埋める 5〜10 ステップの計画を作る
	•	スクリプト: 同じく veritas_os/scripts/decide.py

cd ~/veritas_clean_test2

python veritas_os/scripts/decide.py \
  --query-file veritas_os/prompts/plan_from_weakpoints.txt \
  --input veritas_os/scripts/logs/agi_weakpoints.json \
  --out veritas_os/scripts/logs/plan_veritas_worldmodel_step3.json \
  --save-md docs/plan_veritas_worldmodel_step3.md

	•	plan_veritas_worldmodel_step3.json
→ extras.planner.steps をそのまま保存する JSON
	•	docs/plan_veritas_worldmodel_step3.md
→ 人間が読めるプラン Markdown

plan_from_weakpoints.txt 例：

agi_weakpoints.json の弱点を読み、
「WorldModel Step3」をテーマに 6 ステップ前後の改善計画を、
planner.steps 形式で出力してください。

⸻

4. 実装 (Implementation) フェーズ

ここは Git + エディタ 中心（VERITAS スクリプトではなく人間作業）。

cd ~/veritas_clean_test2

# 実験ブランチを切る
git checkout -b feature/worldmodel-step3

# (VSCode / PyCharm / vim などで)
#   - veritas_os/core/world.py
#   - veritas_os/core/kernel.py
#   - docs/*.md
# を編集

# 変更をコミット
git add veritas_os/core/world.py veritas_os/core/kernel.py docs/*
git commit -m "WorldModel step3: causal loop + self-improve wiring"

5. 検証 (Evaluation) フェーズ

5-1. ベンチ再実行（Before/After 比較用）
	•	用途: 変更後の挙動をベンチで計測

cd ~/veritas_clean_test2

# 代表ベンチのみ
python veritas_os/benchmarks/bench.py \
  --bench-id agi_veritas_self_hosting \
  --api-url "$VERITAS_API_URL" \
  --api-key "$VERITAS_API_KEY" \
  --api-secret "$VERITAS_API_SECRET"

# 必要なら全ベンチ
python veritas_os/scripts/run_benchmarks.py \
  --api-url "$VERITAS_API_URL" \
  --api-key "$VERITAS_API_KEY" \
  --api-secret "$VERITAS_API_SECRET"

5-2. ベンチ結果のサマリ生成
	•	用途: Before/After のメトリクス比較を Markdown 化
	•	スクリプト（想定）: veritas_os/scripts/bench_summary.py

cd ~/veritas_clean_test2

python veritas_os/scripts/bench_summary.py \
  --logs-dir veritas_os/scripts/logs \
  --out veritas_os/scripts/logs/bench_summary_worldmodel_step3.md

5-3. doctor_report 再生成（変更後）

cd ~/veritas_clean_test2

python veritas_os/scripts/generate_doctor_report.py \
  --logs-dir veritas_os/scripts/logs \
  --out veritas_os/scripts/logs/doctor_report_after_worldmodel_step3.json

6. ロールバック / 採用 フェーズ

6-1. 採用（良さそうなら）

cd ~/veritas_clean_test2

# main ブランチにマージ
git checkout main
git merge --no-ff feature/worldmodel-step3

# world_state に「成功」として記録する /v1/decide 呼び出し例
python veritas_os/scripts/decide.py \
  --query "WorldModel step3 の変更を採用する。world_state に progress と notes を更新して。" \
  --out veritas_os/scripts/logs/decision_adopt_worldmodel_step3.json

6-2. ロールバック（ダメだった場合）

cd ~/veritas_clean_test2

# ブランチを破棄 or revert
git checkout main
git revert <feature/worldmodel-step3 のマージコミットID>  # or 未マージならブランチ削除

# world_state.json に「rollback」メモだけ残す
python veritas_os/scripts/decide.py \
  --query "WorldModel step3 の変更はロールバックした。world_state の notes に rollback を記録して。" \
  --out veritas_os/scripts/logs/decision_rollback_worldmodel_step3.json

7. オプション: バックアップ・同期系

7-1. ログ＆メモリの Zip バックアップ
	•	スクリプト: veritas_os/scripts/backup_logs.sh

cd ~/veritas_clean_test2

bash veritas_os/scripts/backup_logs.sh

7-2. Google Drive 等への同期（rclone）
	•	スクリプト: veritas_os/scripts/sync_to_drive.sh

cd ~/veritas_clean_test2

bash veritas_os/scripts/sync_to_drive.sh

8. まとめ用ショート版（よく使う順）

# 1) ベンチ & doctor
python veritas_os/benchmarks/bench.py --bench-id agi_veritas_self_hosting ...
python veritas_os/scripts/generate_doctor_report.py ...

# 2) 弱点 → プラン
python veritas_os/scripts/decide.py --query-file ...weakpoints... \
  --input ...doctor_report.json \
  --out ...agi_weakpoints.json

python veritas_os/scripts/decide.py --query-file ...plan_from_weakpoints... \
  --input ...agi_weakpoints.json \
  --out ...plan_*.json \
  --save-md docs/plan_*.md

# 3) 実装（手作業＋git）

# 4) 検証
python veritas_os/benchmarks/bench.py --bench-id agi_veritas_self_hosting ...
python veritas_os/scripts/bench_summary.py ...
python veritas_os/scripts/generate_report.py ...

# 5) 採用 or ロールバック
git merge / git revert
python veritas_os/scripts/decide.py --query "採用/rollback を world_state に記録して" ...



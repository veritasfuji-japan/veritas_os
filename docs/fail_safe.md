# VERITAS Fail-Safe & Rollback 仕様書

Version: 1.0  
Scope: /v1/decide・Self-Improve ループ・bench 実行時の安全設計  
Owner: 藤下 + VERITAS OS  
Status: Draft（Self-Improve 対象）

---

## 1. Overview（目的）

このドキュメントは、VERITAS OS における

- フェイルセーフ（fail-safe）
- ロールバック（rollback）
- メイン系の「壊さないための運用ルール」

を定義する。

目的は 3つ：

1. **バグ / 性能劣化 / リスク増加** が起きたときに、  
   「何を見て」「どう止めて」「どう元に戻すか」を明文化する  
2. Self-Improve ループが暴走せず、  
   **常に main ブランチは「そこそこ安定」** を保つ  
3. 失敗も含めた履歴を **world_state / decision_log / doctor_report** に  
   構造的に残し、次の改善の材料にする

---

## 2. 安全境界と責務

### 2.1 安全境界（Safety Boundary）

VERITAS の「壊したくない境界」を次の3層で定義する：

1. **外部環境**  
   - ファイル破壊、ネットワーク暴走、外部 API への危険な操作 など  
   - → FUJI Gate / セキュリティレイヤで制限（`docs/fuji_gate_safety.md`）

2. **VERITAS プロジェクト自体**  
   - `~/veritas_clean_test2` 以下のコード・ログ・設定  
   - → Git ブランチ運用 + バックアップ + ロールバックルールで保護

3. **藤下本人の生活 / 収益 / 法的リスク**  
   - 危険な自動行動の提案・実行  
   - → FUJI + Self-Improve 制約（人間承認必須）

### 2.2 Fail-Safe の基本方針

- **主語は常に「main ブランチ」**  
  - main が壊れないように、Self-Improve 変更は  
    常に `feature/*` ブランチで行う
- 怪しい変化があったら  
  - 「自動で続行」ではなく  
  - **いったん止めて藤下に聞く**（人間が最終判断）
- ロールバックは  
  - 「Git の状態」 + 「world_state のメモ」  
  - この 2つセットで管理する

---

## 3. 代表的な失敗シナリオ

### 3.1 実行系（Runtime）失敗

- /v1/decide が 500 / 例外を頻繁に出す
- レイテンシが急激に悪化（例: median +50%以上）
- bench 実行が途中でクラッシュする

### 3.2 品質・価値系の劣化

- `value_ema` が継続的に低下する
- 「回答の質」が明らかに落ちる（主観的にも）

### 3.3 安全性（Safety）問題

- FUJI Gate が reject する率が急増
- 危険な提案（法的リスク / 自傷他害系）が増えたと判断される

### 3.4 Data / WorldModel 破損

- `world_state.json` の形式が崩れる / 読めなくなる
- `decision_log.jsonl` が壊れて doctor_report が生成できない

---

## 4. 検知シグナル（Detection Signals）

### 4.1 メトリクスベース（metrics）

`docs/metrics.md` に定義したメトリクスを使う。

例：

- `decision_latency_ms_median`  
  - baseline 比 +50%以上の悪化 → 「要注意」
- `crash_free_rate`  
  - 0.99 未満に低下 → 「安定性に問題」
- `value_ema`  
  - 一定期間（例: 10 decisions）連続で減少 → 「品質劣化の兆候」
- `risk_effective`  
  - 0.3 以上 → 「危険ゾーン」

### 4.2 ログベース

- `veritas_os/scripts/logs/decision_log.jsonl`  
  - 大量の ERROR / EXCEPTION 文字列
- `veritas_os/scripts/logs/bench_*.json`  
  - `status_code != 200`  
  - or `decision_status == "reject"` の急増

### 4.3 doctor_report ベース

- `veritas_os/scripts/logs/doctor_report.json` 内で  
  - `warnings` / `errors` フィールドに  
    「レイテンシ悪化」「crash_free_rate低下」 などが書かれている

→ **観測フェーズ** では、これらをまとめて見て  
「赤信号 / 黄信号 / 青信号」を判断する。

---

## 5. Fail-Safe ポリシー（レベル別）

### 5.1 レベル分類

- **Level 0: 正常**  
  - メトリクスは目標範囲内、警告なし

- **Level 1: 要注意（Warning）**  
  - 軽い劣化・一時的なエラー増加  
  - 例: レイテンシ +20〜50%、value_ema やや低下 など

- **Level 2: 部分停止（Partial Stop）**  
  - 明確な劣化・連続エラー・安全面の懸念  
  - 例: crash_free_rate < 0.99, risk_effective >= 0.3 など

- **Level 3: 緊急停止（Emergency Stop）**  
  - 危険な挙動 / 連続クラッシュ / 外部へのリスク  
  - 例: 危険な自動行動提案が続く、bench がほぼ動かない

### 5.2 レベル別のアクション

#### Level 1: 要注意

- Self-Improve 新サイクルの開始を**一時停止**（様子見）
- `doctor_report.json` に「warning」として記録
- 次のサイクルでは「原因調査」を最優先テーマにする

#### Level 2: 部分停止

- 新しい Self-Improve 変更（feature ブランチ）を中断  
- 直近の変更を優先的に疑う
- 手順：
  1. `git log` で直近コミットを確認
  2. `git checkout <安定していたコミット>` でローカル検証
  3. 必要なら `git revert` 検討
- `/v1/decide` の本番利用は継続しても OK だが、  
  危険なクエリは避ける（FUJI に従う）

#### Level 3: 緊急停止

- `/v1/decide` API の使用を一時停止（サーバーを止める or CLI 側でブロック）
- Self-Improve・bench 系スクリプトの実行を止める
- Git で **直近の変更を完全にロールバック** する

---

## 6. ロールバック手順（Git + WorldModel）

### 6.1 基本パターン

#### パターン A: feature ブランチ未マージ

- 状況: `feature/worldmodel-step3` などを試してみたが、  
  main にまだマージしていない
- 手順:
  ```bash
  git checkout main
  git branch -D feature/worldmodel-step3

	•	world_state 側:
	•	/v1/decide で「実験は採用せずに捨てた」というメモを残す

パターン B: feature ブランチを main にマージ済み
	•	状況: feature/... を main にマージした後で問題が発覚

	•	手順:

git log --oneline
git revert <マージコミットID>

	•	world_state 側:
	•	/v1/decide で
「WorldModel step3 の変更を rollback した」
として notes に経緯を残す

6.2 world_state.json 上での記録

ロールバックを行った場合、world_state.json にも履歴を残す：

"projects": {
  "veritas_agi": {
    "name": "VERITASのAGI化",
    "status": "in_progress",
    "progress": 0.98,
    "decision_count": 250,
    "last_risk": 0.08,
    "notes": "2025-11-19: WorldModel step3 の変更を rollback。原因: latency +60%, crash_free_rate 0.95."
  }
}
	•	ロールバックで progress を少し下げるのもアリ（例: -0.02）
→ 「一歩進んで半歩戻る」のイメージ

⸻

7. doctor_report / Self-Improve との接続

7.1 doctor_report 側の役割
	•	doctor_report.json に、以下の情報を含める：
	•	level（0〜3）
	•	warnings[] / errors[]
	•	代表メトリクスの Before/After
	•	推奨アクション（例: 「ロールバック検討」「原因調査」）

7.2 Self-Improve ループでの扱い
	•	観測フェーズ
	•	最新の doctor_report / metrics を読み、level を判定
	•	解釈フェーズ
	•	level >= 2 の場合は、「新機能の追加」ではなく
「原因調査・暫定対処」をテーマにプラン生成
	•	ロールバック/採用フェーズ
	•	「bench_summary + doctor_report + world_state」を見て、
人間が最終判断する

⸻

8. バックアップ & アーカイブ戦略（簡易）
	•	veritas_os/scripts/backup_logs.sh
	•	logs/ ディレクトリを Zip 化して日付付きで保存
	•	veritas_os/scripts/sync_to_drive.sh
	•	rclone などで Google Drive 等に同期

運用ルール（案）：
	•	Self-Improve ループ 1サイクル完了ごとに
	•	backup_logs.sh → sync_to_drive.sh を実行
	•	緊急事態（Level 3）時は
	•	API 停止 → バックアップ → Git ロールバック
	•	の順で対応する

⸻

9. 運用ルールまとめ（チェックリスト）
	1.	すべての自動改善は feature ブランチで行う
	2.	main へのマージ前に
	•	bench / doctor / metrics を確認し、
「少なくとも悪化していない」ことを確認する
	3.	悪化が見えたら
	•	Self-Improve 新サイクルは止める
	•	原因調査を最優先テーマにする
	4.	重大な劣化や安全懸念があれば
	•	Git でロールバック + world_state にメモ
	5.	重要サイクルの前後では
	•	backup_logs.sh + sync_to_drive.sh を回す


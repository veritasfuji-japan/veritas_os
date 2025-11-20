# VERITAS Decide パイプライン / モジュール間データフロー  
Version: 1.0  
Status: Step2 - module_callflow.md

---

## 1. 全体フロー（/v1/decide）

```mermaid
flowchart LR
    subgraph Client
        U[User / CLI / Bench]
    end

    subgraph API["veritas_os.api.server"]
        R[HTTP /v1/decide<br>Request(JSON)]
        FUJI_PRE[FUJI Gate (pre-check)]
        PLAN[PlannerOS<br>/core/planner.py]
        KERNEL[Decision Kernel<br>/core/kernel.py]
        LLM[OpenAI LLM<br>(DebateOS内部)]
        FUJI_POST[FUJI Gate (post-eval)]
        WORLD[WorldModel.update_from_decision<br>/core/world.py]
        MEM[MemoryOS<br>decision_log.jsonl<br>trust_log.jsonl]
        RESP[HTTP Response<br>JSON]
    end

    U --> R
    R --> FUJI_PRE
    FUJI_PRE --> PLAN
    PLAN --> KERNEL
    KERNEL --> LLM
    LLM --> KERNEL
    KERNEL --> FUJI_POST
    FUJI_POST --> MEM
    FUJI_POST --> WORLD
    MEM --> RESP
    WORLD --> RESP
    FUJI_POST --> RESP

2. 詳細データフロー（フィールドレベル）

2.1 入力〜Planner 〜 Kernel

flowchart TD
    subgraph Input["Input Payload"]
        Ctx[context {...}]
        Q[query (string or object)]
        Opts[alternatives[] (optional)]
    end

    Ctx -->|server で補完| Ctx2[ctx_normalized]
    Q --> Ctx2
    Opts --> Ctx2

    Ctx2 --> FUJI_PRE[FUJI Gate pre_check()]
    FUJI_PRE -->|status, risk, notes| Ctx3[ctx_with_risk]

    Ctx3 --> PLAN[planner.plan()]
    PLAN -->|extras.planner.steps[]| PLAN_STEPS[plan_steps]

    PLAN_STEPS --> KERNEL[kernel.decide()]
    Ctx3 --> KERNEL
    Opts --> KERNEL

    KERNEL -->|chosen, alternatives, evidence, debate, telos_score| DEC[decision_json]

    DEC --> FUJI_POST[FUJI Gate post_evaluate()]
    FUJI_POST -->|risk, decision_status| DEC2[decision_with_gate]

    DEC2 --> MEM[MemoryOS.write_logs()]
    DEC2 --> WORLD[WorldModel.update_from_decision()]

    MEM --> RESP[HTTP Response JSON]
    WORLD --> RESP
    DEC2 --> RESP

2.2 主なフィールド一覧
	•	context:
	•	user_id, session_id, mode, goals, constraints, time_horizon など
	•	planner.steps[]:
	•	id, title, objective, tasks, metrics, risks, done_criteria, dependencies
	•	decision_json（kernel 出力）:
	•	chosen, alternatives, values, evidence, debate, telos_score, fuji, extras
	•	fuji:
	•	status, risk, reasons, violations, modifications, redactions, safe_instructions

⸻

3. WorldModel 周りの因果フロー

flowchart LR
    DEC[decision_with_gate<br>(kernel + planner + fuji)]
    WORLD_LOAD[world._load_state()]
    WORLD_UPD[world.update_from_decision()]
    WORLD_SAVE[world._save_state()]
    SNAP[world.snapshot()<br>next_hint_for_veritas_agi()]

    DEC --> WORLD_LOAD
    WORLD_LOAD --> WORLD_UPD
    WORLD_UPD --> WORLD_SAVE
    WORLD_SAVE --> SNAP

更新される主なフィールド:
	•	projects.veritas_agi.progress
	•	projects.veritas_agi.decision_count
	•	projects.veritas_agi.last_query
	•	projects.veritas_agi.last_risk
	•	projects.veritas_agi.last_plan_steps
	•	meta.last_users[<user_id>]...

⸻

4. Bench 実行時の流れ（bench.py → /v1/decide）

sequenceDiagram
    participant B as bench.py
    participant S as veritas_os.api.server
    participant K as kernel
    participant W as world
    participant M as memory

    B->>S: POST /v1/decide (bench context + query)
    S->>K: decide(context, query, options)
    K->>K: DebateOS / telos / scoring
    K-->>S: decision_json
    S->>W: update_from_decision(...)
    S->>M: write decision_log & trust_log
    S-->>B: response_json (used for bench_summary)

5. 各モジュールの責務（サマリ）
	•	API (server.py)
	•	HTTP /v1/decide を受け取り、context 正規化、FUJI pre/post 呼び出し、レスポンス組み立てを行う。
	•	FUJI Gate
	•	入力・出力の安全性とリスクを評価し、status / risk / modifications を返す。
	•	PlannerOS
	•	context と bench / world_state を元に extras.planner.steps[] を生成する。
	•	Decision Kernel
	•	Planner の plan と LLM(DebateOS)を使って decision_json（chosen + alternatives）を構築する。
	•	DebateOS + LLM
	•	候補案を多面的に評価し、スコアリング・telos 整合度の推定を行う。
	•	WorldModel
	•	decision を元に world_state.json を更新し、プロジェクト進捗やリスクのトレンドを保持する。
	•	MemoryOS
	•	decision_log.jsonl / trust_log.jsonl などに思考ログを保存し、将来の decision の evidence として利用する。
	•	CLI / Bench
	•	人間や自動ベンチマークからの呼び出しフロントエンド。
	•	/v1/decide を叩き、結果をローカルに保存／可視化する。


---
# VERITAS モジュール責務定義（module_responsibilities.md）

Version: 1.0  
Status: Step2 – 自己改善ループ視点の責務定義  
Scope: kernel / planner / memory / world / fuji / debate / api / cli

---

## 1. 全体像

VERITAS は「/v1/decide を中心に回る自己改善ループ」を前提に、  
以下 8 モジュールで構成される：

- **api** … 外部インターフェース（HTTP /v1/decide, /v1/status など）
- **fuji** … 安全性・倫理・リスク評価（FUJI Gate）
- **planner** … マルチステップの意思決定プラン作成
- **kernel** … DebateOS を含む中核の意思決定エンジン
- **debate** … 複数案の比較・対話・評価
- **memory** … decision_log / trust_log などの長期ログ保存
- **world** … world_state.json による中期的な「世界状態」管理
- **cli** … ローカル実行用インターフェース（bench, doctor, sync など）

これらは `/v1/decide` 呼び出しごとに、以下の順で主に作用する：

> api → fuji(pre) → planner → kernel(+debate) → fuji(post) → memory / world → api(respond)

---

## 2. モジュール責務マトリクス（表）

| モジュール | 主な所在 | 主な責務 | 主な入力 | 主な出力 | 永続化・関連ファイル |
|-----------|----------|----------|----------|----------|------------------------|
| **api** | `veritas_os/api/server.py` | HTTP リクエスト受付 / context 正規化 / 各モジュール呼び出しオーケストレーション | HTTP JSON (`context`, `query`, `options`) | HTTP JSON レスポンス（`decision_json` + メタ情報） | なし（ログ永続化は memory / world に委譲） |
| **fuji** | `veritas_os/core/fuji.py` | 入出力の安全性チェック / リスク評価 / 修正指示（modifications / redactions） | 正規化後 context + query + decision | `status`, `risk`, `reasons`, `violations`, `modifications`, `decision_status` | FUJI の結果は decision_json 内 `fuji` フィールドとして保存 |
| **planner** | `veritas_os/core/planner.py` | 自己改善ループ前提の「マルチステップ計画」を生成（extras.planner.steps） | context（goals, constraints, time_horizon, world_state, bench） | `extras.planner.steps[]`（plan ステップ配列） | steps 自体は response / logs に含まれる。二次的に world / memory から参照される |
| **kernel** | `veritas_os/core/kernel.py` | Planner プラン + LLM(DebateOS) を統合し、最終的な `chosen` / `alternatives` を決定 | 正規化 context, planner.steps, options, FUJI pre 情報 | `decision_json`（chosen, alternatives, values, evidence, debate, telos_score, extras） | decision_json は memory / world へ渡されログ化・状態更新される |
| **debate** | `veritas_os/core/debate.py` | 複数候補案の生成・比較・議論・スコアリング | kernel から渡された候補案・評価基準（telos, values） | debate サマリ・スコア・推奨案 | `decision_json.debate` に埋め込まれ、memory ログとして永続化 |
| **memory** | `veritas_os/core/memory.py` + `scripts/logs/` | decision_log / trust_log 等への追記 / 過去決定の検索・要約 | decision_with_gate（FUJI 後の決定 JSON） | ログファイルへの追記 / 将来の decision の evidence として参照 | `scripts/logs/decision_log.jsonl`, `trust_log.jsonl`, 他 |
| **world** | `veritas_os/core/world.py` + `scripts/logs/world_state.json` | 「プロジェクト進捗」「リスクトレンド」など中期世界状態の更新・スナップショット生成 | decision_with_gate（特に values, fuji, extras.world 関連） | `world_state.json` 更新 / `snapshot()` / `next_hint_for_veritas_agi()` | `scripts/logs/world_state.json` |
| **cli** | `veritas_os/scripts/*.py`（bench, bench_plan, doctor, sync など） | ローカルからの /v1/decide 呼び出し, ベンチ実行, ログ集計, GitHub/Drive 同期 | コマンドライン引数 + ローカル JSON ファイル（bench, logs） | ベンチ JSON, タスクプラン JSON, レポート, 各種補助スクリプトの出力 | `scripts/logs/benchmarks/*.json`, `scripts/logs/doctor_report.json`, バックアップ zip など |

---

## 3. 各モジュールの詳細責務

### 3.1 API モジュール（api）

**主な役割**

- `/v1/decide` エンドポイントを公開
- HTTP リクエストから `context`, `query`, `options` を抽出
- デフォルト値補完・フォーマット正規化（`ctx_normalized`）  
- FUJI pre / planner / kernel / FUJI post / memory / world を正しい順番で呼び出す
- 例外ハンドリング・エラーコード・HTTP レスポンスの組み立て

**自己改善ループにおける役割**

- ループの入り口と出口を一元管理する「ゲートウェイ」
- 外部（人間 / bench / CLI）と内部 (kernel/planner/…) の境界レイヤー
- API レベルでのバージョン管理・後方互換性の担保

---

### 3.2 FUJI Gate（fuji）

**主な役割**

- **pre_check**:
  - 入力 query / context のリスク評価（違法・高リスク・ポリシー違反の検知）
  - 必要に応じて redaction / modifications / safe_instructions を付与
- **post_evaluate**:
  - kernel + debate + planner が生成した `decision_json` 全体を評価
  - `risk`, `decision_status`, `violations` を付与し、必要なら修正・ブロック

**自己改善ループにおける役割**

- 「危険な方向への自己改善」を抑制する **安全バリア**
- Telos / ValueCore と連携し、「価値の逸脱」「偏りの強化」を早期検知する
- 将来的には world_state のリスクトレンドとも連携し、  
  長期的なバイアスやドリフトを検出する役割も担う

---

### 3.3 PlannerOS（planner）

**主な役割**

- `context.goals`, `constraints`, `world_state`, `bench` などを入力に、
  `extras.planner.steps[]` を生成する
- 各 step は以下を含む：
  - `id`, `title`, `objective`, `tasks`, `metrics`, `risks`, `done_criteria`, `dependencies`
- Bench 実行時は、ベンチの要求仕様（success_criteria など）も踏まえてプランを拡張

**自己改善ループにおける役割**

- 「観測→解釈→設計→実装→検証→ロールバック」という  
  **自己改善サイクルの骨格** を定義する
- world_state の `projects.veritas_agi.progress` と整合した  
  中期ロードマップを作る「計画レイヤー」
- bench_plan.py などから呼ばれ、**具体的なコード変更タスク** へのブリッジになる

---

### 3.4 Decision Kernel（kernel）

**主な役割**

- planner.steps, context, options を受け取り、  
  DebateOS + LLM を用いて候補案を展開
- Telos（価値観）、ValueCore、FUJI 情報を踏まえつつ、
  `chosen` / `alternatives` / `values` / `evidence` / `debate` を組み立てる
- 「1 回の /v1/decide 呼び出しに対する最終的な意思決定」を行う

**自己改善ループにおける役割**

- ループ内の「実際の思考と選択」の中心
- Planner が定義したステップ構造の上で、
  各ステップの具体的なアクション案を評価・選択する
- 出力された decision_json は memory / world で再利用され、
  次回以降の decision を間接的に変えていく

---

### 3.5 DebateOS（debate）

**主な役割**

- 複数の候補（戦略・回答・計画）を生成・比較
- 立場の異なるエージェント風の視点で pros/cons を議論
- 合意案 / 推奨案を `debate` セクションとして kernel に返す

**自己改善ループにおける役割**

- 「自己批判」「反対意見」「代替案」を内蔵することで、  
  単純な greediness（局所最適）を避ける
- 長期的には：
  - world_state 上の progress / risk を参照し、
  - 「今は攻めるフェーズか / 守るフェーズか」などの判断を補強する役割へ拡張可能

---

### 3.6 MemoryOS（memory）

**主な役割**

- `decision_log.jsonl` / `trust_log.jsonl` などへの追記：
  - 各 /v1/decide の decision_json
  - FUJI 結果
  - 実際に「採用された or ロールバックされた」履歴
- 必要に応じて：
  - 過去 decision の検索・要約
  - 信頼度（trust）や ValueCore の drift の観測

**自己改善ループにおける役割**

- 「長期記憶」レイヤーとして、  
  数百〜数千回レベルの decision 履歴を保持
- Doctor / bench / world_state 更新の際の evidence ソースになる：
  - doctor_report の根拠
  - bench のメトリクス（成功率, error rate, latency トレンド）算出の土台

---

### 3.7 WorldModel（world）

**主な役割**

- `world_state.json` の読み込み・更新・スナップショット生成
- プロジェクト単位の状態管理：
  - `projects.veritas_agi.progress`
  - `decision_count`, `last_risk`, `latency_ms_median` など
- `next_hint_for_veritas_agi()` による「次の一手」候補の生成

**自己改善ループにおける役割**

- MemoryOS が「ログの海」だとすると、  
  WorldModel は **「要約された世界状態」** を持つ
- Planner は WorldModel を入力にして「今どのフェーズか？」を判断し、  
  ステップを変える（実装フェーズ / 安全強化フェーズ / 検証フェーズ など）
- これにより、VERITAS は「進捗とリスクに応じて戦略を変える」  
  中期的 AGI 研究 OS として振る舞える

---

### 3.8 CLI / Scripts（cli）

**主な役割**

- `bench.py` / `run_benchmarks.py`：
  - ベンチ YAML を読み /v1/decide を叩き、結果 JSON を保存
- `bench_plan.py`：
  - bench + world_state + doctor_report を入力に `planner.generate_code_tasks()` を呼び、
    「具体的コード変更タスク JSON」を生成
- `doctor.py` / `generate_report.py`：
  - ログから doctor_report を生成し、システムの健康状態を可視化
- `sync_to_drive.sh` / backup スクリプト：
  - ログ / レポート / world_state のバックアップ・スナップショットを作成

**自己改善ループにおける役割**

- 人間（藤下）が「レビューすべき単位」にまとめてくれるレイヤー：
  - ベンチ結果 → タスクリスト
  - ログ → doctor_report
  - 状態 → zip バックアップ
- 自動ループと人間レビューの間に入る「実務用ツール群」として機能

---

## 4. モジュール間の責務境界（簡易ルール）

- **api はロジックを持たない**  
  → 安全判断・計画・推論・状態更新は、必ず各 core モジュールに委譲する。

- **fuji は「可否」と「修正」だけを返す**  
  → 具体的な改善プランや実装案は planner / kernel 側の責務。

- **planner は「計画」を返し、「選択」はしない**  
  → 具体的にどの案を採用するかは kernel + debate 側の責務。

- **kernel は「1 回の decision の責任者」**  
  → ただし長期進捗の管理（進捗率やステージ遷移）は world が担当。

- **memory は「すべての決定の証拠保全」**  
  → 解釈・要約・ステージ判断は world / doctor / planner 側。

- **world は「プロジェクト状態の単一ソース・オブ・トゥルース」**  
  → 「今どこまで来たか？」の最終回答は world_state を見る。

- **cli は「人間が触る窓」であり、ビジネスロジックは持たない**  
  → あくまで API / core モジュールを安全に叩くためのラッパ。

---

## 5. 今後の拡張余地（Step3〜5 での改善フック）

- planner / world 間のフィードバック強化：
  - world_state に基づく「自動マイルストーン更新」
- fuji / world 連携：
  - 長期リスクのトレンドを見た「フェーズ変更警告」
- memory / doctor / bench の統合ダッシュボード：
  - 「決定品質」「安全性」「進捗」の 3 軸モニタリング

これらは Step3 「自己改善ループのフェーズ設計」と  
Step5 「フェイルセーフとロールバック戦略」で具体化される。

---

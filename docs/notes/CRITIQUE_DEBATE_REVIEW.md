# Critique & Debate モジュール レビュー

**レビュー日**: 2026-04-06
**対象バージョン**: critique v2.1.1 / debate v3 (safety_valve)
**レビュー対象ファイル**:

- `veritas_os/core/critique.py` (602行)
- `veritas_os/core/debate.py` (898行)
- `veritas_os/core/pipeline/pipeline_critique.py` (434行)
- `veritas_os/core/types.py` (型定義)

---

## 1. Critique モジュール (`core/critique.py`)

### 良い点

- 8種類のルールベース分析（根拠不足、信頼性、リスク、複雑度、価値、実現可能性、タイムライン、リスク/価値バランス）が網羅的
- `analyze()` (生リスト) と `analyze_dict()` (dict契約) の二層API設計は互換性と安全性のバランスが良い
- `_as_float`, `_as_non_negative_int` 等の防御的パース、`bool` 除外チェック (`not isinstance(risk, bool)`) が丁寧
- `_MAX_MIN_ITEMS = 100` でメモリ枯渇防止

### 改善候補

| # | 箇所 | 内容 | 優先度 |
|---|------|------|--------|
| C-1 | `_severity_rank` / `_norm_severity` | 両方 severity を解釈するが役割が微妙に異なる。同じ文字列マッピングを2箇所で管理している。定数テーブルの共通化で保守性向上 | 低 |
| C-2 | L328 `risk * 100.0` | `value == 0` 時のゼロ除算回避で `risk * 100.0` としているが、マジックナンバーの根拠が不明。閾値次第で誤検知しうる | 中 |
| C-3 | `ensure_min_items` | `_DEFAULT_PAD_CRITIQUES` が3件のみ。`min_items > 3` で同一項目が重複する（`i % len(...)` で循環）。パッド重複を許容する意図を明示すべき | 低 |

---

## 2. Debate モジュール (`core/debate.py`)

### 良い点

- 3段階フォールバック（normal -> degraded -> safe_fallback）で堅牢
- ハードブロック (`_is_hard_blocked`) + 危険テキスト検出 (`_looks_dangerous_text`) + verdict正規化の多重安全弁
- `_safe_json_extract_like` のJSON救出が非常に強力（fenceブロック除去 -> brace抽出 -> 末尾削り -> options配列部分回収）
- ペイロードサイズ制限 (`MAX_OPTIONS_PAYLOAD_BYTES`, `MAX_JSON_NESTED_DEPTH`) によるDoS対策

### 改善候補

| # | 箇所 | 内容 | 優先度 |
|---|------|------|--------|
| D-1 | `_looks_dangerous_text` | `"virus"`, `"drugs"`, `"hacking"` 等は正当な文脈（サイバーセキュリティ、医療、ゲーム等）でも出現する。false positive でフォールバックに落ちるリスクあり。コンテキスト考慮やホワイトリスト機構の検討を推奨 | 高 |
| D-2 | `_calc_risk_delta` | `safety_view` に「リスク」が含まれるだけで +0.08 される。「リスクなし」「リスク低減済み」等のポジティブ文脈でも加算される。否定表現の除外ロジックが部分的（`"問題なし"`, `"安全"` のみ）で不十分 | 高 |
| D-3 | L884 `source: "openai_llm"` | LLMバックエンド名がハードコード。`llm_client` のメタ情報から取得するか定数化すべき | 低 |
| D-4 | `_safe_json_extract_like` 内のネスト関数群 | `_truncate_string`, `_validate_option`, `_sanitize_options`, `_extract_objects_from_array` 等がすべて関数内関数。テスト容易性のためにモジュールレベルに引き上げるか別ユーティリティに分離推奨 | 中 |
| D-5 | 末尾削りループ (L486-496) | `attempts >= 50` で打ち切るが、巨大JSONの場合パフォーマンスに影響しうる。打ち切り時のログ出力を追加すべき | 低 |

---

## 3. Pipeline Critique (`core/pipeline/pipeline_critique.py`)

### 良い点

- critique が何であっても必ず `dict + findings >= 3` の契約を保証する設計
- `_normalize_critique_payload` が `list / dict / str / None` すべてを受け入れる堅牢性
- メトリクス (`critique_findings_count`, `critique_ok`) とdegradedフラグの自動設定

### 改善候補

| # | 箇所 | 内容 | 優先度 |
|---|------|------|--------|
| P-1 | `_pad_findings` (L63-143) | findings を正規化した後、再度全件を走査して必須キーを保証する二重正規化。一度で完結させた方が効率的 | 低 |
| P-2 | `_run_critique_best_effort` | `async` 宣言だが内部は同期処理のみ（`await` なし）。将来のLLMベースcritique追加の準備であればコメントを追加すべき | 中 |

---

## 4. 型定義の乖離 (`core/types.py`)

| # | 問題 | 詳細 | 優先度 |
|---|------|------|--------|
| T-1 | `CritiquePoint.severity` | 型定義: `Literal["low", "medium", "high"]` / 実装: `"low" \| "med" \| "high"` -- **`"medium"` vs `"med"` の不一致** | 高 |
| T-2 | `DebateViewpoint.role` | 型定義: `Literal["pro", "con", "third_party", "synthesizer"]` / 実装: `Architect / Critic / Safety / Judge` -- **型と実装が乖離** | 高 |

---

## 5. 総合評価

| 観点 | 評価 | コメント |
|------|------|---------|
| 堅牢性・フォールバック | A | 多段フォールバック、例外を出さない設計 |
| 安全性 | B+ | ハードブロック+危険テキスト検出+ペイロード制限。ただし誤検知リスクあり |
| テスト容易性 | B- | ネスト関数が多く単体テストしづらい箇所あり |
| 型の一貫性 | C | types.py と実装間に乖離あり |
| 保守性 | B | キーワードベースの判定はスケールしにくい |

---

## 6. 推奨アクション（優先度順）

1. **[高] T-1/T-2**: `types.py` の `CritiquePoint` / `DebateViewpoint` を実装に合わせて修正
2. **[高] D-2**: `_calc_risk_delta` の否定表現（「リスクなし」等）誤検知を修正
3. **[高] D-1**: `_looks_dangerous_text` にコンテキスト考慮 or ホワイトリスト導入
4. **[中] D-4**: `_safe_json_extract_like` 内のネスト関数をモジュールレベルに引き上げ
5. **[中] P-2**: `_run_critique_best_effort` の async 意図をコメントで明示
6. **[中] C-2**: リスク/価値バランスのゼロ除算回避ロジック見直し

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


---

## 7. 実施ログ（2026-04-06 更新）

優先度順に、以下を実装済み。

1. **[高][完了] T-1/T-2 型定義の乖離修正**
   - `CritiquePoint.severity` を `"low" | "med" | "medium" | "high"` に拡張し、実装互換性を確保。
   - `DebateViewpoint.role` を実装上の `Architect/Critic/Safety/Judge` を含む Literal に拡張。

2. **[高][完了] D-2 `_calc_risk_delta` の否定表現誤検知を修正**
   - `_is_keyword_negated()` を追加し、`「リスクなし」「問題なし」「違反なし」` 等の否定文脈ではリスク加算を抑制。
   - 従来どおり、実際のリスク表現（重大/違反/深刻）では加算されることを維持。

3. **[高][完了] D-1 `_looks_dangerous_text` の文脈考慮導入**
   - 防御的・教育的文脈（対策/予防/セキュリティ/training 等）を benign context として導入。
   - ただし `「爆弾の作り方」` や `"how to make ..."` など明示的有害意図パターンは強制ブロック。

4. **[低〜中][完了] D-3 メタ情報の定数化**
   - `source: "openai_llm"` を `DEBATE_SOURCE_OPENAI` に定数化。

5. **[テスト追加][完了] Debate 安全ヒューリスティクスの単体テスト追加**
   - benign context false positive 抑制
   - 明示的有害意図のブロック継続
   - risk negation の加算抑制
   - 実リスクでの加算維持

6. **[中][完了] D-4 `_safe_json_extract_like` のネスト関数をモジュールレベルへ分離**
   - `_truncate_string` / `_validate_option` / `_sanitize_options` / `_extract_objects_from_array` をトップレベル化。
   - 目的: 単体テスト容易性と責務分離を改善し、JSON救出ロジックの追跡性を向上。

7. **[中][完了] P-2 `_run_critique_best_effort` の async 意図を明文化**
   - 現在は同期処理中心であること、将来の非同期 Critique 実装差し替えのために async 契約を維持していることを docstring に追記。

8. **[中][完了] C-2 リスク/価値ゼロ除算回避ロジックの明確化**
   - `risk * 100.0` を廃止し、`value_floor=0.01` を使う有界比率 (`risk / max(value, 0.01)`) に変更。
   - マジックナンバーの意味を `value_floor` として `details` に露出し、監査性を向上。

9. **[テスト追加][完了] JSON救出とリスク/価値比率の単体テスト追加**
   - 破損JSONからの options 救出（不正scoreの除外を含む）
   - 深すぎるネストの除外
   - value=0 時の有限比率保証

10. **[中][完了] P-1 `_pad_findings` の二重正規化を単一パス化**
   - `pipeline_critique.py` に `_normalize_finding_item()` を追加し、1件ごとの正規化責務を分離。
   - `_pad_findings()` は `list/dict/other` それぞれで同ヘルパーを再利用し、再走査なしで `min_items` パディングまで完了する構成へ変更。
   - 期待効果: 可読性・テスト容易性の向上、不要な2回目走査の削減。

11. **[低][完了] C-1 severity マッピングの共通化**
   - `critique.py` に `_SEVERITY_ALIASES` を追加し、`_norm_severity` と `_severity_rank` で同一テーブルを利用。
   - これにより `"medium"`/`"critical"` など同義語追加時のメンテナンスポイントを1箇所へ集約。

12. **[テスト追加][完了] Pipeline Critique 正規化の単体テスト追加**
   - `_normalize_finding_item()` の alias 入力（`issue`/raw `details`/非文字 `fix`）の正規化を検証。
   - `_pad_findings()` が入力項目とデフォルト項目の双方で canonical schema を維持することを検証。

13. **[高][完了] D-1 追加強化: benign 語の混入による回避耐性を向上**
   - `_looks_dangerous_text()` に actionable intent パターン（`deploy/distribute/execute/weaponize`、`実行/配布/悪用` など）を追加。
   - これにより `training/教育` など benign context が共存しても、攻撃実行意図を含むテキストはブロック継続。
   - 単体テストを追加し、`"教育目的"` と `"malware deploy"` の同居ケースを危険判定することを確認。

14. **[高][完了] D-2 追加強化: 英単語リスク語の部分一致誤検知を抑制**
   - `_calc_risk_delta()` の英語キーワード評価を単純な部分一致から、語境界付きパターン判定へ変更。
   - 例: 従来は `ban` が `bank` に誤一致しうるが、今回の変更で単語 `ban` のみを加点対象に限定。
   - 既存の否定語判定（`no risk`, `safe` など）との併用を維持しつつ、不要なリスク加算を低減。
   - 単体テストを追加し、`"Bank transfer ... No risk"` 文脈で負方向（安全寄り）デルタを維持することを確認。

15. **[低][完了] C-3 追加強化: `ensure_min_items` の重複パディング意図を監査可能化**
   - `min_items > len(_DEFAULT_PAD_CRITIQUES)` の場合にテンプレート循環再利用される仕様を docstring に明記。
   - 再利用パディング項目には `details.pad_reused=True` と `details.pad_cycle_index` を付与し、監査ログ上で「重複由来」を判別可能にした。
   - 単体テストを追加し、4件目以降のパディング項目に再利用メタデータが入ることを検証。

16. **[高][完了] D-1 追加強化: instructional cue（手順/コード提示）を危険意図として優先ブロック**
   - `_looks_dangerous_text()` に `_INSTRUCTIONAL_CUE_PATTERNS` を追加。
   - `教育/研究/training` など benign context が同居していても、`「ハッキングの手順」「malware script/tutorial」` のような**実行可能性を高める説明**を含む場合は危険判定を優先。
   - 単体テストを追加し、`研究/教育` を含む文面でも「具体的手順+コード+危険語」の同居ケースがブロックされることを確認。

17. **[低][完了] D-5 末尾削りループの監視ログを強化**
   - `_safe_json_extract_like()` の tail-trim retry cap を `TAIL_TRIM_RETRY_CAP` 定数化し、運用調整時の可視性を改善。
   - 打ち切り時ログに `attempts/cap/candidate_endings/payload_bytes` を追加し、巨大入力や異常フォーマット時の解析容易性を向上。
   - 単体テストを追加し、retry cap 到達時に warning ログが出ることを検証。

18. **[高][完了] D-1 追加強化: weak benign ラベル単体での危険判定回避を禁止**
   - `_contains_benign_context()` を強化し、`training/教育/研究` などの **弱い benign 語のみ** では安全文脈と見なさない仕様へ変更。
   - `対策/防止/検知/security/defensive` などの **防御シグナル（strong term）** が同時にある場合のみ benign 文脈として許可。
   - 単体テストを追加し、`"training material + malware"` のような弱ラベル偽装ケースが危険判定されることを確認。

### セキュリティ注意（実装時点）

- benign context の導入により false positive は低減される一方、**攻撃者が安全語を混ぜて回避を試みるリスク**がある。
- そのため、明示的有害意図パターンは優先的に評価し、検出時は benign 判定より強くブロックする設計とした。
- さらに actionable intent（実行/配布/悪用、deploy/distribute など）を危険意図として上位評価し、**安全語付きプロンプトでのすり抜け耐性**を補強した。
- あわせて instructional cue（手順/チュートリアル/コード提示）を危険意図として上位評価し、**「教育目的」を偽装した実行可能情報の提供リスク**を低減した。
- さらに weak benign 語（`training/教育/研究` など）単体では免責しないようにし、**安全語を添えた回避プロンプト**への耐性を強化した。
- 追加で、将来的には FUJI 側の判定結果・ユーザー意図分類・監査ログ相関で多層化することを推奨。
- JSON救出ロジックは防御的だが、**巨大入力によるCPU/メモリ負荷リスク**は依然として存在する。`MAX_OPTIONS_PAYLOAD_BYTES` / `MAX_JSON_NESTED_DEPTH` / tail-trim retry cap ログを継続監視すること。
- 英語キーワードの誤検知（`ban` vs `bank` など）は軽減したが、**スラング・難読化・多言語混在の回避表現**は依然として残存リスク。辞書運用と監査ログの定期レビューを継続すること。

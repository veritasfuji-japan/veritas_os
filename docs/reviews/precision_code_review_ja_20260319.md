# VERITAS OS Precision Code Review フォローアップ（2026-03-19）

## 前提

- 指定された `docs/reviews/precision_code_review_ja_20260319.md` は作業開始時点で未存在だった。
- そのため、既存の最新レビュー群（特に `docs/reviews/technical_dd_review_ja_20260315.md` と `docs/reviews/CODE_REVIEW_CONSISTENCY_2026_03_15_JP.md`）を起点に、**高優先度かつ未解消で、責務境界を越えない項目だけ**を再確認した。

## 優先度判断

今回の再点検では、既存レビュー中の Critical / High の多くが既に解消済みだった。未解消かつ実害が大きい候補として、以下を最優先と判断した。

1. **NaN / Inf による gate 数値汚染**
   - `pipeline_policy` は FUJI risk / EMA / Debate risk delta を受け取り、最終 gate 判定に反映する。
   - `NaN` が混入すると比較・clamp が壊れ、安全判定や学習量が不安定になる。
   - Planner / Kernel / Fuji / MemoryOS の責務越境なしで、`pipeline_policy` 内に局所修正できる。

## 実施した改善

### P1: `pipeline_policy` の非有限数 fail-closed 化

- `_coerce_finite_probability()` を追加し、`NaN` / `Inf` / 型不正値を `0.0〜1.0` の有限値へ正規化するようにした。
- FUJI precheck の `risk` 表示用値を同ヘルパーへ統一した。
- `stage_value_core()` で:
  - `value_ema` の `NaN` を安全既定値 `0.5` へ補正。
  - `fuji_dict["risk"]` の `NaN` / `Inf` を **fail-closed で `1.0`** として扱うよう修正。
  - `effective_risk` も再度有限値検証してから利用するよう修正。
- `stage_gate_decision()` で:
  - Debate 由来の `risk_delta` が `NaN` / `Inf` の場合は無効化。
  - マージ後 `risk` / `effective_risk` も有限値検証を通すよう修正。

## 無駄な改善をしなかった理由

- 暗号化バイパスや TrustLog 強制など、既存レビューで挙がっていたより重い問題は、現コードでは既に fail-closed 実装済みだったため再改修していない。
- `pipeline.py` や `fuji.py` 全域への広範な例外整理は、今回の未解消 P1 論点より効果が薄く、変更面積も大きいため見送った。
- 責務境界維持のため、Planner / Kernel / Fuji / MemoryOS には横断的修正を入れていない。

## テスト

- `stage_value_core()` に対し、`ema="nan"` と `risk="nan"` が入っても `value_ema=0.5`、`effective_risk` が fail-closed 側へ倒れる回帰テストを追加。
- `stage_gate_decision()` に対し、Debate の `risk_delta="nan"` が無視され、既存 risk を汚染しないことを確認する回帰テストを追加。

## セキュリティ警告

- **警告**: この修正は「非有限数の混入」に対する fail-closed 強化であり、入力値そのものの真正性を保証するものではない。
- 外部入力や replay データを受け取る経路では、引き続きソース検証・署名検証・監査ログ確認を併用すべき。

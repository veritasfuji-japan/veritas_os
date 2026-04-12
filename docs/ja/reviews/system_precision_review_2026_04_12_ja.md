# システム精密レビュー（2026-04-12）

## 1. レビュー概要
- 実施日: 2026-04-12 (UTC)
- 対象: `veritas_os` コア、品質/セキュリティ検査スクリプト、責務境界の整合性
- 目的: 現行システムの実運用観点（責務境界・安全性・回帰耐性）を精密確認し、優先改善項目を明確化する

## 2. 実施した検証コマンド（再現可能）
1. `python scripts/architecture/check_responsibility_boundaries.py`
2. `python scripts/security/check_bare_except_usage.py`
3. `pytest -q veritas_os/tests/test_responsibility_boundaries.py`
4. `python -m pytest -q veritas_os/tests/test_responsibility_boundary_checker.py`
5. `rg -n "TODO|FIXME|HACK|XXX" veritas_os scripts frontend/app frontend/lib | head -n 120`
6. `rg -n "subprocess\\.|os\\.system\\(|shell=True|pickle|yaml\\.load\\(|eval\\(|exec\\(" veritas_os scripts | head -n 200`

## 3. 総合評価（結論）
- **責務境界の静的検証は合格**（Planner / Kernel / Fuji / MemoryOS の越境を抑止するガードが稼働）。
- **責務境界関連テストは全件パス**（5件 + 30件）。
- **`bare except` は未検出**で、例外ハンドリング品質は最低ラインを満たす。
- 一方で、運用スクリプト群には `subprocess` 利用箇所が一定数存在し、設定不備時の運用リスク（コマンド実行面）に注意が必要。
- また `TODO` が一部テスト内に残っており、設計意図としては妥当でも「未実装項目の可視化・期限管理」を強化すべき。

## 4. ドメイン別レビュー

### 4.1 責務境界（Planner / Kernel / Fuji / MemoryOS）
- 境界チェッカーが **passed** を返しており、現時点のコードベースは責務定義違反を検出していない。
- `test_responsibility_boundaries.py` と `test_responsibility_boundary_checker.py` がともに成功し、境界仕様とチェッカー実装の回帰耐性は高い。
- 結論: **「責務を越える変更禁止」という運用ルールに対する技術的ガードは有効**。

### 4.2 セキュリティ
- `bare except` は 0 件で、障害隠蔽リスクは低い。
- ランタイム pickle 廃止方針はコード・検査スクリプト双方で維持されている。
- ただし `subprocess` 呼び出しは複数箇所に存在するため、引数固定・タイムアウト・監査ログの継続運用が前提。

#### セキュリティ警告（必読）
1. **運用スクリプトのコマンド実行面**
   - 事実: レポート生成/ヘルスチェック系で `subprocess` が利用される。
   - リスク: 実行環境変数やコマンド引数の取り回しを誤ると、意図しない実行フローを許す可能性。
   - 推奨: `shell=False` の強制、許可コマンドの明示 allowlist、タイムアウトの標準化、失敗時の監査イベント統一。
2. **pickle 移行CLIの限定的残存リスク**
   - 事実: オフライン移行用途として restricted unpickler を使うコードが存在。
   - リスク: 運用手順逸脱（本番経路で誤用）時に攻撃面が拡大し得る。
   - 推奨: CI で「移行CLIは本番起動経路から参照不可」を継続検証し、Runbook でも分離を明文化。

### 4.3 品質・保守性
- TODO 系コメントは主にテスト/説明文脈に偏在し、直ちに本番障害へ直結する内容は限定的。
- ただし長期では「未実装だが既知のギャップ」が蓄積するため、優先度ラベル付きの backlog 管理へ接続することを推奨。

## 5. 優先度付きアクション

### P0（即時）
- `subprocess` 利用箇所に対する **統一セキュリティ・チェックリスト** をリポジトリ規約へ昇格。

### P1（短期）
- TODO（特に backend contract 系）を issue 化し、期限とオーナーを設定。
- pytest-asyncio の deprecation warning（loop scope 未設定）を明示設定で解消し、将来の挙動変化を予防。

### P2（中期）
- 責務境界チェッカー結果をリリースゲートへ強制連結（必須チェック化）し、運用例外をゼロ化。

## 6. 最終判定
- 現行システムは、**責務境界と基本セキュリティ規律を高い水準で維持**している。
- ただし、運用スクリプトに内在するコマンド実行面のリスク管理を継続強化しない場合、将来的な設定事故や運用逸脱が主要リスクとなる。
- よって判定は **「運用可能（条件付き）」**。条件は「subprocess 統制の標準化」と「既知 TODO の計画的解消」。

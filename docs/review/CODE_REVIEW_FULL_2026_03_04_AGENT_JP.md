# CODE REVIEW FULL (2026-03-04, Agent)

## 対象
- リポジトリ全体（backend / frontend / scripts / packages）
- 重点: Planner / Kernel / Fuji / MemoryOS の責務境界、テスト健全性、既知セキュリティチェック

## 実行したチェック
1. `python scripts/architecture/check_responsibility_boundaries.py`
2. `python scripts/security/check_next_public_key_exposure.py`
3. `pytest -q`

## 結果サマリ
- 責務境界チェック: **PASS**
- Next.js 公開環境変数の秘密情報露出チェック: **PASS**
- テスト: **2692 passed, 3 skipped**

## 指摘事項（重要度順）

### 1) Startup 設定検証失敗時に起動継続する挙動（中〜高）
- `startup` フック内の設定検証で例外を包括捕捉し、warning ログのみで継続している。
- 誤設定状態でAPIが起動し続けると、認証・監査・通信設定の意図しない緩和に気づきにくくなる。
- 推奨:
  - 本番 (`VERITAS_ENV=prod`) では fail-fast（例外再送出）を標準化。
  - dev/stg のみ warning 継続を許可する運用分岐を明示。

### 2) FastAPI `on_event` の非推奨API利用（中）
- `@app.on_event("startup"|"shutdown")` は FastAPI の lifespan 移行対象。
- 直近は動作するが、中長期で保守・互換性リスク。
- 推奨:
  - `lifespan` コンテキストへ移行し、起動/停止処理を一本化。

## セキュリティ観点
- 既存の自動チェックでは秘密情報露出の重大問題は未検出。
- ただし上記「設定検証失敗時の起動継続」は**運用時セキュリティリスク**として監視対象にすべき。

## 総評
- テスト網羅と自動チェックの健全性は高い。
- 一方で、起動ライフサイクルの fail-safe 設計と非推奨APIの解消は、次リリースで優先的に改善する価値がある。

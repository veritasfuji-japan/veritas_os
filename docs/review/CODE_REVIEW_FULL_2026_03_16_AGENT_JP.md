# VERITAS OS 完成度レビュー（バックエンド + フロントエンド全体）

- 日付: 2026-03-16
- レビュー方法:
  - バックエンド (`veritas_os/**/*.py`) とフロントエンド (`frontend/**/*.ts`, `frontend/**/*.tsx`) の全ファイルを機械走査
  - コア責務ファイル（Planner/Kernel/Fuji/MemoryOS, API/BFF, Middleware）を精読
  - 自動テストとセキュリティ/責務境界チェッカーを実行

---

## エグゼクティブサマリー

**総合完成度: 86/100（実運用直前レベル）**

- **バックエンド: 87/100**
  - 3789 tests pass の土台は非常に強い
  - Pipeline/FUJI/Memory/監査ログ/Replay が実装済み
  - 一方で `api/server.py`, `core/memory.py`, `core/fuji.py` の巨大化が継続しており、保守性と変更リスクを押し上げている
- **フロントエンド: 84/100**
  - 140 tests pass、BFF + CSP + trace_id の防御設計は良い
  - 主要画面（Console/Audit/Governance/Risk）が機能単位で揃っている
  - ただし CSP が互換モードでは `unsafe-inline` を残しており、厳格運用はフラグ依存

---

## 根拠（コードベース事実）

1. プロジェクトは「In Development」ステータスで明示。README でも「production-approaching governance infrastructure」と位置付け。  
2. パイプラインは責務分離モジュール群（inputs/execute/policy/response/persist/replay）へ分割済みで、単一エントリポイントを維持。  
3. FUJI は deny/hold/allow の不変条件と fail-closed 的思想をコメントで明示し、実装上も安全寄り。  
4. MemoryOS は pickle 実行をランタイムでブロックし、RCEリスクを警告する設計。  
5. フロントエンド BFF で API キーをサーバ側に閉じ、経路制限・ロール制御・body size 制限・trace_id 伝搬を実装。  
6. Middleware は CSP nonce 配布・httpOnly BFF cookie・各種セキュリティヘッダを実装。  
7. Planner / Kernel / Fuji / MemoryOS の責務境界チェックが専用スクリプトで維持され、レビュー時実行でも pass。

---

## セキュリティ評価（必須警告を含む）

### 良い点
- BFF で API 秘密情報がブラウザへ露出しにくい設計
- Memory の pickle 廃止方針がコードで強制
- リスクの高い subprocess shell / raw upload / public key exposure / runtime pickle を専用スクリプトで検査可能

### 警告（運用上の注意）
1. **Auth store failure mode を `open` にすると、nonce登録失敗時に通過する設計が存在**。本番では `closed` 固定が望ましい。  
2. **CSP はデフォルト互換モードで `unsafe-inline` を残すため、厳格なXSS耐性は nonce 強制フラグ依存**。段階導入後は strict 常時化を推奨。  
3. **BFF が `NEXT_PUBLIC_VERITAS_API_BASE_URL` をフォールバック参照**するため、運用ミスで公開側環境変数に内部構成を載せる余地がある。`VERITAS_API_BASE_URL` 専用運用へ寄せると安全。

---

## 完成度内訳（5段階）

- 機能網羅性: **4.5/5**
- 品質保証（テスト）: **5.0/5**
- セキュリティ基盤: **4.0/5**
- 保守性/可読性: **3.5/5**
- 運用準備（監査/可観測性/ガバナンス）: **4.5/5**

---

## 優先度つき改善提案（責務境界を越えない範囲）

### P0（直近）
- `VERITAS_AUTH_STORE_FAILURE_MODE` を本番プロファイルで `closed` 強制
- `VERITAS_CSP_ENFORCE_NONCE=true` の本番既定化（互換検証完了後）
- `NEXT_PUBLIC_VERITAS_API_BASE_URL` 依存を運用ガイドで禁止

### P1（次スプリント）
- `api/server.py` の機能分割（ルータ層・監査層・ヘルス/メトリクス層）
- `core/memory.py` / `core/fuji.py` のサブモジュール化をさらに進める

### P2（継続改善）
- フロントE2E（Playwright）を CI 標準ゲートへ強化
- 既存の豊富なレビュー文書群を「最新1本 + 変更差分」に再編成し、運用判断を簡素化

---

## 結論

VERITAS OS は、**監査可能性・安全ゲート・再現性・ガバナンス UI** の主要要件が実装済みで、テスト密度も高い。現時点の完成度は「実運用直前」だが、

- Auth failure fail-open 設定余地の封じ込み
- CSP strict 化
- 巨大モジュールの分割による変更安全性向上

を完了すれば、運用品質はさらに安定する。

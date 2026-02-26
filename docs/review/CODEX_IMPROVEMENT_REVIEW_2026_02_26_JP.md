# CODEX 改善再レビュー（2026-02-26, JP）

## 結論

前回（2026-02-25）の改善提案に対して、**実装は大きく前進**しています。
ただし、「改善点を全て実装」の観点では **未完了項目が残存** しています。

- **完了（または実質完了）**
  1. Planner の正規化処理分離（`planner_normalization.py` 抽出）
  2. Kernel/Fuji/Memory の capability flag + manifest 可視化
  3. MemoryOS の runtime pickle 移行経路の実質停止（fail-closed）
  4. Kernel の doctor 自動実行ガード強化（デフォルト opt-in + confinement 必須）

- **未完了（継続対応が必要）**
  1. `except Exception` の段階的削減（特に Kernel / Memory）
  2. optional import の完全な設定駆動化（ImportError 依存の残存）
  3. MemoryOS から RestrictedUnpickler 系コードの完全撤去（runtime 停止済みだがコード残存）

---

## 評価サマリ（前回提案との対応）

### P0: broad exception の縮小

**判定: 部分完了**

- Planner では broad exception が解消済み（`except Exception` 0件）。
- 一方で Kernel / Memory には broad exception が依然多数残存。
- Fuji も 1 箇所残存。

**観測メモ（簡易カウント）**
- planner: 0
- kernel: 17
- fuji: 1
- memory: 28

**次アクション（優先）**
- まず Kernel の制御フロー上位（decision, pipeline連携, doctor周辺）から
  `ValueError/TypeError/OSError` 等へ分割。
- Memory は I/O と依存ロード経路を優先して分類。

---

### P1: optional import の整理（責務境界）

**判定: 部分完了**

- capability flag 導入と manifest 出力は実装済み。
- ただし Fuji の `yaml`、Memory の `sentence_transformers` など、
  ImportError で機能可否を決める経路が残存。

**コメント**
- 設定（feature flag）で「使う/使わない」を先に確定し、
  import 失敗は「設定不整合エラー」として扱う方が再現性が高い。

---

### P1: Planner の正規化ユーティリティ整理

**判定: 完了**

- `planner_normalization.py` に正規化ロジックとポリシーテーブルを抽出。
- `planner.py` は同モジュールを利用する構成に移行済み。
- 単体テスト（`test_planner_normalization.py`）で主要挙動を確認可能。

---

### P2: MemoryOS の legacy pickle 廃止前倒し

**判定: 実質完了（ただしコードクリーンアップ未完）**

- runtime で legacy pickle migration を常時無効化し、
  セキュリティ警告を出す fail-closed 挙動を確認。
- 一方で RestrictedUnpickler 等の互換コードは残っているため、
  最終的には完全削除して保守負債を解消すべき。

**セキュリティ警告**
- runtime 停止済みでリスクは大幅低下。
- ただし legacy 互換コードが残る限り、将来の再有効化事故リスクはゼロではない。

---

### P2: Doctor 自動実行の運用ガード強化（Kernel）

**判定: 完了**

- `ctx.get("auto_doctor", False)` によりデフォルト無効（opt-in）。
- seccomp/AppArmor の confinement が有効でない場合は実行スキップ。
- python executable / log fd の安全検証も実装済み。

**セキュリティ警告**
- subprocess 実行は依然として高リスク経路。
- 本番では追加で OS レベル制約（seccomp/AppArmor プロファイル固定、
  実行ユーザー最小権限化）を運用基準へ明文化すること。

---

## 責務境界の再判定

- Planner: 正規化責務の分離により改善。
- Kernel: 安全ガードは強化されたが、例外境界の粗さで依然肥大化傾向。
- Fuji: capability 化は進展、ただし optional import 依存が一部残る。
- MemoryOS: pickle runtime 廃止は良好。互換残骸の撤去が次段階。

---

## 最終判定（再レビュー）

- **前回提案の実装達成度: 約 75%（4項目中 2完了 + 2部分完了）**
- **リリース可否:** 重大停止級ではないため継続可。
- **次スプリント必須:**
  1. Kernel/Memory の broad exception を高頻度経路から分割
  2. optional import を設定駆動へ一本化
  3. Memory の legacy 互換コードを最終削除（runtime から完全分離済みを確定）

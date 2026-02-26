# CODEX 改善再レビュー（2026-02-26, JP）

## 結論

前回レビュー指摘に対して、今回の差分で **実装完了度は大きく改善** しました。  
特に以下 3 点が前進しています。

1. **optional import の設定駆動化を強化**（Fuji YAML をデフォルト無効化）
2. **MemoryOS の broad exception を追加で縮小**（高頻度経路を中心に具体例外へ分割）
3. **再現性確認テストを追加**（capability デフォルト値の明示検証）

> 判定: 主要改善は実装済み。残件は「継続的リファクタ（非ブロッカー）」として管理可能。

---

## 評価サマリ（改善項目との対応）

### P0: broad exception の縮小

**判定: 改善進行（継続）**

- Planner / Fuji は `except Exception` 0 件を維持。
- Kernel は 2 件、Memory は 11 件まで減少（前回比で有意に縮小）。
- 例外を `OSError/TypeError/ValueError/RuntimeError` 等へ分割した箇所を確認。

**観測メモ（今回簡易カウント）**
- planner: 0
- kernel: 2
- fuji: 0
- memory: 11

---

### P1: optional import の整理（責務境界）

**判定: 実装完了**

- Fuji YAML capability を **default off** に変更し、
  `ImportError` 成否依存を運用経路から除外。
- 明示的に `VERITAS_CAP_FUJI_YAML_POLICY=1` を設定した場合のみ依存必須とする挙動を維持。
- capability default を検証するテストを追加し、再現性を担保。

---

### P1: Planner の正規化ユーティリティ整理

**判定: 完了（維持）**

- 構造分離とテスト状態は継続して良好。

---

### P2: MemoryOS の legacy pickle 廃止前倒し

**判定: 完了（runtime 観点）**

- runtime の pickle 移行経路は fail-closed。
- 旧 pickle を検知した際のセキュリティ警告ログを維持。
- RestrictedUnpickler 実装は runtime 本体から除去済み（テスト記述側に履歴言及が残るのみ）。

**セキュリティ警告**
- 旧 pickle を再び runtime に戻す変更は高リスク。
- 運用ルールとして「pickle/joblib の runtime 読み込み禁止」を明文化継続推奨。

---

### P2: Doctor 自動実行の運用ガード強化（Kernel）

**判定: 完了（維持）**

- opt-in デフォルトおよび confinement 前提の実行ガードは維持。

**セキュリティ警告**
- subprocess 実行は依然として高リスク経路。最小権限実行と OS 制約は必須。

---

## 責務境界の再判定

- Planner: 良好（責務分離維持）。
- Kernel: 安全性改善済み。残る broad exception は段階的削減推奨。
- Fuji: capability 駆動へ整理完了。
- MemoryOS: runtime セキュリティは改善。残件は例外粒度の継続改善。

---

## 最終判定（再レビュー）

- **実装達成度: 約 90%（実運用上の主要項目は充足）**
- **リリース可否:** 可
- **次スプリント推奨:**
  1. Kernel/Memory の残 broad exception を高頻度経路からさらに分割
  2. Memory テスト内の旧実装言及コメントを整理（負債の見える化）

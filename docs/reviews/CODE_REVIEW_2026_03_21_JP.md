# VERITAS OS コードレビュー（2026-03-21）

## 概要

本レビューでは、リポジトリ全体の構成を走査した上で、特に以下を重点確認した。

- Planner / Kernel / FUJI / MemoryOS の責務境界
- API サーバと pipeline オーケストレーション
- BFF / フロントエンド API プロキシ
- セキュリティ対策と代表テスト

総評として、VERITAS OS は**責務分離・監査性・セキュリティ意識が高い**一方、
互換レイヤを多く抱えるため、中核モジュールのレビューコストが高い。
また、一部に可用性優先で fail-open 気味の設計が見られるため、
production では fail-closed を強める余地がある。

---

## 総合評価

- **設計品質**: 高い
- **責務分離**: 概ね良好
- **テスト文化**: 強い
- **セキュリティ意識**: 高い
- **保守性**: 良いが、中核ファイルの肥大化が課題

---

## 良い点

### 1. 責務境界が文書化され、テストでも担保されている

Planner / Kernel / FUJI / MemoryOS の責務がアーキテクチャ文書で明文化され、
import 方向・I/O 所有・公開 API をテストで固定している点は非常に良い。

### 2. Pipeline 分割の方向性が良い

`pipeline.py` は orchestration に寄せ、
input / execute / policy / response / persist / replay に処理を分割している。
大型コードベースの中でも、この部分は改善方向が明確である。

### 3. BFF の権限制御が堅実

フロント側の `/api/veritas/*` プロキシでは、
許可パスのホワイトリスト化、ロール制御、危険な path segment の拒否、
trace ID の伝播などが実装されている。

### 4. セキュリティ対策が具体的

Kernel の subprocess 起動周辺では、seccomp / AppArmor / 実行ファイル検証 /
`O_NOFOLLOW` を考慮したログ FD 作成など、防御的な実装が入っている。

### 5. 外部入力のサニタイズが丁寧

GitHub Adapter は control chars / bidi chars / 不正 URL /
credential 埋め込み URL を除外し、UI 偽装や header 汚染リスクを下げている。

---

## 主な懸念点

### 1. Planner / Kernel がまだ重い

責務境界の方針は正しいが、`planner.py` と `kernel.py` は
依然として互換レイヤと制御分岐を多く抱えている。
新規ロジックが helper/stage 側に寄らず本体に戻ると、
今後さらにレビューが難しくなる。

### 2. production では fail-open 気味な箇所がある

API サーバは可用性を高める設計になっているが、
安全機能の読み込み失敗時にも warning のみで継続する箇所がある。
これは「落ちない」代わりに「保護が弱まったまま動く」リスクを持つ。

### 3. Memory 破損時の見え方が弱い

MemoryStore は JSON decode error や I/O error 時に空配列へフォールバックするため、
破損・消失・未登録の区別が上位から見えにくい。
監査性・運用性の面で改善余地がある。

---

## セキュリティ警告

### 警告 1. sanitize import failure 時に API が継続する

PII masking の import に失敗しても warning のみで動作継続する設計は、
production では注意が必要である。
安全機能の障害を availability 優先で吸収しているため、
規制環境では fail-closed を検討すべきである。

### 警告 2. BFF の API キーが import 時に固定される

Next.js 側の BFF ルートでは `VERITAS_API_KEY` を module import 時に読み込んでいる。
そのため緊急ローテーション時に即時反映されず、
再起動まで古いキーが残る可能性がある。

### 警告 3. Memory 読み込み失敗が silent degradation になりやすい

memory ファイルの破損や読み込み失敗時に empty-state へ倒れるため、
障害検知が遅れるおそれがある。
health / audit への明示的な露出が望ましい。

---

## 優先度つき改善提案

### P0

- production で sanitize import failure を fail-closed にする

### P1

- [x] BFF の `VERITAS_API_KEY` を request 時に取得する形へ変更し、緊急ローテーションを即時反映できるようにする
  - 2026-03-21 対応済み。`frontend/app/api/veritas/[...path]/route.ts` で module import 時の固定読み込みを廃止し、各 request ごとに `process.env.VERITAS_API_KEY` を再評価するよう変更した。これにより BFF 再起動なしでもキー更新が次リクエストから反映される。
  - `frontend/app/api/veritas/[...path]/route.test.ts` に、未設定時の 503 応答と、連続 2 リクエストで異なる API キーが upstream に送られる回帰テストを追加した。
- Memory corruption / load failure を health / audit に反映する

### P2

- `planner.py` / `kernel.py` の互換ロジックを helper/stage へさらに移送する

### P3

- フロント API client の abort 原因判定を改善し、timeout と user cancel を分離する

---

## 結論

VERITAS OS は、研究用途の試作を超えて、
**監査性・安全性・責務分離を強く意識した実装**になっている。
特に boundary 契約、BFF 制御、セキュリティ回帰テストは評価できる。

一方で、今後の継続改善では、
「壊れても落とさない」設計を「壊れたら安全側に倒す」設計へどこまで寄せるかが重要である。
production / enterprise 運用を強く意識するなら、
fail-closed の適用範囲を広げることを推奨する。

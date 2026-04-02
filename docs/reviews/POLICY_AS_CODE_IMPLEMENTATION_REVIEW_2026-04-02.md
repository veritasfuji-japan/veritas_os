# Policy-as-Code 実装状況レビュー（2026-04-02）

## 対象範囲
本レビューは、`veritas_os/policy/*` のコンパイラ・実行時評価・テスト生成、および `pipeline_policy` 側のランタイム接続点を中心に、**現時点でコード上に実装済みの事実**を整理したもの。

---

## 1. 結論サマリ（実装ステータス）

- **実装済み（中核）**
  - Policy source（YAML/JSON）を strict schema で検証し、Canonical IR へ正規化する経路がある。
  - IR から `manifest.json` / `manifest.sig` / `canonical_ir.json` / `explain.json` / bundle archive を出力するコンパイラがある。
  - runtime adapter が manifest 署名（SHA-256整合）を検証してから bundle をロードする。
  - evaluator が scope/conditions/constraints/requirements を評価し、`allow / require_human_review / escalate / halt / deny` を決定する。
  - pipeline に optional bridge があり、`compiled_policy_bundle_dir` 指定時に評価結果を `ctx.response_extras["governance"]["compiled_policy"]` へ反映できる。

- **実装済み（品質担保）**
  - コンパイラ成果物、決定性、改ざん検知、ランタイム判定、テストベクトル生成に対する pytest が存在。

- **未実装 / 制約あり（運用面）**
  - `pipeline` 側の compiled policy enforcement は **opt-in**（`policy_runtime_enforce` が true のときのみ FUJI 判定へ強制反映）。
  - 署名は現状 `manifest.json` の SHA-256 ハッシュ一致確認であり、鍵管理付き電子署名（公開鍵検証）ではない。
  - runtime evaluator の `regex` 演算は動的 `re.search` を直接使っており、ポリシー由来パターンの複雑性制御が未実装。

---

## 2. 実装詳細レビュー

### 2.1 コンパイル層（Policy source → Canonical IR → Bundle）

`compile_policy_to_bundle` は、以下を一貫して実施している。

1. source policy 読み込み＋schema 検証
2. canonical IR 正規化
3. semantic hash 算出
4. `compiled/canonical_ir.json` と `compiled/explain.json` の生成
5. manifest 生成（bundle contents 含む）
6. `manifest.sig`（manifest payload の SHA-256 hex）生成
7. bundle archive 作成

このため、**「Policy-as-Codeのコンパイル基盤」は既に動作する状態**と判断できる。

### 2.2 実行時層（Bundle load / verify → Policy evaluate）

runtime adapter は `manifest.sig` と `manifest.json` の整合を検証し、不一致時はロードを拒否する。これにより、少なくとも bundle 受け渡し時の単純改ざんは検知できる。

evaluator は policy 単位で下記を判定する。

- scope（domain/route/actor）
- conditions / constraints（一致判定）
- required_evidence / required_reviewers / minimum_approval_count
- outcome precedence（deny が最優先）

さらに、`allow` outcome でも要件不足なら `halt` / `require_human_review` に引き上げる実装があり、fail-safe 寄りの振る舞いを一部担保している。

### 2.3 パイプライン接続（FUJI連携）

`stage_fuji_precheck` 内で `_apply_compiled_policy_runtime_bridge` が呼ばれ、compiled policy 結果が governance extras に反映される。

ただし FUJI 最終判定への反映は `policy_runtime_enforce` が true の場合のみで、false では観測のみ。現状は段階導入として妥当だが、**本番強制を期待する環境では設定ミスが安全性ギャップになる**。

### 2.4 テスト/検証基盤

以下の観点がテスト済み。

- コンパイル成功・失敗
- 生成成果物の存在
- semantic hash / manifest の決定性
- manifest 改ざん時の runtime load 失敗
- runtime outcomes（allow/escalate/halt/deny/require_human_review）
- policy test_vectors からの deterministic test case 生成

したがって、**PoCを超えた「実運用前検証が可能な基盤」**には到達している。

---

## 3. セキュリティ観点（警告を含む）

> ⚠️ **警告1: 署名モデルが「ハッシュ整合」に留まる**
>
> `manifest.sig` は manifest 本体の SHA-256 値で、秘密鍵署名の検証ではない。攻撃者が bundle 一式を書き換え可能な前提では、`manifest.json` と `manifest.sig` を同時に再生成できるため、真正性保証としては不十分。

> ⚠️ **警告2: runtime evaluator の regex 実行リスク**
>
> `regex` operator が `re.search(expected, actual)` を実行するため、ポリシー供給源が不信な場合に ReDoS（高コスト正規表現）耐性が弱い。現状は trusted policy 前提なら許容だが、将来の外部供給を考えると制約（長さ・複雑性・timeout）が必要。

> ⚠️ **警告3: enforcement が opt-in**
>
> `policy_runtime_enforce=false` だと compiled policy は観測のみ。設定ミス時に policy 違反を reject できない可能性がある。環境ごとの強制フラグ管理（prod で true 固定、CI で検査）を推奨。

---

## 4. 責務境界（Planner / Kernel / FUJI / MemoryOS）観点

今回確認した実装は主に以下の責務に収まっており、レイヤ越境は限定的。

- FUJI / pipeline 側: 最終ゲート連携・拒否反映
- policy モジュール: Policy-as-Code の compilation / adaptation / evaluation
- governance 側: 管理ポリシー（JSON）運用

特に、MemoryOS 内部責務へ Policy-as-Code が直接侵入する実装はレビュー範囲では確認されなかった。

---

## 5. 総合評価

- **成熟度評価**: `β+`（基盤は十分、運用強制と暗号署名の強化が次段階）
- **現状の到達点**: 「Policy → IR → Bundle → Runtime評価 → Pipeline反映」の縦断経路は成立。
- **優先改善項目（高）**:
  1. `manifest.sig` を公開鍵署名方式へ移行（署名者真正性の確立）
  2. `regex` operator の安全制約（ガードレール）
  3. 本番で `policy_runtime_enforce` を強制する設定/起動時検証

---

## 6. 2026-04-02 改善実施ログ（最小改善のみ）

- **実施内容（優先改善項目 #2 に対応）**
  - runtime evaluator の `regex` 判定にガードレールを追加。
    - パターン長の上限
    - 検査対象文字列長の上限
    - ネスト量指定子（例: `(a+)+`）を含む高コスト化しやすいパターンの拒否
    - 不正 regex（`re.error`）の安全失敗（match しない扱い）
  - 既存判定フローは維持し、`regex` 条件が危険/過大な入力の場合のみ不成立に倒す最小変更とした。
  - pipeline bridge の非強制モードに運用警告を追加。
    - `compiled_policy` の判定が `deny / halt / escalate / require_human_review` の場合、
      `policy_runtime_enforce=false` で未反映のまま通過していることを warning ログで明示。
    - FUJI の既存判定ロジックは変更せず、設定ミス検知性のみを向上させた。

- **追加テスト**
  - 正常な `regex` 条件は従来どおり一致して発火すること。
  - 上限超過入力では `regex` 条件が発火せず、policy outcome が適用されないこと。
  - ネスト量指定子パターンでは `regex` 条件が発火せず、policy outcome が適用されないこと。
  - `policy_runtime_enforce=false` かつ compiled policy の最終判定が `deny` のとき、
    FUJI のステータスを強制変更しないこと、および warning が出ること。

- **セキュリティ補足**
  - 本対応は ReDoS リスクを「低減」するものであり、完全排除ではない。
  - 外部供給ポリシーを許可する場合は、将来的に regex engine timeout または RE2 系エンジン導入を推奨。

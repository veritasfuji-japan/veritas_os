# 型安全性ベースライン

> 英語版（`docs/en/operations/type-safety-baseline.md`）が正本です。
> この日本語版は補助説明です。

## 目的

この文書は、VERITAS OS における最初の型安全性ベースラインを定義します。
このベースラインは意図的に狭い範囲に限定し、商用DDで説明可能な、
反復可能かつ低リスクな typecheck ゲートを先に導入することを目的とします。

## 現在のスコープ

実行コマンド:

```bash
python -m scripts.quality.check_type_baseline
```

現在の対象:

- `scripts/demo/one_day_poc_shared.py`
- `scripts/demo/one_day_poc_benchmark.py`
- `scripts/demo/one_day_poc_smoke.py`

## 実行方法

開発依存関係を導入後、次を実行します。

```bash
pip install -e ".[dev]"
python -m scripts.quality.check_type_baseline
```

## このベースラインで示せること

- 開発者/DD向けに、mypy ベースラインコマンドを反復実行できること。
- 選択した PoC/demo 補助パスで静的型チェックが通ること。
- 型安全性導入を段階的品質項目として追跡していること。

## このベースラインで示せないこと

- リポジトリ全体の型カバレッジ。
- リポジトリ全体 strict typing。
- すべてのガバナンスモジュールの strict typing。
- ランタイム正当性の保証。
- API互換性の保証。


## 依存関係上の位置づけ

`mypy` は、このベースラインをリポジトリの品質確認フローで一貫して導入・実行できるように、development/full dependency manifest に含めています。これは VERITAS の runtime behavior、governance semantics、API contracts、evidence packet shape、provider behavior を変更するものではありません。本番イメージから開発用ツールを除外する必要がある場合は、この baseline PR とは別に deployment profile / Docker install path の最適化として扱ってください。

## 拡張ロードマップ

このベースラインは最小構成であり、段階的に拡張予定です。
次段階候補:

- `veritas_os/core/value_core.py`
- `veritas_os/core/llm_client.py`
- bind/admissibility 関連モジュール
- TrustLog / RBAC の公開サーフェス

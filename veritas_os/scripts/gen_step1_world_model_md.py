#!/usr/bin/env python3
"""
Step1: 世界モデルと安全境界（FUJI Gate）用の Markdown テンプレを生成するスクリプト。
"""

from pathlib import Path
from datetime import datetime

# このスクリプトは veritas_os/scripts/ に置く前提
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent.parent  # ~/veritas_clean_test2 配下のルート想定
DOCS_DIR = ROOT_DIR / "docs" / "agi_self_hosting"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = DOCS_DIR / "step1_world_model_and_fuji_gate.md"


def main() -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    content = f"""# Step1: 世界モデルと安全境界の言語化

> 自動生成日時: {now}

## 1. 目的 (Objective)

- 現実的制約付き AGI 研究の世界モデルを言語化する
- FUJI Gate を含む **安全境界** を明文化し、後続ステップ (step2〜5) の前提にする

---

## 2. 現状の利用環境・リソース制約

- 開発マシン / OS:
  - 例: macOS / メモリ / CPU など
- ローカルディレクトリ構成:
  - 例: `~/veritas_clean_test2`, `veritas_os/`, `scripts/`, `docs/` ...
- 利用できる外部サービス:
  - GitHub: 〇 / ✕ （リポジトリ名・運用方針）
  - Drive / rclone: 〇 / ✕ （同期先パス）
- LLM / API 制約:
  - 利用できるモデル、トークン制限、料金など
- 人間 (藤下) の時間制約:
  - 週 10〜15 時間程度
  - 1 セッションあたりの集中時間の目安: 〜分

> ※ このセクションは「後で変更されること前提」で良いので、とりあえず現時点のリアルを書き出す。

---

## 3. 想定される失敗モード一覧

下の表を埋めるイメージで、**主要リスクを 10 個以上** 列挙する。

| ID | カテゴリ | 概要 | 影響 (Impact) | 発生しやすさ (Likelihood) | メモ |
|----|----------|------|----------------|----------------------------|------|
| F-01 | 設計の暴走 | 例: 構想だけ膨らんで実装に落ちない | 高 / 中 / 低 | 高 / 中 / 低 |  |
| F-02 | ログ破綻 | 決定ログが肥大化して読めなくなる / 欠損する |  |  |  |
| F-03 | 人間の過負荷 | レビューすべき情報が多すぎて追えない |  |  |  |
| F-04 | メトリクス不整合 | 指標がバラバラで改善か悪化か判断できない |  |  |  |
| F-05 | API 仕様変更 | OpenAI や外部 API の仕様変更でクラッシュ |  |  |  |
| F-06 | バイアスの固定化 | 間違った value 設計で自己強化ループに入る |  |  |  |
| F-07 | バックアップ不備 | ログや config を失ってロールバック不能 |  |  |  |
| F-08 | セキュリティ | 秘匿情報を誤って commit / アップロード |  |  |  |
| F-09 | 設計と実装の乖離 | docs と実装がズレて「何が正か」不明 |  |  |  |
| F-10 | メンテ不能化 | 将来読み返したときに自分でも理解不能 |  |  |  |

> 必要に応じて F-11 以降も追加して OK。

---

## 4. FUJI Gate の役割と安全境界

### 4.1 FUJI Gate の基本方針（テキスト）

- 例:
  - 倫理 / 法律 / 安全性に関して **事前チェック** を行うゲート
  - 「許可 / ブロック / 要人間レビュー」の 3 つのフラグで判定
  - 高リスクの decision は **必ず人間レビュー必須** にする  など

ここに **1〜2 パラグラフ** で、VERITAS 全体に対する FUJI Gate の位置づけを書く。

### 4.2 安全境界（何を「やらない」か）

- 例:
  - 法律・利用規約に抵触しそうな自動化は行わない
  - 金銭・取引・対外コミュニケーションを **自動で確定させる** ことはしない
  - システム設定やファイル削除のような **破壊的操作** は、人間の明示的 OK なしに実行しない
  - 長期的な価値観変更を伴う提案は、必ず「代替案」とセットで提示する

### 4.3 FUJI Gate の判定ロジック（ドラフト）

- 判定入力の例:
  - `risk`: 0.0〜1.0
  - `telos_score`
  - `violations`: [ "law", "ethics", ... ]
- 判定出力の例:
  - `status`: "allow" | "review" | "block"
  - `reasons`: [...  ]
- 簡単な擬似ルール案:
  - `risk >= 0.4` → `status = "block"`
  - `0.2 <= risk < 0.4` → `status = "review"`
  - `risk < 0.2` → `status = "allow"`

> 実際の実装ルールは別ファイル（例: `fuji_config.json`）に落とし込む想定。

---

## 5. モニタリング指標とメトリクス（step1 視点）

step1 で観測したい指標の候補：

- 失敗モードの **カバレッジ**
  - 例: 「F-xx リストが 10 個以上あるか」
- FUJI Gate 判定ログ
  - 例: 直近 N 件の decision で `status="block"` が何件あったか
- 人間レビュー負荷
  - 例: 週あたりレビューに使った時間（主観でも OK）

ここに **「とりあえず運用開始時に見るメトリクス」** を箇条書きで書く。

---

## 6. Done Criteria（完了条件）

- [ ] 現状の利用環境・制約が 1〜2 ページ程度で整理されている
- [ ] 主要な失敗モードが **10 個以上** 列挙されている
- [ ] FUJI Gate の役割・安全境界がテキストで説明されている
- [ ] 判定ロジックのドラフト（閾値イメージ）が書かれている
- [ ] 「どのメトリクスを眺めながら運用するか」の初期案がある

> 上のチェックボックスがすべて ✅ になったら、step1 は完了とみなして OK。
"""

    OUT_PATH.write_text(content, encoding="utf-8")
    print(f"[OK] Markdown template generated: {OUT_PATH}")


if __name__ == "__main__":
    main()


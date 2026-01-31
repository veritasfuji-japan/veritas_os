# Self-Healing Loop (自己修復ループ)

## 目的
FUJI Safety Gate が `REJECTED` を返した場合に、FujiFeedback（action / hint）を再入力として使い、
人間が介入しなくても思考を修正して再実行する仕組みを提供します。
同時に、安全性と監査性を最優先し、無限ループや価値観の勝手な変更を防ぐためのガードレールを実装しています。

## Self-Healing の安全装置（ガードレール）
- **最大試行回数**: `VERITAS_MAX_HEALING_ATTEMPTS`（デフォルト 3）
- **予算上限**: `VERITAS_HEALING_MAX_SECONDS`（デフォルト 20秒）と `VERITAS_HEALING_MAX_STEPS`（デフォルト 6）
- **同一エラー連続停止**: `VERITAS_HEALING_MAX_SAME_ERROR`（デフォルト 2）
- **差分なし停止**: 再入力が前回と実質同一（attempt を除外した構造比較）なら停止
- **安全系 (F-4xxx) は原則自己修復しない**: F-4001 / F-4003 を含む安全系は即 HUMAN_REVIEW

## HealingPolicy（F-code → action）
| F-code | アクション | 方針 |
|---|---|---|
| F-1002 Insufficient Evidence | REQUEST_EVIDENCE | 不足根拠の収集・明示 |
| F-1005 Inconsistent Data | RE-CRITIQUE | 矛盾点の整理と根拠の再評価 |
| F-2101 Critique Unresolved | RE-DEBATE | Critique指摘を最優先で再議論 |
| F-2203 Logic Leap | RE-DEBATE | 推論の飛躍を分解・補完 |
| F-3001 ValueCore Mismatch | HUMAN_REVIEW | 価値観再解釈は人間レビュー |
| F-3008 Ethical Boundary | HUMAN_REVIEW | 倫理境界越えは即停止 |
| F-4xxx Safety/Security | HUMAN_REVIEW | 自己修復禁止（即停止） |

## 停止条件と HUMAN_REVIEW 遷移
以下のいずれかに該当すると Self-Healing を停止し、HUMAN_REVIEW に移行します。
- 最大試行回数超過
- 予算上限超過（時間 / ステップ）
- 同一エラー連続発生
- 差分なし停止（前回と実質同一の入力）
- F-3xxx / F-4xxx 等のポリシーで HUMAN_REVIEW 指定

## TrustLog への記録内容
各 attempt ごとに以下のメタデータを TrustLog に追加します。
- `healing_enabled`
- `healing_attempt`
- `prev_error_code`
- `chosen_action`
- `budget_remaining`
- `diff_summary`
- `linked_trust_log_id`
- `stop_reason`（停止時）

## Self-Healing 入力フォーマット
Self-Healing 再入力は次のフォーマットに統一しています。

```json
{
  "original_task": "オリジナルのタスク文",
  "last_output": {
    "chosen": {"id": "step_1", "title": "..." },
    "plan": {"steps": [...]}
  },
  "rejection": {
    "status": "REJECTED",
    "gate": "FUJI_SAFETY_GATE_v2",
    "error": { "code": "F-2101", "message": "...", "detail": "...", "layer": "...", "severity": "HIGH", "blocking": true },
    "feedback": { "action": "RE-DEBATE", "hint": "..." },
    "trust_log_id": "TL-20250101-0001"
  },
  "attempt": 1,
  "policy_decision": "policy_map:F-2101->RE-DEBATE"
}
```

## 例: F-2101 での再実行
1. FUJI Gate が `REJECTED`（F-2101）を返す  
2. HealingPolicy が `RE-DEBATE` を選択  
3. 上記テンプレートに `attempt=1` を含めた再入力を作成  
4. 再実行し、ガードレールに抵触しない限り最大3回まで再試行


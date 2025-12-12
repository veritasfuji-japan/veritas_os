# veritas_os/tests/test_value_core.py
import json
from pathlib import Path

from veritas_os.core import value_core


# ============
# 基本ユーティリティ
# ============
def test_clean_text_removes_numbers_and_exponents():
    s = "Value 123 and 45.6 and 7.8e-10 remain"
    cleaned = value_core._clean_text(s)
    assert "123" not in cleaned
    assert "45.6" not in cleaned
    assert "7.8e-10" not in cleaned
    assert "Value" in cleaned


def test_to_float_and_clip01_basic():
    assert value_core._to_float(1) == 1.0
    assert value_core._to_float(" 2.5 ") == 2.5
    assert value_core._to_float(None, default=0.7) == 0.7
    assert value_core._to_float("xxx", default=0.9) == 0.9

    assert value_core._clip01(-1) == 0.0
    assert value_core._clip01(0.5) == 0.5
    assert value_core._clip01(5) == 1.0
    assert value_core._clip01("0.3") == 0.3
    assert value_core._clip01("xxx") == 0.0


def test_normalize_weights_empty_returns_default_copy():
    result = value_core._normalize_weights({})
    assert result == value_core.DEFAULT_WEIGHTS
    # コピーであること（同一オブジェクトではない）
    assert result is not value_core.DEFAULT_WEIGHTS


def test_normalize_weights_clips_values():
    w = {"ethics": 2.0, "user_benefit": -1.0}
    result = value_core._normalize_weights(w)
    assert 0.0 <= result["ethics"] <= 1.0
    assert 0.0 <= result["user_benefit"] <= 1.0


# ============
# ValueProfile load/save/update
# ============
def test_value_profile_load_creates_default_when_missing(tmp_path, 
monkeypatch):
    cfg_dir = tmp_path / "veritas_cfg"
    monkeypatch.setattr(value_core, "CFG_DIR", cfg_dir)
    monkeypatch.setattr(value_core, "CFG_PATH", cfg_dir / "value_core.json")

    prof = value_core.ValueProfile.load()
    # デフォルト + 正規化された重みになっていること
    assert set(prof.weights.keys()) == set(value_core.DEFAULT_WEIGHTS.keys())
    assert all(0.0 <= v <= 1.0 for v in prof.weights.values())
    assert value_core.CFG_PATH.exists()


def test_value_profile_save_writes_normalized(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "veritas_cfg2"
    monkeypatch.setattr(value_core, "CFG_DIR", cfg_dir)
    monkeypatch.setattr(value_core, "CFG_PATH", cfg_dir / "value_core.json")

    prof = value_core.ValueProfile(weights={"ethics": 2.0, "user_benefit": 
-1.0})
    prof.save()

    assert value_core.CFG_PATH.exists()
    with value_core.CFG_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    w = data["weights"]
    assert 0.0 <= w["ethics"] <= 1.0
    assert 0.0 <= w["user_benefit"] <= 1.0


def test_value_profile_update_from_scores_moves_toward_scores(tmp_path, 
monkeypatch):
    cfg_dir = tmp_path / "veritas_cfg3"
    monkeypatch.setattr(value_core, "CFG_DIR", cfg_dir)
    monkeypatch.setattr(value_core, "CFG_PATH", cfg_dir / "value_core.json")

    prof = value_core.ValueProfile(weights={"ethics": 0.0})
    prof.update_from_scores({"ethics": 1.0}, lr=0.5)

    # 0→1 を lr=0.5 で更新 → 0.5 付近になるはず
    assert 0.4 <= prof.weights["ethics"] <= 0.6
    assert value_core.CFG_PATH.exists()


# ============
# heuristic_value_scores
# ============
def test_heuristic_value_scores_negative_words():
    s = value_core.heuristic_value_scores("これは犯罪と違法な行為です", 
{})
    assert s["ethics"] == 0.0
    assert s["legality"] == 0.0
    assert s["harm_avoid"] == 0.0


def test_heuristic_value_scores_risky_words():
    s = value_core.heuristic_value_scores("これはギャンブルや投機の話です", {})
    assert s["reversibility"] <= 0.4 + 1e-6
    assert s["reversibility"] >= 0.4 - 1e-6
    assert s["efficiency"] <= 0.5 + 1e-6
    assert s["efficiency"] >= 0.5 - 1e-6


def test_heuristic_value_scores_positive_and_autonomy_words():
    s = value_core.heuristic_value_scores("このレポートを報告して説明と検証を行う", 
{})
    assert s["truthfulness"] >= 0.9
    assert s["accountability"] >= 0.8

    s2 = value_core.heuristic_value_scores("自動・自律システムについて", 
{})
    assert s2["autonomy"] >= 0.7


# ============
# evaluate（学習フラグあり/なし）
# ============
class _DummyProfileNoSave:
    def __init__(self):
        self.weights = value_core.DEFAULT_WEIGHTS.copy()
        self.updated = False

    def update_from_scores(self, scores, lr=0.02):
        self.updated = True

    def save(self):
        # 呼ばれない想定（必要ならダミー）
        pass


def test_evaluate_respects_no_learn_values(monkeypatch):
    dummy = _DummyProfileNoSave()

    # ValueProfile.load を差し替え
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    res = value_core.evaluate("テストクエリ", {"no_learn_values": True})
    assert isinstance(res, value_core.ValueResult)
    assert dummy.updated is False  # 学習されていない


class _DummyProfileWithSave:
    def __init__(self):
        self.weights = value_core.DEFAULT_WEIGHTS.copy()
        self.updated = False
        self.saved = False

    def update_from_scores(self, scores, lr=0.02):
        self.updated = True

    def save(self):
        self.saved = True


def test_evaluate_updates_when_learning_enabled(tmp_path, monkeypatch):
    dummy = _DummyProfileWithSave()

    cfg_dir = tmp_path / "veritas_cfg_eval"
    monkeypatch.setattr(value_core, "CFG_DIR", cfg_dir)
    monkeypatch.setattr(value_core, "CFG_PATH", cfg_dir / 
"value_core.json")

    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    res = value_core.evaluate("コードを改善して最適化する", {})
    assert 0.0 <= res.total <= 1.0
    assert res.top_factors
    assert isinstance(res.rationale, str)
    assert dummy.updated is True


# ============
# update_weights
# ============
class _DummyProfileForUpdate:
    def __init__(self):
        self.weights = {"ethics": 0.5}
        self.saved = False

    def save(self):
        self.saved = True


def test_update_weights_uses_normalization(monkeypatch):
    dummy = _DummyProfileForUpdate()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    result = value_core.update_weights({"ethics": 2.0, "user_benefit": 
10})
    assert dummy.saved is True
    assert 0.0 <= result["ethics"] <= 1.0
    assert 0.0 <= result["user_benefit"] <= 1.0


# ============
# rebalance_from_trust_log
# ============
class _DummyProfileForRebalance:
    def __init__(self):
        self.weights = {
            "truthfulness": 0.8,
            "accountability": 0.7,
            "efficiency": 0.6,
        }
        self.saved = False

    def save(self):
        self.saved = True


def test_rebalance_from_trust_log_handles_missing_file(tmp_path):
    # 存在しないパスでも例外なく終わること（print だけ）
    log_path = tmp_path / "no_such_log.jsonl"
    value_core.rebalance_from_trust_log(str(log_path))


def test_rebalance_from_trust_log_low_ema_increases_truth_and_accountability(
    tmp_path, monkeypatch
):
    dummy = _DummyProfileForRebalance()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    log_path = tmp_path / "trust_log_low.jsonl"
    with log_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"score": 0.5}) + "\n")
        f.write(json.dumps({"score": 0.6}) + "\n")

    value_core.rebalance_from_trust_log(str(log_path))

    assert dummy.saved is True
    assert dummy.weights["truthfulness"] >= 0.8
    assert dummy.weights["accountability"] >= 0.7


def test_rebalance_from_trust_log_high_ema_increases_efficiency(tmp_path, 
monkeypatch):
    dummy = _DummyProfileForRebalance()
    monkeypatch.setattr(
        value_core.ValueProfile,
        "load",
        classmethod(lambda cls: dummy),
    )

    log_path = tmp_path / "trust_log_high.jsonl"
    with log_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"score": 0.95}) + "\n")
        f.write(json.dumps({"score": 0.98}) + "\n")

    value_core.rebalance_from_trust_log(str(log_path))

    assert dummy.saved is True
    assert dummy.weights["efficiency"] >= 0.6


# ============
# append_trust_log
# ============
def test_append_trust_log_writes_jsonl(tmp_path, monkeypatch):
    log_path = tmp_path / "trust_log.jsonl"
    monkeypatch.setattr(value_core, "TRUST_LOG_PATH", log_path)

    value_core.append_trust_log(
        user_id="user123",
        score=1.5,  # クリップされるはず
        note="test-note",
        source="unit",
        extra={"foo": "bar"},
    )

    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])

    assert rec["user_id"] == "user123"
    assert rec["score"] == 1.0  # 0..1 にクリップされている
    assert rec["note"] == "test-note"
    assert rec["source"] == "unit"
    assert rec["extra"]["foo"] == "bar"


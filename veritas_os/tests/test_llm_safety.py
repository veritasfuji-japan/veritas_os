# veritas_os/tests/test_llm_safety.py
import os
from typing import Any, Dict, List

from veritas_os.tools import llm_safety


# -----------------------------
# ヒューリスティック部のテスト
# -----------------------------


def test_heuristic_analyze_safe_english():
    """英語だけのテキストなら PII も illicit も付かない想定。"""
    # "harmless" だと "harm" にヒットするので避ける
    text = "Hello, this is a simple question about the weather today."
    res = llm_safety._heuristic_analyze(text)

    assert res["ok"] is True
    assert isinstance(res["risk_score"], float)
    # ベースラインが 0.05 なのでこのくらいのレンジなら OK
    assert 0.0 <= res["risk_score"] <= 0.1
    # 英語のみなので PII も illicit も検出されないはず
    assert "PII" not in res["categories"]
    assert "illicit" not in res["categories"]
    assert "fallback" in res["raw"]



def test_heuristic_analyze_illicit_and_pii():
    """危険ワード + 
PII（電話・メール・住所・名前っぽい漢字）が揃ったケース。"""
    text = (
        "I want to kill someone. "
        "Phone: 090-1234-5678, email: test@example.com, "
        "address: 東京都1-2-3 山田太郎"
    )

    res = llm_safety._heuristic_analyze(text)

    assert res["ok"] is True
    # 危険ワードがあるので high risk 気味
    assert res["risk_score"] >= 0.8
    # illicit と PII の両方が付くはず
    assert "illicit" in res["categories"]
    assert "PII" in res["categories"]

    raw = res["raw"]
    assert "banned_hits" in raw
    assert "kill" in raw["banned_hits"]
    assert "pii_hits" in raw
    # phone / email / address / name_like のどれかが入っていること
    assert any(tag in raw["pii_hits"] for tag in ["phone", "email", 
"address", "name_like"])


# -----------------------------
# _llm_available のテスト
# -----------------------------


def test_llm_available_false_when_no_client_and_no_key(monkeypatch):
    """OpenAI クライアントが None かつ API キーが無い場合は False。"""
    monkeypatch.setattr(llm_safety, "OpenAI", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_VERITAS", raising=False)

    assert llm_safety._llm_available() is False


def test_llm_available_true_with_client_and_key(monkeypatch):
    """OpenAI クライアントがあり、キーがあれば True。"""

    class DummyClient:
        pass

    monkeypatch.setattr(llm_safety, "OpenAI", DummyClient)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")

    assert llm_safety._llm_available() is True


# -----------------------------
# _analyze_with_llm のテスト（ダミークライアント）
# -----------------------------


def test_analyze_with_llm_parses_response(monkeypatch):
    """Responses API 風のダミーオブジェクトから JSON 
を正しく抜き出せるか。"""

    class DummyOutputItem:
        def __init__(self, parsed: Dict[str, Any]):
            self.parsed = parsed

    class DummyResponse:
        def __init__(self):
            self.output: List[DummyOutputItem] = [
                DummyOutputItem(
                    {
                        "risk_score": 0.9,
                        "categories": ["illicit", "PII"],
                        "rationale": "test rationale",
                    }
                )
            ]

        def model_dump_json(self) -> str:
            # 本物と同じインターフェースだけあれば良い
            return '{"dummy": true}'

    class DummyResponses:
        last_kwargs: Dict[str, Any] | None = None

        def create(self, **kwargs: Any) -> DummyResponse:
            DummyResponses.last_kwargs = kwargs
            return DummyResponse()

    class DummyClient:
        def __init__(self, api_key: str | None = None):
            self.api_key = api_key
            self.responses = DummyResponses()

    monkeypatch.setattr(llm_safety, "OpenAI", DummyClient)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-456")
    monkeypatch.setenv("VERITAS_SAFETY_MODEL", "dummy-safety-model")

    res = llm_safety._analyze_with_llm(
        "dummy text",
        context={"stakes": 0.8},
        alternatives=[{"title": "alt-1"}],
        max_categories=1,
    )

    assert res["ok"] is True
    assert res["risk_score"] == 0.9
    # max_categories=1 なので 1個だけ返るはず
    assert res["categories"] == ["illicit"]
    assert res["rationale"] == "test rationale"
    assert res["model"] == "dummy-safety-model"
    assert "latency_ms" in res["raw"]
    assert res["raw"]["scoring"]["llm_risk"] == 0.9
    assert "response" in res["raw"]
    assert '"dummy": true' in res["raw"]["response"]
    assert DummyResponses.last_kwargs["temperature"] == 0


def test_score_risk_prefers_heuristic_override():
    """ヒューリスティックが高い場合は決定論的に上書きされる。"""
    heuristic = {
        "risk_score": 0.6,
        "categories": ["illicit"],
    }
    scored = llm_safety._score_risk(
        llm_risk=0.2,
        llm_categories=["PII"],
        heuristic=heuristic,
    )

    assert scored["risk_score"] >= 0.6
    assert "heuristic_risk_override" in scored["notes"]


def test_normalize_categories_deduplicates_and_clips():
    """カテゴリ正規化は重複を除去し、各要素を64文字で制限する。"""
    overlong = "x" * 120
    normalized = llm_safety._normalize_categories(
        [" PII ", "PII", "", "illicit", overlong],
        max_categories=10,
    )

    assert normalized[0] == "PII"
    assert normalized[1] == "illicit"
    assert len(normalized[2]) == 64
    assert len(normalized) == 3




def test_normalize_categories_strips_controls_and_casefold_dedup():
    """制御文字を除去し、大文字小文字差分の重複を抑止する。"""
    normalized = llm_safety._normalize_categories(
        [" PII\x00", "pii", "\n\tillicit\r", "ILLICIT"],
        max_categories=10,
    )

    assert normalized == ["PII", "illicit"]
def test_normalize_categories_respects_non_positive_limit():
    """上限が 0 以下なら空配列を返す。"""
    normalized = llm_safety._normalize_categories(["PII", "illicit"], max_categories=0)
    assert normalized == []


# -----------------------------
# run() の挙動テスト
# -----------------------------


def test_run_forced_heuristic_mode(monkeypatch):
    """VERITAS_SAFETY_MODE=heuristic なら LLM 
有無にかかわらずヒューリスティックを使う。"""
    monkeypatch.setenv("VERITAS_SAFETY_MODE", "heuristic")

    called = {}

    def fake_heuristic(text: str) -> Dict[str, Any]:
        called["text"] = text
        return {
            "ok": True,
            "risk_score": 0.2,
            "categories": ["PII"],
            "rationale": "fake heuristic",
            "model": "heuristic_fallback",
            "raw": {},
        }

    monkeypatch.setattr(llm_safety, "_heuristic_analyze", fake_heuristic)
    # _llm_available が True だとしても無視されるはず
    monkeypatch.setattr(llm_safety, "_llm_available", lambda: True)

    res = llm_safety.run("test text", context={"stakes": 0.7})

    assert called["text"] == "test text"
    assert res["ok"] is True
    assert res["model"] == "heuristic_fallback"
    assert res["risk_score"] == 0.2
    assert "VERITAS_SAFETY_MODE" in os.environ


def test_run_uses_llm_when_available(monkeypatch):
    """ヒューリスティック強制無し & LLM 利用可能なら _analyze_with_llm 
が使われる。"""
    monkeypatch.delenv("VERITAS_SAFETY_MODE", raising=False)

    monkeypatch.setattr(llm_safety, "_llm_available", lambda: True)

    called = {}

    def fake_llm(
        text: str,
        context: Dict[str, Any] | None = None,
        alternatives: List[Dict[str, Any]] | None = None,
        max_categories: int = 5,
    ) -> Dict[str, Any]:
        called["args"] = (text, context, alternatives, max_categories)
        return {
            "ok": True,
            "risk_score": 0.12,
            "categories": ["custom"],
            "rationale": "from llm",
            "model": "dummy-llm",
            "raw": {},
        }

    monkeypatch.setattr(llm_safety, "_analyze_with_llm", fake_llm)

    res = llm_safety.run(
        "please classify",
        context={"stakes": 0.9},
        alternatives=[{"title": "opt1"}],
        max_categories=3,
    )

    assert called["args"][0] == "please classify"
    assert called["args"][1] == {"stakes": 0.9}
    assert called["args"][3] == 3
    assert res["model"] == "dummy-llm"
    assert res["categories"] == ["custom"]


def test_run_llm_error_falls_back_to_heuristic(monkeypatch):
    """LLM 
で例外が起きた場合はヒューリスティックにフォールバックし、raw.llm_error 
を付ける。"""
    monkeypatch.delenv("VERITAS_SAFETY_MODE", raising=False)

    monkeypatch.setattr(llm_safety, "_llm_available", lambda: True)

    def fake_llm_error(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise RuntimeError("boom-llm")

    monkeypatch.setattr(llm_safety, "_analyze_with_llm", fake_llm_error)

    def fake_heuristic(text: str) -> Dict[str, Any]:
        return {
            "ok": True,
            "risk_score": 0.3,
            "categories": ["PII"],
            "rationale": "heuristic used",
            "model": "heuristic",
            "raw": {},
        }

    monkeypatch.setattr(llm_safety, "_heuristic_analyze", fake_heuristic)

    res = llm_safety.run("some text")

    assert res["ok"] is True
    assert res["model"] == "heuristic"
    assert res["risk_score"] == 0.3
    assert "raw" in res
    assert "llm_error" in res["raw"]
    assert res["raw"]["llm_error"] == "LLM safety head unavailable"


def test_run_uses_heuristic_when_no_llm(monkeypatch):
    """LLM 利用不可（API 
キー無し等）の場合はヒューリスティックに落ちる。"""
    monkeypatch.delenv("VERITAS_SAFETY_MODE", raising=False)
    monkeypatch.setattr(llm_safety, "_llm_available", lambda: False)

    called = {}

    def fake_heuristic(text: str) -> Dict[str, Any]:
        called["text"] = text
        return {
            "ok": True,
            "risk_score": 0.05,
            "categories": [],
            "rationale": "no llm",
            "model": "heuristic_fallback",
            "raw": {},
        }

    monkeypatch.setattr(llm_safety, "_heuristic_analyze", fake_heuristic)

    res = llm_safety.run("no llm case")

    assert called["text"] == "no llm case"
    assert res["ok"] is True
    assert res["model"] == "heuristic_fallback"
    assert res["risk_score"] == 0.05

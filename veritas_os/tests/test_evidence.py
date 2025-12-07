# tests/test_evidence.py

from veritas_os.core.evidence import collect_local


def _snippets(evidence_list):
    return [e["snippet"] for e in evidence_list]


def test_collect_local_fallback_when_no_context():
    """goals / stakes / constraints 何もないときはフォールバック説明だけが返る。"""
    evs = collect_local(intent="other", query="", context={})

    assert len(evs) >= 1
    snippets = _snippets(evs)
    assert any("クエリの意図に沿うようスコアリング済み" in s for s in snippets)


def test_collect_local_weather_intent_adds_weather_evidence():
    """intent=weather のときは天候に関するエビデンスが追加される。"""
    evs = collect_local(intent="weather", query="明日の天気は？", context={})

    snippets = _snippets(evs)
    assert any("天候は影響大" in s for s in snippets)


def test_collect_local_fatigue_and_health_goal():
    """クエリに「疲れ」が含まれるか、goals に『健康/回復』があるときの分岐。"""
    ctx = {"goals": ["健康", "収入アップ"]}
    evs = collect_local(
        intent="plan",
        query="最近疲れが取れないのでどうしたらいい？",
        context=ctx,
    )

    snippets = _snippets(evs)
    assert any("疲労時は回復優先" in s for s in snippets)


def test_collect_local_high_stakes_branch():
    """stakes ≥ 0.7 で『慎重側に倒す』メッセージが追加される。"""
    evs = collect_local(
        intent="decision",
        query="重要なキャリア選択について相談したい",
        context={"stakes": 0.9},
    )

    snippets = _snippets(evs)
    assert any("stakesが高いため慎重側に倒す方が後悔が少ない" in s for s in snippets)


def test_collect_local_constraints_branch():
    """constraints があるときに『制約: ...』のエビデンスが追加される。"""
    ctx = {"constraints": ["時間がない", "予算が少ない"]}
    evs = collect_local(
        intent="decision",
        query="どう進めるべき？",
        context=ctx,
    )

    snippets = _snippets(evs)
    assert any("制約:" in s and "時間がない" in s for s in snippets)


def test_collect_local_limits_to_four_items():
    """
    すべての条件を同時に満たした場合でも、戻り値は最大4件に truncate される。
    """
    ctx = {
        "goals": ["健康"],
        "stakes": 0.95,
        "constraints": ["時間がない", "予算が少ない"],
    }
    evs = collect_local(
        intent="weather",  # weather + health + high_stakes + constraints
        query="最近疲れもあるけど、明日の天気を含めて考えたい",
        context=ctx,
    )

    assert 1 <= len(evs) <= 4



from veritas_os.core.critique import ensure_min_items


def test_ensure_min_items_marks_reused_padding_entries() -> None:
    """min_items がテンプレート件数を超える場合の再利用情報を検証する。"""
    padded = ensure_min_items([], min_items=5)

    assert len(padded) == 5
    assert padded[0]["details"].get("pad_reused") is None
    assert padded[1]["details"].get("pad_reused") is None
    assert padded[2]["details"].get("pad_reused") is None

    assert padded[3]["details"]["pad_reused"] is True
    assert padded[3]["details"]["pad_cycle_index"] == 3
    assert padded[4]["details"]["pad_reused"] is True
    assert padded[4]["details"]["pad_cycle_index"] == 4

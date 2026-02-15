from pathlib import Path

import numpy as np

from veritas_os.memory.index_cosine import CosineIndex


def test_cosine_index_load_resets_non_finite_vectors(tmp_path: Path) -> None:
    """Loaded index with NaN vectors should be reset for safe search behavior."""
    idx_path = tmp_path / "index.npz"
    np.savez(
        idx_path,
        vecs=np.array([[1.0, np.nan], [2.0, 3.0]], dtype=np.float32),
        ids=np.array(["a", "b"], dtype=str),
    )

    idx = CosineIndex(dim=2, path=idx_path)

    assert idx.size == 0
    assert idx.vecs.shape == (0, 2)
    assert idx.ids == []


def test_cosine_index_load_keeps_finite_vectors(tmp_path: Path) -> None:
    """Loaded index with finite vectors should remain available for retrieval."""
    idx_path = tmp_path / "index.npz"
    np.savez(
        idx_path,
        vecs=np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        ids=np.array(["x", "y"], dtype=str),
    )

    idx = CosineIndex(dim=2, path=idx_path)

    assert idx.size == 2
    results = idx.search(np.array([1.0, 0.0], dtype=np.float32), k=1)
    assert results[0][0][0] == "x"

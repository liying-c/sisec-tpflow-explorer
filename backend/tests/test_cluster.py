import numpy as np
import pytest

from conftest import GROUPS, nan_array
from sisec.cluster import hclust
from sisec.data import METRICS


def test_cut_two_groups():
    h = hclust(np.array([[0], [10], [0.2], [10.3], [0.1]]))
    lab = h.cut(2)
    assert lab[0] == lab[2] == lab[4] != lab[1] == lab[3]
    changes = sum(lab[a] != lab[b] for a, b in zip(h.order, h.order[1:]))
    assert changes == 1                     # 同群在 order 裡相鄰


def test_cut_bounds():
    h = hclust(np.array([[0.0], [1.0], [5.0]]))
    assert len(set(h.cut(1))) == 1 and len(set(h.cut(9))) == 3


def test_merges_record_height_and_size():
    h = hclust(np.array([[0.0], [1.0], [5.0]]))
    assert [(m.a, m.b, m.id, m.height, m.size) for m in h.merges] == [(0, 1, 3, 1.0, 2), (2, 3, 4, 4.5, 3)]
    assert h.order == (2, 0, 1)


@pytest.mark.parametrize("group", GROUPS)
@pytest.mark.parametrize("metric", METRICS)
def test_golden_cluster(golden, group, metric):
    g = golden(group)
    pct = np.nan_to_num(nan_array(g["stage"]["pct"]), nan=0.5)      # (系統, 曲目, 指標)
    h = hclust(pct[:, :, METRICS.index(metric)].T)                   # 每首歌一列
    want = g["cluster"][metric]
    assert list(h.order) == want["order"]
    assert [(m.a, m.b, m.id, m.size) for m in h.merges] == [(m["a"], m["b"], m["id"], m["size"]) for m in want["merges"]]
    np.testing.assert_allclose([m.height for m in h.merges], [m["height"] for m in want["merges"]], atol=1e-9)
    for k in (2, 3, 4, 5):
        assert h.cut(k) == want["labels"][str(k)]

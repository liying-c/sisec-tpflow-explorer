import numpy as np
import pytest

from conftest import GROUPS
from sisec.data import METRICS, TARGETS
from sisec.stats import classical_mds, correlation_distance, nanmedian, pearson, wilcoxon


def test_nanmedian():
    assert nanmedian(np.array([4, np.nan, 1, 2, 3.0])) == 2.5
    assert nanmedian(np.array([3, 1, 2.0])) == 2
    assert np.isnan(nanmedian(np.array([np.nan, np.nan])))


def test_nanmedian_axis():
    out = nanmedian(np.array([[1, 2, 3.0], [np.nan, np.nan, np.nan]]), axis=1)
    assert out[0] == 2 and np.isnan(out[1])


def test_pearson():
    assert abs(pearson(np.array([1, 2, 3, 4.0]), np.array([2, 4, 6, 8.0])) - 1) < 1e-12
    assert abs(pearson(np.array([1, 2, 3.0]), np.array([3, 2, 1.0])) + 1) < 1e-12
    assert np.isnan(pearson(np.array([1, 2, np.nan]), np.array([1, 2, 3.0])))
    assert np.isnan(pearson(np.array([1, 1, 1.0]), np.array([1, 2, 3.0])))


def test_wilcoxon_clear_and_symmetric():
    i = np.arange(50)
    a = 10 + np.sin(i)
    assert wilcoxon(a, a - 1 + 0.3 * np.cos(3 * i)).p < 1e-3
    assert wilcoxon(a, a + np.where(i % 2, 0.5, -0.5)).p > 0.5


def test_wilcoxon_too_few():
    assert wilcoxon(np.array([1, 2, np.nan]), np.array([0, 0, 0.0])) == (0, 1, 2)


def test_wilcoxon_sign_of_z():
    a = np.arange(10.0)
    assert wilcoxon(a + 1, a).z > 0 > wilcoxon(a, a + 1).z


def test_mds_recovers_planar_distances():
    pts = np.array([[0, 0], [3, 0], [0, 4], [3, 4.0]])
    d = np.linalg.norm(pts[:, None] - pts[None], axis=-1)
    xy = classical_mds(d)
    assert np.abs(np.linalg.norm(xy[:, None] - xy[None], axis=-1) - d).max() < 1e-9


def test_mds_collinear_points_have_flat_second_axis():
    d = np.abs(np.subtract.outer([0.0, 1, 3], [0.0, 1, 3]))
    xy = classical_mds(d)
    assert np.abs(xy[:, 1]).max() < 1e-6 and abs(abs(xy[2, 0] - xy[0, 0]) - 3) < 1e-9


def test_mds_repeated_eigenvalue_is_deterministic_and_exact():
    # 正三角形：兩個特徵值相同，特徵向量不唯一
    d = 2 * (1 - np.eye(3))
    xy = classical_mds(d)
    assert np.abs(np.linalg.norm(xy[:, None] - xy[None], axis=-1) - d).max() < 1e-9
    assert xy[2, 0] > xy[0, 0]                      # 第一軸朝向遞增的參考向量


def test_correlation_distance_all_nan_row():
    d = correlation_distance(np.array([[1, 2, 3.0], [3, 2, 1.0], [np.nan] * 3]))
    assert d[0, 1] == 2 and d[0, 2] == 2 and d[2, 2] == 0


# ---------- 與現有 JS 在真實資料上的結果比對 ----------
@pytest.mark.parametrize("group", GROUPS)
@pytest.mark.parametrize("which", [0, 1])
def test_golden_mds(ds, golden, group, which):
    ov = golden(group)["overview"][which]
    ids = ds.system_ids()
    rows = [ids.index(s) for s in ov["visible"]]
    profiles = ds.scores[rows, TARGETS.index(ov["target"]), :, METRICS.index(ov["metric"])]
    xy = classical_mds(correlation_distance(profiles))
    dist = np.linalg.norm(xy[:, None] - xy[None], axis=-1)
    np.testing.assert_allclose(dist, ov["mdsDistances"], atol=1e-6)
    np.testing.assert_allclose(xy, ov["mdsXY"], atol=1e-6)      # 沒有鏡射

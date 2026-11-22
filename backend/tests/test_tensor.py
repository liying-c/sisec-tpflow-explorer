import numpy as np
import pytest

from conftest import GROUPS, nan_array, outer
from sisec.tensor import (
    kmeans,
    partition_mode,
    percentile_ranks,
    rank_one,
    recommend_partition,
    successive_rank_one,
)


def test_percentile_ranks_ties():
    assert percentile_ranks(np.array([10, 30, 20, 20.0])).tolist() == [0.125, 0.875, 0.5, 0.5]


def test_percentile_ranks_skips_nan():
    out = percentile_ranks(np.array([3.0, np.nan, 1.0]))
    assert out[[0, 2]].tolist() == [0.75, 0.25] and np.isnan(out[1])


def test_percentile_ranks_keeps_shape():
    assert percentile_ranks(np.array([[4.0, 1.0], [2.0, 3.0]])).tolist() == [[0.875, 0.125], [0.375, 0.625]]


def test_rank_one_recovers_rank_one_tensor():
    X = outer([1, 2, 3], [0.5, 1, 1.5, 2], [2, 1])
    r = rank_one(X)
    assert r.cost < 1e-12
    assert abs(r.vectors[0][2] / r.vectors[0][0] - 3) < 1e-6
    assert all(abs(np.linalg.norm(v) - 1) < 1e-9 and (v >= 0).all() for v in r.vectors)
    assert np.allclose(r.reconstruct(), X)


def test_rank_one_zero_tensor():
    r = rank_one(np.zeros((2, 3)))
    assert r.weight == 0 and r.cost == 0


def test_rank_one_works_on_matrices():
    X = outer([1, 2], [3, 1, 2])
    assert rank_one(X).cost < 1e-12


def test_kmeans_two_blobs():
    a = kmeans(np.array([[0, 0], [0.1, 0], [5, 5], [5.1, 5], [0, 0.1]]), 2)
    assert a[0] == a[1] == a[4] != a[2] == a[3]


def test_kmeans_k_larger_than_n():
    assert len(set(kmeans(np.array([[0.0], [1.0]]), 5).tolist())) == 2


def test_partition_recovers_planted_groups(planted):
    p = partition_mode(planted, 1, 2)
    assert sorted(sorted(g.tolist()) for g in p.groups) == [[0, 1, 2, 3], [4, 5, 6, 7]]
    assert p.cost < 1e-10 <= rank_one(planted).cost


def test_recommend_picks_planted_mode(planted):
    rec = recommend_partition(planted, 2)
    assert rec[0].mode == 1 and [r.cost for r in rec] == sorted(r.cost for r in rec)


def test_successive_weights_decrease(planted):
    c = successive_rank_one(planted, 3)
    assert len(c) >= 2 and c[0].weight >= c[1].weight


def test_partition_single_element_mode():
    assert partition_mode(np.ones((1, 3, 2)), 0, 2) is None


# ---------- 與現有 JS 在真實資料上的結果比對 ----------
def base_tensor(g):
    return np.nan_to_num(nan_array(g["stage"]["pct"]), nan=0.5)


@pytest.mark.parametrize("group", GROUPS)
def test_golden_root_fit(golden, group):
    g = golden(group)
    r = rank_one(base_tensor(g))
    assert r.weight == pytest.approx(g["partition"]["root"]["lambda"], rel=1e-9)
    assert r.cost == pytest.approx(g["partition"]["root"]["cost"], rel=1e-9)


@pytest.mark.parametrize("group", GROUPS)
def test_golden_partitions(golden, group):
    g = golden(group)
    X = base_tensor(g)
    for want in g["partition"]["splits"]:
        mode, k = want["mode"], want["k"]
        got = partition_mode(X, mode, k)
        assert [grp.tolist() for grp in got.groups] == [c["idx"][mode] for c in want["children"]], (mode, k)
        cost = next(r["cost"] for r in want["rec"] if r["mode"] == mode)
        assert got.cost == pytest.approx(cost, rel=1e-9), (mode, k)


@pytest.mark.parametrize("group", GROUPS)
def test_golden_recommendation_order(golden, group):
    g = golden(group)
    X = base_tensor(g)
    for want in g["partition"]["auto"]:
        assert [p.mode for p in recommend_partition(X, want["k"])] == [r["mode"] for r in want["rec"]]

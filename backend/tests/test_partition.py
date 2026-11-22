import numpy as np
import pytest

from conftest import GROUPS, nan_array
from sisec.partition import block, split, summarize

FULL = [range(5), range(8), range(3)]


def test_block_selects_and_reorders():
    X = np.multiply.outer([1, 2.0], [3, 1, 2.0])
    assert block(X, [[0, 1], [2, 0]]).tolist() == [[2, 3], [4, 6]]


def test_root_unexplained_positive(planted):
    assert summarize(planted).unexplained > 0.01


def test_unexplained_of_zero_block_is_zero():
    assert summarize(np.zeros((2, 2, 2))).unexplained == 0


def test_split_planted(planted):
    s = split(planted, FULL, 1, 2)
    assert s.mode == 1 and abs(s.reductions[1] - 1) < 1e-9 and set(s.reductions) == {0, 1, 2}
    assert sorted(sorted(c[1]) for c in s.children) == [[0, 1, 2, 3], [4, 5, 6, 7]]
    assert all(list(c[0]) == [0, 1, 2, 3, 4] for c in s.children)
    child = summarize(block(planted, s.children[0]))
    assert child.unexplained < 1e-10
    m = child.modes[0]
    assert np.abs([m.q1, m.med, m.q3]).max() < 1e-9
    assert (np.diff(m.model) > 0).all() or (np.diff(m.model) < 0).all()
    assert child.representative(0) == 2


def test_split_auto_picks_mode_1(planted):
    assert split(planted, FULL, None, 2).mode == 1


def test_second_level_split_keeps_base_indices(planted):
    first = split(planted, FULL, 1, 2).children[0]
    second = split(planted, first, 0, 2)
    assert all(sorted(c[1]) == sorted(first[1]) for c in second.children)
    assert sorted(i for c in second.children for i in c[0]) == [0, 1, 2, 3, 4]


def test_split_impossible():
    assert split(np.ones((1, 4, 2)), [[0], range(4), range(2)], 0, 2) is None


# ---------- 與現有 JS 在真實資料上的結果比對 ----------
def base_tensor(g):
    return np.nan_to_num(nan_array(g["stage"]["pct"]), nan=0.5)


def assert_summary(got, want, idx):
    assert got.unexplained == pytest.approx(want["unexplained"], abs=1e-9)
    for m, rows in enumerate(want["modes"]):
        assert [r["index"] for r in rows] == list(idx[m])
        for field, key in [("model", "model"), ("q1", "q1"), ("med", "med"), ("q3", "q3"), ("abs_dev", "absDev")]:
            np.testing.assert_allclose(getattr(got.modes[m], field), [r[key] for r in rows], atol=1e-9, rtol=0)
    assert idx[1][got.representative(1)] == want["representativeTrack"]


@pytest.mark.parametrize("group", GROUPS)
def test_golden_root_summary(golden, group):
    g = golden(group)
    X = base_tensor(g)
    idx = [list(range(n)) for n in X.shape]
    assert_summary(summarize(X), g["partition"]["root"], idx)


@pytest.mark.parametrize("group", GROUPS)
def test_golden_splits_and_children(golden, group):
    g = golden(group)
    X = base_tensor(g)
    idx = [list(range(n)) for n in X.shape]
    cases = [(w["mode"], w) for w in g["partition"]["splits"]] + [(None, w) for w in g["partition"]["auto"]]
    for mode, want in cases:
        got = split(X, idx, mode, want["k"])
        assert got.mode == want["mode"]
        assert list(got.reductions) == [r["mode"] for r in want["rec"]]
        np.testing.assert_allclose(list(got.reductions.values()), [r["reduction"] for r in want["rec"]], atol=1e-9)
        assert [[list(ix) for ix in c] for c in got.children] == [c["idx"] for c in want["children"]]
        for child, w in zip(got.children, want["children"]):
            assert_summary(summarize(block(X, child)), w, child)


@pytest.mark.parametrize("group", GROUPS)
def test_golden_second_level(golden, group):
    g = golden(group)
    X = base_tensor(g)
    want = g["partition"]["second"]
    got = split(X, want["parentIdx"], want["mode"], want["k"])
    assert [[list(ix) for ix in c] for c in got.children] == [c["idx"] for c in want["children"]]
    np.testing.assert_allclose(list(got.reductions.values()), [r["reduction"] for r in want["rec"]], atol=1e-9)

import numpy as np
import pytest

from conftest import GROUPS
from sisec.data import METRICS, TARGETS
from sisec.graph import dominance_edges, longest_path_layers, pairwise, transitive_reduction


def test_reduction_and_layers():
    edges = [(0, 1), (1, 2), (0, 2), (0, 3)]
    red = transitive_reduction(4, edges)
    assert sorted(red) == [(0, 1), (0, 3), (1, 2)]
    assert longest_path_layers(4, red) == [0, 1, 2, 1]


def test_pairwise_counts():
    pw = pairwise(np.array([[3, 2, 1, 5.0], [1, 2, 2, np.nan]]))
    assert pw.wins[0, 1] == 1 and pw.wins[1, 0] == 1 and pw.n[0, 1] == 3


def test_clear_winner_gets_an_edge():
    base = np.sin(np.arange(50.0))
    assert dominance_edges(pairwise(np.vstack([base + 1, base]))) == [(0, 1)]


def test_pairwise_nan_profile_makes_no_edge():
    prof = np.vstack([np.arange(50.0), np.full(50, np.nan)])
    assert dominance_edges(pairwise(prof)) == []


@pytest.mark.parametrize("group", GROUPS)
@pytest.mark.parametrize("which", [0, 1])
def test_golden_dominance(ds, golden, group, which):
    ov = golden(group)["overview"][which]
    dom = ov["dominance"]
    order = dom["order"]
    ids = ds.system_ids()
    rows = [ids.index(s) for s in order]
    profiles = ds.scores[rows, TARGETS.index(ov["target"]), :, METRICS.index(ov["metric"])]
    pw = pairwise(profiles)
    assert pw.wins.tolist() == dom["wins"] and pw.n.tolist() == dom["n"]
    np.testing.assert_allclose(pw.p, dom["p"], atol=1e-6)
    edges = dominance_edges(pw)
    assert len(edges) == dom["allEdges"]
    reduced = transitive_reduction(len(order), edges)
    assert [[order[a], order[b]] for a, b in reduced] == dom["edges"]
    assert longest_path_layers(len(order), reduced) == [dom["layers"][s] for s in order]

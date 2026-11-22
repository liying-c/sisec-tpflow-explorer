import pytest

from conftest import GROUPS, assert_close
from sisec import views
from sisec.api import to_json


def pick(rows, keys):
    return [{k: r[k] for k in keys} for r in rows]


@pytest.mark.parametrize("group", GROUPS)
@pytest.mark.parametrize("which", [0, 1])
def test_golden_overview(ds, golden, group, which):
    g = golden(group)
    want = g["overview"][which]
    got = to_json(views.overview(ds, want["metric"], want["target"], frozenset(g["categories"])))
    assert_close(got["ranking"], want["ranking"])
    assert_close(got["leaderboard"], want["leaderboard"])
    assert_close(got["colorDomain"], want["colorDomain"])
    assert_close(got["tracksSorted"], want["tracksSorted"])
    # 姓名大小寫不比：JS 的 \b\w 不認得非 ASCII 字母，會把 Stöter 寫成 StöTer（見下方測試）
    lower = lambda edges: [{**e, "shared": [n.lower() for n in e["shared"]]} for e in edges]
    assert_close(lower(got["authorEdges"]), lower(want["authorEdges"]))
    assert_close(pick(got["map"], ["x", "y"]), [{"x": x, "y": y} for x, y in want["mdsXY"]], atol=1e-6)
    assert [p["system"] for p in got["map"]] == want["visible"]
    dom, wd = got["dominance"], want["dominance"]
    assert dom["order"] == wd["order"] and dom["edges"] == wd["edges"]
    assert dom["allEdges"] == wd["allEdges"] and dom["layers"] == wd["layers"]
    assert dom["wins"] == wd["wins"] and dom["n"] == wd["n"]
    assert_close(dom["p"], wd["p"], atol=1e-6)


def test_overview_profiles_follow_track_ids(ds):
    got = views.overview(ds, "SDR", "vocals", frozenset({"blind"}))
    assert got["trackIds"] == ds.track_ids()
    assert list(got["profiles"]["2DFT"][:1]) == [2.463]          # scores_track.csv 第一列


@pytest.mark.parametrize("group", GROUPS)
def test_golden_stage(ds, golden, group):
    g = golden(group)
    got = to_json(views.stage(ds, frozenset(g["categories"])))
    assert_close(got, g["stage"])


def test_author_names_are_title_cased_with_non_ascii_letters(ds):
    edges = views.overview(ds, "SDR", "vocals", frozenset({"supervised", "supervised+extra", "blind", "oracle"}))["authorEdges"]
    names = {n for e in edges for n in e["shared"]}
    assert "Fabian-Robert Stöter" in names and "Jen-Yu Liu" in names


def test_author_edge_ignores_annotations_and_short_tokens(ds):
    edges = views.overview(ds, "SDR", "vocals", frozenset({"blind"}))["authorEdges"]
    assert all("(" not in n and len(n) > 3 for e in edges for n in e["shared"])

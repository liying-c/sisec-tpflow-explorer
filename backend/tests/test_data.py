import numpy as np

from sisec.data import TARGETS


def test_shape_and_axes(ds):
    assert ds.scores.shape == (31, 5, 50, 4)
    assert len(ds.systems) == 31 and len(ds.tracks) == 50


def test_known_cell(ds):
    s = ds.system_ids().index("2DFT")
    t = ds.track_ids().index("am-contra-heart-peripheral")
    assert ds.scores[s, TARGETS.index("vocals"), t].tolist() == [2.463, 5.230, 3.381, 17.196]


def test_missing_is_nan(ds):
    s = ds.system_ids().index("2DFT")
    assert np.isnan(ds.scores[s, TARGETS.index("drums")]).all()


def test_visible_keeps_file_order(ds):
    idx = ds.visible({"oracle"})
    assert {ds.systems[i]["category"] for i in idx} == {"oracle"}
    assert list(idx) == sorted(idx) and len(idx) == 6


def test_track_duration_is_int(ds):
    assert ds.tracks[0]["duration_s"] == 209

import csv
import itertools
import json

import pytest
from fastapi.testclient import TestClient

from sisec.api import app, get_dataset
from sisec.data import DEFAULT_DATA_DIR, load_dataset

ALL = ["supervised", "supervised+extra", "blind", "oracle"]
FULL = [list(range(31)), list(range(50)), list(range(4))]


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def tiny_client(tmp_path):
    """只有 2 個系統的資料集：階段 2–4 的系統數不足。"""
    keep = None
    for name in ("systems.csv", "tracks.csv", "scores_track.csv"):
        with (DEFAULT_DATA_DIR / name).open(newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        if name == "systems.csv":
            rows = rows[:3]
            keep = {r[0] for r in rows[1:]}
        elif name == "scores_track.csv":
            rows = [rows[0]] + [r for r in rows[1:] if r[0] in keep]
        with (tmp_path / name).open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
    tiny = load_dataset(tmp_path)
    app.dependency_overrides[get_dataset] = lambda: tiny
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_meta(client):
    meta = client.get("/api/meta").json()
    assert len(meta["systems"]) == 31 and len(meta["tracks"]) == 50
    assert meta["systems"][0]["system"] == "2DFT" and meta["tracks"][0]["duration_s"] == 209


def test_readme_findings(client):
    st = client.post("/api/stage", json={"categories": ALL}).json()
    root = client.post("/api/partition/summary", json={"categories": ALL, "idx": FULL}).json()
    assert round(root["unexplained"], 3) == 0.081

    def cut(mode, k):
        return client.post("/api/partition/split", json={"categories": ALL, "idx": FULL, "mode": mode, "k": k}).json()

    def red(r, m):
        return next(x["reduction"] for x in r["reductions"] if x["mode"] == m)

    by_metric = cut(2, 2)
    assert round(red(by_metric, 2), 2) == 0.36
    groups = sorted(sorted(st["metrics"][i] for i in c["idx"][2]) for c in by_metric["children"])
    assert groups == [["ISR", "SAR"], ["SDR", "SIR"]]
    by_system = cut(0, 3)
    assert round(red(by_system, 0), 2) == 0.34
    small = min(by_system["children"], key=lambda c: len(c["idx"][0]))
    assert {st["systems"][i]["system"] for i in small["idx"][0]} == {"MIX", "HPLP", "REP1"}
    assert sorted(len(c["idx"][0]) for c in by_system["children"]) == [3, 13, 15]
    by_track = cut(1, 3)
    assert round(red(by_track, 1), 2) == 0.09
    assert sorted(len(c["idx"][1]) for c in by_track["children"]) == [2, 21, 27]


def test_split_children_carry_their_summaries(client):
    r = client.post("/api/partition/split", json={"categories": ALL, "idx": FULL, "mode": 0, "k": 3}).json()
    child = r["children"][0]
    again = client.post("/api/partition/summary", json={"categories": ALL, "idx": child["idx"]}).json()
    assert child["summary"] == again
    assert [m["index"] for m in again["modes"]] == child["idx"]
    assert again["representativeTrack"] in child["idx"][1]


def test_auto_mode_matches_lowest_cost(client):
    r = client.post("/api/partition/split", json={"categories": ALL, "idx": FULL, "mode": None, "k": 3}).json()
    assert r["ok"] and r["mode"] == r["reductions"][0]["mode"]
    assert len(r["reductions"]) == 3


def test_cluster_shape(client):
    r = client.post("/api/cluster", json={"categories": ALL, "metric": "SDR"}).json()
    assert sorted(r["order"]) == list(range(50)) and len(r["merges"]) == 49
    assert set(r["labels"]) == {"2", "3", "4", "5"} and len(set(r["labels"]["4"])) == 4


SUBSETS = [list(c) for r in range(1, 5) for c in itertools.combinations(ALL, r)]
TARGETS = ["vocals", "drums", "bass", "other", "accompaniment"]
METRICS = ["SDR", "SIR", "SAR", "ISR"]


def strict_json(response):
    """標準 JSON 不允許 NaN / Infinity；Python 預設會放行，這裡明確拒絕。"""
    def reject(token):
        raise AssertionError(f"回應裡出現 {token}")
    return json.loads(response.text, parse_constant=reject)


@pytest.mark.parametrize("cats", SUBSETS, ids=lambda c: "+".join(c))
def test_no_nan_in_any_response(client, cats):
    scope = {"categories": cats}
    for i, target in enumerate(TARGETS):        # 每個 stem 都測；指標輪流，四個都會用到
        r = client.post("/api/overview", json={**scope, "metric": METRICS[i % 4], "target": target})
        assert r.status_code == 200
        strict_json(r)
    st = strict_json(client.post("/api/stage", json=scope))
    full = [list(range(len(st["systems"]))), list(range(len(st["tracks"]))), list(range(4))]
    for metric in METRICS:
        strict_json(client.post("/api/cluster", json={**scope, "metric": metric}))
    strict_json(client.post("/api/partition/summary", json={**scope, "idx": full}))
    for mode in (None, 0, 1, 2):
        strict_json(client.post("/api/partition/split", json={**scope, "idx": full, "mode": mode, "k": 3}))


def test_missing_scores_become_null_and_rank_last(client):
    # drums：盲分離系統整列缺值
    r = client.post("/api/overview", json={"metric": "SIR", "target": "drums", "categories": ALL})
    ranking = r.json()["ranking"]
    blind = [x for x in ranking if x["category"] == "blind"]
    assert len(blind) == 7 and all(x["median"] is None for x in blind)
    assert ranking[-1]["median"] is None and ranking[0]["median"] is not None
    blind_names = {x["system"] for x in blind}
    assert not any(a in blind_names or b in blind_names for a, b in r.json()["dominance"]["edges"])


def test_more_groups_than_elements_gives_one_group_per_element(client):
    # 只有 2 個系統卻要切 5 群：切成 2 群（每個元素一群），不是錯誤
    body = {"categories": ALL, "idx": [[0, 1], list(range(50)), [0, 1, 2, 3]], "mode": 0, "k": 5}
    r = client.post("/api/partition/split", json=body).json()
    assert r["ok"] and sorted(c["idx"][0] for c in r["children"]) == [[0], [1]]


def test_too_few_systems(tiny_client):
    cats = {"categories": ALL}
    st = tiny_client.post("/api/stage", json=cats)
    assert st.status_code == 200 and st.json()["ready"] is False
    assert tiny_client.post("/api/overview", json={**cats, "metric": "SDR", "target": "vocals"}).json()["map"] == []
    assert tiny_client.post("/api/cluster", json={**cats, "metric": "SDR"}).status_code == 422
    assert tiny_client.post("/api/partition/summary", json={**cats, "idx": [[0], [0], [0]]}).status_code == 422
    r = tiny_client.post("/api/partition/split", json={**cats, "idx": [[0], [0], [0]], "mode": None, "k": 2})
    assert r.status_code == 422 and "不足" in r.json()["detail"]


def test_unsplittable_returns_ok_false(client):
    body = {"categories": ALL, "idx": [[0], list(range(50)), [0, 1, 2, 3]], "mode": 0, "k": 2}
    r = client.post("/api/partition/split", json=body)
    assert r.status_code == 200 and r.json() == {"ok": False}


@pytest.mark.parametrize("idx", [[[], [0], [0]], [[99], [0], [0]], [[-1], [0], [0]], [[0, 0], [0], [0]], [[0], [0]]])
def test_bad_index_is_422(client, idx):
    assert client.post("/api/partition/summary", json={"categories": ALL, "idx": idx}).status_code == 422
    body = {"categories": ALL, "idx": idx, "mode": 0, "k": 2}
    assert client.post("/api/partition/split", json=body).status_code == 422


def test_bad_enum_is_422(client):
    assert client.post("/api/overview", json={"metric": "XYZ", "target": "vocals", "categories": ALL}).status_code == 422
    assert client.post("/api/stage", json={"categories": []}).status_code == 422
    assert client.post("/api/stage", json={"categories": ["nope"]}).status_code == 422
    body = {"categories": ALL, "idx": FULL, "mode": 3, "k": 2}
    assert client.post("/api/partition/split", json=body).status_code == 422
    assert client.post("/api/partition/split", json={**body, "mode": 0, "k": 9}).status_code == 422


def test_cors_allows_dev_origin(client):
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"

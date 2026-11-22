"""把分數陣列組成各張圖需要的資料。

這一層決定「哪些系統可見、依什麼排序、哪一塊張量」，演算法本身在其他模組。
回傳的 dict 裡可以有 ndarray 與 NaN，轉成 JSON 是 api.py 的事。
"""
from __future__ import annotations

import re
from dataclasses import asdict
from functools import lru_cache

import numpy as np

from . import partition
from .cluster import hclust
from .data import METRICS, TARGETS, Dataset
from .graph import dominance_edges, longest_path_layers, pairwise, transitive_reduction
from .stats import classical_mds, correlation_distance, nanmedian
from .tensor import percentile_ranks

ALPHA = 0.05
STAGE_TARGET = "vocals"   # 階段 2–4 固定看人聲：唯一涵蓋全部 31 個系統的目標
MIN_STAGE_SYSTEMS = 3
CLUSTER_KS = (2, 3, 4, 5)


class NotEnoughSystems(ValueError):
    def __init__(self):
        super().__init__("可見系統不足，無法計算")


def _frozen(value):
    """把結果裡的每個陣列設成唯讀後原樣回傳。

    下面的結果會被 lru_cache 留著重複回傳；陣列若可寫，一次就地修改會汙染之後所有請求。
    """
    if isinstance(value, np.ndarray):
        value.setflags(write=False)
    elif isinstance(value, dict):
        for v in value.values():
            _frozen(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _frozen(v)
    return value


# ---------- 排序 ----------
def _best_first(values: np.ndarray) -> np.ndarray:
    """由大到小的穩定排序，缺值排最後。"""
    return np.argsort(-np.where(np.isfinite(values), values, -np.inf), kind="stable")


def _hardest_first(values: np.ndarray) -> np.ndarray:
    """由小到大的穩定排序，缺值排最後。"""
    return np.argsort(np.where(np.isfinite(values), values, np.inf), kind="stable")


def _difficulty(ds: Dataset, systems: np.ndarray, profiles: np.ndarray) -> np.ndarray:
    """曲目難度 = 非 oracle 系統在該曲的中位數；沒有非 oracle 系統時用全部。profiles 的列對應 systems。"""
    pool = np.array([ds.systems[i]["category"] != "oracle" for i in systems])
    return nanmedian(profiles[pool] if pool.any() else profiles, axis=0)


def _system_row(ds: Dataset, i: int, median: float) -> dict:
    return {"system": ds.systems[i]["system"], "category": ds.systems[i]["category"], "median": median}


# ---------- 共同作者 ----------
def _authors(field: str) -> list[str]:
    """作者字串 → 正規化後的姓名（去掉「(implementation author)」這類註記），保持順序、不重複。"""
    names = (re.sub(r"\(.*?\)", "", part).strip().lower() for part in re.split(r",| and ", field or "", flags=re.I))
    return list(dict.fromkeys(name for name in names if len(name) > 3))


def _author_edges(ds: Dataset, systems: np.ndarray) -> list[dict]:
    authors = [_authors(ds.systems[i]["authors"]) for i in systems]
    edges = []
    for a in range(len(systems)):
        for b in range(a + 1, len(systems)):
            shared = [name for name in authors[a] if name in authors[b]]
            if shared:
                edges.append({
                    "a": ds.systems[systems[a]]["system"],
                    "b": ds.systems[systems[b]]["system"],
                    "shared": [re.sub(r"\b\w", lambda m: m.group().upper(), name) for name in shared],
                })
    return edges


# ---------- 階段 1：一個指標、一個 stem ----------
def meta(ds: Dataset) -> dict:
    return {"systems": list(ds.systems), "tracks": list(ds.tracks)}


@lru_cache(maxsize=128)
def overview(ds: Dataset, metric: str, target: str, categories: frozenset[str]) -> dict:
    m, g = METRICS.index(metric), TARGETS.index(target)
    vis = ds.visible(categories)
    names = [ds.systems[i]["system"] for i in vis]
    profiles = ds.scores[vis, g, :, m]                       # (可見系統, 曲目)
    medians = nanmedian(profiles, axis=1)
    by_target = nanmedian(ds.scores[vis, :, :, m], axis=2)   # (可見系統, 目標)
    order = _best_first(medians)

    ranking = [_system_row(ds, vis[i], medians[i]) for i in order]
    leaderboard = [{**row, "values": dict(zip(TARGETS, by_target[i]))} for row, i in zip(ranking, order)]

    # 色階範圍：可見系統在所有 stem 上的分數，取 5% 與 99% 分位數（避開極端值）
    finite = ds.scores[vis, :, :, m]
    finite = finite[np.isfinite(finite)]
    color_domain = np.quantile(finite, [0.05, 0.99]) if finite.size else [0, 10]

    difficulty = _difficulty(ds, vis, profiles)
    tracks_sorted = [{**ds.tracks[t], "difficulty": difficulty[t]} for t in _hardest_first(difficulty)]

    # 方法地圖：距離 = sqrt(2(1 − r))
    points = []
    if len(vis) >= 3:
        xy = classical_mds(correlation_distance(profiles))
        points = [{**_system_row(ds, vis[i], medians[i]), "x": xy[i, 0], "y": xy[i, 1]} for i in range(len(vis))]

    # 優勢圖：依排行順序兩兩比較
    pw = pairwise(profiles[order])
    edges = dominance_edges(pw, ALPHA)
    reduced = transitive_reduction(len(order), edges)
    ranked = [names[i] for i in order]
    dominance = {
        "order": ranked,
        "edges": [[ranked[a], ranked[b]] for a, b in reduced],
        "allEdges": len(edges),
        "layers": dict(zip(ranked, longest_path_layers(len(order), reduced))),
        "wins": pw.wins, "n": pw.n, "p": pw.p,
    }
    return _frozen({
        "ranking": ranking, "leaderboard": leaderboard,
        "trackIds": ds.track_ids(), "profiles": dict(zip(names, profiles)),
        "colorDomain": color_domain, "tracksSorted": tracks_sorted,
        "map": points, "authorEdges": _author_edges(ds, vis), "dominance": dominance,
    })


# ---------- 階段 2–4：人聲、四個指標 ----------
@lru_cache(maxsize=4)
def _percentiles(ds: Dataset) -> np.ndarray:
    """(系統, 曲目, 指標) 的百分位：每個指標各自對「全部系統 × 全部曲目」的人聲分數排名。

    四個指標尺度不同、dB 有負值，轉換後才能放進同一個非負張量。不受類別篩選影響。
    """
    vocals = ds.scores[:, TARGETS.index(STAGE_TARGET)]
    return _frozen(np.stack([percentile_ranks(vocals[..., m]) for m in range(len(METRICS))], axis=-1))


@lru_cache(maxsize=32)
def _stage_axes(ds: Dataset, categories: frozenset[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """階段 2–4 的列與欄：系統依人聲 SDR 中位數由高到低，曲目由難到易。回傳 (系統, 中位數, 曲目, 難度)。"""
    vis = ds.visible(categories)
    sdr = ds.scores[vis, TARGETS.index(STAGE_TARGET), :, METRICS.index("SDR")]
    medians = nanmedian(sdr, axis=1) if len(vis) else np.array([])
    keep = np.isfinite(medians)
    vis, sdr, medians = vis[keep], sdr[keep], medians[keep]
    order = _best_first(medians)
    systems, sdr, medians = vis[order], sdr[order], medians[order]
    difficulty = _difficulty(ds, systems, sdr) if len(systems) else np.full(len(ds.tracks), np.nan)
    tracks = _hardest_first(difficulty)
    return _frozen((systems, medians, tracks, difficulty[tracks]))


@lru_cache(maxsize=32)
def stage(ds: Dataset, categories: frozenset[str]) -> dict:
    systems, medians, tracks, difficulty = _stage_axes(ds, categories)
    cells = np.ix_(systems, tracks)
    vis = ds.visible(categories)
    anchor = nanmedian(ds.scores[vis, TARGETS.index(STAGE_TARGET)], axis=1) if len(vis) else []   # (可見系統, 指標)
    return _frozen({
        "ready": len(systems) >= MIN_STAGE_SYSTEMS,
        "systems": [_system_row(ds, i, med) for i, med in zip(systems, medians)],
        "tracks": [{**ds.tracks[t], "difficulty": d} for t, d in zip(tracks, difficulty)],
        "metrics": list(METRICS),
        "pct": _percentiles(ds)[cells],
        "raw": ds.scores[:, TARGETS.index(STAGE_TARGET)][cells],
        "anchor": [
            {"system": ds.systems[i]["system"], "category": ds.systems[i]["category"], **dict(zip(METRICS, row))}
            for i, row in zip(vis, anchor)
        ],
    })


@lru_cache(maxsize=32)
def base_tensor(ds: Dataset, categories: frozenset[str]) -> np.ndarray:
    """系統 × 曲目 × 指標的百分位張量（缺值以中間值 0.5 代替），順序同 stage()。"""
    systems, _, tracks, _ = _stage_axes(ds, categories)
    if len(systems) < MIN_STAGE_SYSTEMS:
        raise NotEnoughSystems
    return _frozen(np.nan_to_num(_percentiles(ds)[np.ix_(systems, tracks)], nan=0.5))


@lru_cache(maxsize=128)
def cluster(ds: Dataset, categories: frozenset[str], metric: str) -> dict:
    """圖 6：每首歌的特徵 = 它那一欄（各系統在該指標的百分位）。"""
    songs = base_tensor(ds, categories)[:, :, METRICS.index(metric)].T
    tree = hclust(songs)
    return {
        "order": list(tree.order),
        "merges": [asdict(m) for m in tree.merges],
        "labels": {str(k): tree.cut(k) for k in CLUSTER_KS},
    }


# ---------- 分割樹 ----------
def check_index(shape: tuple[int, ...], idx: partition.Index) -> None:
    if len(idx) != len(shape):
        raise ValueError(f"idx 必須有 {len(shape)} 個維度")
    for size, ix in zip(shape, idx):
        if not ix or len(set(ix)) != len(ix) or min(ix) < 0 or max(ix) >= size:
            raise ValueError("idx 的每個維度必須是不重複、在範圍內的非空清單")


def _summary(base: np.ndarray, idx: partition.Index) -> dict:
    s = partition.summarize(partition.block(base, idx))
    return {
        "unexplained": s.unexplained,
        "modes": [
            {"index": list(ix), "model": m.model, "q1": m.q1, "med": m.med, "q3": m.q3, "absDev": m.abs_dev}
            for ix, m in zip(idx, s.modes)
        ],
        "representativeTrack": idx[1][s.representative(1)],
    }


def partition_summary(ds: Dataset, categories: frozenset[str], idx: partition.Index) -> dict:
    base = base_tensor(ds, categories)
    check_index(base.shape, idx)
    return _summary(base, idx)


def partition_split(ds: Dataset, categories: frozenset[str], idx: partition.Index, mode: int | None, k: int) -> dict:
    base = base_tensor(ds, categories)
    check_index(base.shape, idx)
    result = partition.split(base, idx, mode, k)
    if result is None:
        return {"ok": False}
    return {
        "ok": True,
        "mode": result.mode,
        "reductions": [{"mode": m, "reduction": r} for m, r in result.reductions.items()],
        "children": [{"idx": child, "summary": _summary(base, child)} for child in result.children],
    }

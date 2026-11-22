"""TPFlow（Liu, Xu & Ren, IEEE TVCG 2019）第 3 節：piecewise rank-one tensor decomposition。

張量就是 ndarray。numpy 只負責算術（收縮、範數、排序）；每個演算法的步驟都寫在這裡，
對照論文的式子。輸入必須是完整（無 NaN）的張量。
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import reduce

import numpy as np


# ---------- 名次與百分位 ----------
def average_ranks(values: np.ndarray) -> np.ndarray:
    """一維陣列的名次（從 1 開始），同值取平均名次。"""
    _, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
    last = np.cumsum(counts)                    # 每組同值的最後一個名次
    return (last - (counts - 1) / 2)[inverse]


def percentile_ranks(values: np.ndarray) -> np.ndarray:
    """(平均名次 − 0.5) / n，值域 (0, 1)。只在有限值之間排名，其餘保留為 NaN。"""
    values = np.asarray(values, dtype=float)
    out = np.full(values.shape, np.nan)
    ok = np.isfinite(values)
    if ok.any():
        out[ok] = (average_ranks(values[ok]) - 0.5) / ok.sum()
    return out


# ---------- rank-one 近似（交替最小平方法） ----------
@dataclass(frozen=True, eq=False)
class RankOne:
    """X ≈ λ · v₀ ⊗ v₁ ⊗ …，每個 v 是單位向量。"""

    weight: float                     # λ
    vectors: tuple[np.ndarray, ...]
    cost: float                       # 殘差平方和；可加總，子張量的 cost 相加可與母張量比較

    def reconstruct(self) -> np.ndarray:
        return self.weight * reduce(np.multiply.outer, self.vectors)


def _contract_others(X: np.ndarray, vectors: list[np.ndarray], mode: int) -> np.ndarray:
    """把 mode 以外的每個維度都與它的向量收縮掉，剩下 mode 上的一個向量。

    三維時就是 einsum("ijk,j,k->i", X, b, c)。由後往前收縮，前面維度的軸編號才不會變。
    """
    for axis in reversed(range(X.ndim)):
        if axis != mode:
            X = np.tensordot(X, vectors[axis], axes=(axis, 0))
    return X


def rank_one(X: np.ndarray, *, nonneg: bool = True, iters: int = 200, tol: float = 1e-10) -> RankOne:
    """固定其他維度時，某一維的最小平方解就是把張量與其他向量收縮後正規化；輪流更新到收斂。

    nonneg 為真時把負值截為 0（論文對第一組 loading vectors 的限制）。
    """
    X = np.asarray(X, dtype=float)
    vectors = [np.full(n, 1 / np.sqrt(n)) for n in X.shape]
    weight = 0.0
    for _ in range(iters):
        change = 0.0
        for mode in range(X.ndim):
            w = _contract_others(X, vectors, mode)
            if nonneg:
                w = w.clip(min=0)
            norm = np.linalg.norm(w)
            if norm == 0:
                return RankOne(0.0, tuple(vectors), float(np.sum(X**2)))
            w = w / norm
            change += np.abs(w - vectors[mode]).sum()
            vectors[mode], weight = w, float(norm)
        if change < tol:
            break
    fit = RankOne(weight, tuple(vectors), 0.0)
    return RankOne(weight, fit.vectors, float(np.sum((X - fit.reconstruct()) ** 2)))


def successive_rank_one(X: np.ndarray, rank: int = 3) -> list[RankOne]:
    """連續分解：第 1 組非負，之後對殘差再做 rank-one（不限制正負）。"""
    components: list[RankOne] = []
    residual = np.asarray(X, dtype=float)
    for r in range(rank):
        fit = rank_one(residual, nonneg=(r == 0))
        if fit.weight == 0:
            break
        components.append(fit)
        residual = residual - fit.reconstruct()
    return components


# ---------- k-means（確定性初始化：farthest-first） ----------
def _sq_dists(points: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """(n, d) 與 (k, d) → (n, k) 的平方歐氏距離。"""
    return ((points[:, None, :] - centers[None, :, :]) ** 2).sum(axis=-1)


def kmeans(points: np.ndarray, k: int, iters: int = 100) -> np.ndarray:
    """回傳每個點的群編號。初始化不用亂數，重新整理後結果相同。"""
    points = np.asarray(points, dtype=float)
    k = min(k, len(points))
    # 第一個中心取離整體平均最遠的點，之後每次取離已選中心最遠的點
    centers = [points[np.argmax(_sq_dists(points, points.mean(axis=0)[None]))]]
    while len(centers) < k:
        nearest = _sq_dists(points, np.array(centers)).min(axis=1)
        centers.append(points[np.argmax(nearest)])
    centers = np.array(centers)

    labels = np.full(len(points), -1)
    for _ in range(iters):
        nearest = _sq_dists(points, centers).argmin(axis=1)
        if np.array_equal(nearest, labels):
            break
        labels = nearest
        for g in range(k):
            members = points[labels == g]
            if len(members):                     # 空群的中心留在原地
                centers[g] = members.mean(axis=0)
    return labels


# ---------- 沿一個維度分割（論文式 2 的近似解） ----------
@dataclass(frozen=True, eq=False)
class Partition:
    mode: int
    groups: tuple[np.ndarray, ...]    # 該維度上的索引，依群內第一特徵的平均由大到小
    cost: float                       # 各群 rank-one cost 的總和


def partition_mode(X: np.ndarray, mode: int, k: int, rank: int = 3) -> Partition | None:
    """1. 連續分解取前 rank 組；2. 該維度上每個元素的特徵 = (λ₁·v₁[j], …, λ_R·v_R[j])；
    3. k-means 分成 k 群；4. 每群各自做非負 rank-one。該維度不足 2 個元素時回傳 None。
    """
    n = X.shape[mode]
    if n < 2:
        return None
    components = successive_rank_one(X, rank)
    features = np.column_stack([c.weight * c.vectors[mode] for c in components])
    labels = kmeans(features, min(k, n))
    groups = [np.flatnonzero(labels == g) for g in range(k)]
    groups = sorted((g for g in groups if len(g)), key=lambda g: -features[g, 0].mean())
    cost = sum(rank_one(np.take(X, g, axis=mode)).cost for g in groups)
    return Partition(mode, tuple(groups), float(cost))


def recommend_partition(X: np.ndarray, k: int, rank: int = 3) -> list[Partition]:
    """每個維度都試切，依分割後的總 cost 由小到大排序。"""
    tried = (partition_mode(X, mode, k, rank) for mode in range(X.ndim))
    return sorted((p for p in tried if p is not None), key=lambda p: p.cost)

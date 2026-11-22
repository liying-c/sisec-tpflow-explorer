"""統計工具：中位數、相關、古典 MDS、Wilcoxon signed-rank test。

numpy 只當算術用，每個方法的步驟都寫在這裡。缺值一律是 NaN。
"""
from __future__ import annotations

import math
import warnings
from typing import NamedTuple

import numpy as np

from .tensor import average_ranks


def nanmedian(a: np.ndarray, axis: int | None = None):
    """忽略 NaN 的中位數；整段都是 NaN 時回傳 NaN（不發警告）。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(a, axis=axis)


def pearson(x: np.ndarray, y: np.ndarray) -> float:
    """Pearson 相關係數，只用兩邊都有值的配對。配對不足 3 個或其中一方沒有變異時為 NaN。"""
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3:
        return math.nan
    dx, dy = x[ok] - x[ok].mean(), y[ok] - y[ok].mean()
    sxx, syy = dx @ dx, dy @ dy
    return float(dx @ dy / math.sqrt(sxx * syy)) if sxx > 0 and syy > 0 else math.nan


def correlation_distance(profiles: np.ndarray) -> np.ndarray:
    """(n, 樣本) → (n, n) 的距離 d = sqrt(2(1 − r))，即標準化剖面之間的歐氏距離。

    r 算不出來（缺值太多）時取最大距離 2。
    """
    n = len(profiles)
    dist = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            r = pearson(profiles[i], profiles[j])
            dist[i, j] = dist[j, i] = 2.0 if math.isnan(r) else math.sqrt(max(0.0, 2 * (1 - r)))
    return dist


def _toward(reference: np.ndarray, space: np.ndarray, taken: list[np.ndarray]) -> np.ndarray:
    """space（欄為正交基底）裡與 taken 正交、且最靠近 reference 的單位向量。

    reference 在剩下的方向上已經沒有分量時（同一個特徵空間要取第二軸），
    改用它的平方、立方……：這些向量線性獨立，所以一定找得到，而且結果不取決於 space 用哪一組基底。
    """
    for power in range(1, len(reference) + 1):
        target = reference**power
        v = space @ (space.T @ target)
        for t in taken:
            v = v - (t @ v) * t
        norm = np.linalg.norm(v)
        if norm > 1e-9 * np.linalg.norm(target):
            return v / norm
    raise ValueError("space 的維度不足")


def classical_mds(dist: np.ndarray) -> np.ndarray:
    """古典 MDS（Torgerson）：距離矩陣 → n 個二維座標。

    B = −½ · J D² J（雙中心化），取 B 最大的兩個特徵對，座標 = v · √λ。

    特徵向量並不唯一：正負號任意，特徵值重複時整個特徵空間裡的方向都可以。
    這裡固定取「特徵空間中最靠近一個遞增參考向量」的方向，結果才確定、畫面也不會鏡射。
    （特徵值重複會實際發生：沒有分數的系統彼此距離都是 2，形成一個正單體。）
    """
    n = len(dist)
    centering = np.eye(n) - 1 / n
    B = -0.5 * centering @ (np.asarray(dist, dtype=float) ** 2) @ centering
    values, vectors = np.linalg.eigh(B)
    values, vectors = values[::-1], vectors[:, ::-1]          # 由大到小
    tol = 1e-8 * max(abs(values[0]), abs(values[-1]), 1e-300)
    reference = 1 + 0.01 * np.arange(n)

    coords = np.zeros((n, 2))
    taken: list[np.ndarray] = []
    start = 0                                                  # 目前特徵空間的第一欄
    for axis in range(2):
        if start >= n or values[start] <= tol:
            break
        stop = start + int(np.sum(values[start:] >= values[start] - tol))
        v = _toward(reference, vectors[:, start:stop], taken)
        coords[:, axis] = v * math.sqrt(values[start])
        taken.append(v)
        if len(taken) == stop - start:                         # 這個特徵空間用完了，換下一個
            start, taken = stop, []
    return coords


class Wilcoxon(NamedTuple):
    z: float
    p: float   # 雙尾
    n: int     # 非零差值的個數


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def wilcoxon(a: np.ndarray, b: np.ndarray) -> Wilcoxon:
    """Wilcoxon signed-rank test（配對樣本，常態近似，含同值修正）。

    n ≥ 20 時常態近似已足夠；這裡 n = 50 首歌。非零差值不足 6 個時不檢定，回傳 p = 1。
    """
    d = a - b
    d = d[np.isfinite(d) & (d != 0)]
    n = len(d)
    if n < 6:
        return Wilcoxon(0, 1, n)
    ranks = average_ranks(np.abs(d))
    w_plus = ranks[d > 0].sum()
    ties = np.unique(np.abs(d), return_counts=True)[1]
    mean = n * (n + 1) / 4
    variance = n * (n + 1) * (2 * n + 1) / 24 - (ties**3 - ties).sum() / 48
    z = float((w_plus - mean) / math.sqrt(variance))
    return Wilcoxon(z, 2 * (1 - _normal_cdf(abs(z))), n)

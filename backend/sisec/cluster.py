"""階層式分群（average linkage、歐氏距離），供 cluster heatmap 使用。"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Merge:
    a: int          # 被合併的兩群；葉節點 id 為 0…n−1
    b: int
    id: int         # 新群的 id：第 i 次合併產生 n+i
    height: float   # 合併時兩群的距離
    size: int


@dataclass(frozen=True)
class Dendrogram:
    n: int
    merges: tuple[Merge, ...]
    order: tuple[int, ...]   # 葉節點由左到右

    def cut(self, k: int) -> list[int]:
        """把樹切成 k 群：反覆拆開高度最大的那個節點。回傳每個點的群編號。"""
        by_id = {m.id: m for m in self.merges}
        height = lambda node: by_id[node].height if node in by_id else -np.inf
        parts = [self.merges[-1].id] if self.merges else [0]
        while len(parts) < min(k, self.n):
            at = max(range(len(parts)), key=lambda i: height(parts[i]))   # 平手取最前面
            top = by_id[parts[at]]
            parts[at : at + 1] = [top.a, top.b]
        labels = [0] * self.n
        for group, node in enumerate(parts):
            for leaf in self._leaves(node, by_id):
                labels[leaf] = group
        return labels

    @staticmethod
    def _leaves(node: int, by_id: dict[int, Merge]) -> list[int]:
        if node not in by_id:
            return [node]
        m = by_id[node]
        return Dendrogram._leaves(m.a, by_id) + Dendrogram._leaves(m.b, by_id)


def hclust(points: np.ndarray) -> Dendrogram:
    """每一步合併距離最近的兩群；新群到其他群的距離是兩個舊距離依成員數的加權平均
    （Lance–Williams 更新式，等同於兩群所有成員兩兩距離的平均）。
    """
    points = np.asarray(points, dtype=float)
    n = len(points)
    # 距離矩陣預留合併後新群的位置；尚未存在或已被合併的群距離為 inf
    dist = np.full((2 * n - 1, 2 * n - 1), np.inf)
    dist[:n, :n] = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=-1)
    size = np.ones(2 * n - 1, dtype=int)
    active = list(range(n))            # 現存的群，依建立順序
    merges: list[Merge] = []

    for new in range(n, 2 * n - 1):
        sub = dist[np.ix_(active, active)]
        sub[np.tril_indices(len(active))] = np.inf          # 只看 i < j 的配對
        i, j = np.unravel_index(np.argmin(sub), sub.shape)  # 平手取最先遇到的一對
        a, b = active[i], active[j]
        height = float(sub[i, j])
        size[new] = size[a] + size[b]
        merged = (dist[a] * size[a] + dist[b] * size[b]) / size[new]
        active = [c for c in active if c not in (a, b)]
        dist[new, active] = dist[active, new] = merged[active]
        active.append(new)
        merges.append(Merge(a, b, new, height, int(size[new])))

    by_id = {m.id: m for m in merges}
    root = merges[-1].id if merges else 0
    return Dendrogram(n, tuple(merges), tuple(Dendrogram._leaves(root, by_id)))

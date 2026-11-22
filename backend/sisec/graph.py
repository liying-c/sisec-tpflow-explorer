"""優勢圖：兩兩比較 → 顯著優於的邊 → 遞移化簡 → 分層（Hasse diagram）。

節點用 0…n−1 的整數表示，輸入的剖面已依排行由高到低排序。
"""
from __future__ import annotations

from functools import cache
from typing import NamedTuple

import numpy as np

from .stats import wilcoxon

Edge = tuple[int, int]   # (a, b)：a 顯著優於 b


class Pairwise(NamedTuple):
    """皆為 (n, n)；[i, j] 是「i 對 j」。"""

    wins: np.ndarray   # i 贏過 j 的樣本數（相同不算贏）
    n: np.ndarray      # 兩邊都有值的樣本數
    p: np.ndarray      # Wilcoxon 雙尾 p 值（對稱）


def pairwise(profiles: np.ndarray) -> Pairwise:
    ok = np.isfinite(profiles)
    both = ok[:, None, :] & ok[None, :, :]
    wins = ((profiles[:, None, :] > profiles[None, :, :]) & both).sum(axis=-1)
    count = len(profiles)
    p = np.ones((count, count))
    for i in range(count):
        for j in range(i + 1, count):
            p[i, j] = p[j, i] = wilcoxon(profiles[i], profiles[j]).p
    return Pairwise(wins, both.sum(axis=-1), p)


def dominance_edges(pw: Pairwise, alpha: float = 0.05) -> list[Edge]:
    """排行較前的 i 顯著優於 j：p < alpha 且勝率過半。"""
    count = len(pw.p)
    return [
        (i, j)
        for i in range(count)
        for j in range(i + 1, count)
        if pw.p[i, j] < alpha and pw.n[i, j] and pw.wins[i, j] / pw.n[i, j] > 0.5
    ]


def transitive_reduction(n: int, edges: list[Edge]) -> list[Edge]:
    """去掉可由其他邊推得的邊：a→b 多餘，若 a 的另一個直接後繼能走到 b。假設無環。"""
    successors = [set() for _ in range(n)]
    for a, b in edges:
        successors[a].add(b)

    @cache
    def reachable(a: int) -> frozenset[int]:
        return frozenset(successors[a]).union(*(reachable(b) for b in successors[a]))

    return [(a, b) for a, b in edges if not any(b in reachable(c) for c in successors[a] - {b})]


def longest_path_layers(n: int, edges: list[Edge]) -> list[int]:
    """最長路徑分層：0 表示沒有人顯著優於它（頂層）。假設無環。"""
    predecessors = [[] for _ in range(n)]
    for a, b in edges:
        predecessors[b].append(a)

    @cache
    def layer(node: int) -> int:
        return 1 + max(map(layer, predecessors[node]), default=-1)

    return [layer(node) for node in range(n)]

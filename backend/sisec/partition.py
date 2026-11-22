"""分割樹的計算：TPFlow 的漸進式分割流程。

樹的形狀由呼叫端保存；這裡的每個函式都只吃「基底張量 + 每個維度的索引清單」，
算出那一塊子張量的 rank-one 摘要、偏差，或把它再切開。
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .tensor import RankOne, rank_one, recommend_partition

Index = Sequence[Sequence[int]]   # 每個維度在基底張量上的索引清單


def block(base: np.ndarray, idx: Index) -> np.ndarray:
    """基底張量中由 idx 指定的那一塊子張量。"""
    return base[np.ix_(*idx)]


@dataclass(frozen=True, eq=False)
class ModeSummary:
    """一塊子張量在某個維度上的摘要，每個欄位一個元素一筆。"""

    model: np.ndarray     # 摘要對該元素的平均重建值：λ · v[j] · 其他維度向量的平均（單位同資料）
    q1: np.ndarray        # 該元素所有格子「原始 − 重建」的四分位數
    med: np.ndarray       #   （論文 4.2.3 的偏差；用絕對差而非相對差，
    q3: np.ndarray        #    因為百分位接近 0 時相對差會失真）
    abs_dev: np.ndarray   # 平均絕對偏差


@dataclass(frozen=True, eq=False)
class BlockSummary:
    fit: RankOne
    unexplained: float    # 摘要沒解釋到的比例：殘差平方和 / 總平方和
    modes: tuple[ModeSummary, ...]

    def representative(self, mode: int) -> int:
        """摘要值位於中位數的元素（最「典型」的一首歌或一個系統）。

        不用「偏差最小」：分數趨近 0 的元素（例如沒有人聲的純演奏曲）偏差必然最小，卻最不典型。
        """
        order = np.argsort(self.modes[mode].model, kind="stable")
        return int(order[len(order) // 2])


def _mode_summary(residual: np.ndarray, fit: RankOne, mode: int) -> ModeSummary:
    cells = np.moveaxis(residual, mode, 0).reshape(residual.shape[mode], -1)
    q1, med, q3 = np.quantile(cells, [0.25, 0.5, 0.75], axis=1)
    others = np.prod([v.mean() for m, v in enumerate(fit.vectors) if m != mode])
    return ModeSummary(fit.weight * others * fit.vectors[mode], q1, med, q3, np.abs(cells).mean(axis=1))


def summarize(X: np.ndarray) -> BlockSummary:
    fit = rank_one(X)
    total = float(np.sum(X**2))
    residual = X - fit.reconstruct()
    modes = tuple(_mode_summary(residual, fit, m) for m in range(X.ndim))
    return BlockSummary(fit, fit.cost / total if total > 0 else 0.0, modes)


@dataclass(frozen=True, eq=False)
class Split:
    mode: int
    reductions: dict[int, float]            # 每個可切的維度的誤差降幅，依分割後 cost 由小到大
    children: tuple[tuple[tuple[int, ...], ...], ...]   # 每個子塊的基底索引


def split(base: np.ndarray, idx: Index, mode: int | None, k: int) -> Split | None:
    """把 idx 指定的那一塊沿 mode 切成 k 群；mode=None 表示採用自動推薦（cost 最小的維度）。

    該維度切不動、或只切出 1 群時回傳 None。
    """
    X = block(base, idx)
    options = recommend_partition(X, k)
    chosen = next((p for p in options if mode is None or p.mode == mode), None)
    if chosen is None or len(chosen.groups) < 2:
        return None
    before = rank_one(X).cost
    reductions = {p.mode: (1 - p.cost / before if before > 0 else 0.0) for p in options}
    children = tuple(
        tuple(
            tuple(int(ix[j]) for j in group) if m == chosen.mode else tuple(int(i) for i in ix)
            for m, ix in enumerate(idx)
        )
        for group in chosen.groups
    )
    return Split(chosen.mode, reductions, children)

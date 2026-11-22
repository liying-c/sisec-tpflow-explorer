"""資料載入：把 prepare_data.py 產生的 CSV 整理成一個四維分數陣列。

scores[系統, 目標, 曲目, 指標]，缺值為 NaN。之後「某系統在某 stem、某指標上的
50 首歌剖面」就只是一次索引：scores[s, g, :, m]。
"""
from __future__ import annotations

import csv
import math
import os
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

import numpy as np

METRICS = ("SDR", "SIR", "SAR", "ISR")
TARGETS = ("vocals", "drums", "bass", "other", "accompaniment")
CATEGORIES = ("supervised", "supervised+extra", "blind", "oracle")

DEFAULT_DATA_DIR = Path(
    os.environ.get("SISEC_DATA_DIR", Path(__file__).resolve().parents[2] / "public" / "data")
)


@dataclass(frozen=True)
class Dataset:
    systems: tuple[dict, ...]  # systems.csv 的列，順序同檔案
    tracks: tuple[dict, ...]   # tracks.csv 的列；duration_s 為 int
    scores: np.ndarray         # (系統, 目標, 曲目, 指標)，float64，缺值 NaN

    def system_ids(self) -> list[str]:
        return [s["system"] for s in self.systems]

    def track_ids(self) -> list[str]:
        return [t["track_id"] for t in self.tracks]

    def visible(self, categories: Collection[str]) -> np.ndarray:
        """類別在 categories 內的系統索引，保持檔案順序。"""
        return np.array(
            [i for i, s in enumerate(self.systems) if s["category"] in categories], dtype=int
        )


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _score(text: str) -> float:
    """CSV 的一格 → 分數；空字串、非數字、±inf 都當缺值。"""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return math.nan
    return value if math.isfinite(value) else math.nan


def load_dataset(data_dir: Path = DEFAULT_DATA_DIR) -> Dataset:
    data_dir = Path(data_dir)
    systems = tuple(_read(data_dir / "systems.csv"))
    tracks = tuple({**t, "duration_s": int(t["duration_s"])} for t in _read(data_dir / "tracks.csv"))

    system_at = {s["system"]: i for i, s in enumerate(systems)}
    track_at = {t["track_id"]: i for i, t in enumerate(tracks)}
    target_at = {g: i for i, g in enumerate(TARGETS)}

    scores = np.full((len(systems), len(TARGETS), len(tracks), len(METRICS)), np.nan)
    for row in _read(data_dir / "scores_track.csv"):
        cell = system_at[row["system"]], target_at[row["target"]], track_at[row["track_id"]]
        scores[cell] = [_score(row[m]) for m in METRICS]
    scores.setflags(write=False)
    return Dataset(systems, tracks, scores)

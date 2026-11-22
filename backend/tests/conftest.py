import json
from functools import reduce
from pathlib import Path

import numpy as np
import pytest

from sisec.data import DEFAULT_DATA_DIR, load_dataset

GOLDEN_DIR = Path(__file__).parent / "golden"
GROUPS = ("all", "no-oracle")


@pytest.fixture(scope="session")
def ds():
    return load_dataset(DEFAULT_DATA_DIR)


@pytest.fixture(scope="session")
def golden():
    """golden("all") → 現有 JS 在真實資料上的輸出（tests/dump_golden.mjs 產生）。"""
    cache = {}

    def load(name):
        if name not in cache:
            cache[name] = json.loads((GOLDEN_DIR / f"{name}.json").read_text())
        return cache[name]

    return load


def outer(*vectors):
    """向量的外積：rank-one 張量。"""
    return reduce(np.multiply.outer, [np.asarray(v, dtype=float) for v in vectors])


def nan_array(nested):
    """JSON 的巢狀清單 → ndarray，null 轉成 NaN。"""
    return np.array(nested, dtype=float)


@pytest.fixture
def planted():
    """維度 1 的前 4 個與後 4 個元素，在維度 0 上的分佈相反。"""
    a = outer([1, 2, 3, 4, 5], [1, 1.2, 0.9, 1.1], [1, 2, 1])
    b = outer([5, 4, 3, 2, 1], [1, 0.8, 1.1, 1.2], [1, 2, 1])
    return np.concatenate([a, b], axis=1)


def assert_close(got, want, atol=1e-9, path="$"):
    """遞迴比對 JSON 結構：數字用絕對誤差，其餘必須相等；None 只等於 None。"""
    if isinstance(want, dict):
        assert isinstance(got, dict) and got.keys() == want.keys(), f"{path}: {sorted(got)} != {sorted(want)}"
        for key in want:
            assert_close(got[key], want[key], atol, f"{path}.{key}")
    elif isinstance(want, list):
        assert isinstance(got, list) and len(got) == len(want), f"{path}: 長度不同"
        for i, (g, w) in enumerate(zip(got, want)):
            assert_close(g, w, atol, f"{path}[{i}]")
    elif isinstance(want, float) and isinstance(got, (int, float)) and not isinstance(got, bool):
        assert abs(got - want) <= atol, f"{path}: {got} != {want}"
    else:
        assert got == want, f"{path}: {got!r} != {want!r}"

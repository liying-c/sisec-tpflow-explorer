"""FastAPI 路由。這一層只做 HTTP 的事：驗證參數、呼叫 views、把結果轉成 JSON。

後端不保存任何使用者狀態；分割樹的形狀由前端持有，每次送來索引清單。
"""
from __future__ import annotations

import math
import os
from functools import lru_cache
from typing import Annotated, Literal

import numpy as np
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import views
from .data import DEFAULT_DATA_DIR, Dataset, load_dataset

Metric = Literal["SDR", "SIR", "SAR", "ISR"]
Target = Literal["vocals", "drums", "bass", "other", "accompaniment"]
Category = Literal["supervised", "supervised+extra", "blind", "oracle"]


class Scope(BaseModel):
    categories: Annotated[list[Category], Field(min_length=1)]

    def cats(self) -> frozenset[str]:
        return frozenset(self.categories)


class OverviewRequest(Scope):
    metric: Metric
    target: Target


class ClusterRequest(Scope):
    metric: Metric


class BlockRequest(Scope):
    idx: list[list[int]]


class SplitRequest(BlockRequest):
    mode: Literal[0, 1, 2] | None = None      # None = 自動推薦
    k: Annotated[int, Field(ge=2, le=5)]


def to_json(value):
    """ndarray → 清單、numpy 純量 → Python 純量、非有限的浮點數 → None（JSON 沒有 NaN）。"""
    if isinstance(value, dict):
        return {key: to_json(v) for key, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json(v) for v in value]
    if isinstance(value, np.ndarray):
        return to_json(value.tolist())
    if isinstance(value, np.generic):
        return to_json(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@lru_cache(maxsize=1)
def get_dataset() -> Dataset:
    return load_dataset(DEFAULT_DATA_DIR)


Data = Annotated[Dataset, Depends(get_dataset)]


def _compute(fn, *args):
    try:
        return to_json(fn(*args))
    except ValueError as error:               # 含 NotEnoughSystems 與不合法的索引
        raise HTTPException(status_code=422, detail=str(error)) from error


app = FastAPI(title="SiSEC 2018 explorer API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("SISEC_ALLOW_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/meta")
def meta(ds: Data):
    return _compute(views.meta, ds)


@app.post("/api/overview")
def overview(req: OverviewRequest, ds: Data):
    return _compute(views.overview, ds, req.metric, req.target, req.cats())


@app.post("/api/stage")
def stage(req: Scope, ds: Data):
    return _compute(views.stage, ds, req.cats())


@app.post("/api/cluster")
def cluster(req: ClusterRequest, ds: Data):
    return _compute(views.cluster, ds, req.cats(), req.metric)


@app.post("/api/partition/summary")
def partition_summary(req: BlockRequest, ds: Data):
    return _compute(views.partition_summary, ds, req.cats(), req.idx)


@app.post("/api/partition/split")
def partition_split(req: SplitRequest, ds: Data):
    return _compute(views.partition_split, ds, req.cats(), req.idx, req.mode, req.k)

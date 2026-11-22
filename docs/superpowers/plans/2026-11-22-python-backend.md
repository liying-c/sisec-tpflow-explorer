# Python 後端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `src/` 的統計、張量、圖論演算法改用 Python（numpy + 手寫演算法）實作成 FastAPI 後端，Vue 只留畫圖與互動，畫面與數字不變。

**Architecture:** `backend/sisec/` 是純函式的 Python 套件，分數存成一個四維 `ndarray`；`views.py` 把它組成各張圖需要的資料，`api.py` 只做 HTTP 轉換。後端無狀態，分割樹的形狀（索引清單）由前端保存。先用現有 JS 在真實資料上輸出基準檔，Python 逐項比對後才刪 JS。

**Tech Stack:** Python ≥ 3.12、numpy、FastAPI、uvicorn、pytest、uv；前端維持 Vue 3 + d3 + Vite。

**Spec:** `docs/superpowers/specs/2026-11-22-python-backend-design.md`

## Global Constraints

- 執行期依賴只有 `numpy`、`fastapi`、`uvicorn`。不得使用 scipy、scikit-learn、tensorly、networkx、pandas。
- numpy 只當算術用（陣列、索引、`einsum`、範數、排序、`eigh`、`quantile`）；演算法步驟自己寫，對照論文式子，不逐句翻譯 JS 的迴圈。
- 所有平手都取索引最小者（`np.argmax` / `np.argmin` 的預設行為），排序用 `kind="stable"`。
- JSON 裡缺值一律是 `null`；回應不得出現 `NaN` / `Infinity`。
- 在分支 `python-backend` 上工作，不推 master（推 master 會自動部署 Pages）。
- 不改 `prepare_data.py` 的輸出格式、不改視覺設計、不動 `public/data/frames/`。
- README「目前的發現」的數字與分群成員不得改變。
- 程式註解與文件用繁體中文，沿用 repo 現有風格。

## Review Focus

1. **可見系統太少**（只勾一個類別、少於 3 個系統）：`/api/stage` 回 `ready: false`，分割與分群端點回 422，前端顯示原本的提示，不得 500。→ Task 6
2. **整列缺值**（盲分離系統在 drums / bass / other 沒有分數）：中位數是 `null`、排行排在最後、優勢圖不產生邊、MDS 距離用 2。→ Task 4、Task 6
3. **切不動的分割**（該維度只剩 1 個元素、k 大於元素數、分完只有 1 群）：回 `ok: false`，前端不改樹。→ Task 2、Task 6
4. **回應亂序**（快速連點指標或類別）：較舊的回應不得蓋掉較新的狀態。→ Task 7
5. **後端連不上或冷啟動很慢**：畫面顯示載入中與明確的錯誤訊息，不是空白頁。→ Task 7
6. **索引清單不合法**（空、越界、重複）：回 422。→ Task 6

---

### Task 0: 分支與 JS 基準檔

**Files:**
- Create: `tests/dump_golden.mjs`
- Create: `backend/tests/golden/*.json`

**Interfaces:**
- Produces: 基準檔，後續每個 Task 的 pytest 讀取。索引一律是「階段順序」下的位置（系統依人聲 SDR 中位數由高到低、曲目依難度由難到易），並同時附上 `systems`、`tracks` 的 id 清單以便對照。

- [ ] **Step 1:** `git switch -c python-backend`
- [ ] **Step 2:** 寫 `tests/dump_golden.mjs`：用 `node:fs` 讀 `public/data/*.csv`（用 `d3.csvParse` + `d3.autoType`），匯入現有的 `src/stats.js`、`src/tensor.js`、`src/partition.js`，照 `src/App.vue` 第 60–225 行的推導，對兩組類別（`all` = 四類全選；`no-oracle` = 去掉 oracle）各輸出一個檔 `backend/tests/golden/<組名>.json`，內容：
  - `overview`（指標 SDR、stem vocals，另一份指標 SIR、stem drums）：`ranking`（系統與中位數）、`leaderboard`、`colorDomain`、`tracksSorted`（id 與難度）、`mdsDistances`（MDS 座標的兩兩距離矩陣）、`mdsXY`、`edges`（化簡後）、`allEdges`、`layers`、`pairs`（每對系統的 `wins`、`n`、`p`）
  - `stage`：`systems`、`tracks`、`pct`（S×T×4 巢狀陣列）、`anchor`
  - `cluster`（四個指標各一份）：`order`、`merges`、`labels`（k = 2…5）
  - `partition`：根節點的 `lambda`、`cost`、`unexplained`、三個維度的 `modeSummary`、`representative`（維度 1）；對 mode ∈ {0,1,2} × k ∈ {2,3,4} 的 `groups`、`cost`、`reduction`；另外「沿系統切 3 群後，對第 1 個子塊沿指標切 2 群」的同樣欄位
  - 數值用完整精度輸出，`NaN` 寫成 `null`
- [ ] **Step 3:** Run: `node tests/dump_golden.mjs` → 產生兩個 JSON；人工核對 `all.json` 的 `partition.unexplained` ≈ 0.081，mode 2 / k 2 的 `reduction` ≈ 0.36，mode 0 / k 3 ≈ 0.34，mode 1 / k 3 ≈ 0.09（README 的數字）。不符就先停下來回報。
- [ ] **Step 4:** Commit（`tests/dump_golden.mjs`、`backend/tests/golden/`）

---

### Task 1: 後端骨架與資料載入

**Files:**
- Create: `backend/pyproject.toml`、`backend/sisec/__init__.py`、`backend/sisec/data.py`
- Test: `backend/tests/test_data.py`、`backend/tests/conftest.py`

**Interfaces:**
- Produces:
  ```python
  METRICS = ("SDR", "SIR", "SAR", "ISR")
  TARGETS = ("vocals", "drums", "bass", "other", "accompaniment")

  @dataclass(frozen=True)
  class Dataset:
      systems: tuple[dict, ...]      # systems.csv 的列，順序同檔案
      tracks: tuple[dict, ...]       # tracks.csv 的列；duration_s 為 int
      scores: np.ndarray             # shape (系統, 目標, 曲目, 指標)，float64，缺值 NaN
      def system_ids(self) -> list[str]
      def track_ids(self) -> list[str]
      def visible(self, categories: Collection[str]) -> np.ndarray   # 系統索引，保持檔案順序

  def load_dataset(data_dir: Path) -> Dataset
  DEFAULT_DATA_DIR: Path   # repo 根目錄的 public/data，可用環境變數 SISEC_DATA_DIR 覆寫
  ```
- `conftest.py` 提供 fixture `ds`（`load_dataset(DEFAULT_DATA_DIR)`，session 範圍）與 `golden(name)`（讀 `tests/golden/<name>.json`）。

- [ ] **Step 1:** `backend/pyproject.toml`：專案名 `sisec`，`requires-python = ">=3.12"`，dependencies `numpy`、`fastapi`、`uvicorn`；dev group `pytest`、`httpx`。
- [ ] **Step 2: 寫測試**
  ```python
  def test_shape_and_axes(ds):
      assert ds.scores.shape == (31, 5, 50, 4)
      assert len(ds.systems) == 31 and len(ds.tracks) == 50

  def test_known_cell(ds):   # scores_track.csv 第一列
      s, t = ds.system_ids().index("2DFT"), ds.track_ids().index("am-contra-heart-peripheral")
      assert ds.scores[s, TARGETS.index("vocals"), t].tolist() == [2.463, 5.230, 3.381, 17.196]

  def test_missing_is_nan(ds):   # 盲分離系統沒有 drums
      s = ds.system_ids().index("2DFT")
      assert np.isnan(ds.scores[s, TARGETS.index("drums")]).all()

  def test_visible_keeps_file_order(ds):
      idx = ds.visible({"oracle"})
      assert {ds.systems[i]["category"] for i in idx} == {"oracle"} and list(idx) == sorted(idx)
  ```
- [ ] **Step 3:** Run: `cd backend && uv run pytest tests/test_data.py -v` → FAIL（模組不存在）
- [ ] **Step 4:** 實作 `data.py`：用標準函式庫 `csv` 讀檔；CSV 裡空字串、非數字、`inf` 都當 NaN。
- [ ] **Step 5:** 同一指令 → PASS
- [ ] **Step 6:** Commit

---

### Task 2: 張量演算法（`tensor.py`）

**Files:**
- Create: `backend/sisec/tensor.py`
- Test: `backend/tests/test_tensor.py`

**Interfaces:**
- Produces:
  ```python
  def percentile_ranks(values: np.ndarray) -> np.ndarray
      # (平均名次 − 0.5) / n，只在有限值之間排名，NaN 原樣保留；輸出形狀同輸入

  @dataclass(frozen=True)
  class RankOne:
      weight: float                    # λ
      vectors: tuple[np.ndarray, ...]  # 每個維度一個單位向量
      cost: float                      # 殘差平方和
      def reconstruct(self) -> np.ndarray     # λ · v0 ⊗ v1 ⊗ …

  def rank_one(X: np.ndarray, *, nonneg: bool = True, iters: int = 200, tol: float = 1e-10) -> RankOne
  def successive_rank_one(X: np.ndarray, rank: int = 3) -> list[RankOne]
  def kmeans(points: np.ndarray, k: int, iters: int = 100) -> np.ndarray   # 每個點的群編號

  @dataclass(frozen=True)
  class Partition:
      mode: int
      groups: tuple[np.ndarray, ...]   # 該維度上的區域索引，依群內第一特徵平均由大到小
      cost: float                      # 各群 rank-one cost 的總和

  def partition_mode(X: np.ndarray, mode: int, k: int, rank: int = 3) -> Partition | None
  def recommend_partition(X: np.ndarray, k: int, rank: int = 3) -> list[Partition]   # cost 由小到大
  ```

演算法由簽名與測試決定不了的部分（必須照做，才能與 JS 的結果一致）：

- **rank_one**：向量初值為 `1/√n`；每一輪依維度 0、1、2… 的順序更新，更新第 m 維時把張量與其他維度「目前的」向量收縮（對任意維數都要能用，`np.tensordot` 依序收縮或動態組 `einsum` 下標皆可）；`nonneg` 時把負值截為 0；除以範數，λ = 最後一次更新的範數；一輪內各維度 `|新 − 舊|` 的總和 < `tol` 就停。任何一次範數為 0 → 回傳 `weight=0`、當下的向量、`cost = ΣX²`。
- **successive_rank_one**：第 1 組 `nonneg=True`，之後對殘差做 `nonneg=False`；遇到 `weight == 0` 就停。
- **kmeans**：farthest-first 初始化——第一個中心是離整體平均最遠的點，之後每次取「到已選中心的最小距離」最大的點；接著重複「指派到最近中心 → 沒有任何點換群就停 → 更新中心（空群的中心不動）」。距離用平方歐氏距離。
- **partition_mode**：該維度元素數 < 2 → `None`。特徵 = 每一組的 `weight · vectors[mode]` 疊成 `(n, 組數)`；`kmeans(特徵, min(k, n))`；去掉空群；依群內第一特徵的平均由大到小排；每群取 `np.take(X, 群, axis=mode)` 做 `rank_one`。

- [ ] **Step 1: 寫測試**（合成資料，由 `tests/check_tensor.mjs` 改寫；`outer(*vs)` 用 `functools.reduce(np.multiply.outer, vs)`）
  ```python
  def test_percentile_ranks_ties():
      assert percentile_ranks(np.array([10, 30, 20, 20.])).tolist() == [0.125, 0.875, 0.5, 0.5]

  def test_percentile_ranks_skips_nan():
      out = percentile_ranks(np.array([3., np.nan, 1.]))
      assert out[[0, 2]].tolist() == [0.75, 0.25] and np.isnan(out[1])

  def test_rank_one_recovers_rank_one_tensor():
      X = outer([1, 2, 3.], [0.5, 1, 1.5, 2], [2, 1.])
      r = rank_one(X)
      assert r.cost < 1e-12
      assert abs(r.vectors[0][2] / r.vectors[0][0] - 3) < 1e-6
      assert all(abs(np.linalg.norm(v) - 1) < 1e-9 and (v >= 0).all() for v in r.vectors)
      assert np.allclose(r.reconstruct(), X)

  def test_rank_one_zero_tensor():
      r = rank_one(np.zeros((2, 3)))
      assert r.weight == 0 and r.cost == 0

  def test_kmeans_two_blobs():
      a = kmeans(np.array([[0, 0], [0.1, 0], [5, 5], [5.1, 5], [0, 0.1]]), 2)
      assert a[0] == a[1] == a[4] != a[2] == a[3]

  def test_kmeans_k_larger_than_n():
      assert len(set(kmeans(np.array([[0.], [1.]]), 5).tolist())) == 2

  @pytest.fixture
  def planted():   # 維度 1 的前 4 個與後 4 個元素，在維度 0 上分佈相反
      A = outer([1, 2, 3, 4, 5.], [1, 1.2, 0.9, 1.1], [1, 2, 1.])
      B = outer([5, 4, 3, 2, 1.], [1, 0.8, 1.1, 1.2], [1, 2, 1.])
      return np.concatenate([A, B], axis=1)

  def test_partition_recovers_planted_groups(planted):
      p = partition_mode(planted, 1, 2)
      assert sorted(sorted(g.tolist()) for g in p.groups) == [[0, 1, 2, 3], [4, 5, 6, 7]]
      assert p.cost < 1e-10 <= rank_one(planted).cost

  def test_recommend_picks_planted_mode(planted):
      assert recommend_partition(planted, 2)[0].mode == 1

  def test_successive_weights_decrease(planted):
      c = successive_rank_one(planted, 3)
      assert len(c) >= 2 and c[0].weight >= c[1].weight

  def test_partition_single_element_mode():
      assert partition_mode(np.ones((1, 3, 2)), 0, 2) is None
  ```
- [ ] **Step 2: 加基準測試**（真實資料，兩組類別都跑）：用 `golden("all")["stage"]["pct"]` 轉成 `ndarray` 當輸入，比對
  - `rank_one` 的 `weight`、`cost`：相對誤差 < 1e-9
  - 對 mode ∈ {0,1,2} × k ∈ {2,3,4}：`partition_mode` 的 `groups` 與基準**完全相同**（含群的順序），`cost` 相對誤差 < 1e-9
- [ ] **Step 3:** Run: `cd backend && uv run pytest tests/test_tensor.py -v` → FAIL
- [ ] **Step 4:** 實作 `tensor.py`
- [ ] **Step 5:** 同一指令 → PASS。若只有基準測試的分群不符，先檢查平手規則與更新順序，不要放寬測試。
- [ ] **Step 6:** Commit

---

### Task 3: 區塊摘要（`partition.py`）

**Files:**
- Create: `backend/sisec/partition.py`
- Test: `backend/tests/test_partition.py`

**Interfaces:**
- Consumes: `rank_one`、`RankOne`、`recommend_partition`、`Partition`（Task 2）
- Produces:
  ```python
  Index = Sequence[Sequence[int]]     # 每個維度在基底張量上的索引清單

  def block(base: np.ndarray, idx: Index) -> np.ndarray      # np.ix_ 取子張量

  @dataclass(frozen=True)
  class ModeSummary:                  # 每個欄位長度 = 該維度的元素數
      model: np.ndarray               # λ · v[j] · 其他維度向量的平均
      q1: np.ndarray; med: np.ndarray; q3: np.ndarray   # 「原始 − 重建」的四分位（np.quantile 預設的線性內插）
      abs_dev: np.ndarray             # 平均絕對偏差

  @dataclass(frozen=True)
  class BlockSummary:
      fit: RankOne
      unexplained: float              # cost / ΣX²；ΣX² 為 0 時是 0
      modes: tuple[ModeSummary, ...]
      def representative(self, mode: int) -> int
          # 依 model 做穩定排序後位於 n // 2 的元素（區域索引）

  def summarize(X: np.ndarray) -> BlockSummary

  @dataclass(frozen=True)
  class Split:
      mode: int
      reductions: dict[int, float]    # 每個可切的維度：1 − 分割後 cost / 分割前 cost（分割前為 0 時是 0）
      children: tuple[Index, ...]     # 基底索引

  def split(base: np.ndarray, idx: Index, mode: int | None, k: int) -> Split | None
      # mode=None 表示自動推薦（cost 最小者）；該維度切不動或只得到 1 群 → None
  ```

- [ ] **Step 1: 寫測試**（沿用 Task 2 的 `planted`，放進 `conftest.py`）
  ```python
  def test_block_selects_and_reorders():
      X = np.multiply.outer([1, 2.], [3, 1, 2.])
      assert block(X, [[0, 1], [2, 0]]).tolist() == [[2, 3], [4, 6]]

  def test_root_unexplained_positive(planted):
      assert summarize(planted).unexplained > 0.01

  def test_split_planted(planted):
      full = [range(5), range(8), range(3)]
      s = split(planted, full, 1, 2)
      assert s.mode == 1 and abs(s.reductions[1] - 1) < 1e-9 and set(s.reductions) == {0, 1, 2}
      assert sorted(sorted(c[1]) for c in s.children) == [[0, 1, 2, 3], [4, 5, 6, 7]]
      assert all(list(c[0]) == [0, 1, 2, 3, 4] for c in s.children)
      child = summarize(block(planted, s.children[0]))
      assert child.unexplained < 1e-10
      m = child.modes[0]
      assert np.abs([m.q1, m.med, m.q3]).max() < 1e-9
      assert (np.diff(m.model) > 0).all() or (np.diff(m.model) < 0).all()
      assert child.representative(0) == 2

  def test_split_auto_picks_mode_1(planted):
      assert split(planted, [range(5), range(8), range(3)], None, 2).mode == 1

  def test_second_level_split_keeps_base_indices(planted):
      first = split(planted, [range(5), range(8), range(3)], 1, 2).children[0]
      second = split(planted, first, 0, 2)
      assert all(sorted(c[1]) == sorted(first[1]) for c in second.children)
      assert sorted(i for c in second.children for i in c[0]) == [0, 1, 2, 3, 4]

  def test_split_impossible():
      assert split(np.ones((1, 4, 2)), [[0], range(4), range(2)], 0, 2) is None
  ```
- [ ] **Step 2: 加基準測試**：根節點的 `unexplained`、三個維度的 `model` / `q1` / `med` / `q3`（絕對誤差 < 1e-9）、`representative(1)`；`split` 的 `reductions`；以及基準檔裡那個第二層分割。
- [ ] **Step 3:** Run → FAIL
- [ ] **Step 4:** 實作
- [ ] **Step 5:** Run → PASS
- [ ] **Step 6:** Commit

---

### Task 4: 統計與優勢圖（`stats.py`、`graph.py`）

**Files:**
- Create: `backend/sisec/stats.py`、`backend/sisec/graph.py`
- Test: `backend/tests/test_stats.py`、`backend/tests/test_graph.py`

**Interfaces:**
- Produces（`stats.py`）：
  ```python
  def nanmedian(a: np.ndarray, axis: int | None = None) -> np.ndarray | float   # 全缺值 → NaN，不發警告
  def pearson(x: np.ndarray, y: np.ndarray) -> float          # 只用兩邊都有限的配對；配對 < 3 或變異為 0 → NaN
  def correlation_distance(profiles: np.ndarray) -> np.ndarray
      # (n, 曲目) → (n, n)，d = sqrt(max(0, 2(1 − r)))，r 為 NaN 時 d = 2，對角線 0
  def classical_mds(dist: np.ndarray) -> np.ndarray           # (n, 2)

  class Wilcoxon(NamedTuple): z: float; p: float; n: int
  def wilcoxon(a: np.ndarray, b: np.ndarray) -> Wilcoxon
  ```
- Produces（`graph.py`）：
  ```python
  class Pairwise(NamedTuple):         # 皆為 (n, n)；[i, j] 是「i 對 j」
      wins: np.ndarray; n: np.ndarray; p: np.ndarray
  def pairwise(profiles: np.ndarray) -> Pairwise
  def dominance_edges(pw: Pairwise, alpha: float = 0.05) -> list[tuple[int, int]]
      # i < j（輸入已依排行排序）、p < alpha 且 wins/n > 0.5
  def transitive_reduction(n: int, edges: list[tuple[int, int]]) -> list[tuple[int, int]]
  def longest_path_layers(n: int, edges: list[tuple[int, int]]) -> list[int]   # 0 = 沒有人顯著優於它
  ```

由簽名決定不了的部分：

- **wilcoxon**：差值去掉 NaN 配對與 0；剩下不足 6 個 → `(0, 1, n)`。對 |差值| 取平均名次；W⁺ 為正差值的名次和；平均 `n(n+1)/4`；變異數 `n(n+1)(2n+1)/24 − Σ(t³ − t)/48`（t 為每組同值的個數）；雙尾 p 用 `math.erf` 算常態 CDF。平均名次可重用 `percentile_ranks` 背後的同一個排名函式（把它抽成 `tensor.py` 或 `stats.py` 的 `average_ranks`，兩邊共用）。
- **classical_mds**：B = −½·J·D²·J；`np.linalg.eigh` 取特徵值最大的兩個，值 ≤ 0 的那一軸座標為 0；座標 = 向量 · √值。**正負號規則**：把每個特徵向量翻成與 `1 + 0.01·arange(n)` 的內積為正（這是現有 JS 冪次迭代的初值，所以方向會與現在的畫面相同）。
- **transitive_reduction**：邊 (a, b) 多餘，若 a 有另一個直接後繼 c ≠ b 能走到 b。假設無環。
- **pairwise** 用廣播一次算出 wins 與 n；p 值逐對呼叫 `wilcoxon`。

- [ ] **Step 1: 寫測試**
  ```python
  def test_nanmedian():
      assert nanmedian(np.array([4, np.nan, 1, 2, 3.])) == 2.5
      assert np.isnan(nanmedian(np.array([np.nan, np.nan])))

  def test_pearson():
      assert abs(pearson(np.array([1, 2, 3, 4.]), np.array([2, 4, 6, 8.])) - 1) < 1e-12
      assert abs(pearson(np.array([1, 2, 3.]), np.array([3, 2, 1.])) + 1) < 1e-12
      assert np.isnan(pearson(np.array([1, 2, np.nan]), np.array([1, 2, 3.])))

  def test_wilcoxon_clear_and_symmetric():
      i = np.arange(50)
      a = 10 + np.sin(i)
      assert wilcoxon(a, a - 1 + 0.3 * np.cos(3 * i)).p < 1e-3
      assert wilcoxon(a, a + np.where(i % 2, 0.5, -0.5)).p > 0.5

  def test_wilcoxon_too_few():
      assert wilcoxon(np.array([1, 2, np.nan]), np.array([0, 0, 0.])) == (0, 1, 2)

  def test_mds_recovers_planar_distances():
      pts = np.array([[0, 0], [3, 0], [0, 4], [3, 4.]])
      d = np.linalg.norm(pts[:, None] - pts[None], axis=-1)
      xy = classical_mds(d)
      assert np.abs(np.linalg.norm(xy[:, None] - xy[None], axis=-1) - d).max() < 1e-9

  def test_correlation_distance_all_nan_row():
      d = correlation_distance(np.array([[1, 2, 3.], [3, 2, 1.], [np.nan] * 3]))
      assert d[0, 1] == 2 and d[0, 2] == 2 and d[2, 2] == 0

  def test_reduction_and_layers():
      edges = [(0, 1), (1, 2), (0, 2), (0, 3)]
      red = transitive_reduction(4, edges)
      assert sorted(red) == [(0, 1), (0, 3), (1, 2)]
      assert longest_path_layers(4, red) == [0, 1, 2, 1]

  def test_pairwise_nan_profile_makes_no_edge():
      prof = np.vstack([np.arange(50.), np.full(50, np.nan)])
      assert dominance_edges(pairwise(prof)) == []
  ```
- [ ] **Step 2: 加基準測試**（兩組類別 × 兩份 overview）：`pairs` 的 `wins`、`n` 完全相同、`p` 絕對誤差 < 1e-6；`edges`、`allEdges`、`layers` 完全相同；MDS 的兩兩距離絕對誤差 < 1e-6，且 `mdsXY` 逐點絕對誤差 < 1e-6（驗證沒有鏡射）。
- [ ] **Step 3:** Run → FAIL
- [ ] **Step 4:** 實作
- [ ] **Step 5:** Run → PASS
- [ ] **Step 6:** Commit

---

### Task 5: 階層式分群（`cluster.py`）

**Files:**
- Create: `backend/sisec/cluster.py`
- Test: `backend/tests/test_cluster.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Merge: a: int; b: int; id: int; height: float; size: int

  @dataclass(frozen=True)
  class Dendrogram:
      n: int
      merges: tuple[Merge, ...]       # 葉節點 id 為 0…n−1，第 i 次合併產生 id n+i
      order: tuple[int, ...]          # 葉節點由左到右
      def cut(self, k: int) -> list[int]      # 每個點的群編號

  def hclust(points: np.ndarray) -> Dendrogram   # average linkage、歐氏距離
  ```

由簽名決定不了的部分：

- 每一步合併距離最小的一對；平手時取「現存群依建立順序排列」下最先遇到的一對（外層先、內層後）。新群到其他群的距離 = 兩個舊距離依成員數加權平均。
- `order` = 根的成員順序，合併時是「a 的成員接 b 的成員」。
- `cut(k)`：從根開始，反覆把高度最大的那個內部節點換成它的左右子節點（原地取代、保持位置），直到有 `min(k, n)` 塊；群編號就是塊在清單裡的位置。

- [ ] **Step 1: 寫測試**
  ```python
  def test_cut_two_groups():
      h = hclust(np.array([[0], [10], [0.2], [10.3], [0.1]]))
      lab = h.cut(2)
      assert lab[0] == lab[2] == lab[4] != lab[1] == lab[3]
      changes = sum(lab[a] != lab[b] for a, b in zip(h.order, h.order[1:]))
      assert changes == 1                     # 同群在 order 裡相鄰

  def test_cut_bounds():
      h = hclust(np.array([[0.], [1.], [5.]]))
      assert len(set(h.cut(1))) == 1 and len(set(h.cut(9))) == 3
  ```
- [ ] **Step 2: 加基準測試**：四個指標、兩組類別，`order` 完全相同、`merges` 的 `a` / `b` / `size` 相同且 `height` 絕對誤差 < 1e-9、k = 2…5 的 `labels` 完全相同。輸入點 = 每首歌一列、各階段系統的百分位，NaN 以 0.5 代替。
- [ ] **Step 3:** Run → FAIL
- [ ] **Step 4:** 實作
- [ ] **Step 5:** Run → PASS
- [ ] **Step 6:** Commit

---

### Task 6: 視圖組裝與 API（`views.py`、`api.py`）

**Files:**
- Create: `backend/sisec/views.py`、`backend/sisec/api.py`
- Test: `backend/tests/test_views.py`、`backend/tests/test_api.py`

**Interfaces:**
- Consumes: Task 1–5 的全部公開函式
- Produces（`views.py`，全部回傳可直接轉 JSON 的 `dict`，但值仍可含 NaN）：
  ```python
  STAGE_TARGET = "vocals"; ALPHA = 0.05

  def meta(ds) -> dict
  def overview(ds, metric: str, target: str, categories: frozenset[str]) -> dict
  def stage(ds, categories: frozenset[str]) -> dict
  def cluster(ds, categories: frozenset[str], metric: str) -> dict
  def partition_summary(ds, categories: frozenset[str], idx: Index) -> dict
  def partition_split(ds, categories: frozenset[str], idx: Index, mode: int | None, k: int) -> dict
  def base_tensor(ds, categories) -> tuple[np.ndarray, list[int], list[int]] | None   # 張量、系統索引、曲目索引；不足 3 個系統 → None
  ```
- Produces（`api.py`）：`app: FastAPI`，路由與回應欄位如下。`stage`、`base_tensor`、`overview` 用 `functools.lru_cache` 快取（參數都可雜湊）。

| 路由 | 請求 | 回應 |
|---|---|---|
| `GET /api/health` | — | `{"ok": true}` |
| `GET /api/meta` | — | `{systems: [...], tracks: [...]}`（CSV 的欄位原樣） |
| `POST /api/overview` | `{metric, target, categories: [..]}` | `{ranking: [{system, category, median}], leaderboard: [{system, category, median, values: {target: median}}], trackIds: [..], profiles: {system: [每首歌的分數]}`（順序同 `trackIds`）`, colorDomain: [lo, hi], tracksSorted: [{track_id, artist, title, duration_s, difficulty}], map: [{system, category, x, y, median}], authorEdges: [{a, b, shared: [..]}], dominance: {order: [system], edges: [[a, b]], allEdges, layers: {system: int}, wins: [[..]], n: [[..]], p: [[..]]}}` |
| `POST /api/stage` | `{categories}` | `{ready, systems: [{system, category, median}], tracks: [{track_id, artist, title, duration_s, difficulty}], metrics: [..], pct: S×T×4, raw: S×T×4, anchor: [{system, category, SDR, SIR, SAR, ISR}]}` |
| `POST /api/cluster` | `{categories, metric}` | `{order: [..], merges: [{a, b, id, height, size}], labels: {"2": [..], "3": [..], "4": [..], "5": [..]}}`（索引是 `stage.tracks` 的位置） |
| `POST /api/partition/summary` | `{categories, idx: [[..], [..], [..]]}` | `{unexplained, modes: [{index: [..], model, q1, med, q3, absDev}] × 3, representativeTrack}`（`index` 與 `representativeTrack` 是基底索引） |
| `POST /api/partition/split` | `{categories, idx, mode: 0\|1\|2\|null, k}` | `{ok, mode, reductions: [{mode, reduction}]`（依 cost 由小到大）`, children: [{idx, summary: 同上}]}`；切不動時 `{ok: false}` |

`views.py` 的推導規則（照 `src/App.vue` 第 60–225 行，這裡列出不可改的部分）：

- 可見系統 = 類別在 `categories` 內者，保持檔案順序。排行依中位數由大到小，缺值排最後，穩定排序。
- `colorDomain` = 可見系統在**所有 stem**、該指標的有限分數的 5% 與 99% 分位數（d3 的 `quantile` 與 `np.quantile` 預設同為線性內插）；沒有資料時 `[0, 10]`。
- 曲目難度 = 可見的**非 oracle** 系統在該曲的中位數（沒有非 oracle 系統時用全部可見系統），由小到大，缺值排最後。
- MDS：可見系統少於 3 個時 `map` 為空清單。
- 共同作者：作者欄位以 `,` 或 ` and `（不分大小寫）切開，去掉括號註記、去空白、轉小寫，長度 > 3 才算；回傳時每個單字首字母大寫。
- 優勢圖的輸入順序是 `ranking` 的順序。
- 階段：百分位對**全部 31 個系統**的人聲分數、每個指標各自排名（不受類別影響）；階段系統 = 可見且人聲 SDR 中位數有限者，依該中位數由大到小；階段曲目依人聲 SDR 的難度；`ready` = 階段系統 ≥ 3。
- 基底張量 = 階段系統 × 階段曲目 × 四個指標的百分位，缺值填 0.5。
- 分群的點 = 每首階段曲目一列、各階段系統在該指標的百分位，缺值填 0.5。

`api.py` 的規則：

- 請求用 pydantic 模型驗證：`metric` 必須在 `METRICS`、`target` 在 `TARGETS`、`categories` 非空且都是已知類別、`k` 在 2–5、`idx` 恰為 3 個非空清單、元素不重複且在基底張量的範圍內。不合法 → 422。
- `ready` 為假時呼叫 `cluster` / `partition/*` → 422，訊息「可見系統不足」。
- 回應送出前，一個共用的函式把 `ndarray` 轉成清單、非有限的浮點數轉成 `None`。
- CORS：允許的來源讀環境變數 `SISEC_ALLOW_ORIGINS`（逗號分隔），預設 `http://localhost:5173`。

- [ ] **Step 1: 寫 `test_views.py`**——基準比對（兩組類別）：`overview` 的 `ranking`、`leaderboard`、`colorDomain`、`tracksSorted`；`stage` 的 `systems`、`tracks`、`pct`、`anchor`。浮點數絕對誤差 < 1e-9，id 順序完全相同。
- [ ] **Step 2: 寫 `test_api.py`**（`fastapi.testclient.TestClient`）
  ```python
  ALL = ["supervised", "supervised+extra", "blind", "oracle"]

  def test_readme_findings(client):
      st = client.post("/api/stage", json={"categories": ALL}).json()
      full = [list(range(31)), list(range(50)), list(range(4))]
      root = client.post("/api/partition/summary", json={"categories": ALL, "idx": full}).json()
      assert round(root["unexplained"], 3) == 0.081
      def cut(mode, k): return client.post("/api/partition/split", json={"categories": ALL, "idx": full, "mode": mode, "k": k}).json()
      red = lambda r, m: next(x["reduction"] for x in r["reductions"] if x["mode"] == m)
      by_metric = cut(2, 2)
      assert round(red(by_metric, 2), 2) == 0.36
      assert sorted(sorted(st["metrics"][i] for i in c["idx"][2]) for c in by_metric["children"]) == [["ISR", "SAR"], ["SDR", "SIR"]]
      by_system = cut(0, 3)
      assert round(red(by_system, 0), 2) == 0.34
      small = min(by_system["children"], key=lambda c: len(c["idx"][0]))
      assert {st["systems"][i]["system"] for i in small["idx"][0]} == {"MIX", "HPLP", "REP1"}
      assert sorted(len(c["idx"][0]) for c in by_system["children"]) == [3, 13, 15]
      by_track = cut(1, 3)
      assert round(red(by_track, 1), 2) == 0.09
      assert sorted(len(c["idx"][1]) for c in by_track["children"]) == [2, 21, 27]

  def test_auto_mode_matches_lowest_cost(client):
      r = client.post("/api/partition/split", json={"categories": ALL, "idx": FULL, "mode": None, "k": 3}).json()
      assert r["ok"] and r["mode"] == r["reductions"][0]["mode"]

  def test_no_nan_in_any_response(client):      # drums：盲分離系統整列缺值
      r = client.post("/api/overview", json={"metric": "SIR", "target": "drums", "categories": ALL})
      assert r.status_code == 200 and "NaN" not in r.text and "Infinity" not in r.text
      blind = [x for x in r.json()["ranking"] if x["category"] == "blind"]
      assert blind and all(x["median"] is None for x in blind)
      assert r.json()["ranking"][-1]["median"] is None

  def test_too_few_systems(client):             # 只有一個 oracle 以外很小的組合不存在，改用假資料夾或單一系統類別
      st = client.post("/api/stage", json={"categories": ["supervised+extra"]}).json()
      if not st["ready"]:
          assert client.post("/api/cluster", json={"categories": ["supervised+extra"], "metric": "SDR"}).status_code == 422

  def test_unsplittable_returns_ok_false(client):
      r = client.post("/api/partition/split", json={"categories": ALL, "idx": [[0], list(range(50)), [0, 1, 2, 3]], "mode": 0, "k": 2})
      assert r.status_code == 200 and r.json() == {"ok": False}

  @pytest.mark.parametrize("idx", [[[], [0], [0]], [[99], [0], [0]], [[0, 0], [0], [0]], [[0], [0]]])
  def test_bad_index_is_422(client, idx):
      assert client.post("/api/partition/summary", json={"categories": ALL, "idx": idx}).status_code == 422

  def test_bad_enum_is_422(client):
      assert client.post("/api/overview", json={"metric": "XYZ", "target": "vocals", "categories": ALL}).status_code == 422
      assert client.post("/api/stage", json={"categories": []}).status_code == 422
  ```
  `test_too_few_systems`：實作時先查 `systems.csv` 各類別的系統數；若沒有任何單一類別少於 3 個系統，改用一份只含 2 個系統的臨時資料夾（`tmp_path` + `SISEC_DATA_DIR`）來測，條件判斷要拿掉，測試必須真的斷言 `ready is False` 與 422。
- [ ] **Step 3:** Run: `cd backend && uv run pytest -v` → 新測試 FAIL
- [ ] **Step 4:** 實作 `views.py`、`api.py`
- [ ] **Step 5:** Run: `cd backend && uv run pytest -v` → 全部 PASS
- [ ] **Step 6:** Run: `cd backend && uv run uvicorn sisec.api:app --port 8000`，另開 `curl -s localhost:8000/api/health` → `{"ok":true}`
- [ ] **Step 7:** Commit

---

### Task 7: 前端改接 API

**Files:**
- Create: `src/api.js`
- Modify: `src/App.vue`（script 全段）、`src/components/ClusterHeatmap.vue`、`vite.config.js`、`package.json`
- Delete: `src/data.js`、`src/stats.js`、`src/tensor.js`、`src/partition.js`、`tests/check_stats.mjs`、`tests/check_tensor.mjs`、`tests/dump_golden.mjs`

**Interfaces:**
- Consumes: Task 6 的路由與回應欄位
- Produces（`src/api.js`）：
  ```js
  export const api = { meta(), overview({metric, target, categories}), stage({categories}),
    cluster({categories, metric}), summary({categories, idx}), split({categories, idx, mode, k}) }
  export function loadFrames(trackId)     // 照舊用 d3.csv 讀 `${import.meta.env.BASE_URL}data/frames/<id>.csv`
  export function latest(fn)              // 包一個非同步函式：只有最後一次呼叫的結果會被回傳，較早的回 undefined
  ```
  - API 基底網址 = `import.meta.env.VITE_API_URL ?? ''`（空字串時走同源的 `/api`，由 Vite proxy 轉發）。
  - 回應進來時遞迴把 `null` 數值轉成 `NaN` 的工作集中在這一個檔；HTTP 非 2xx 時丟出帶狀態碼與伺服器訊息的 `Error`。

`App.vue` 的改法：

- 狀態（`metric`、`target`、`cats`、`selected`、`selectedTrack`、網址參數、深色模式、`anchorX/Y`、`clusterK`、`splitMode`、`splitK`、`focusId`、`compareIds`）與所有事件處理函式的對外行為不變。
- 新增 `shallowRef`：`meta`、`ov`（overview）、`st`（stage）、`cl`（cluster）。`watch([metric, target, cats])` → `ov`；`watch(cats)` → `st`；`watch([cats, metric])` 且 `st.ready` → `cl`。每個都用 `latest()` 包起來（Review Focus 4）。
- 原本的 computed 改成從這些回應取值，名稱保留，模板才不用大改：`ranking`、`leaderboardRows`、`colorDomain`、`mapPoints`（`info` 由 `meta` 補上）、`authorEdges`、`tracksSorted`、`stageSystems`、`stageTracks`、`anchorPoints`、`stageReady`。
- 元件仍收函式 props，但函式改成查表：`valueAt` 查 `ov.profiles`；`pctAt` / `rawAt` 查 `st.pct` / `st.raw`（用 `Map` 把 system、track_id、metric 轉成位置）；`dominance.win(a, b)` 查 `ov.dominance` 的三個矩陣並回傳 `{wins, n, rate, p}`；`dominance.layers` 轉成 `Map`。
- 分割樹：節點是普通物件 `{id, parent, label, idx, unexplained, modes, representativeTrack, children, splitMode, rec}`，id 由前端遞增。
  - `st` 更新且 `ready` 時：呼叫 `api.summary` 建根節點（`idx` 為三個完整範圍），再處理網址參數 `p`（呼叫 `api.split`）。
  - `doSplit` / `undoSplit` 變成非同步；`split` 回 `ok: false` 時不改樹。子節點標籤維持 `${MODE_NAMES[mode]}第 ${i + 1} 群`。等待期間「分割」按鈕停用。
  - `panels` 用節點上已存的 `modes`（不再即時計算）；`jumpToRepresentative` 用 `representativeTrack`。
  - `MODE_NAMES`、`MODE_UNITS` 搬進 `src/series.js`。
- 載入與錯誤（Review Focus 5）：第一次載入沿用現有的 `loading` / `error` 畫面，錯誤訊息改成「無法連上計算伺服器（<訊息>）。若伺服器剛喚醒，請稍候重新整理。」；之後每次重新計算時，在控制列顯示「計算中…」，失敗時顯示同一句錯誤並保留上一次的畫面。

`ClusterHeatmap.vue`：移除 `hclust` 的匯入與呼叫，新增 prop `clustering: { order, merges, labels }`（`labels` 是 k → 陣列的物件），其餘畫圖程式不動；`clustering` 還沒到時畫空白。

其他：

- `vite.config.js` 加 `server.proxy: { '/api': 'http://localhost:8000' }`。
- `package.json`：`check` 改成 `cd backend && uv run pytest -q`；新增 `api`：`cd backend && uv run uvicorn sisec.api:app --reload --port 8000`。

- [ ] **Step 1:** 寫 `src/api.js`
- [ ] **Step 2:** 改 `App.vue`、`ClusterHeatmap.vue`、`series.js`、`vite.config.js`、`package.json`
- [ ] **Step 3:** 刪除上列 JS 檔；Run: `grep -rn "stats.js\|tensor.js\|partition.js\|data.js" src tests` → 沒有結果
- [ ] **Step 4:** Run: `npm run build` → 成功，沒有無法解析的匯入
- [ ] **Step 5: 實機驗證**（同時開 `npm run api` 與 `npm run dev`，用瀏覽器逐項確認並截圖）：
  - `/?p=03&sel=MIX,TAK2`：畫面與 `screenshot-final.png` 一致（分割樹 3 群、A/B/C 區塊模式圖、MIX 與 TAK2 高亮）
  - 根節點卡片顯示 8.1%；「自動推薦」切 2 群後讀數為「依指標 −36%」開頭
  - 切換指標、stem、類別：八張圖都更新，沒有主控台錯誤
  - 快速連點四個指標按鈕：最後停在最後點的那個指標的結果（Review Focus 4）
  - 把類別關到只剩一個：階段 2–4 顯示原本的「系統不足」提示，沒有錯誤
  - 停掉後端再重新整理：看到錯誤訊息而不是空白頁（Review Focus 5）
  - 分割 → 再分割子節點 → 復原；沿曲目分割後圖 3 依分群重排
- [ ] **Step 6:** Commit

---

### Task 8: 部署設定與文件

**Files:**
- Create: `Procfile`、`requirements.txt`、`.python-version`（皆在 repo 根目錄，Heroku 從根目錄建置）
- Modify: `.github/workflows/deploy.yml`、`README.md`、`.gitignore`

- [ ] **Step 1:** `Procfile`：`web: uvicorn sisec.api:app --app-dir backend --host 0.0.0.0 --port $PORT`；`requirements.txt` 列 `numpy`、`fastapi`、`uvicorn`（版本與 `backend/uv.lock` 一致，用 `uv export --no-dev --no-hashes` 產生）；`.python-version` 與 `pyproject.toml` 的下限一致。
- [ ] **Step 2:** Run（模擬 Heroku 的啟動方式）：`PORT=8001 uv run --project backend uvicorn sisec.api:app --app-dir backend --port 8001` 後 `curl -s localhost:8001/api/health` → `{"ok":true}`，且 `curl -s -X POST localhost:8001/api/stage -H 'content-type: application/json' -d '{"categories":["oracle","blind","supervised","supervised+extra"]}' | head -c 80` 有資料（確認從 repo 根目錄啟動時找得到 `public/data`）。
- [ ] **Step 3:** `deploy.yml` 的 build 步驟加 `env: VITE_API_URL: ${{ vars.API_URL }}`，並在 build 前加一個 job 跑 `uv run pytest -q`（`astral-sh/setup-uv`）。
- [ ] **Step 4:** 更新 README：「新增的程式」表改成 `backend/sisec/*.py` 各檔的內容；「方法」裡與實作有關的句子（確定性初始化等）保留；「執行」改成兩個服務的啟動方式與 `npm run check`（現在跑 pytest）；補一段「架構」：前端在 GitHub Pages、後端在 Heroku、兩者之間的六個端點。
- [ ] **Step 5:** `.gitignore` 加 `backend/.venv/`、`__pycache__/`、`.pytest_cache/`
- [ ] **Step 6:** Commit
- [ ] **Step 7（等使用者）:** Heroku 帳號通過審核後，由使用者登入，再一起完成：建立 app、設定 `SISEC_ALLOW_ORIGINS=https://liying-c.github.io`、部署分支、在 GitHub repo 變數設定 `API_URL`、確認線上頁面能連到後端後才合併到 master。機型與是否休眠在這一步查證後決定。

# 演算法搬到 Python 後端：設計

日期：2026-11-22

## 目的

把 `src/` 裡的演算法改用 Python 實作，Vue 只負責畫圖與互動。不是逐句翻譯：以演算法的數學脈絡重新表達，讓程式讀起來接近論文的式子。

## 目標、非目標、不可發生的事

- **目標**：Vue 端不再有任何統計、張量或圖論計算；Python 端可以單獨用 pytest 驗證；畫面與互動和現在相同。
- **非目標**：不改視覺設計、不加新圖、不改 `prepare_data.py` 的輸出格式、不動逐秒資料（`frames/*.csv` 仍由前端直接讀，純顯示用）。
- **不可發生**：README「目前的發現」的數字（8.1%、36%、34%、9%，以及各群的成員）在搬移後改變；master 上出現依賴後端、但後端還沒上線的前端。

## 考慮過的做法

| 做法 | 取捨 | 結果 |
|---|---|---|
| A. FastAPI 後端，Vue 用 `fetch` 呼叫 | 前後端分離最乾淨；需要另外代管後端 | **採用**（使用者決定） |
| B. Pyodide 在瀏覽器執行同一份 Python | 維持純靜態網站；首次載入多十幾 MB | 不採用 |
| C. 事先算好存成 JSON | 分割樹可任意遞迴，組合無法窮舉 | 不可行 |

## 使用者決定的事

- 採用 A，同一個 repo，後端放 `backend/`。
- **numpy 當計算機，演算法手寫**：陣列、索引、`einsum`、範數、排序、特徵分解交給 numpy；演算法本身（rank-one ALS、連續分解、k-means、分割與推薦、偏差四分位、Wilcoxon、MDS、階層式分群、遞移化簡）自己寫。不使用 scipy、scikit-learn、tensorly、networkx。
- 代管傾向 Cloudflare Workers，尚未定案（見「代管」）。

## 我做的決定（可推翻）

### 1. 套件結構

```
backend/
  pyproject.toml          # 依賴：numpy、fastapi；開發：pytest、uvicorn
  sisec/
    data.py               # 讀 CSV → 分數陣列 scores[system, target, track, metric]（缺值為 NaN）
    stats.py              # nanmedian 排行、Pearson、Wilcoxon（常態近似）、古典 MDS
    graph.py              # 顯著優於的邊、遞移化簡、最長路徑分層
    tensor.py             # 百分位、rank-one ALS、連續分解、k-means、沿維度分割、推薦
    cluster.py            # 階層式分群（average linkage）
    partition.py          # 子張量的摘要：未解釋比例、各維度的模型值與偏差四分位、代表元素
    api.py                # FastAPI 路由，只做參數轉換，不含演算法
  worker.py               # Cloudflare Workers 進入點（兩行）
  tests/
    golden/               # 由現有 JS 在真實資料上產生的基準輸出
```

資料在後端：`data.py` 把分數整理成一個四維 `ndarray`，之後「某系統在某 stem、某指標的 50 首歌剖面」就只是一次索引，取代現在的三層 `Map`。

### 2. 後端無狀態，樹由前端持有

分割樹的節點只是「三個維度各自的索引清單」。前端保存樹的形狀（id、父子關係、索引清單），後端每次收到索引清單，回傳那一塊的計算結果。後端不記任何使用者狀態，適合 Workers。

### 3. API（粗粒度，回傳矩陣而不是函式）

| 端點 | 輸入 | 輸出 | 取代的現有程式 |
|---|---|---|---|
| `GET /api/meta` | 無 | 系統、曲目的屬性 | `loadAll` |
| `POST /api/overview` | 指標、stem、類別 | 排行與五個 stem 的中位數、分數矩陣（系統 × 曲目）、色階範圍、曲目難度排序、MDS 座標、共同作者連線、優勢圖（邊、層、兩兩勝場與 p 值矩陣） | `App.vue` 階段 1 的 computed |
| `POST /api/stage` | 類別 | 人聲的系統與曲目順序、百分位張量與原始值、四指標中位數 | `pct`、`stageSystems`、`stageTracks`、`anchorPoints` |
| `POST /api/cluster` | 類別、指標 | 葉節點順序、合併紀錄、k = 2…5 的分群標籤 | `ClusterHeatmap.vue` 內的 `hclust` 呼叫 |
| `POST /api/partition/summary` | 類別、索引清單 | 未解釋比例、三個維度的摘要與偏差、代表曲目 | `makeNode`、`modeSummary`、`representative` |
| `POST /api/partition/split` | 類別、索引清單、維度或 auto、k | 三個維度各自的降幅、選中的維度、每個子塊的索引清單與摘要 | `splitNode` |

缺值在 JSON 裡一律是 `null`，前端在 API 用戶端這一處轉回 `NaN`。

### 4. 前端的改動

- 刪除 `src/stats.js`、`src/tensor.js`、`src/partition.js`、`tests/check_*.mjs`。
- `src/data.js` 改成 API 用戶端（含 `null` → `NaN`）。
- `App.vue`：計算類的 computed 改成「狀態改變 → 呼叫 API → 存結果」，加上載入中與失敗的顯示；元件收到的 `win`、`valueAt`、`pctAt` 等函式改成查表。
- `ClusterHeatmap.vue` 改收分群結果當 props。
- API 網址由建置時的環境變數 `VITE_API_URL` 決定；開發時用 Vite proxy 轉到本機的 uvicorn。後端對 Pages 的網域開 CORS。

### 5. 數值一致性

- **基準檔**：刪 JS 之前，先用現有 JS 在 `public/data` 上輸出基準（根節點未解釋比例、每個維度與 k 的分群成員與誤差、優勢圖的邊、分群切法、MDS 兩兩距離），pytest 逐項比對。原本 36 項合成資料的檢查也改寫成 pytest。
- **平手規則**照 JS：k-means 的 farthest-first 與指派、階層式分群挑最近的一對，都取索引最小者；葉節點順序沿用「左子樹成員接右子樹成員」。這樣圖 6 的順序不變。
- **MDS**：`eigh` 的特徵向量正負號任意，比對時用兩兩距離；另外固定一個正負號規則，使座標與現在的畫面同向、不會鏡射。
- **Wilcoxon**：維持常態近似與同值修正，CDF 用標準函式庫的 `math.erf`（比現在的近似式更準，p 值差異在 1e-7 以內，不影響 0.05 的判定；基準檔會確認邊沒有變）。

### 6. 代管（延後決定）

**2026-11-22 更新：改用 Heroku。** 使用者已用 GitHub Student Developer Pack 申請 Heroku 額度（每月 13 美元、24 個月），審核中。Heroku 跑一般的 CPython，沒有 10 ms 的 CPU 上限，下面的 Workers 試驗與 `worker.py` 不再需要；以下 Workers 的內容只留作紀錄。

後端寫成一般的 FastAPI 應用，不綁任何平台。先完成並在本機驗證，再部署。

已查到的事實（2026-11-22）：

- Workers 免費方案每個請求 10 ms CPU；付費方案每月 5 美元，預設 30 秒。Workers 用 Pyodide 執行 Python，本機 numpy 的速度不能代表它，要以實際部署後量到的 CPU 時間為準。
- Cloudflare 學生方案免除 12 個月的 5 美元月費，但目前只限美國、18 歲以上、`.edu` 信箱。
- Render 免費方案可跑一般的 Python 服務，閒置 15 分鐘後休眠，喚醒約一分鐘。

**待辦的試驗**：部署一個最小的 Worker（numpy + FastAPI + 一次與推薦分割同規模的計算），量 CPU 時間，同時確認 numpy 能用、資料檔能否隨程式打包（不行的話改為啟動後向靜態網站抓 CSV 並快取在記憶體）。這需要使用者的 Cloudflare 帳號。

### 7. Git

在分支 `python-backend` 上進行。推到 master 會自動部署 Pages，所以要等後端網址上線後才合併。

## 留給實作的

- 每個端點回應的確切欄位名稱。
- 前端載入中狀態的呈現方式。
- README「新增的程式」與「執行」兩節的更新。

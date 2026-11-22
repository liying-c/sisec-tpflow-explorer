# 基準檔

`all.json` 與 `no-oracle.json` 是改寫成 Python **之前**，用原本的 JavaScript 實作在 `public/data/` 上算出的結果。
pytest 用它們確認 Python 版的分群成員、誤差、優勢圖的邊、分群樹與 MDS 座標和原本一致。

這兩個檔不會再重新產生：產生它們的 JS 演算法已經從 repo 移除。它們的角色是「改寫當下的對照」，
之後若刻意改變演算法的行為，應該直接更新對應的測試，而不是設法重跑舊程式。

需要查看或重現當時的產生方式時，腳本與舊實作都在 git 歷史裡：

```bash
git show 40a06bf:tests/dump_golden.mjs      # 產生腳本
git show 40a06bf:src/tensor.js              # 當時的 JS 實作（另有 stats.js、partition.js、data.js）
git worktree add /tmp/sisec-js 40a06bf && cd /tmp/sisec-js && npm ci && node tests/dump_golden.mjs
```

兩組資料的差別只在可見的系統類別：`all` 是四類全選，`no-oracle` 去掉 oracle。

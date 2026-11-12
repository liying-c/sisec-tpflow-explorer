# 資料來源

本資料夾的 CSV 由 `prepare_data.py` 從 SiSEC 2018 MUS 評測的公開結果彙整而成：

- 原始結果：<https://github.com/sigsep/sigsep-mus-2018>（各參賽系統以 pull request 提交的 museval 逐秒分數與系統說明）
- 評測活動論文：F.-R. Stöter, A. Liutkus, N. Ito, "The 2018 Signal Separation Evaluation Campaign," LVA/ICA 2018. <https://arxiv.org/abs/1804.06267>
- 評測工具：museval（BSS Eval v4）<https://github.com/sigsep/sigsep-mus-eval>
- 測試曲目來自 MUSDB18 <https://sigsep.github.io/datasets/musdb.html>；本專案只使用曲名，不包含任何音訊。

原始結果 repo 未附授權條款；本專案僅將分數（量測事實）彙整後用於教學與研究，不複製各團隊撰寫的方法說明，系統說明請見原始 repo 中各系統的 `description.md`。
作者與機構欄位取自各系統的署名，用於標示來源。

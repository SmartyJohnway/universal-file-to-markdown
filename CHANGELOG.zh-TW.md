# 變更紀錄

[English](CHANGELOG.md)

本檔案記錄專案的重要變更。

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本編號在實務可行範圍內遵循 Semantic Versioning。

## [尚未發布]

### 修正

- 修正 PPTX Markdown 圖片路徑，使其透過 bundle 的 `assets/` 目錄解析。
- 驗證本機 Markdown 圖片目標，拒絕遺失、絕對或逸出 bundle 的路徑。
- 強制轉換狀態與 warning/error payload 一致。
- 成功轉換報告必須包含非空的主要 engine。

### 新增

- 未支援副檔名使用 MarkItDown fallback 時新增正式 warning。
- 增加 Markdown 資產可用性與報告合約的 regression coverage。

### 規劃中

- 增加真實加密 Office、SmartArt、embedded OLE 與複雜掃描表格的 integration fixtures。
- 在維持 schema 1.0 相容性的前提下，持續改善各格式的 canonical granularity 與 provenance。

## [1.6.0] - 2026-07-21

### 新增

- 在 `schemas/` 中加入 document、element、table 與 chunk JSON Schemas。
- 建立具有 synthetic root 與 parent/child references 的 canonical 階層文件模型。
- 產出經 schema 驗證的 `document.json`、`chunks.jsonl` 與 canonical table assets。
- Bundle validator 可檢查 schema、root/tree reachability、cycle、數量、跨檔案參照、chunk 限制、table dimensions、cell bounds 與資產一致性。
- 實作 2,000 字元 chunk 硬上限，依 paragraph、line、word 與 table row 優先切分。
- 大型 Markdown table 分割後，後續 chunk 會重複 header。
- Chunks 增加 page、sheet、slide、source file 與 element references。
- PPTX 支援 slide、group、title、paragraph、list、table、chart、image 與 speaker note 等 shape-level canonical elements。
- XLSX 支援空白列欄分隔的 block elements、chart/image references 與 cell-range locators。
- 數位 PDF 支援具 bbox 的文字 blocks 與 tables，並避免表格文字重複輸出。
- PNG、JPEG、TIFF、BMP 與 WebP 可直接進入 image OCR 路徑。
- 新增 runtime capability probe，檢查必要 Python dependencies 與選配系統工具。
- 新增 GitHub Actions workflow，執行依賴安裝、capability preflight、測試與 Python source compilation。
- 增加 release-hardening regression tests，測試數量擴充至約 65 項。
- 加入 Apache License 2.0、授權範圍、第三方 dependency 說明與 citation metadata。
- 加入貢獻、治理、安全、支援、行為準則、maintainer 與作者資訊文件。
- 加入 Issue/PR templates、CODEOWNERS、Dependabot、CodeQL、dependency review、metadata validation、Markdown link check、release gate 與 clean release package workflows。
- 加入發布流程、發布檢查清單、release notes 草稿、repository settings 指引，以及安全與 dependency policy 文件。

### 變更

- 明確區分技能版本與資料 schema 版本：skill `1.6.0`、schema `1.0`。
- 所有 table converters 正規化為共同合約，包含 dimensions、merge-anchor cells、rectangular grid、engine、confidence 與 source locator。
- 獨立 HTML table assets 保留 rowspan 與 colspan；CSV 則明確記錄 merges 已被展平。
- PPTX bullet 判斷改為先處理明確的 `buNone`、`buChar` 與 `buAutoNum`，再解析 body-like placeholder 的 layout/master inheritance；普通 textbox 預設為 prose。
- Office preflight 現在會區分有效 OOXML ZIP、損毀 container 與 OLE-based encrypted Office。
- 圖片 OCR provenance 會記錄實際使用 RapidOCR 或 Tesseract，不再繼承錯誤引擎標籤。
- 失敗的 rerun 會先清除已知產物，避免舊 canonical outputs 殘留。
- Source locator schema 增加 page、slide、sheet、shape、table index 與 bbox 型別約束。
- 中英文 README 已更新 Apache-2.0、發布治理與 release-quality checks。

### 修正

- 損毀或被截斷的 OOXML 不再被誤判為密碼保護。
- Bundle validator 現在會拒絕 missing root、root parent 錯誤、disconnected elements、hierarchy cycle、count mismatch、duplicate chunk ID、invalid split index、char count mismatch、table dimensions 錯誤與 cell 越界。
- Standalone image conversion 不再錯誤回報 `openpyxl_custom` OCR engine。
- 普通 PPTX textbox 不再被錯誤轉成 bullet list。
- Grouped PPTX tables 可保留於 canonical table output。
- SmartArt 與 embedded OLE 會被偵測、定位並回報，不再靜默遺失。

## [1.5.1] - 2026-07-21

### 新增

- SmartArt 與 embedded OLE presence detection，以及明確 conversion warnings。
- 統一 element 的 engine、confidence 與 source locator 欄位。
- 掃描 PDF 的 table-likelihood warning gate。
- 增加 grouped PPTX tables、standalone merged HTML、schema normalization 與 unsupported-content disclosure 的 regression tests。

### 變更

- Group-shape rendering 會將 nested table data 傳遞至 table assets。
- Canonical table data 包含 merge-aware cell geometry，可供 standalone HTML 使用。
- 掃描 PDF 只有在頁面存在明顯 table-like alignment 時，才會發出 `TABLE_STRUCTURE_UNVERIFIED`。

### 修正

- Office 合併表格輸出為 standalone HTML 時可保留 rowspan 與 colspan。
- PPTX group 內的 table 不再從 `tables/` 產物遺失。

### 原始候選版已知問題

- 最初的 v1.5.1 candidate 將沒有明確 PPTX bullet XML 的 paragraph 視為 bullet，導致普通 textbox 被轉成清單；此問題已在 v1.6.0 修正。

## [1.5.0] - 2026-07-19

### 新增

- 建立獨立 `python-pptx` converter，不再只依賴通用 MarkItDown fallback。
- PPTX 支援 merged table rendering、picture extraction、chart summary、speaker notes 與 group-shape recursion。
- 新增 `document.json`、`chunks.jsonl` 與 standalone table assets。
- DOCX 增加 run-level formatting、hyperlinks、notes、headers、footers 與表格處理。
- XLSX 增加公式保留、數值/日期格式、comments、hyperlinks、hidden-state metadata、charts 與 image references。
- 建立正式 pytest regression suite。

### 變更

- Canonical output 從只有 Markdown，進化為可追溯的 AI/RAG bundle。
- 格式路由除副檔名外，也開始使用 magic bytes 與 OOXML container inspection。
- Office encryption detection 從 boolean 改為明確狀態處理。

### 修正

- 短篇數位 PDF 不再因文字少於 50 字而被錯誤送入 OCR。
- Big5/CP950 CSV 不再於缺乏結構與語言檢查時，被當成合理的 UTF-16 輸出。
- XLSX 公式缺少 cached value 時會保留公式並回報 `FORMULA_RESULT_UNAVAILABLE`，不再靜默輸出空白儲存格。
- EML 附件檔名增加 path traversal 與撞名防護。

## [1.1.0] - 2026-07-18

### 新增

- 初版離線優先 multi-format router。
- 自訂 XLSX conversion，支援 merge-aware HTML tables。
- 自訂 DOCX conversion，支援水平與垂直合併儲存格。
- PDF digital-text extraction 與 OCR fallback。
- CSV、JSON、EML、Pandoc 與 MarkItDown fallback 路徑。
- `manifest.json` 與 `conversion-report.json`。
- Near-empty output、mojibake indicators、OCR confidence 與 table uncertainty 品質檢查。

### 建立的設計原則

- 優先使用 deterministic structural parsers，而不是依賴單一 universal converter。
- Markdown pipe table 無法表達合併儲存格時，使用 HTML 保留結構。
- 受限環境優先採用輕量離線引擎。
- 不把 `document.md` 單獨視為轉換成功證據。

[尚未發布]: https://github.com/SmartyJohnway/universal-file-to-markdown/commits/main
[1.6.0]: https://github.com/SmartyJohnway/universal-file-to-markdown/commit/d4ff2d29a65dce6d0f84780c8d22effe10fe4f5d
[1.5.1]: https://github.com/SmartyJohnway/universal-file-to-markdown/commits/main
[1.5.0]: https://github.com/SmartyJohnway/universal-file-to-markdown/commits/main
[1.1.0]: https://github.com/SmartyJohnway/universal-file-to-markdown/commits/main

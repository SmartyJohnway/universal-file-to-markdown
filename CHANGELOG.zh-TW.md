# 變更紀錄

[English](CHANGELOG.md)

本檔案記錄專案的重要變更。

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本編號在實務可行範圍內遵循 Semantic Versioning。

## [1.8.0] - 尚未發布

### 新增 (Added)

* 新增 PDF page 共用 deterministic ordering plan，同時驅動 Markdown projection 與 canonical element 順序。
* 新增 line-level PDF region 重組，避免 PyMuPDF 把同一水平帶的獨立左右欄合成單一 block。
* 新增 column-major XY-cut、full-width 頁首頁尾 band 與依 bbox 插回表格的排序。
* PPTX reading plan 現納入 placeholder role、layout zone、column flow、group-local order 與穩定 source-order fallback。
* 新增 additive `properties.layout` hints，以及 caption、table、figure、speaker note 的強證據 `properties.associations`。
* 新增每頁 PDF `source_extraction_index` 證據，與 deterministic 視覺閱讀順序分開保存。
* Bundle validation 新增跨 element association 與 sibling reading-order 驗證。

### 變更 (Changed)

* 多欄 PDF 與並排 PPTX 現會採 deterministic 排序；無法證明作者意圖時仍保留 uncertainty warning。
* Canonical schema 維持 `1.0`；layout 與 association 是向後相容的 optional properties。

### 修復 (Fixed)

* Digital PDF table 會依 bbox 插回頁內位置，不再固定附加於所有 prose 之後。
* 狹窄頁首與頁尾不會被誤分配至 body 左欄。
* 缺少外框幾何的 PPTX group proxy 會安全回退到 source order，不再產生無效 `reading_order`。

## [1.7.3] - 尚未發布

### 新增 (Added)

* 新增只告警、不自動重排的多欄 PDF 與 PPTX 視覺流歧義偵測，並提供 machine-readable evidence。
* 新增 release truth consistency gate，涵蓋 VERSION、SKILL、README、project status、changelog、workflow 文件與 AI Review schema 的 mirrored version。
* 新增 rejected OCR advisory target、本機 Markdown link scope、native timeout 傳遞與 layout uncertainty 正反案例 regression coverage。

### 修復 (Fixed)

* rejected OCR table candidate 在沒有 canonical table 時，會產生不可寫入 projection 的 `advisory` target，不再退回 `element_range`。
* Markdown link gate 不再掃描本機 qualification、Hermes、scratch、cache 與虛擬環境內容。
* RapidOCR／PyMuPDF native probe 改用可設定的 30 秒預設 timeout，降低 cold start／contention 假失敗，同時保留 subprocess isolation。
* AI Review regression runner 改用 repository-local pytest temp，避免 Windows user-temp root 無權限造成假失敗。
* release package evidence 現可在網路檔案系統記錄 source Git SHA，且不修改全域 Git trust 設定。
* release metadata 現正確反映已發布的 `v1.7.2` stable release，並移除英文 README 重複標題。
* citation metadata 現正確反映 stable `v1.7.2`，並納入 release package profile。

### 變更 (Changed)

* v1.7.3 只偵測 reading-order 風險；實際重排留給 v1.8 release line。

## [1.7.2] - 2026-07-24

### 新增 (Added)

* 原生 TXT 轉換器（`convert_text.py`），支援 `.txt`、`.text`、`.log`。
* 原生 Markdown 轉換器（`convert_markdown.py`），支援 `.md`、`.markdown`。
* 使用者主動指定 AI Review 之 CLI 參數（`prepare_ai_review.py` 新增 `--force-user-request` 與 `--target-table`）。
* OCR 諮詢性審查目標（`target_type: "advisory"`）。
* 具備 Route 感知能力的選用套件依賴回報機制（`capability_probe.py`）。
* 跨格式合併表格 AI Review 觸發條件（`table_has_merged_geometry`）。

### 修復 (Fixed)

* 修復 OOXML 合併表格（DOCX、XLSX、PPTX）未觸發 AI Review 資格的問題。
* 修復 capability probe 未揭露 MarkItDown 缺失的問題。
* 修正文件中錯誤的 AI Review Schema 檔名。
* 修正可讀性投影 CLI 渲染範例指令。
* 修復 Package 內執行迴歸 runner 缺少 `tests/` 目錄時產生未處理 Traceback 的問題。
* 修復 Big5 / CP950 / GB18030 歧義字元解碼被過度自信呈現的問題。

### 變更 (Changed)

* 編碼歧義情況現會明確回報未解析狀態並提醒使用者。
* Agent Skill Package 正式排除僅存於原始碼庫之迴歸 runner。
* `.txt` 與 `.md` 格式不再依賴 MarkItDown 通用 fallback route。

## [1.7.1] - 2026-07-24

*未發布的整合里程碑（Unpublished integration milestone）。未建立 v1.7.1 tag 或 GitHub Release。已由 v1.7.2 取代。*

### 修復 (Fixed)

* 修正 VERSION, SKILL, README, VERSIONING, PROJECT_STATUS, CHANGELOG 及鏡像 schema 約束間的 release-state 元資料一致性。
* 修復損壞或於 Package 中無法解析的 Markdown 連結。
* 修正將僅存在於 Repository 的測試指令誤列為 Runtime Package 指令的問題。
* 補充 Release Package 驗證中不完整的產物預期。

### 新增 (Added)

* 支援雙重 Package Profiles：`release` 與 `agent-skill`。
* 支援相容於 Agent Skills 標準的上傳 ZIP。
* 新增獨立的 Agent Skill Package 驗證模式（Validator profile）。
* 於 `references/ai_review_workflow.md` 新增完整 AI Review 工作流文件。
* 新增 Package Profile 專屬之 Qualification Helper 與單元測試。
* 新增解壓後 Package 之 Markdown 連結驗證機制。

### 變更 (Changed)

* Release Package 與 Agent Skill Package 現採用獨立的內容邊界與驗證合約。
* Agent Skill ZIP 僅包含單一頂層 Skill 目錄（`universal-file-to-markdown/`），且 `SKILL.md` 位於其根目錄。
* 完整迴歸測試明確標示為 Source Repository 驗證資產，不包含於 Runtime Package 中。

## [1.7.0-rc1] - 2026-07-23

此版本為 release candidate，並非已發布的 stable release。已發布的 stable release 仍為 `1.6.0`，`1.7.0` 是目標 stable release。

### 新增

- 可重現跨格式 regression runner、決定性正規化與 fingerprints、Phase 5 workflow coverage、OCR containment cases，以及逐 case progress reporting。

### 變更

- 合格驗證 RapidOCR `1.4.4`；宣告 requirement 為 `rapidocr-onnxruntime>=1.4,<2`。
- 文件化 Python 3.10–3.12 支援範圍、Python 3.11 主要合格 runtime 與明確的 Python 3.13 排除。
- 統一版本、runtime、dependency、格式與 capability 文件；schema 版本仍獨立於技能版本。

### 修正

- 格式錯誤的 workflow artifacts 不再使 unified runner crash；readable-projection writes 與 absolute-path validation 可跨平台執行。

### Qualification

- RC head 完整 pytest：197 passed。
- RC head unified corpus：pending；正式 release qualification 前必須在此 release-candidate head 完成。
- 歷史 Phase 6 evidence（pre-RC main head）：194 tests passed，unified corpus 18/18 passed。

## [尚未發布]

## [1.6.1-rc2] - 2026-07-22

### 新增

- 以隔離子程序執行 PyMuPDF import 與最小 PDF 功能 smoke test，避免 native dependency crash 終止 capability probe 主程序。
- capability report 加入 runtime environment 與 PyMuPDF package version evidence。
- 文件化 Python 與 native dependency 相容性政策。

### 變更

- 將 PyMuPDF 限定為 `>=1.26.4,<1.27`，以提高已測 runtime 的可重現性；這不表示後續版本普遍有問題。

### 修正

- 修正 PPTX Markdown 圖片路徑，使其透過 bundle 的 `assets/` 目錄解析。
- 驗證本機 Markdown 圖片目標，拒絕遺失、絕對或逸出 bundle 的路徑。
- 強制轉換狀態與 warning/error payload 一致。
- 成功轉換報告必須包含非空的主要 engine。

### 新增

- 未支援副檔名使用 MarkItDown fallback 時新增正式 warning。
- 增加 Markdown 資產可用性與報告合約的 regression coverage。

### 變更

- 在 v1.6.1 迭代開發期間，暫時將開發驗證 workflows 改為手動 dispatch，以節省 GitHub Actions 用量。
- Release tag 的 packaging 仍維持自動執行。

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

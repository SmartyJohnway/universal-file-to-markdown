# Universal File to Markdown

[English](README.md) · [變更紀錄](CHANGELOG.zh-TW.md)

這是一套具決定性、離線優先的文件正規化技能，可將支援的檔案轉換成 Markdown，以及供 AI 分析、RAG、稽核與後續自動化使用的 schema 驗證輸出包。

本專案重視透明度與可追溯性，不會只把 `document.md` 視為成功證據。每次轉換還會產出品質報告、來源 manifest、canonical elements、受限長度 chunks、表格資產與 bundle 驗證結果。

## 文件索引

- [English README](README.md)
- [繁體中文 README](README.zh-TW.md)
- [English changelog](CHANGELOG.md)
- [繁體中文變更紀錄](CHANGELOG.zh-TW.md)
- [AI 技能操作合約](SKILL.md)
- [格式能力矩陣](references/capability_matrix.md)
- [引擎說明與升級指引](references/engine_notes.md)
- [貢獻指南](CONTRIBUTING.md)
- [安全政策](SECURITY.md)
- [支援政策](SUPPORT.md)
- [治理方式](GOVERNANCE.md)
- [發布流程](RELEASING.md)
- [發布檢查清單](RELEASE_CHECKLIST.md)
- [授權說明](docs/LICENSING.md)

## 主要特色

- 支援 PDF、掃描圖片、DOCX、XLSX/XLSM、PPTX、CSV/TSV、JSON、EML，以及 Pandoc 可處理的 markup 格式。
- 採用輕量結構解析器與離線 OCR，不需要 PyTorch runtime，也不需在執行時下載外部模型。
- 針對繁體中文 Big5/CP950 編碼提供候選評分與歧義揭露。
- Office 合併儲存格可輸出保留 rowspan/colspan 的 HTML。
- 混合型 PDF 會逐頁區分 digital 與 scanned 路徑。
- 產出 canonical 階層元素，並在可取得時保留頁碼、工作表、投影片、shape、表格與 bbox 定位。
- RAG chunks 具有 2,000 字元硬上限。
- 對不支援或低信心內容明確警告，不以 silent success 掩蓋資訊遺失。
- 驗證 schema、階層、chunk 參照、表格尺寸、資產與整體 bundle 一致性。

## 支援格式

| 輸入 | 主要引擎 | Canonical 粒度 | 重要行為 |
|---|---|---|---|
| DOCX | python-docx + OOXML | heading、paragraph、list item、table | 粗斜體、連結、註記、頁首頁尾、合併儲存格 |
| XLSX/XLSM | openpyxl | sheet、空白分隔 block、table、chart/image reference | 公式、註解、合併儲存格、隱藏狀態 metadata |
| PPTX | python-pptx + OOXML | slide、group、title、paragraph、list、table、chart、image、note | bullet inheritance、穩定資產名稱、SmartArt/OLE 揭露 |
| 數位 PDF | PyMuPDF + pdfplumber | page、定位文字 block、table | 表格文字去重與 bbox 定位 |
| 掃描 PDF | RapidOCR；Tesseract fallback | page、OCR region、table | OCR confidence 與 table likelihood |
| PNG/JPEG/TIFF/BMP/WebP | RapidOCR；Tesseract fallback | OCR region、table | 直接離線圖片 OCR |
| CSV/TSV | Python stdlib CSV | canonical table | UTF-8 優先，搭配繁體中文編碼評分 |
| JSON | Python stdlib JSON | structured block | Unicode JSON 美化輸出 |
| EML | Python stdlib email | email、attachment | 附件檔名清理與避免撞名 |
| HTML/EPUB/RST/Org/TeX | Pandoc | structured block | Pandoc 不存在時明確失敗 |

`.doc`、`.xls`、`.ppt` 等舊式二進位 Office 格式不直接解析，請先轉為 OOXML 後再執行。

## 輸出包

每次轉換會產出以下目錄內容：

```text
document.md              供人與 LLM 閱讀的 Markdown
document.json            Canonical 階層元素，schema 1.0
chunks.jsonl              含定位資訊的 RAG chunks，最長 2,000 字元
tables/                   Canonical JSON、CSV 與保留合併結構的 HTML
assets/                   擷取的圖片與附件
manifest.json             來源 SHA-256、版本、時間與最終狀態
conversion-report.json   引擎細節、警告與 bundle 驗證結果
```

重新執行時只會清除已知產物；若後續轉換失敗，不會留下前一次成功執行的過期 canonical outputs。

## 安裝

建議使用 Python 3.10 以上版本。

```bash
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

選配系統工具：

- `tesseract`：作為 Latin script OCR fallback。
- `pandoc`：處理 HTML、EPUB、RST、Org 與 TeX 路徑。

轉換前先檢查執行環境：

```bash
python scripts/capability_probe.py --json
```

若缺少必要 Python dependency，probe 會以非零狀態碼結束；選配系統工具缺少時只會列出，不會使 probe 失敗。

## 使用方式

```bash
python scripts/router.py INPUT_FILE --output OUTPUT_DIRECTORY
```

若舊式文字編碼判定有歧義，可明確指定 codec：

```bash
python scripts/router.py input.csv --output output --encoding gb18030
```

也可獨立驗證既有輸出包：

```bash
python scripts/validate_bundle.py OUTPUT_DIRECTORY
```

最終轉換狀態為 `failed` 時，router 會以非零狀態碼結束。

## 如何判讀結果

每次都應檢查 `conversion-report.json`。

- `passed`：轉換與 bundle validation 成功，且未偵測到資訊遺失。
- `passed_with_warnings`：輸出可用，但存在已明確揭露的不確定性或不支援結構。
- `failed`：不得把 canonical 或 RAG 輸出視為有效結果。

成功的 bundle 應包含：

```json
{
  "bundle_validation": {
    "status": "passed"
  }
}
```

常見警告包括公式快取值不存在、編碼歧義、OCR confidence 偏低、疑似但未重建的掃描表格、SmartArt/OLE 未解析，以及 Excel chart 僅以 reference 表示。

## Canonical contracts

技能版本與資料 schema 版本彼此獨立：

```text
skill_version: 1.6.0
document/table/chunk schema_version: 1.0
```

所有 canonical element 都具有固定的階層、content format、engine、confidence、source locator、properties 與 warnings 欄位。Canonical table 以 `cells` 保留 merge anchors，並提供矩形 `grid` 供 CSV 與後續處理使用。

JSON Schemas 位於 `schemas/`；各格式的 element 粒度與限制記錄於 `references/capability_matrix.md`。

## 已知邊界

- 掃描表格重建採用幾何與 heuristic 方法，複雜無框線或大量合併儲存格的表格可能需要較重型解析器。
- SmartArt 與 embedded OLE 會被偵測與定位，但不會展開內容。
- Excel chart 目前以 canonical reference 表示，不會重建繪圖 series。
- PPTX 閱讀順序依 top/left 幾何排序，重疊或多閱讀流版面可能不準確。
- DOCX tracked changes、nested tables 與精確 inline-image anchoring 仍有限制。
- 舊式二進位 Office 與轉回 Office 格式不在目前範圍內。

## 開發與發布檢查

```bash
python scripts/capability_probe.py --json
python -m pytest tests/ -q
python -m py_compile scripts/*.py tests/*.py
```

GitHub Actions 會在 push 與 pull request 時執行上述檢查。發布專用檢查請參考 `RELEASING.md` 與 `RELEASE_CHECKLIST.md`。

## 專案結構

```text
SKILL.md                    AI skill 操作合約
scripts/                    Router、converters、models、validation 與 utilities
schemas/                    Canonical JSON Schemas
references/                 Capability matrix 與 engine notes
tests/                      Regression 與 integration tests
requirements.txt            Runtime 與測試 dependencies
```

## 授權

本專案採用 [Apache License 2.0](LICENSE)。

此授權允許商業使用、修改與再散布，但須遵守授權條款，並包含明確的 contributor patent grant。第三方 dependencies 仍適用各自授權，請參考 `THIRD_PARTY_NOTICES.md` 與 `LICENSES.md`。
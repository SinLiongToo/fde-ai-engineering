# AI 工程實戰課：給前線部署工程師 (FDE)
### AI Engineering for Forward Deployed Engineers

給有經驗的軟體工程師的中英雙語課程：如何在客戶環境中，把 LLM 系統從 demo 做到能上線、能維運。
每一章都對應一段可離線執行、附測試的 Python 程式。

A bilingual (繁體中文 / English) course for experienced engineers on taking LLM systems from demo to
production in customer environments. Every chapter maps to offline, tested Python code.

---

## 內容 / Contents

| # | 章節 | Chapter | 練習 / Lab |
|---|------|---------|-----------|
| 1 | FDE 是做什麼的 | What FDEs actually do | |
| 2 | 從需求到上線的交付流程 | The engagement lifecycle | |
| 3 | 與 Coding Agent 協作 | Working with coding agents | `labs/code_reviewer` |
| 4 | 結構化輸出與資料契約 | Structured output and contracts | `labs/core/contracts.py` |
| 5 | 檢索與 RAG | Retrieval and RAG | `labs/core/retrieval.py` |
| 6 | Agent、工具與人工審核 | Agents, tools and approvals | `labs/core/agent.py`, `labs/mcp_sre` |
| 7 | 評測：把感覺變成數字 | Evals: from vibes to numbers | `labs/core/evals.py` |
| 8 | 上線：可觀測性、安全與成本 | Production: observability, security, cost | |
| 9 | 實作練習與延伸資源 | Labs and further reading | |

第 4 到 7 章各有一個瀏覽器內的互動示範，使用和 Python 練習相同的演算法（檢索示範已驗證與 Python 結果一致）。

Chapters 4–7 each include an in-browser demo running the same algorithms as the Python labs
(the retrieval demo is verified to match the Python results exactly).

## 使用 / Usage

**網站 / Website** — 純靜態 HTML，不需要建置。直接開啟 `docs/index.html`，或：

```bash
python -m http.server 8000 --directory docs
# http://localhost:8000
```

要放上 GitHub Pages：Settings → Pages → Source 選 `main` 分支的 `/docs` 資料夾。

To publish on GitHub Pages: Settings → Pages → deploy from the `/docs` folder on `main`.

**練習 / Labs** — Python 3.10+，不需要 API key。

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest                     # 58 tests
python -m labs.core.evals            # eval gate against labs/core/baseline.json
python -m labs.mcp_sre.cli --stdio   # MCP server over a real stdio subprocess
```

## 專案結構 / Layout

```text
docs/                    網站 / website (static HTML, no build step)
  index.html             首頁、課程地圖、自我評估
  01-…09-*.html          九個章節
  assets/site.css        設計系統：顏色變數、深淺色、版面
  assets/site.js         側欄、目錄、語言/主題切換、小測驗、進度
  assets/demos/*.js      第 4–7 章的互動示範
labs/
  core/                  第 4–7 章：契約、檢索、agent、評測
  code_reviewer/         AST 靜態分析 + 選用 LLM 補充
  mcp_sre/               最小 MCP server/client + SRE 診斷 workflow
.github/workflows/ci.yml 單元測試 + 評測 gate
```

## 維護 / Maintaining

- **雙語**：每段內容以相鄰的 `lang="zh-Hant"` 與 `lang="en"` 元素撰寫，CSS 依 `html[data-lang]` 顯示其中一種。
  修改時兩種語言一起改。中文段落請寫在同一行，避免換行在中文字之間產生多餘空白。
- **新增章節**：複製任一章節頁，修改 `data-page` 與標題，再把章節加進 `docs/assets/site.js` 的 `CHAPTERS`。
- **程式碼與網頁一致**：網頁中的程式碼節錄來自 `labs/`。修改 lab 時，同步更新對應章節的節錄。

- **Bilingual**: every piece of content is written as adjacent `lang="zh-Hant"` and `lang="en"` elements;
  CSS shows one based on `html[data-lang]`. Edit both together.
- **Adding a chapter**: copy a chapter page, change `data-page` and titles, and add it to `CHAPTERS` in `docs/assets/site.js`.
- **Keep code and pages in sync**: code excerpts on the pages come from `labs/`; update both together.

## 授權 / License

MIT，見 [LICENSE](LICENSE)。

"""專案設定集中在這裡，不要散落在各個檔案。"""

MODEL = "claude-opus-5-5"
MAX_TOKENS = 4000

# 本地開源模型（透過 Ollama 執行）。先執行 `ollama pull qwen2.5:3b` 下載模型。
# 3B 量化版約 2 GB，一般筆電（8 GB 記憶體）可以跑；記憶體或顯存夠的話可改成 qwen2.5:7b 等較大的模型。
OLLAMA_MODEL = "qwen2.5:3b"
OLLAMA_HOST = "http://localhost:11434"   # 可用環境變數 OLLAMA_HOST 覆寫
OLLAMA_TIMEOUT_SECONDS = 300             # CPU 跑模型可能很慢，逾時設長一點

# 每百萬 token 的價格（美元）：(輸入, 輸出)。
# ⚠ 價格會變動，請以官方定價頁為準。這裡的數字查詢於 2026-10。
PRICES_PER_MTOK = {
    "claude-opus-5-5": (4.00, 20.00),
}
# 本地模型沒有 API 費用（但有硬體、電費與維運成本，見進階篇第 08 章）

# 機器人的行為參數
SEARCH_TOP_N = 3          # 每次最多放幾段手冊進 prompt
MAX_HISTORY_TURNS = 4     # 只保留最近幾輪對話（一問一答算一輪）
MAX_TOOL_ROUNDS = 3       # 一個問題最多呼叫幾輪工具，避免無限迴圈
MAX_RETRIES = 1           # 回答格式不合格時，最多重試幾次

"""專案設定集中在這裡，不要散落在各個檔案。"""

MODEL = "claude-opus-5-5"
MAX_TOKENS = 4000

# 每百萬 token 的價格（美元）：(輸入, 輸出)。
# ⚠ 價格會變動，請以官方定價頁為準。這裡的數字查詢於 2026-10。
PRICES_PER_MTOK = {
    "claude-opus-5-5": (4.00, 20.00),
}

# 機器人的行為參數
SEARCH_TOP_N = 3          # 每次最多放幾段手冊進 prompt
MAX_HISTORY_TURNS = 4     # 只保留最近幾輪對話（一問一答算一輪）
MAX_TOOL_ROUNDS = 3       # 一個問題最多呼叫幾輪工具，避免無限迴圈
MAX_RETRIES = 1           # 回答格式不合格時，最多重試幾次

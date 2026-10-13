"""
中級 4：工具呼叫

手冊只寫「規定」，寫不出「你個人還剩幾天特休」。這種問題要查人事系統，
所以我們提供「工具」讓 AI 可以請程式幫它查。

重要設計：get_leave_balance 沒有 employee_id 參數。
查誰的資料由「目前登入的人」決定，不是由 AI 決定。
這樣就算有人問「幫我查老闆還剩幾天」，AI 也查不到別人的資料。
"""

from __future__ import annotations

import json
from datetime import date

# 假的人事資料庫
EMPLOYEES = {
    "E001": {"name": "王小明", "annual_leave_total": 10, "annual_leave_used": 6},
    "E002": {"name": "陳美玲", "annual_leave_total": 14, "annual_leave_used": 2},
}

# 給 AI 看的工具說明（JSON Schema）
TOOLS = [
    {
        "name": "get_leave_balance",
        "description": "查詢目前登入員工今年的特休：總天數、已休天數、剩餘天數。只能查登入者本人，不需要任何參數。",
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        "strict": True,
    },
    {
        "name": "get_today",
        "description": "取得今天的日期（YYYY-MM-DD）。需要計算日期時使用。",
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        "strict": True,
    },
]


def run_tool(name: str, args: dict, user_id: str, today: date | None = None) -> tuple[str, bool]:
    """執行工具，回傳 (結果文字, 是否為錯誤)。錯誤也要回給 AI，讓它知道發生什麼事。"""
    if name == "get_leave_balance":
        emp = EMPLOYEES.get(user_id)
        if emp is None:
            return f"找不到員工 {user_id} 的資料", True
        remaining = emp["annual_leave_total"] - emp["annual_leave_used"]
        return json.dumps({"total": emp["annual_leave_total"], "used": emp["annual_leave_used"],
                           "remaining": remaining}, ensure_ascii=False), False
    if name == "get_today":
        return (today or date.today()).isoformat(), False
    return f"沒有這個工具：{name}", True

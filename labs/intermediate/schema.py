"""
中級 2：結構化回答

機器人的回答不是一段自由文字，而是固定格式的 JSON：
    {"found": true, "answer": "...", "citations": ["H01"]}

好處：程式可以檢查它。例如
- 說「找到了」就一定要附出處
- 出處必須是這次真的搜尋到的段落（不能編一個 H99）
- 說「沒找到」就不能附出處
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationInfo, model_validator

# 送給 API 的 JSON Schema：只放結構（型別、必填），規則由下面的 Pydantic 模型檢查
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean", "description": "手冊或工具結果裡有沒有這個問題的答案"},
        "answer": {"type": "string", "description": "給員工看的回答，繁體中文，簡潔"},
        "citations": {"type": "array", "items": {"type": "string"}, "description": "引用的段落編號，例如 H01"},
    },
    "required": ["found", "answer", "citations"],
    "additionalProperties": False,
}


class BotAnswer(BaseModel):
    found: bool
    answer: str = Field(min_length=1)
    citations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_citations(self, info: ValidationInfo) -> "BotAnswer":
        ctx = info.context or {}
        retrieved = set(ctx.get("retrieved_ids", []))
        used_tool = ctx.get("used_tool", False)

        if self.found and not self.citations and not used_tool:
            raise ValueError("found 為 true 時，citations 不能是空的：請附上段落編號")
        if not self.found and self.citations:
            raise ValueError("found 為 false 時，不應該有 citations")
        unknown = [c for c in self.citations if c not in retrieved]
        if unknown:
            raise ValueError(f"引用了這次沒有提供的段落：{', '.join(unknown)}；只能引用 {sorted(retrieved)}")
        return self


def parse_answer(raw: str, retrieved_ids: list[str], used_tool: bool = False) -> BotAnswer:
    """把模型的文字輸出解析成 BotAnswer；不合格會丟出 pydantic.ValidationError。"""
    return BotAnswer.model_validate_json(raw, context={"retrieved_ids": retrieved_ids, "used_tool": used_tool})

"""
中級 1：把「呼叫 AI」包成一個小介面

機器人的其他程式只認得 `llm.create(...)` 這一個方法，回傳一個 Reply。
所以我們可以有兩種實作：
- ClaudeLLM：真的呼叫 Claude API（需要 ANTHROPIC_API_KEY）
- FakeLLM：離線的假模型，規則固定，用來開發與測試，不花錢、結果可重現

這個技巧叫「依賴注入」：需要什麼由外面傳進來，而不是寫死在程式裡。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import MAX_TOKENS, MODEL
from .search import expand_synonyms, pieces


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class Reply:
    content: Any                 # 原封不動放回對話歷史用的內容區塊
    text: str                    # 所有文字區塊合併
    tool_calls: list[ToolCall]
    stop_reason: str             # end_turn / tool_use / max_tokens / refusal ...
    input_tokens: int
    output_tokens: int


class LLM(Protocol):
    def create(self, system: str, messages: list[dict], tools: list[dict] | None = None,
               output_schema: dict | None = None) -> Reply: ...


class ClaudeLLM:
    def __init__(self, model: str = MODEL, max_tokens: int = MAX_TOKENS):
        import anthropic  # 只有真的要呼叫 API 時才需要安裝

        self.client = anthropic.Anthropic()  # 讀取環境變數 ANTHROPIC_API_KEY
        self.model = model
        self.max_tokens = max_tokens

    def create(self, system, messages, tools=None, output_schema=None) -> Reply:
        kwargs: dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens,
                                  "system": system, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        if output_schema:
            kwargs["output_config"] = {"format": {"type": "json_schema", "schema": output_schema}}
        r = self.client.messages.create(**kwargs)
        return Reply(
            content=r.content,
            text="".join(b.text for b in r.content if b.type == "text"),
            tool_calls=[ToolCall(b.id, b.name, b.input) for b in r.content if b.type == "tool_use"],
            stop_reason=r.stop_reason,
            input_tokens=r.usage.input_tokens,
            output_tokens=r.usage.output_tokens,
        )


# ---------------------------------------------------------------- 離線假模型

CONTEXT_LINE = re.compile(r"^\[(H\d+)\] (.+)$", re.M)
BALANCE_QUESTION = re.compile(r"(剩.*(特休|年假))|((特休|年假).*剩)")


@dataclass
class FakeLLM:
    """
    規則式的假模型（不是 AI）：
    - 問到「還剩幾天特休」且有工具可用 → 先呼叫 get_leave_balance
    - 收到工具結果 → 用結果回答
    - 其他問題 → 從提供的手冊段落中，挑和問題最相近的一句話當答案
    - 沒有提供段落 → 回答「手冊沒有寫到這件事」
    mistakes：前幾次回答故意犯的錯（例如 "fake_citation"），用來測試重試機制。
    token 數用字數估算，不是真的 token。
    """

    mistakes: list[str] = field(default_factory=list)
    calls: int = 0

    def create(self, system, messages, tools=None, output_schema=None) -> Reply:
        self.calls += 1
        question, context = self._find_question(messages)
        last = messages[-1]["content"]
        tool_results = last if isinstance(last, list) else []

        if tools and BALANCE_QUESTION.search(question) and not tool_results:
            call = ToolCall(id=f"toolu_fake_{self.calls}", name="get_leave_balance", input={})
            content = [{"type": "tool_use", "id": call.id, "name": call.name, "input": call.input}]
            return self._reply(system, messages, content, "", [call], "tool_use")

        if tool_results:
            data = json.loads(tool_results[0]["content"])
            cites = ["H01"] if "H01" in context else []
            answer = {"found": True, "answer": f"你今年還剩 {data['remaining']} 天特休（共 {data['total']} 天，已休 {data['used']} 天）。",
                      "citations": cites}
        else:
            answer = self._extract(question, context)

        if self.mistakes:
            mistake = self.mistakes.pop(0)
            if mistake == "fake_citation":
                answer = {**answer, "found": True, "citations": ["H99"]}
            elif mistake == "no_citation":
                answer = {**answer, "found": True, "citations": []}
        text = json.dumps(answer, ensure_ascii=False)
        return self._reply(system, messages, [{"type": "text", "text": text}], text, [], "end_turn")

    @staticmethod
    def _find_question(messages: list[dict]) -> tuple[str, dict[str, str]]:
        for m in reversed(messages):
            if m["role"] == "user" and isinstance(m["content"], str) and "問題：" in m["content"]:
                body = m["content"]
                question = body.rsplit("問題：", 1)[1].strip()
                return question, dict(CONTEXT_LINE.findall(body))
        return "", {}

    @staticmethod
    def _extract(question: str, context: dict[str, str]) -> dict:
        """挑和問題最相近的那一段，直接引用整段內容。"""
        q = pieces(expand_synonyms(question))
        best = (0, None, "")
        for doc_id, text in context.items():
            score = len(q & pieces(text))
            if score > best[0]:
                best = (score, doc_id, text)
        if best[1] is None:
            return {"found": False, "answer": "手冊沒有寫到這件事，建議詢問人資部門。", "citations": []}
        return {"found": True, "answer": f"根據手冊 {best[1]}：{best[2]}", "citations": [best[1]]}

    @staticmethod
    def _reply(system, messages, content, text, tool_calls, stop_reason) -> Reply:
        approx_in = len(system) + len(json.dumps(messages, ensure_ascii=False, default=str))
        return Reply(content, text, tool_calls, stop_reason, approx_in, max(len(text), 10))

"""
中級 1：把「呼叫 AI」包成一個小介面

機器人的其他程式只認得 `llm.create(...)` 這一個方法，回傳一個 Reply。
所以我們可以有三種實作：
- ClaudeLLM：呼叫雲端的 Claude API（需要 ANTHROPIC_API_KEY）
- OllamaLLM：呼叫在自己電腦上執行的開源模型（需要安裝 Ollama），資料不離開本機
- FakeLLM：離線的假模型，規則固定，用來開發與測試，不花錢、結果可重現

這個技巧叫「依賴注入」：需要什麼由外面傳進來，而不是寫死在程式裡。
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import MAX_TOKENS, MODEL, OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS
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


# ---------------------------------------------------------------- 本地開源模型（Ollama）

class OllamaLLM:
    """
    呼叫本機 Ollama 的 /api/chat。Ollama 的訊息格式和 Claude 不同，這裡負責互相轉換，
    讓 bot.py 完全不用改：
      Claude 格式                                Ollama 格式
      system 參數                         →      {"role": "system"} 訊息
      assistant 的 tool_use 區塊           →      assistant 訊息的 tool_calls（沒有 id）
      user 訊息裡的 tool_result 區塊       →      {"role": "tool", "tool_name": ...} 訊息
      tools 的 input_schema               →      {"type": "function", "function": {"parameters": ...}}
      output_config 的 JSON Schema        →      format 欄位
    ⚠ 小模型對工具呼叫與 JSON 格式的遵守程度通常不如大型模型，請用 I6 的評測量出差距。
    """

    def __init__(self, model: str = OLLAMA_MODEL, host: str | None = None,
                 timeout: float = OLLAMA_TIMEOUT_SECONDS, max_tokens: int = MAX_TOKENS):
        self.model = model
        self.host = (host or os.getenv("OLLAMA_HOST") or OLLAMA_HOST).rstrip("/")
        self.timeout = timeout
        self.max_tokens = max_tokens
        self._calls = 0

    def create(self, system, messages, tools=None, output_schema=None) -> Reply:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + to_ollama_messages(messages),
            "stream": False,
            "options": {"num_predict": self.max_tokens},
        }
        if tools:
            body["tools"] = [to_ollama_tool(t) for t in tools]
        if output_schema:
            body["format"] = output_schema
        data = self._post("/api/chat", body)

        self._calls += 1
        msg = data.get("message", {})
        text = msg.get("content") or ""
        calls = []
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):           # 保險起見：有些版本可能回傳字串
                args = json.loads(args or "{}")
            calls.append(ToolCall(id=f"ollama_{self._calls}_{i}", name=fn.get("name", ""), input=args))

        # 用 Claude 格式存回對話歷史，bot.py 才能一致處理
        content: list[dict] = []
        if text:
            content.append({"type": "text", "text": text})
        content += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in calls]

        if calls:
            stop = "tool_use"
        elif data.get("done_reason") == "length":
            stop = "max_tokens"
        else:
            stop = "end_turn"
        return Reply(content, text, calls, stop,
                     int(data.get("prompt_eval_count") or 0), int(data.get("eval_count") or 0))

    def _post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(self.host + path, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"連不到 Ollama（{self.host}）。請確認已安裝並啟動 Ollama，"
                f"且已執行 `ollama pull {self.model}`。原始錯誤：{e}"
            ) from e


def to_ollama_tool(tool: dict) -> dict:
    return {"type": "function", "function": {
        "name": tool["name"], "description": tool.get("description", ""), "parameters": tool["input_schema"]}}


def to_ollama_messages(messages: list[dict]) -> list[dict]:
    """把 Claude 格式的對話歷史轉成 Ollama 格式。"""
    out: list[dict] = []
    tool_names: dict[str, str] = {}      # tool_use id → 工具名稱（Ollama 的工具結果要寫名稱）
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
            continue
        blocks = [b if isinstance(b, dict) else b.model_dump() for b in content]
        if m["role"] == "assistant":
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            calls = []
            for b in blocks:
                if b.get("type") == "tool_use":
                    tool_names[b["id"]] = b["name"]
                    calls.append({"function": {"name": b["name"], "arguments": b.get("input") or {}}})
            msg: dict[str, Any] = {"role": "assistant", "content": text}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
        else:
            for b in blocks:
                if b.get("type") == "tool_result":
                    out.append({"role": "tool", "content": str(b.get("content", "")),
                                "tool_name": tool_names.get(b.get("tool_use_id"), "")})
                elif b.get("type") == "text":
                    out.append({"role": "user", "content": b.get("text", "")})
    return out


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

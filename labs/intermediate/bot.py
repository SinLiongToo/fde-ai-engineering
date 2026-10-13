"""
員工手冊問答機器人：把前面每一章的零件組起來。

一次提問的流程：
  1. 搜尋手冊（search.py）
  2. 組 prompt：相關段落 + 問題
  3. 呼叫 AI；如果它要用工具，就執行工具、把結果交回去，再呼叫一次（最多 MAX_TOOL_ROUNDS 輪）
  4. 檢查回答格式與出處（schema.py）；不合格就把錯誤告訴它，重試一次
  5. 記錄用量，並把「問題 + 最終回答」存進對話歷史（不存手冊段落，省 token）
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError

from . import config
from .llm import LLM
from .schema import ANSWER_SCHEMA, BotAnswer, parse_answer
from .search import Searcher
from .tools import TOOLS, run_tool

SYSTEM_PROMPT = """你是「星河軟體」的員工手冊助理，回答員工關於公司規定的問題。

規則：
1. 只根據 <手冊> 裡的段落，或工具查到的結果回答。不要用一般常識補充公司規定。
2. 回答要附上引用的段落編號（例如 H01）。
3. 如果手冊和工具都沒有答案，found 設為 false，並建議詢問人資部門。不要猜。
4. 問到個人資料（例如自己還剩幾天特休）時，使用工具查詢。
5. 用繁體中文，簡潔回答。"""


def build_user_message(question: str, hits) -> str:
    if hits:
        context = "\n".join(f"[{h.chunk.id}] {h.chunk.full}" for h in hits)
    else:
        context = "（沒有找到相關段落）"
    return f"<手冊>\n{context}\n</手冊>\n\n問題：{question}"


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, reply) -> None:
        self.calls += 1
        self.input_tokens += reply.input_tokens
        self.output_tokens += reply.output_tokens

    def cost_usd(self, model: str = config.MODEL) -> float:
        price_in, price_out = config.PRICES_PER_MTOK[model]
        return (self.input_tokens * price_in + self.output_tokens * price_out) / 1_000_000


@dataclass
class Turn:
    question: str
    answer: BotAnswer | None
    retrieved: list[str]
    tool_calls: list[dict] = field(default_factory=list)
    attempts: int = 1
    error: str | None = None
    usage: Usage = field(default_factory=Usage)


class HandbookBot:
    def __init__(self, llm: LLM, user_id: str = "E001", searcher: Searcher | None = None,
                 max_history_turns: int = config.MAX_HISTORY_TURNS):
        self.llm = llm
        self.user_id = user_id            # 由登入系統決定，AI 無法更改
        self.searcher = searcher or Searcher()
        self.max_history_turns = max_history_turns
        self.history: list[dict] = []     # 只存「問題」與「最終回答文字」
        self.total_usage = Usage()

    def ask(self, question: str) -> Turn:
        hits = self.searcher.search(question, top_n=config.SEARCH_TOP_N)
        retrieved = [h.chunk.id for h in hits]
        turn = Turn(question, None, retrieved)

        recent = self.history[-2 * self.max_history_turns:] if self.max_history_turns else []
        messages = recent + [{"role": "user", "content": build_user_message(question, hits)}]

        reply = self._call(messages, turn)
        # ---- 工具迴圈：只要 AI 要求用工具，就執行並交回結果
        rounds = 0
        while reply.stop_reason == "tool_use" and reply.tool_calls:
            rounds += 1
            if rounds > config.MAX_TOOL_ROUNDS:
                turn.error = f"工具呼叫超過 {config.MAX_TOOL_ROUNDS} 輪，已停止"
                return self._finish(turn)
            messages.append({"role": "assistant", "content": reply.content})  # 原封不動放回去
            results = []
            for call in reply.tool_calls:
                content, is_error = run_tool(call.name, call.input, self.user_id)
                turn.tool_calls.append({"name": call.name, "input": call.input, "result": content, "is_error": is_error})
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": content, "is_error": is_error})
            messages.append({"role": "user", "content": results})          # 所有結果放在同一則訊息
            reply = self._call(messages, turn)

        if reply.stop_reason in ("max_tokens", "refusal"):
            turn.error = f"沒有可用的回答（stop_reason={reply.stop_reason}）"
            return self._finish(turn)

        # ---- 檢查格式與出處；不合格就回饋錯誤，重試
        used_tool = bool(turn.tool_calls)
        for attempt in range(config.MAX_RETRIES + 1):
            turn.attempts = attempt + 1
            try:
                turn.answer = parse_answer(reply.text, retrieved, used_tool)
                break
            except ValidationError as err:
                if attempt == config.MAX_RETRIES:
                    turn.error = "回答格式檢查失敗：" + "; ".join(e["msg"] for e in err.errors())
                    return self._finish(turn)
                feedback = "你上一次的回答沒有通過檢查：\n" + "\n".join(f"- {e['msg']}" for e in err.errors()) + \
                           "\n請修正後重新回答，只輸出 JSON。"
                messages += [{"role": "assistant", "content": reply.content}, {"role": "user", "content": feedback}]
                reply = self._call(messages, turn, tools=False)

        self.history += [{"role": "user", "content": question},
                         {"role": "assistant", "content": turn.answer.answer}]
        return self._finish(turn)

    def reset(self) -> None:
        self.history = []

    def _call(self, messages: list[dict], turn: Turn, tools: bool = True):
        reply = self.llm.create(SYSTEM_PROMPT, messages, TOOLS if tools else None, ANSWER_SCHEMA)
        turn.usage.add(reply)
        return reply

    def _finish(self, turn: Turn) -> Turn:
        self.total_usage.calls += turn.usage.calls
        self.total_usage.input_tokens += turn.usage.input_tokens
        self.total_usage.output_tokens += turn.usage.output_tokens
        return turn

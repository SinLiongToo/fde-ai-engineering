"""
第 6 章：Agent、狀態與人工審核 / Chapter 6: Agents, state and human approval

這個檔案用不到 100 行的核心邏輯，示範 LangGraph 這類框架背後的機制：
This file shows, framework-free, the mechanics that LangGraph-style frameworks provide:

1. 迴圈：planner 決定下一步 → 執行工具 → 結果寫回狀態 → 再問 planner。
   Loop: planner picks next action -> run tool -> write result to state -> repeat.
2. 狀態可序列化，每一步都存 checkpoint，程序掛掉可以從最後一步接續。
   State is serializable and checkpointed after every step.
3. 風險標在「工具」上，而不是去掃描 SQL 字串找 DROP/DELETE。
   Risk is declared on the tool, not guessed by scanning SQL for keywords.
4. 非唯讀工具會中斷 (interrupt)，等人核准後用同一個 thread_id 恢復 (resume)。
   Non-read tools interrupt; a human approves; the run resumes on the same thread.
5. 最小權限：唯讀工具使用唯讀資料庫連線。就算模型塞了 DELETE，資料庫也會拒絕。
   Least privilege: the read tool uses a read-only DB connection.
6. 步數上限，防止無窮迴圈燒錢。
   A step budget stops runaway loops.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Protocol

Risk = Literal["read", "write", "destructive"]
Status = Literal["running", "waiting_approval", "done", "rejected", "halted"]


# ------------------------------------------------------------------ tools

@dataclass
class Tool:
    name: str
    description: str
    risk: Risk
    fn: Callable[..., Any]


def make_database() -> tuple[sqlite3.Connection, sqlite3.Connection]:
    """回傳 (讀寫連線, 唯讀連線)，兩者指向同一個記憶體資料庫。"""
    uri = f"file:lab-{uuid.uuid4().hex}?mode=memory&cache=shared"
    rw = sqlite3.connect(uri, uri=True)
    rw.executescript(
        """
        CREATE TABLE api_tokens (id INTEGER PRIMARY KEY, customer TEXT, expires_days_ago INTEGER);
        INSERT INTO api_tokens (customer, expires_days_ago) VALUES
          ('acme', 45), ('acme', -10), ('globex', 90), ('initech', 5), ('globex', 31);
        """
    )
    rw.commit()
    ro = sqlite3.connect(uri, uri=True)
    ro.execute("PRAGMA query_only = ON")  # 資料庫層級的唯讀 / enforced by the database
    return rw, ro


def build_tools(rw: sqlite3.Connection, ro: sqlite3.Connection) -> dict[str, Tool]:
    def run_select(sql: str) -> list[tuple]:
        return ro.execute(sql).fetchall()

    def delete_expired_tokens(older_than_days: int) -> dict:
        if older_than_days < 30:
            raise ValueError("refusing to delete tokens expired less than 30 days ago")
        cur = rw.execute("DELETE FROM api_tokens WHERE expires_days_ago > ?", (older_than_days,))
        rw.commit()
        return {"deleted": cur.rowcount}

    tools = [
        Tool("run_select", "Run a read-only SQL query.", "read", run_select),
        Tool("delete_expired_tokens", "Delete tokens expired more than N days ago.", "destructive",
             delete_expired_tokens),
    ]
    return {t.name: t for t in tools}


# ------------------------------------------------------------------ state

@dataclass
class ToolCall:
    tool: str
    args: dict
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class AgentState:
    thread_id: str
    goal: str
    status: Status = "running"
    steps: int = 0
    max_steps: int = 8
    history: list[dict] = field(default_factory=list)   # 每次工具呼叫與結果 / calls and results
    pending: dict | None = None                         # 等待核准的呼叫 / call awaiting approval
    approvals: list[dict] = field(default_factory=list)  # 稽核紀錄 / audit trail

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, default=str)

    @classmethod
    def from_json(cls, raw: str) -> "AgentState":
        return cls(**json.loads(raw))


class CheckpointStore:
    """
    以 JSON 字串保存每一步，模擬放在 Postgres 的 checkpoint 表。
    存字串（而不是物件參照）可以確保狀態真的可序列化。
    Stores JSON strings, which proves the state really is serializable.
    """

    def __init__(self) -> None:
        self._rows: dict[str, list[str]] = {}

    def save(self, state: AgentState) -> None:
        self._rows.setdefault(state.thread_id, []).append(state.to_json())

    def latest(self, thread_id: str) -> AgentState:
        return AgentState.from_json(self._rows[thread_id][-1])

    def history(self, thread_id: str) -> list[AgentState]:
        return [AgentState.from_json(r) for r in self._rows.get(thread_id, [])]


# ------------------------------------------------------------------ planner

class Planner(Protocol):
    """真實系統中這裡是 LLM：看狀態，決定下一個工具呼叫；回傳 None 表示完成。"""

    def next_action(self, state: AgentState) -> ToolCall | None: ...


class ScriptedPlanner:
    """離線用的規則式 planner，行為固定，方便測試 / Deterministic stand-in for an LLM."""

    def next_action(self, state: AgentState) -> ToolCall | None:
        done = [h["tool"] for h in state.history]
        goal = state.goal.lower()
        if "run_select" not in done:
            return ToolCall("run_select", {"sql": "SELECT customer, expires_days_ago FROM api_tokens "
                                                  "WHERE expires_days_ago > 30"})
        if "clean" in goal and "delete_expired_tokens" not in done:
            return ToolCall("delete_expired_tokens", {"older_than_days": 30})
        return None


# ------------------------------------------------------------------ runtime

@dataclass
class Decision:
    approved: bool
    approver: str
    reason: str = ""


class Agent:
    def __init__(self, tools: dict[str, Tool], planner: Planner, store: CheckpointStore):
        self.tools, self.planner, self.store = tools, planner, store

    def start(self, goal: str, thread_id: str | None = None, max_steps: int = 8) -> AgentState:
        state = AgentState(thread_id=thread_id or uuid.uuid4().hex[:8], goal=goal, max_steps=max_steps)
        self.store.save(state)
        return self._loop(state)

    def resume(self, thread_id: str, decision: Decision) -> AgentState:
        state = self.store.latest(thread_id)
        if state.status != "waiting_approval" or state.pending is None:
            raise ValueError(f"thread {thread_id} is not waiting for approval (status={state.status})")
        call = ToolCall(**state.pending)
        state.approvals.append({
            "call_id": call.id, "tool": call.tool, "args": call.args,
            "approved": decision.approved, "approver": decision.approver, "reason": decision.reason,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        state.pending = None
        if not decision.approved:
            state.status = "rejected"
            self.store.save(state)
            return state
        state.status = "running"
        self._execute(state, call)
        self.store.save(state)
        return self._loop(state)

    def _loop(self, state: AgentState) -> AgentState:
        while state.status == "running":
            if state.steps >= state.max_steps:
                state.status = "halted"
                break
            call = self.planner.next_action(state)
            if call is None:
                state.status = "done"
                break
            tool = self.tools.get(call.tool)
            if tool is None:
                state.history.append({"tool": call.tool, "args": call.args, "error": "unknown tool"})
                state.steps += 1
            elif tool.risk != "read":
                state.pending = asdict(call)
                state.status = "waiting_approval"   # interrupt：交給人決定 / hand off to a human
            else:
                self._execute(state, call)
            self.store.save(state)
        self.store.save(state)
        return state

    def _execute(self, state: AgentState, call: ToolCall) -> None:
        tool = self.tools[call.tool]
        entry: dict[str, Any] = {"id": call.id, "tool": call.tool, "args": call.args}
        try:
            entry["result"] = tool.fn(**call.args)
        except Exception as e:  # 錯誤當作結果回給 planner，而不是讓整個 agent 崩潰
            entry["error"] = f"{type(e).__name__}: {e}"
        state.history.append(entry)
        state.steps += 1


def new_agent() -> tuple[Agent, sqlite3.Connection]:
    rw, ro = make_database()
    return Agent(build_tools(rw, ro), ScriptedPlanner(), CheckpointStore()), rw


if __name__ == "__main__":
    agent, db = new_agent()
    s = agent.start("Clean up API tokens that expired over a month ago")
    print("status:", s.status, "| pending:", s.pending)
    s = agent.resume(s.thread_id, Decision(approved=True, approver="alice@example.com", reason="ticket OPS-123"))
    print("status:", s.status)
    for h in s.history:
        print(" ", h)
    print("remaining rows:", db.execute("SELECT COUNT(*) FROM api_tokens").fetchone()[0])

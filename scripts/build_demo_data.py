"""
重新產生網頁示範用的資料檔，讓網頁與 Python 程式保持一致。
修改 labs/intermediate 的手冊、同義詞、價格或工具流程後執行：

    python scripts/build_demo_data.py

產生：
  docs/assets/demos/handbook_data.js  手冊段落、同義詞、門檻、價格（I3、I5 示範）
  docs/assets/demos/tooltrace.js      一次工具呼叫的完整訊息紀錄（I4 示範）
"""

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from labs.intermediate import config  # noqa: E402
from labs.intermediate.bot import HandbookBot  # noqa: E402
from labs.intermediate.llm import FakeLLM  # noqa: E402
from labs.intermediate.search import PUNCT, SYNONYMS, Searcher, load_chunks  # noqa: E402

DEMOS = ROOT / "docs" / "assets" / "demos"


def build_handbook_data() -> None:
    data = {
        "chunks": [{"id": c.id, "title": c.title, "text": c.text} for c in load_chunks()],
        "synonyms": SYNONYMS,
        "punct": "".join(sorted(PUNCT)),
        "min_score": Searcher().min_score,
        "model": config.MODEL,
        "prices": config.PRICES_PER_MTOK,
    }
    (DEMOS / "handbook_data.js").write_text(
        "// 由 scripts/build_demo_data.py 產生，請勿手動修改\n"
        "window.FDE_HANDBOOK = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8",
    )


def build_tool_trace(question: str = "我今年還剩幾天特休？") -> None:
    steps = []

    class Recorder:
        def __init__(self):
            self.inner = FakeLLM()

        def create(self, system, messages, tools=None, output_schema=None):
            steps.append({"kind": "request", "messages": copy.deepcopy(messages),
                          "tools": [t["name"] for t in tools] if tools else []})
            reply = self.inner.create(system, messages, tools, output_schema)
            steps.append({"kind": "reply", "stop_reason": reply.stop_reason, "content": copy.deepcopy(reply.content)})
            return reply

    turn = HandbookBot(Recorder(), user_id="E001").ask(question)
    steps.append({"kind": "final", "answer": turn.answer.model_dump()})
    (DEMOS / "tooltrace.js").write_text(
        f"// 由 scripts/build_demo_data.py 產生：實際執行 labs/intermediate 的紀錄（FakeLLM，問題：{question}）\n"
        "window.FDE_TOOL_TRACE = " + json.dumps(steps, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    build_handbook_data()
    build_tool_trace()
    print("updated", DEMOS / "handbook_data.js", "and", DEMOS / "tooltrace.js")

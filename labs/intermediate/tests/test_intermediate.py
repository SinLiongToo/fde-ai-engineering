import json

import pytest
from pydantic import ValidationError

from labs.intermediate import config, evals
from labs.intermediate.bot import HandbookBot, build_user_message
from labs.intermediate.llm import FakeLLM, Reply, ToolCall
from labs.intermediate.schema import parse_answer
from labs.intermediate.search import Searcher, expand_synonyms, load_chunks
from labs.intermediate.tools import TOOLS, run_tool


# ---------------------------------------------------------------- search (I3)

def test_handbook_chunks():
    chunks = load_chunks()
    assert [c.id for c in chunks] == [f"H{i:02d}" for i in range(1, 13)]
    assert chunks[4].title == "遠端工作"


def test_synonyms_expand_query():
    assert "筆記型電腦" in expand_synonyms("筆電壞了")


@pytest.mark.parametrize("version,laptop_found,lunch_found", [
    ("v1", False, True),    # v1：同義詞找不到、沒寫的事亂配
    ("v2", False, False),   # v2：門檻擋掉亂配，但同義詞仍找不到
    ("v3", True, False),    # v3：兩者都解決
])
def test_search_versions(version, laptop_found, lunch_found):
    s = Searcher(version=version)
    assert ("H08" in [h.chunk.id for h in s.search("筆電壞了可以自己拿去修嗎？")]) == laptop_found
    assert bool(s.search("公司有提供免費午餐嗎？")) == lunch_found


def test_search_comparison_numbers():
    table = evals.compare_search_versions()
    assert table["v1"]["total"] == "11/18"
    assert table["v3"]["total"] == "15/18"


# ---------------------------------------------------------------- schema (I2)

def test_valid_answer():
    a = parse_answer('{"found": true, "answer": "三天", "citations": ["H01"]}', ["H01", "H03"])
    assert a.citations == ["H01"]


@pytest.mark.parametrize("raw,msg", [
    ('{"found": true, "answer": "x", "citations": []}', "不能是空的"),
    ('{"found": true, "answer": "x", "citations": ["H99"]}', "H99"),
    ('{"found": false, "answer": "x", "citations": ["H01"]}', "不應該有"),
    ('{"found": true, "answer": "", "citations": ["H01"]}', "at least 1"),
])
def test_invalid_answers(raw, msg):
    with pytest.raises(ValidationError, match=msg):
        parse_answer(raw, ["H01"])


def test_tool_answer_may_skip_citations():
    assert parse_answer('{"found": true, "answer": "剩 4 天", "citations": []}', [], used_tool=True)


# ---------------------------------------------------------------- tools (I4)

def test_tools_take_no_employee_id():
    for tool in TOOLS:
        assert "employee_id" not in tool["input_schema"]["properties"]


def test_leave_balance_uses_logged_in_user():
    assert json.loads(run_tool("get_leave_balance", {}, "E002")[0])["remaining"] == 12
    assert run_tool("get_leave_balance", {}, "E999")[1] is True
    assert run_tool("delete_everything", {}, "E001") == ("沒有這個工具：delete_everything", True)


# ---------------------------------------------------------------- bot (I1, I4, I5)

def test_bot_answers_with_citation():
    t = HandbookBot(FakeLLM()).ask("病假超過幾天要附醫生證明？")
    assert t.answer.found and t.answer.citations == ["H02"] and "三天" in t.answer.answer


def test_bot_says_not_found():
    t = HandbookBot(FakeLLM()).ask("可以帶狗來上班嗎？")
    assert t.answer.found is False and t.retrieved == []


def test_tool_loop():
    t = HandbookBot(FakeLLM(), user_id="E002").ask("我今年還剩幾天特休？")
    assert [c["name"] for c in t.tool_calls] == ["get_leave_balance"]
    assert "12" in t.answer.answer
    assert t.usage.calls == 2


def test_retry_fixes_fake_citation():
    t = HandbookBot(FakeLLM(mistakes=["fake_citation"])).ask("事假一年可以請幾天？")
    assert t.attempts == 2 and t.answer.citations == ["H03"]


def test_gives_up_after_retries():
    t = HandbookBot(FakeLLM(mistakes=["fake_citation"] * 3)).ask("事假一年可以請幾天？")
    assert t.answer is None and "H99" in t.error


class LoopingLLM:
    """永遠要求用工具的模型，用來測試迴圈上限。"""

    def create(self, system, messages, tools=None, output_schema=None):
        call = ToolCall("t1", "get_today", {})
        return Reply([{"type": "tool_use", "id": "t1", "name": "get_today", "input": {}}], "", [call], "tool_use", 10, 10)


def test_tool_rounds_are_capped():
    t = HandbookBot(LoopingLLM()).ask("今天幾號？")
    assert "超過" in t.error and len(t.tool_calls) == config.MAX_TOOL_ROUNDS


def test_history_is_trimmed_and_excludes_context():
    bot = HandbookBot(FakeLLM(), max_history_turns=2)
    for q in ["事假一年可以請幾天？", "病假超過幾天要附醫生證明？", "加班費怎麼算？", "可以帶狗來上班嗎？"]:
        bot.ask(q)
    assert len(bot.history) == 8                         # 全部都存
    sent = bot.history[-2 * bot.max_history_turns:]      # 但每次只送最近 2 輪
    assert len(sent) == 4
    assert all("<手冊>" not in m["content"] for m in bot.history)


def test_usage_cost():
    bot = HandbookBot(FakeLLM())
    bot.ask("事假一年可以請幾天？")
    u = bot.total_usage
    price_in, price_out = config.PRICES_PER_MTOK[config.MODEL]
    assert u.cost_usd() == pytest.approx((u.input_tokens * price_in + u.output_tokens * price_out) / 1e6)


def test_user_message_format():
    msg = build_user_message("Q", Searcher().search("事假一年可以請幾天？"))
    assert msg.startswith("<手冊>\n[H03] 事假：") and msg.endswith("問題：Q")


# ---------------------------------------------------------------- evals (I6)

def test_eval_meets_baseline():
    summary = evals.run_bot(FakeLLM())
    baseline = json.loads(evals.BASELINE_PATH.read_text(encoding="utf-8"))
    assert summary["pass_rate"] >= baseline["pass_rate"]

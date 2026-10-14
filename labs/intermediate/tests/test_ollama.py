"""
OllamaLLM 的測試：啟動一個模擬 Ollama /api/chat 的小型 HTTP 伺服器，
不需要真的安裝 Ollama，也能驗證 HTTP 請求與 Claude ↔ Ollama 的格式轉換。
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from labs.intermediate.bot import HandbookBot
from labs.intermediate.llm import OllamaLLM, to_ollama_messages, to_ollama_tool
from labs.intermediate.tools import TOOLS


class MockOllama(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
        MockOllama.requests.append(body)
        msgs = body["messages"]
        last = msgs[-1]
        question = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), "")
        if last["role"] == "tool":
            data = json.loads(last["content"])
            message = {"role": "assistant",
                       "content": json.dumps({"found": True, "answer": f"你還剩 {data['remaining']} 天特休。", "citations": ["H01"]},
                                             ensure_ascii=False)}
        elif body.get("tools") and "剩" in question:
            message = {"role": "assistant", "content": "",
                       "tool_calls": [{"function": {"name": "get_leave_balance", "arguments": {}}}]}
        elif "[H03]" in question:
            message = {"role": "assistant",
                       "content": json.dumps({"found": True, "answer": "事假一年合計十四天。", "citations": ["H03"]}, ensure_ascii=False)}
        else:
            message = {"role": "assistant",
                       "content": json.dumps({"found": False, "answer": "手冊沒有寫到這件事。", "citations": []}, ensure_ascii=False)}
        payload = json.dumps({"model": body["model"], "message": message, "done": True, "done_reason": "stop",
                              "prompt_eval_count": 120, "eval_count": 30}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # 不要在測試輸出裡印 HTTP log
        pass


@pytest.fixture
def ollama_host():
    MockOllama.requests = []
    server = HTTPServer(("127.0.0.1", 0), MockOllama)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_tool_definition_conversion():
    t = to_ollama_tool(TOOLS[0])
    assert t["type"] == "function"
    assert t["function"]["name"] == "get_leave_balance"
    assert t["function"]["parameters"] == TOOLS[0]["input_schema"]


def test_message_conversion_tool_round_trip():
    claude_style = [
        {"role": "user", "content": "我還剩幾天特休？"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "x1", "name": "get_leave_balance", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x1", "content": '{"remaining": 4}'}]},
    ]
    out = to_ollama_messages(claude_style)
    assert out[1] == {"role": "assistant", "content": "",
                      "tool_calls": [{"function": {"name": "get_leave_balance", "arguments": {}}}]}
    assert out[2] == {"role": "tool", "content": '{"remaining": 4}', "tool_name": "get_leave_balance"}


def test_bot_answers_via_ollama(ollama_host):
    llm = OllamaLLM(model="test-model", host=ollama_host)
    t = HandbookBot(llm).ask("事假一年可以請幾天？")
    assert t.answer.citations == ["H03"] and "十四天" in t.answer.answer
    req = MockOllama.requests[0]
    assert req["model"] == "test-model" and req["stream"] is False
    assert req["messages"][0]["role"] == "system"                  # system 參數轉成第一則訊息
    assert req["format"]["required"] == ["found", "answer", "citations"]  # 結構化輸出
    assert t.usage.input_tokens == 120 and t.usage.output_tokens == 30


def test_tool_loop_via_ollama(ollama_host):
    llm = OllamaLLM(model="test-model", host=ollama_host)
    t = HandbookBot(llm, user_id="E002").ask("我今年還剩幾天特休？")
    assert [c["name"] for c in t.tool_calls] == ["get_leave_balance"]
    assert "12" in t.answer.answer
    second = MockOllama.requests[1]["messages"]
    assert second[-1]["role"] == "tool" and second[-1]["tool_name"] == "get_leave_balance"
    assert second[-2]["tool_calls"][0]["function"]["name"] == "get_leave_balance"


def test_clear_error_when_ollama_is_not_running():
    llm = OllamaLLM(host="http://127.0.0.1:9", timeout=2)   # 沒有服務的連接埠
    with pytest.raises(ConnectionError, match="ollama pull"):
        llm.create("system", [{"role": "user", "content": "hi"}])

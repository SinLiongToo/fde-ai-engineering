import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from labs.intermediate.web import RateLimiter, create_app, make_llm  # noqa: E402


@pytest.fixture
def client():
    return TestClient(create_app(backend="fake", per_minute=5, per_day=50))


def test_index_and_health(client):
    assert "員工手冊助理" in client.get("/").text
    assert client.get("/healthz").json() == {"ok": True, "backend": "fake"}


def test_ask_returns_answer_with_citation(client):
    r = client.post("/api/ask", json={"question": "事假一年可以請幾天？"})
    body = r.json()
    assert r.status_code == 200
    assert body["citations"] == ["H03"] and "十四天" in body["answer"]
    assert body["session_id"]


def test_tool_call_is_reported(client):
    body = client.post("/api/ask", json={"question": "我今年還剩幾天特休？"}).json()
    assert body["tool_calls"][0]["name"] == "get_leave_balance"


def test_session_keeps_history(client):
    sid = client.post("/api/ask", json={"question": "事假一年可以請幾天？"}).json()["session_id"]
    again = client.post("/api/ask", json={"question": "病假呢？", "session_id": sid}).json()
    assert again["session_id"] == sid


@pytest.mark.parametrize("payload", [{"question": ""}, {"question": "x" * 301}, {}])
def test_input_validation(client, payload):
    assert client.post("/api/ask", json=payload).status_code == 422


def test_rate_limit_per_minute(client):
    codes = [client.post("/api/ask", json={"question": "事假幾天？"}).status_code for _ in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


def test_daily_limit_and_window():
    rl = RateLimiter(per_minute=2, per_day=3)
    assert rl.check("a", now=0) is None
    assert rl.check("a", now=1) is None
    assert "一分鐘" in rl.check("a", now=2)          # 同一 IP 一分鐘內超過 2 次
    assert rl.check("a", now=70) is None             # 一分鐘後視窗重置
    assert "額度" in rl.check("b", now=71)           # 全站每天 3 次已用完


def test_claude_backend_requires_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        make_llm("claude")

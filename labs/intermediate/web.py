"""
中級 7：把機器人變成網站

    uvicorn labs.intermediate.web:app --reload        # 本機開發，打開 http://127.0.0.1:8000

設定（環境變數）：
    LLM_BACKEND         fake（預設）| claude | ollama
    ANTHROPIC_API_KEY   LLM_BACKEND=claude 時需要；放在部署平台的「secret」，不要寫進程式或映像檔
    RATE_LIMIT_PER_MINUTE  每個 IP 每分鐘最多幾次（預設 10）
    DAILY_LIMIT         全站每天最多幾次（預設 200）。公開網址一定要有，否則可能被刷爆帳單

⚠ 示範版沒有登入功能，所有訪客都是同一位示範員工（E001）。
  真正上線時，user_id 必須來自登入系統（見 I4：查誰的資料不能由使用者或 AI 決定）。
"""

from __future__ import annotations

import os
import time
import uuid
from collections import OrderedDict, deque
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .bot import HandbookBot
from .llm import ClaudeLLM, FakeLLM, OllamaLLM

STATIC = Path(__file__).parent / "static"
DEMO_USER = "E001"
MAX_SESSIONS = 200


def make_llm(backend: str):
    if backend == "claude":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("LLM_BACKEND=claude 需要設定 ANTHROPIC_API_KEY")
        return ClaudeLLM()
    if backend == "ollama":
        return OllamaLLM(model=os.getenv("OLLAMA_MODEL") or OllamaLLM().model)
    return FakeLLM()


class RateLimiter:
    """記憶體內的簡單限流：每個 IP 一分鐘的滑動視窗 + 全站每日上限。單一執行個體適用。"""

    def __init__(self, per_minute: int, per_day: int):
        self.per_minute, self.per_day = per_minute, per_day
        self.hits: dict[str, deque] = {}
        self.day = ""
        self.day_count = 0

    def check(self, client: str, now: float | None = None) -> str | None:
        now = time.time() if now is None else now
        today = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
        if today != self.day:
            self.day, self.day_count = today, 0
        if self.day_count >= self.per_day:
            return "今天的示範額度已用完，請明天再試。"
        q = self.hits.setdefault(client, deque())
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            return "太頻繁了，請一分鐘後再試。"
        q.append(now)
        self.day_count += 1
        return None


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    session_id: str | None = Field(default=None, max_length=64)


def create_app(backend: str | None = None, per_minute: int | None = None, per_day: int | None = None) -> FastAPI:
    backend = backend or os.getenv("LLM_BACKEND", "fake")
    llm = make_llm(backend)
    limiter = RateLimiter(per_minute or int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")),
                          per_day or int(os.getenv("DAILY_LIMIT", "200")))
    sessions: OrderedDict[str, HandbookBot] = OrderedDict()
    app = FastAPI(title="星河軟體員工手冊助理（示範）")

    def client_ip(request: Request) -> str:
        # 雲端平台會在 X-Forwarded-For 放真正的來源 IP（可被偽造，只適合做粗略限流）
        fwd = request.headers.get("x-forwarded-for", "")
        return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")

    def get_bot(session_id: str | None) -> tuple[str, HandbookBot]:
        sid = session_id if session_id in sessions else uuid.uuid4().hex
        if sid not in sessions:
            sessions[sid] = HandbookBot(llm, user_id=DEMO_USER)
            if len(sessions) > MAX_SESSIONS:          # 記憶體有限：淘汰最久沒用的對話
                sessions.popitem(last=False)
        sessions.move_to_end(sid)
        return sid, sessions[sid]

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "backend": backend}

    @app.post("/api/ask")
    def ask(req: AskRequest, request: Request):
        blocked = limiter.check(client_ip(request))
        if blocked:
            raise HTTPException(status_code=429, detail=blocked)
        sid, bot = get_bot(req.session_id)
        try:
            turn = bot.ask(req.question.strip())
        except ConnectionError:
            raise HTTPException(status_code=503, detail="模型服務暫時無法連線，請稍後再試。")
        return {
            "session_id": sid,
            "backend": backend,
            "answer": turn.answer.answer if turn.answer else None,
            "found": turn.answer.found if turn.answer else None,
            "citations": turn.answer.citations if turn.answer else [],
            "tool_calls": [{"name": c["name"], "result": c["result"]} for c in turn.tool_calls],
            "error": turn.error,
        }

    return app


app = create_app()

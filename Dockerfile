# 員工手冊機器人（中級篇 I7）。可部署到 Google Cloud Run 或 Hugging Face Spaces（Docker）。
FROM python:3.12-slim

# 以非 root 使用者執行（Hugging Face Spaces 要求 uid 1000；對其他平台也比較安全）
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    LLM_BACKEND=fake \
    PORT=7860
WORKDIR $HOME/app

COPY --chown=user requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# 只複製網頁版需要的程式，不包含測試與其他 lab
COPY --chown=user labs/__init__.py labs/__init__.py
COPY --chown=user labs/intermediate labs/intermediate

EXPOSE 7860
# Cloud Run 會用環境變數 PORT 指定連接埠（覆寫上面的 7860）
CMD ["sh", "-c", "uvicorn labs.intermediate.web:app --host 0.0.0.0 --port ${PORT}"]

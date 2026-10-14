"""
和員工手冊機器人聊天。

    python -m labs.intermediate.chat            # 有 ANTHROPIC_API_KEY 用 Claude，沒有就用離線假模型
    python -m labs.intermediate.chat --fake     # 強制使用假模型
    python -m labs.intermediate.chat --ollama   # 使用本機 Ollama 的開源模型（資料不離開電腦）
    python -m labs.intermediate.chat --ollama --model qwen2.5:7b

指令：/usage 看用量與費用、/reset 清除對話、/quit 離開
"""

from __future__ import annotations

import argparse
import os
import sys

from .bot import HandbookBot
from .config import OLLAMA_MODEL
from .llm import ClaudeLLM, FakeLLM, OllamaLLM


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--ollama", action="store_true", help="使用本機 Ollama 的開源模型")
    ap.add_argument("--model", default=OLLAMA_MODEL, help="Ollama 模型名稱")
    ap.add_argument("--user", default="E001", help="模擬登入的員工編號（E001 或 E002）")
    args = ap.parse_args()

    if args.ollama:
        llm, mode = OllamaLLM(model=args.model), f"本機開源模型 {args.model}（Ollama）"
    elif not args.fake and os.getenv("ANTHROPIC_API_KEY"):
        llm, mode = ClaudeLLM(), "Claude"
    else:
        llm, mode = FakeLLM(), "離線假模型（規則式，不是 AI）"
    print(f"模式：{mode}｜登入者：{args.user}")
    bot = HandbookBot(llm, user_id=args.user)

    while True:
        try:
            q = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q == "/quit":
            break
        if q == "/reset":
            bot.reset()
            print("（對話已清除）")
            continue
        if q == "/usage":
            u = bot.total_usage
            cost = "本機執行，無 API 費用" if args.ollama else f"約 US${u.cost_usd():.4f}"
            print(f"呼叫 {u.calls} 次｜輸入 {u.input_tokens}｜輸出 {u.output_tokens}｜{cost}")
            continue
        try:
            turn = bot.ask(q)
        except ConnectionError as e:
            print(f"機器人：（{e}）")
            continue
        if turn.error:
            print("機器人：（" + turn.error + "）")
            continue
        cites = "、".join(turn.answer.citations)
        print("機器人：" + turn.answer.answer + (f"〔{cites}〕" if cites else ""))
        for call in turn.tool_calls:
            print(f"  ↳ 使用工具 {call['name']} → {call['result']}")


if __name__ == "__main__":
    main()

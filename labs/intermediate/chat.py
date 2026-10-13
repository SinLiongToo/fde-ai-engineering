"""
和員工手冊機器人聊天。

    python -m labs.intermediate.chat            # 有 ANTHROPIC_API_KEY 用 Claude，沒有就用離線假模型
    python -m labs.intermediate.chat --fake     # 強制使用假模型

指令：/usage 看用量與費用、/reset 清除對話、/quit 離開
"""

from __future__ import annotations

import argparse
import os
import sys

from .bot import HandbookBot
from .llm import ClaudeLLM, FakeLLM


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--user", default="E001", help="模擬登入的員工編號（E001 或 E002）")
    args = ap.parse_args()

    use_real = not args.fake and os.getenv("ANTHROPIC_API_KEY")
    llm = ClaudeLLM() if use_real else FakeLLM()
    print("模式：" + ("Claude" if use_real else "離線假模型（規則式，不是 AI）") + f"｜登入者：{args.user}")
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
            print(f"呼叫 {u.calls} 次｜輸入 {u.input_tokens}｜輸出 {u.output_tokens}｜約 US${u.cost_usd():.4f}")
            continue
        turn = bot.ask(q)
        if turn.error:
            print("機器人：（" + turn.error + "）")
            continue
        cites = "、".join(turn.answer.citations)
        print("機器人：" + turn.answer.answer + (f"〔{cites}〕" if cites else ""))
        for call in turn.tool_calls:
            print(f"  ↳ 使用工具 {call['name']} → {call['result']}")


if __name__ == "__main__":
    main()

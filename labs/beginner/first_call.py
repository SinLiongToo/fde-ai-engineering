"""
入門 2：第一次呼叫 AI 的 API

沒有 API key 也可以執行：程式會印出「會送出去的內容」，讓你看懂請求長什麼樣子。
有 API key 的話，會真的呼叫 Claude。

準備（有 key 才需要）：
    pip install anthropic
    設定環境變數 ANTHROPIC_API_KEY（不要把 key 寫在程式碼裡！）

執行：python -m labs.beginner.first_call
"""

import json
import os

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = "你是一位有耐心的程式老師。用繁體中文、簡短地回答，每次不超過三句話。"


def build_request(history, new_question):
    """
    API 不會記得之前聊過什麼。
    所以每一次都要把「全部的對話」連同新問題一起送出去。
    """
    messages = history + [{"role": "user", "content": new_question}]
    return {
        "model": MODEL,
        "max_tokens": 1000,
        "system": SYSTEM_PROMPT,
        "messages": messages,
    }


def call_claude(request):
    """真的呼叫 API，回傳 (回答文字, 用了多少 token)。"""
    import anthropic

    client = anthropic.Anthropic()  # 會自動讀取環境變數 ANTHROPIC_API_KEY
    response = client.messages.create(**request)
    # 回應裡可能有好幾個區塊，我們只取「文字」區塊
    text = "".join(block.text for block in response.content if block.type == "text")
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    return text, usage


def main():
    has_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    history = []
    questions = ["什麼是變數？", "可以舉一個 Python 的例子嗎？"]

    for question in questions:
        request = build_request(history, question)
        print("=" * 60)
        print(f"第 {len(history) // 2 + 1} 次請求，送出 {len(request['messages'])} 則訊息：")
        print(json.dumps(request, ensure_ascii=False, indent=2))

        if has_key:
            answer, usage = call_claude(request)
            print("\nClaude 的回答：", answer)
            print("用量：", usage)
        else:
            answer = "（沒有設定 ANTHROPIC_API_KEY，這裡用假的回答代替）"
            print("\n" + answer)

        # 把這一輪的問與答加進歷史，下一次要一起送出去
        history += [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]


if __name__ == "__main__":
    main()

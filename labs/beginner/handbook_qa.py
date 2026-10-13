"""
入門 4：讓 AI 回答「你的文件」裡的問題

AI 沒讀過你們公司的員工手冊，所以直接問它，它只能亂猜。
做法很簡單，分三步：
    1. 搜尋：從手冊裡找出跟問題最相關的幾段
    2. 組合：把那幾段貼進 prompt，告訴 AI「只能根據這些內容回答」
    3. 回答：把組好的 prompt 送給 AI

這個檔案示範第 1、2 步。第 3 步就是 first_call.py 做的事。

執行：python -m labs.beginner.handbook_qa "請假要提前幾天申請？"
"""

import sys

# 一份很短的「員工手冊」，每段有編號，方便 AI 引用
HANDBOOK = {
    "H1": "特休假：到職滿六個月後有三天特休。請特休需在三個工作天前於系統提出申請，由直屬主管核准。",
    "H2": "病假：一年內合計三十天以內，薪資折半發給。請病假超過三天需附醫生證明。",
    "H3": "上班時間：週一至週五上午九點到下午六點，中午休息一小時。可彈性提早或延後三十分鐘上下班。",
    "H4": "遠端工作：每週最多兩天可在家工作，需事先在團隊行事曆標註，並保持通訊軟體在線。",
    "H5": "報帳：出差的交通與住宿費用，需在出差結束後十四天內附上收據報帳，逾期不受理。",
    "H6": "設備：公司提供筆記型電腦與螢幕。設備遺失或損壞請立即通知 IT 部門，不要自行送修。",
}


def pieces(text):
    """把文字切成「兩個字一組」的小片段，例如「請假」「假要」「要提」。"""
    text = "".join(ch for ch in text if ch.strip() and ch not in "，。？！、：；「」")
    return {text[i:i + 2] for i in range(len(text) - 1)}


def search(question, top_n=2):
    """計算問題和每一段有幾個相同的片段，取最多的前幾段。"""
    q = pieces(question)
    scored = []
    for doc_id, text in HANDBOOK.items():
        overlap = q & pieces(text)
        if overlap:
            scored.append((len(overlap), doc_id, sorted(overlap)))
    scored.sort(reverse=True)
    return [(doc_id, score, shared) for score, doc_id, shared in scored[:top_n]]


def build_prompt(question, found):
    """把找到的段落和問題，組成要送給 AI 的 prompt。"""
    if not found:
        context = "（沒有找到相關段落）"
    else:
        context = "\n".join(f"[{doc_id}] {HANDBOOK[doc_id]}" for doc_id, _, _ in found)
    return (
        "請只根據下面的員工手冊內容回答問題，並在答案後面標註段落編號，例如 [H1]。\n"
        "如果手冊裡沒有答案，請直接說「手冊沒有寫到這件事」，不要自己猜。\n\n"
        f"<手冊>\n{context}\n</手冊>\n\n"
        f"問題：{question}"
    )


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else "請假要提前幾天申請？"
    found = search(question)
    print("找到的段落：")
    for doc_id, score, shared in found:
        print(f"  {doc_id}（相同片段 {score} 個：{'、'.join(shared)}）")
    print("\n要送給 AI 的 prompt：\n")
    print(build_prompt(question, found))

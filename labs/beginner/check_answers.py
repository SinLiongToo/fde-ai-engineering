"""
入門 5：怎麼知道 AI 回答得好不好？

不要只試一兩個問題就說「看起來可以」。
準備一份「考題」：問題 + 正確答案裡一定要出現的關鍵字，
每次修改後都重新考一次，看分數有沒有變差。

這裡的「AI」是假的（直接回傳搜尋到的第一段），讓你不用 API key 也能練習。

執行：python -m labs.beginner.check_answers
"""

from labs.beginner.handbook_qa import HANDBOOK, search

# 考題：問題、答案一定要出現的字、應該引用哪一段
TEST_CASES = [
    {"question": "請特休要提前幾天？", "must_include": ["三個工作天"], "source": "H1"},
    {"question": "病假超過幾天要附證明？", "must_include": ["三天", "醫生證明"], "source": "H2"},
    {"question": "一週可以在家工作幾天？", "must_include": ["兩天"], "source": "H4"},
    {"question": "出差收據要多久內報帳？", "must_include": ["十四天"], "source": "H5"},
    {"question": "筆電壞掉可以自己拿去修嗎？", "must_include": ["IT"], "source": "H6"},
    {"question": "公司有提供午餐嗎？", "must_include": [], "source": None},  # 手冊沒寫：應該說不知道
]


def fake_ai(question):
    """假裝是 AI：找到段落就照抄，找不到就說不知道。"""
    found = search(question, top_n=1)
    if not found:
        return "手冊沒有寫到這件事。", None
    doc_id = found[0][0]
    return f"{HANDBOOK[doc_id]} [{doc_id}]", doc_id


def grade(case, answer, cited):
    """回傳這一題沒通過的原因；空清單代表通過。"""
    problems = []
    for word in case["must_include"]:
        if word not in answer:
            problems.append(f"答案裡沒有「{word}」")
    if case["source"] is None:
        if "沒有寫到" not in answer:
            problems.append("手冊沒寫，卻硬給了答案")
    elif cited != case["source"]:
        problems.append(f"應該引用 {case['source']}，實際引用 {cited}")
    return problems


def run_exam(ai=fake_ai):
    passed = 0
    for case in TEST_CASES:
        answer, cited = ai(case["question"])
        problems = grade(case, answer, cited)
        mark = "✓" if not problems else "✗"
        print(f"{mark} {case['question']}")
        for p in problems:
            print(f"    - {p}")
        passed += not problems
    print(f"\n通過 {passed} / {len(TEST_CASES)} 題")
    return passed


if __name__ == "__main__":
    run_exam()

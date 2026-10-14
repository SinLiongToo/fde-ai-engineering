"""
中級 6：自動測試整個機器人

    python -m labs.intermediate.evals --search          # 比較三個搜尋版本（第 3 章）
    python -m labs.intermediate.evals                   # 用離線假模型跑完整機器人
    python -m labs.intermediate.evals --real            # 用真的 Claude 跑（需要 API key，會花錢）
    python -m labs.intermediate.evals --ollama          # 用本機 Ollama 的開源模型跑（免費，但較慢）
    python -m labs.intermediate.evals --update-baseline # 確認結果後，把分數存成基準

每一題檢查四件事：
  搜尋  相關段落有沒有被找到（手冊沒寫的題目：應該什麼都找不到）
  內容  答案裡有沒有出現關鍵字
  誠實  手冊沒寫的題目，found 是否為 false
  工具  該用工具的題目，有沒有真的呼叫
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .bot import HandbookBot
from .config import OLLAMA_MODEL
from .llm import ClaudeLLM, FakeLLM, OllamaLLM
from .search import Searcher

HERE = Path(__file__).parent
EVAL_PATH = HERE / "eval_set.jsonl"
BASELINE_PATH = HERE / "baseline.json"


def load_cases() -> list[dict]:
    with EVAL_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def search_ok(case: dict, retrieved: list[str]) -> bool:
    if case.get("expect_not_found"):
        return not retrieved
    return case["relevant"][0] in retrieved


def compare_search_versions() -> dict:
    cases = load_cases()
    table = {}
    for version in ("v1", "v2", "v3"):
        s = Searcher(version=version)
        results = [search_ok(c, [h.chunk.id for h in s.search(c["question"])]) for c in cases]
        by_tag: dict[str, list[bool]] = {}
        for c, ok in zip(cases, results):
            for t in c["tags"]:
                by_tag.setdefault(t, []).append(ok)
        table[version] = {"total": f"{sum(results)}/{len(cases)}",
                          **{t: f"{sum(v)}/{len(v)}" for t, v in sorted(by_tag.items())}}
    return table


def grade(case: dict, turn) -> list[str]:
    problems = []
    if not search_ok(case, turn.retrieved):
        problems.append(f"搜尋：找到 {turn.retrieved}，應該是 {case['relevant'] or '（無）'}")
    if turn.error:
        problems.append(f"錯誤：{turn.error}")
        return problems
    a = turn.answer
    for word in case.get("must_include", []):
        if word not in a.answer:
            problems.append(f"內容：答案沒有「{word}」")
    if case.get("expect_not_found") and a.found:
        problems.append("誠實：手冊沒寫，卻回答 found=true")
    if case.get("expect_tool") and case["expect_tool"] not in [c["name"] for c in turn.tool_calls]:
        problems.append(f"工具：沒有呼叫 {case['expect_tool']}")
    return problems


def run_bot(llm) -> dict:
    cases = load_cases()
    passed = 0
    usage_in = usage_out = 0
    for case in cases:
        bot = HandbookBot(llm)          # 每題用新的機器人，題目之間互不影響
        turn = bot.ask(case["question"])
        problems = grade(case, turn)
        passed += not problems
        usage_in += turn.usage.input_tokens
        usage_out += turn.usage.output_tokens
        mark = "✓" if not problems else "✗"
        print(f"{mark} {case['id']:16} {case['question']}")
        for p in problems:
            print(f"      {p}")
    summary = {"cases": len(cases), "passed": passed, "pass_rate": round(passed / len(cases), 4)}
    print(json.dumps(summary, ensure_ascii=False))
    print(f"用量：輸入 {usage_in}、輸出 {usage_out}" + ("（假模型：以字數估算）" if isinstance(llm, FakeLLM) else " token"))
    print(f"模型：{getattr(llm, 'model', 'fake')}")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", action="store_true", help="只比較搜尋版本")
    ap.add_argument("--real", action="store_true", help="使用真的 Claude（需要 ANTHROPIC_API_KEY）")
    ap.add_argument("--ollama", action="store_true", help="使用本機 Ollama 的開源模型")
    ap.add_argument("--model", default=OLLAMA_MODEL, help="Ollama 模型名稱")
    ap.add_argument("--update-baseline", action="store_true")
    args = ap.parse_args(argv)

    if args.search:
        for version, row in compare_search_versions().items():
            print(version, json.dumps(row, ensure_ascii=False))
        return 0

    if args.real and not os.getenv("ANTHROPIC_API_KEY"):
        print("需要設定 ANTHROPIC_API_KEY")
        return 2
    if args.ollama:
        llm = OllamaLLM(model=args.model)
    else:
        llm = ClaudeLLM() if args.real else FakeLLM()
    try:
        summary = run_bot(llm)
    except ConnectionError as e:
        print(e)
        return 2
    if args.real or args.ollama:
        return 0  # 真模型的分數會浮動，這裡只顯示，不和假模型的基準比較

    if args.update_baseline:
        BASELINE_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("已更新基準")
        return 0
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8")) if BASELINE_PATH.exists() else None
    if baseline and summary["pass_rate"] < baseline["pass_rate"]:
        print(f"退步了：{summary['pass_rate']} < 基準 {baseline['pass_rate']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

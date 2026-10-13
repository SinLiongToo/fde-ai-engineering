"""
第 7 章：評測 / Chapter 7: Evaluation

一個能放進 CI 的最小評測框架 / A minimal eval harness you can run in CI:

- golden_set.jsonl：每一筆是「真實問題 + 預期結果」。來源應該是真實流量與錯誤分析，
  而不是憑空想像。每一筆都有 tag，方便看「哪一類」退步了。
  Each case is a real question plus expected outcome, tagged by failure category.
- 程式碼評分（code-based grader）：recall@k、MRR、必含字串、禁止出現的文件（權限）。
  能用程式判斷的，就不要用 LLM 當評審。
  Prefer deterministic graders; reach for LLM-as-judge only when you must.
- 與 baseline 比較：不是只看絕對門檻，而是「這次改動有沒有讓結果變差」。
  Gate on regression against a stored baseline, not only on absolute thresholds.

執行 / Run:
    python -m labs.core.evals                    # 顯示結果並與 baseline 比較
    python -m labs.core.evals --update-baseline  # 確認結果後，更新 baseline
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .retrieval import HybridRetriever, recall_at_k, reciprocal_rank

HERE = Path(__file__).parent
GOLDEN_PATH = HERE / "golden_set.jsonl"
BASELINE_PATH = HERE / "baseline.json"

K = 3
# 允許的退步幅度。資料集很小時，一筆案例就是好幾個百分點，門檻不能設得太緊。
# Allowed regression. With few cases, one case moves the metric a lot.
TOLERANCE = 0.0


@dataclass
class CaseResult:
    id: str
    tags: list[str]
    retrieved: list[str]
    recall: float | None   # None：此案例沒有相關文件（例如權限測試）/ no relevant docs
    rr: float | None
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def load_cases(path: Path = GOLDEN_PATH) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# 「系統」= 一個函式：(query, user_groups) -> 依序排好的 (doc_id, text)。
# 換掉 retriever、chunking、embedding 或 prompt，都只是換掉這個函式。
System = Callable[[str, set[str]], list[tuple[str, str]]]


def default_system() -> System:
    retriever = HybridRetriever()

    def run(query: str, groups: set[str]) -> list[tuple[str, str]]:
        res = retriever.search(query, user_groups=groups, top_n=K)
        return [(d.id, d.text) for d, _ in res.fused]

    return run


def evaluate_case(case: dict, system: System) -> CaseResult:
    groups = set(case.get("user_groups", ["everyone"]))
    hits = system(case["query"], groups)
    ids = [doc_id for doc_id, _ in hits]
    relevant = set(case.get("relevant", []))

    r = CaseResult(case["id"], case.get("tags", []), ids,
                   recall_at_k(ids, relevant, K) if relevant else None,
                   reciprocal_rank(ids, relevant) if relevant else None)

    if r.recall is not None and r.recall < 1.0:
        r.failures.append(f"missing relevant {sorted(relevant - set(ids[:K]))}")
    leaked = set(case.get("forbidden", [])) & set(ids)
    if leaked:
        r.failures.append(f"returned forbidden docs {sorted(leaked)}")  # 權限外洩是最嚴重的失敗
    context = " ".join(text for _, text in hits[:K]).lower()
    for phrase in case.get("must_include", []):
        if phrase.lower() not in context:
            r.failures.append(f"context lacks '{phrase}'")
    return r


def summarize(results: list[CaseResult]) -> dict:
    n = len(results)
    scored = [r for r in results if r.rr is not None]  # 只算有相關文件的案例，避免灌水
    summary = {
        "cases": n,
        "pass_rate": round(sum(r.passed for r in results) / n, 4),
        f"recall@{K}": round(sum(r.recall for r in scored) / len(scored), 4),
        "mrr": round(sum(r.rr for r in scored) / len(scored), 4),
        "acl_leaks": sum(any("forbidden" in f for f in r.failures) for r in results),
    }
    by_tag: dict[str, list[bool]] = {}
    for r in results:
        for t in r.tags:
            by_tag.setdefault(t, []).append(r.passed)
    summary["pass_rate_by_tag"] = {t: round(sum(v) / len(v), 4) for t, v in sorted(by_tag.items())}
    return summary


def compare(current: dict, baseline: dict, tolerance: float = TOLERANCE) -> list[str]:
    """回傳退步項目；空清單代表通過 / Returns regressions; empty means the gate passes."""
    problems = []
    if current["acl_leaks"] > 0:
        problems.append(f"acl_leaks = {current['acl_leaks']} (must be 0)")
    for metric in ("pass_rate", f"recall@{K}", "mrr"):
        if current[metric] < baseline.get(metric, 0) - tolerance:
            problems.append(f"{metric}: {current[metric]:.3f} < baseline {baseline[metric]:.3f}")
    return problems


def run(system: System | None = None) -> tuple[list[CaseResult], dict]:
    system = system or default_system()
    results = [evaluate_case(c, system) for c in load_cases()]
    return results, summarize(results)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--update-baseline", action="store_true")
    args = p.parse_args(argv)

    results, summary = run()
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{mark}] {r.id:22} top{K}={r.retrieved[:K]} " + "; ".join(r.failures))
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if args.update_baseline:
        BASELINE_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"baseline written to {BASELINE_PATH}")
        return 0

    if not BASELINE_PATH.exists():
        print("no baseline yet; run with --update-baseline after reviewing the results")
        return 1
    problems = compare(summary, json.loads(BASELINE_PATH.read_text(encoding="utf-8")))
    for prob in problems:
        print("REGRESSION:", prob)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

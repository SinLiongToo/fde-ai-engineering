"""
AI Code Reviewer
Module: reviewer_agent.py

流程 / Pipeline
1. AST 靜態掃描：確定性、可重現，負責「一定抓得到」的問題。
   Deterministic AST scan: reproducible findings.
2. 規則挑選：只把相關的團隊規則放進 prompt。
   Rule selection: only relevant team rules go into the prompt.
3. （選用）LLM 補充：找出 AST 抓不到的語意問題。LLM 只「提出發現」，
   不負責打分數與決定能不能合併。
   Optional LLM pass: the model proposes extra findings; it does NOT decide the verdict.
4. 驗證與合併：丟棄行號不存在的發現（常見的幻覺），與 AST 結果去重，
   最後由程式計算分數與結論。
   Validate (drop findings on non-existent lines), dedupe, then compute the verdict in code.

設定 GEMINI_API_KEY 才會啟用 LLM；沒有金鑰時完全離線執行。
The LLM pass is enabled only when GEMINI_API_KEY is set; otherwise everything runs offline.
"""

from __future__ import annotations

import os
from typing import List, Optional

from pydantic import BaseModel, Field

from .ast_analyzer import analyze_source_code_ast
from .rule_engine import ArchitectureRule, ArchitectureRuleEngine
from .schemas import CodeIssue, ReviewReport

GEMINI_MODEL = "gemini-2.5-flash"


class LLMFindings(BaseModel):
    """LLM 的輸出契約：只有發現清單 / The LLM returns findings only."""

    issues: List[CodeIssue] = Field(default_factory=list)


class AICodeReviewerAgent:
    def __init__(self, custom_rules_file: Optional[str] = None):
        self.rule_engine = ArchitectureRuleEngine(custom_rules_file)
        self.client = None
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key:
            try:
                from google import genai

                self.client = genai.Client(api_key=api_key)
            except ImportError:
                self.client = None

    def review_file(self, file_path: str) -> ReviewReport:
        with open(file_path, "r", encoding="utf-8") as f:
            source_code = f.read()
        return self.review_source(file_path, source_code)

    def review_source(self, file_path: str, source_code: str) -> ReviewReport:
        total_lines = len(source_code.splitlines()) or 1
        issues = analyze_source_code_ast(file_path, source_code)
        rules = self.rule_engine.retrieve_relevant_rules(source_code)
        notes: list[str] = []
        mode = "STATIC"

        if self.client:
            try:
                llm_issues = self._llm_findings(file_path, source_code, issues, rules)
                kept, dropped = validate_llm_issues(llm_issues, source_code)
                issues = merge_issues(issues, kept)
                mode = "STATIC+LLM"
                if dropped:
                    notes.append(f"dropped {dropped} LLM finding(s) with invalid line numbers")
            except Exception as e:  # LLM 失敗時退回靜態結果，並在摘要中註明
                notes.append(f"LLM pass failed, static results only ({type(e).__name__})")

        summary = f"{len(issues)} issue(s) in {file_path}."
        if notes:
            summary += " " + "; ".join(notes) + "."
        if mode == "STATIC" and not notes:
            summary += " Static analysis only (set GEMINI_API_KEY to add an LLM pass)."

        return ReviewReport.calculate_verdict(
            issues=issues, total_lines=total_lines, mode=mode, summary=summary, target_file=file_path
        )

    def _llm_findings(
        self, file_path: str, source_code: str, ast_issues: List[CodeIssue], rules: List[ArchitectureRule]
    ) -> List[CodeIssue]:
        rules_text = "\n".join(f"- [{r.rule_id}] {r.title} ({r.severity}): {r.description}" for r in rules)
        known = "\n".join(f"- line {i.line_number} {i.rule_id}: {i.title}" for i in ast_issues) or "- none"
        numbered = "\n".join(f"{n:4} | {line}" for n, line in enumerate(source_code.splitlines(), 1))

        prompt = f"""Review this Python file against the team rules below.

<rules>
{rules_text}
</rules>

<already_found_by_static_analysis>
{known}
</already_found_by_static_analysis>

<file path="{file_path}">
{numbered}
</file>

Report only problems that static analysis has NOT already found. Use the line numbers shown
in the left column. If you find nothing new, return an empty list. Do not invent issues to
fill the list. Each suggested_fix must be a concrete code change."""

        response = self.client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"response_mime_type": "application/json", "response_schema": LLMFindings},
        )
        return LLMFindings.model_validate_json(response.text).issues


def validate_llm_issues(issues: List[CodeIssue], source_code: str) -> tuple[List[CodeIssue], int]:
    """丟棄行號超出範圍或指向空白行的發現 / Drop findings that point at non-existent or blank lines."""
    lines = source_code.splitlines()
    kept = [i for i in issues if 1 <= i.line_number <= len(lines) and lines[i.line_number - 1].strip()]
    return kept, len(issues) - len(kept)


def merge_issues(primary: List[CodeIssue], extra: List[CodeIssue]) -> List[CodeIssue]:
    seen = {(i.line_number, i.rule_id) for i in primary}
    merged = list(primary)
    for i in extra:
        if (i.line_number, i.rule_id) not in seen:
            merged.append(i)
            seen.add((i.line_number, i.rule_id))
    return sorted(merged, key=lambda i: i.line_number)

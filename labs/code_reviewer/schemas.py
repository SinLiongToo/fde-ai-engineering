"""
AI Code Reviewer & Architecture Compliance Inspector
Module: schemas.py
Defines strict Pydantic v2 data contracts for code review telemetry,
issues, unified diff patches, and security audit reports.
"""

import re
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator

PLACEHOLDER_PATTERN = re.compile(r"\b(tbd|todo|fixme|fix later|contact (the )?admin|n/a)\b", re.IGNORECASE)


class CodeIssue(BaseModel):
    """Represents a specific code vulnerability or architecture violation."""
    file_path: str = Field(..., description="Path to the inspected source file")
    line_number: int = Field(..., ge=1, description="Line number where the violation starts")
    rule_id: str = Field(..., pattern=r"^[A-Z]{3,4}-\d{3}$", description="Rule identifier (e.g. SEC-001, PERF-002)")
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"] = Field(
        ..., description="Standardized severity level"
    )
    title: str = Field(..., min_length=3, max_length=120, description="Short summary of the issue")
    description: str = Field(..., min_length=10, description="Detailed explanation of the risk and impact")
    code_snippet: str = Field(..., description="Offending code snippet")
    suggested_fix: str = Field(..., min_length=10, description="Clear instructions on how to remediate")
    diff_patch: Optional[str] = Field(None, description="Unified git diff demonstrating the exact code replacement")

    @field_validator("suggested_fix")
    @classmethod
    def reject_lazy_fixes(cls, v: str) -> str:
        """Anti-Hallucination Gate: Rejects lazy suggestions from LLMs."""
        match = PLACEHOLDER_PATTERN.search(v)
        if match:
            raise ValueError(
                f"Suggested fix contains prohibited placeholder '{match.group(0).lower()}'. "
                "Provide concrete code instructions."
            )
        return v


class ReviewReport(BaseModel):
    """Aggregated code review and security audit report."""
    target_file: str = Field(..., description="Analyzed file or module path")
    total_lines: int = Field(..., ge=1, description="Total lines of code analyzed")
    issues: List[CodeIssue] = Field(default_factory=list, description="List of detected issues")
    security_score: int = Field(..., ge=0, le=100, description="Calculated health score from 0 (worst) to 100 (clean)")
    verdict: Literal["PASSED", "WARNING", "BLOCKED"] = Field(
        ..., description="Final deployment or merge recommendation"
    )
    summary: str = Field(..., description="High-level engineering executive summary")
    execution_mode: Literal["STATIC", "STATIC+LLM"] = Field(
        ..., description="STATIC = AST rules only; STATIC+LLM = AST rules plus LLM findings"
    )

    @classmethod
    def calculate_verdict(cls, issues: List[CodeIssue], total_lines: int, mode: str, summary: str, target_file: str) -> "ReviewReport":
        """
        分數與結論由程式計算，不交給 LLM：同樣的發現永遠得到同樣的結論。
        Score and verdict are computed in code, never by the LLM, so they are reproducible.
        """
        has_critical = any(i.severity == "CRITICAL" for i in issues)
        has_high = any(i.severity == "HIGH" for i in issues)

        deductions = 0
        for i in issues:
            if i.severity == "CRITICAL":
                deductions += 40
            elif i.severity == "HIGH":
                deductions += 20
            elif i.severity == "MEDIUM":
                deductions += 10
            elif i.severity == "LOW":
                deductions += 5

        score = max(0, 100 - deductions)

        if has_critical or score < 60:
            verdict = "BLOCKED"
        elif has_high or score < 85:
            verdict = "WARNING"
        else:
            verdict = "PASSED"

        return cls(
            target_file=target_file,
            total_lines=total_lines,
            issues=issues,
            security_score=score,
            verdict=verdict,
            summary=summary,
            execution_mode=mode
        )

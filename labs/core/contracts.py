"""
第 4 章：結構化輸出與資料契約 / Chapter 4: Structured output & data contracts

重點 / Key ideas
- 模型輸出是「不可信的外部輸入」，進入系統前一定要驗證。
  Model output is untrusted input; validate it before anything downstream sees it.
- 結構（型別、欄位）可以交給 provider 的 structured output；
  業務規則（ID 格式、不可空泛的修復建議）一定要自己驗證。
  Structure can be enforced by the provider; business rules are your job.
- 驗證失敗時，把錯誤訊息回饋給模型重試，並設上限。
  On failure, feed the validation errors back to the model, with a retry cap.
"""

from __future__ import annotations

import json
import re
from typing import Callable, Literal

from pydantic import BaseModel, Field, ValidationError, ValidationInfo, field_validator

# 用「整個詞」比對，避免 "todo" 誤殺 "todos"、"n/a" 誤殺 "n/available" 之類的字。
# Whole-word matching, so "todo" does not reject "todos".
PLACEHOLDER_PATTERN = re.compile(
    r"\b(tbd|todo|fixme|n/a|contact (the )?admin|check later|look at (the )?logs)\b",
    re.IGNORECASE,
)


class ClauseRiskAssessment(BaseModel):
    """合約條款風險評估 / Risk assessment for one contract clause."""

    clause_id: str = Field(pattern=r"^CLAUSE-\d{3,4}$", description="e.g. CLAUSE-001")
    title: str = Field(min_length=3, max_length=120)
    risk_level: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    # 注意：模型自報的 confidence 沒有經過校準，只能當參考，不能當機率用。
    # Note: a self-reported confidence is not calibrated. Treat it as a hint.
    confidence: float = Field(ge=0.0, le=1.0)
    findings: list[str] = Field(min_length=1)
    mitigation: str = Field(min_length=25)
    cited_clause_ids: list[str] = Field(default_factory=list)

    @field_validator("findings")
    @classmethod
    def findings_not_blank(cls, v: list[str]) -> list[str]:
        if any(not item.strip() for item in v):
            raise ValueError("findings must not contain blank items")
        return v

    @field_validator("mitigation")
    @classmethod
    def mitigation_is_concrete(cls, v: str) -> str:
        match = PLACEHOLDER_PATTERN.search(v)
        if match:
            raise ValueError(
                f"mitigation contains placeholder text '{match.group(0)}'; "
                "give a concrete, actionable step"
            )
        return v

    @field_validator("cited_clause_ids")
    @classmethod
    def citations_were_retrieved(cls, v: list[str], info: ValidationInfo) -> list[str]:
        """
        依「這次實際檢索到的文件」驗證引用，抓出模型捏造的出處。
        需要在驗證時傳入 context={"retrieved_ids": {...}}；沒有 context 就略過。
        Checks citations against the documents actually retrieved for this request.
        """
        allowed = (info.context or {}).get("retrieved_ids")
        if allowed is not None:
            unknown = [c for c in v if c not in allowed]
            if unknown:
                raise ValueError(f"cites clauses that were not retrieved: {', '.join(unknown)}")
        return v


def format_errors_for_model(err: ValidationError) -> str:
    """把 Pydantic 錯誤整理成模型看得懂的回饋 / Turn errors into model-readable feedback."""
    lines = []
    for e in err.errors():
        loc = ".".join(str(p) for p in e["loc"]) or "(root)"
        lines.append(f"- {loc}: {e['msg']}")
    return "Your previous output failed validation:\n" + "\n".join(lines)


class RepairExhausted(Exception):
    def __init__(self, attempts: list[dict]):
        super().__init__(f"output still invalid after {len(attempts)} attempts")
        self.attempts = attempts


# LLM 呼叫的抽象：輸入「對話訊息」，回傳「原始文字」。
# 真實系統裡這會是 Anthropic / OpenAI / Gemini 的 SDK 呼叫；lab 用假模型以便離線執行。
# Abstract LLM call: messages in, raw text out. Real code wraps a provider SDK.
LLMCall = Callable[[list[dict]], str]


def generate_validated(
    llm: LLMCall,
    prompt: str,
    model_cls: type[BaseModel] = ClauseRiskAssessment,
    max_attempts: int = 3,
    context: dict | None = None,
) -> tuple[BaseModel, list[dict]]:
    """
    驗證 + 修復迴圈 / Validate-and-repair loop.

    回傳 (驗證後物件, 每次嘗試的紀錄)。紀錄要寫進 trace，之後才能分析失敗模式。
    Returns (validated object, attempt log). Ship the log to your tracing backend.
    """
    messages: list[dict] = [{"role": "user", "content": prompt}]
    attempts: list[dict] = []

    for attempt in range(1, max_attempts + 1):
        raw = llm(messages)
        try:
            obj = model_cls.model_validate_json(raw, context=context)
        except ValidationError as err:
            feedback = format_errors_for_model(err)
            attempts.append({"attempt": attempt, "ok": False, "errors": err.errors(include_url=False, include_context=False)})
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": feedback + "\nReturn corrected JSON only."},
            ]
            continue
        attempts.append({"attempt": attempt, "ok": True})
        return obj, attempts

    raise RepairExhausted(attempts)


class ScriptedLLM:
    """
    離線用的假模型：依序回傳預先寫好的輸出，並記錄它收到的訊息。
    Offline stand-in: returns canned outputs in order and records what it was sent.
    """

    def __init__(self, outputs: list[str]):
        self.outputs = list(outputs)
        self.received: list[list[dict]] = []

    def __call__(self, messages: list[dict]) -> str:
        self.received.append([dict(m) for m in messages])
        if not self.outputs:
            raise RuntimeError("ScriptedLLM ran out of outputs")
        return self.outputs.pop(0)


EXAMPLE_VALID = {
    "clause_id": "CLAUSE-004",
    "title": "Zero-downtime schema migration",
    "risk_level": "HIGH",
    "confidence": 0.8,
    "findings": ["Migration script does not set lock_timeout"],
    "mitigation": "Add SET lock_timeout = '2s' before each ALTER TABLE and retry with backoff.",
    "cited_clause_ids": ["CLAUSE-004"],
}

EXAMPLE_LAZY = {**EXAMPLE_VALID, "mitigation": "TBD - contact admin for details on this issue."}


if __name__ == "__main__":
    fake = ScriptedLLM([json.dumps(EXAMPLE_LAZY), json.dumps(EXAMPLE_VALID)])
    result, log = generate_validated(fake, "Assess CLAUSE-004 against the migration script.")
    print(result.model_dump_json(indent=2))
    print(json.dumps(log, indent=2, ensure_ascii=False))

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from labs.code_reviewer.ast_analyzer import analyze_source_code_ast
from labs.code_reviewer.reviewer_agent import AICodeReviewerAgent, LLMFindings
from labs.code_reviewer.rule_engine import ArchitectureRuleEngine
from labs.code_reviewer.schemas import CodeIssue

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    return AICodeReviewerAgent()


def rule_ids(src: str) -> list[str]:
    return [i.rule_id for i in analyze_source_code_ast("x.py", src)]


def test_vulnerable_sample(agent):
    report = agent.review_file(str(SAMPLES / "vulnerable_api.py"))
    assert report.verdict == "BLOCKED"
    assert {"SEC-001", "SEC-002", "SEC-003", "PERF-001", "ARCH-001"} <= {i.rule_id for i in report.issues}
    assert report.execution_mode == "STATIC"


def test_clean_sample(agent):
    report = agent.review_file(str(SAMPLES / "clean_api.py"))
    assert report.issues == []
    assert report.verdict == "PASSED"


@pytest.mark.parametrize("src", [
    'max_tokens = "4096-tokens-limit"',          # 名稱含 token，但不是密鑰
    'token_count_label = "number of tokens"',
    'query = f"Hello {name}, welcome back"',     # 名稱叫 query，但不是 SQL
    'requests_cache.get("k")',                   # 不是 HTTP 呼叫
])
def test_no_false_positives(src):
    assert rule_ids(src) == []


@pytest.mark.parametrize("src,expected", [
    ('API_KEY = "sk-live-abcdef123456"', "SEC-002"),
    ('db_password = "hunter2hunter2"', "SEC-002"),
    ('sql = f"DELETE FROM users WHERE id = {uid}"', "SEC-001"),
    ('cur.execute("SELECT * FROM t WHERE id = " + uid)', "SEC-001"),
    ('cur.execute("TRUNCATE audit_log")', "ARCH-001"),
    ('httpx.post(url, json=body)', "PERF-001"),
])
def test_detections(src, expected):
    assert expected in rule_ids(src)


def test_placeholder_fix_rejected():
    with pytest.raises(ValidationError):
        CodeIssue(file_path="a.py", line_number=1, rule_id="SEC-001", severity="HIGH", title="SQL",
                  description="string built SQL query", code_snippet="x", suggested_fix="TODO: fix later")


def test_markdown_rules(tmp_path):
    f = tmp_path / "rules.md"
    f.write_text("# Team\n\n## UI-001: Dark mode\nSupport both themes.\n", encoding="utf-8")
    assert "UI-001" in [r.rule_id for r in ArchitectureRuleEngine(str(f)).rules]


class FakeGemini:
    """模擬 google-genai client，回傳固定 JSON / Mimics the google-genai client."""

    def __init__(self, payload: dict):
        outer = self

        class Models:
            def generate_content(self, **kwargs):
                outer.prompt = kwargs["contents"]
                return type("R", (), {"text": json.dumps(payload)})()

        self.models = Models()


def llm_issue(line: int, rule: str = "SPEC-001", severity: str = "MEDIUM") -> dict:
    return {"file_path": "x.py", "line_number": line, "rule_id": rule, "severity": severity,
            "title": "Untyped payload", "description": "Endpoint accepts a raw dict payload.",
            "code_snippet": "def f(d):", "suggested_fix": "Accept a Pydantic model instead of dict."}


def test_llm_findings_are_validated_and_merged(agent):
    src = (SAMPLES / "clean_api.py").read_text(encoding="utf-8")
    agent.client = FakeGemini({"issues": [llm_issue(20), llm_issue(9999)]})
    report = agent.review_source("clean_api.py", src)
    assert report.execution_mode == "STATIC+LLM"
    assert [i.line_number for i in report.issues] == [20]       # 行號 9999 被丟棄
    assert "dropped 1" in report.summary
    assert "already_found_by_static_analysis" in agent.client.prompt


def test_verdict_is_computed_not_trusted(agent):
    src = (SAMPLES / "clean_api.py").read_text(encoding="utf-8")
    agent.client = FakeGemini({"issues": [llm_issue(20, "SEC-009", "CRITICAL")]})
    assert agent.review_source("clean_api.py", src).verdict == "BLOCKED"


def test_llm_failure_falls_back_to_static(agent):
    class Broken:
        class models:
            @staticmethod
            def generate_content(**kwargs):
                raise TimeoutError("deadline exceeded")
    agent.client = Broken()
    report = agent.review_file(str(SAMPLES / "vulnerable_api.py"))
    assert report.execution_mode == "STATIC"
    assert "LLM pass failed" in report.summary
    assert LLMFindings(issues=[]).issues == []

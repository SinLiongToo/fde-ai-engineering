"""
AI Code Reviewer & Architecture Compliance Inspector
Module: rule_engine.py
Retrieves and indexes engineering guidelines and compliance standards.
Supports grounding LLM code reviews against project-specific team rules
(e.g. GEMINI.md, team_rules.md, or built-in enterprise baselines).
"""

import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ArchitectureRule:
    rule_id: str
    category: str
    title: str
    severity: str
    description: str
    good_practice: str


# Built-in Enterprise Engineering Baseline Standards
DEFAULT_ENTERPRISE_RULES = [
    ArchitectureRule(
        rule_id="SEC-001",
        category="SECURITY",
        title="SQL Parameterization Requirement",
        severity="CRITICAL",
        description="All SQL queries targeting relational databases (SQLite, PostgreSQL, MySQL) must use parameterized bindings. String concatenation or f-strings inside .execute() is strictly prohibited.",
        good_practice="cursor.execute('SELECT * FROM accounts WHERE id = ?', (acc_id,))"
    ),
    ArchitectureRule(
        rule_id="SEC-002",
        category="SECURITY",
        title="Zero Hardcoded Secrets Policy",
        severity="CRITICAL",
        description="API keys, JWT secrets, database passwords, and private tokens must never be hardcoded in source code files.",
        good_practice="api_key = os.getenv('OPENAI_API_KEY') or pydantic_settings.secret"
    ),
    ArchitectureRule(
        rule_id="PERF-001",
        category="PERFORMANCE",
        title="Explicit Network Call Timeout SLA",
        severity="HIGH",
        description="Every outbound network request (requests, httpx, aiohttp) must specify an explicit timeout float or tuple to prevent thread starvation under network degradation.",
        good_practice="response = requests.get(url, timeout=5.0)"
    ),
    ArchitectureRule(
        rule_id="ARCH-001",
        category="ARCHITECTURE",
        title="Guarded Database Mutations",
        severity="CRITICAL",
        description="Destructive DDL or batch DML statements (DROP TABLE, TRUNCATE, mass DELETE) cannot be executed in standard API request handlers without pre-flight confirmation.",
        good_practice="Isolate DDL in migration scripts with lock_timeout and pre-migration backups."
    ),
    ArchitectureRule(
        rule_id="SPEC-001",
        category="SPEC_CONTRACT",
        title="Pydantic Schema Invariant Enforcement",
        severity="MEDIUM",
        description="API endpoints accepting external JSON payloads must parse and validate inputs through Pydantic v2 models rather than raw untyped dicts.",
        good_practice="def create_user(payload: UserCreateRequest) -> UserResponse:"
    )
]


class ArchitectureRuleEngine:
    """Manages project rules and retrieves contextually relevant guidelines for a given code file."""

    def __init__(self, custom_rules_file: Optional[str] = None):
        self.rules: List[ArchitectureRule] = list(DEFAULT_ENTERPRISE_RULES)
        if custom_rules_file and os.path.exists(custom_rules_file):
            self._load_markdown_rules(custom_rules_file)

    def _load_markdown_rules(self, file_path: str):
        """Loads and parses custom markdown rule files."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Simple markdown section parser
            sections = content.split("## ")
            for sec in sections[1:]:
                lines = sec.strip().splitlines()
                title_line = lines[0] if lines else "Custom Rule"
                rule_id = "CUS-001"
                if ":" in title_line:
                    parts = title_line.split(":", 1)
                    rule_id = parts[0].strip()
                    title = parts[1].strip()
                else:
                    title = title_line
                
                body = "\n".join(lines[1:])
                self.rules.append(ArchitectureRule(
                    rule_id=rule_id if len(rule_id) <= 7 else "CUS-001",
                    category="CUSTOM",
                    title=title,
                    severity="HIGH",
                    description=body[:300],
                    good_practice="Follow guidelines specified in " + file_path
                ))
        except Exception:
            pass

    def retrieve_relevant_rules(self, source_code: str) -> List[ArchitectureRule]:
        """
        規則挑選：用關鍵字判斷哪些規則與這份程式碼相關，只把相關規則放進 prompt。
        規則很多時，可以改用第 5 章的檢索方法。
        Rule selection by keyword. With hundreds of rules, swap in retrieval (chapter 5).
        """
        code_lower = source_code.lower()
        selected: List[ArchitectureRule] = []

        for r in self.rules:
            # Rule SEC-001 applies if database operations are present
            if r.rule_id == "SEC-001" and any(k in code_lower for k in ["sql", "select", "insert", "update", "cursor", "execute", "db"]):
                selected.append(r)
            # Rule SEC-002 applies if strings or tokens appear
            elif r.rule_id == "SEC-002":
                selected.append(r)
            # Rule PERF-001 applies if HTTP requests are made
            elif r.rule_id == "PERF-001" and any(k in code_lower for k in ["requests", "httpx", "http", "fetch", "url", "api"]):
                selected.append(r)
            # Rule ARCH-001 applies if mutations are attempted
            elif r.rule_id == "ARCH-001" and any(k in code_lower for k in ["drop", "truncate", "delete", "destroy"]):
                selected.append(r)
            # Rule SPEC-001 applies if endpoints or dicts are used
            elif r.rule_id == "SPEC-001" and any(k in code_lower for k in ["def ", "class ", "json", "dict", "request"]):
                selected.append(r)

        return selected if selected else self.rules[:3]

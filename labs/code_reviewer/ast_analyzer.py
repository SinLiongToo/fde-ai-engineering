"""
AI Code Reviewer & Architecture Compliance Inspector
Module: ast_analyzer.py
Performs deterministic static analysis using Python's built-in `ast` module.
Extracts functions, detects SQL injections, unhandled timeouts, hardcoded secrets,
and dangerous operations before invoking or supplementing LLM reasoning.
"""

import ast
import re
from typing import List, Dict, Any
from .schemas import CodeIssue

# 以底線切開變數名，逐段比對，避免 max_tokens、token_count 這類誤報。
# Compare name parts, so `max_tokens` or `token_count` are not flagged.
SECRET_NAME_PARTS = {"key", "secret", "token", "password", "passwd", "pwd", "credential", "credentials"}
NON_SECRET_NAME_PARTS = {"max", "count", "limit", "len", "length", "url", "path", "name", "type", "header"}
SQL_MARKERS = ("SELECT ", "INSERT INTO", "UPDATE ", "DELETE FROM", "DROP ", "TRUNCATE ")
DESTRUCTIVE_SQL = ("DROP TABLE", "DROP DATABASE", "TRUNCATE ")


def looks_like_secret_name(name: str) -> bool:
    parts = set(name.lower().split("_"))
    return bool(parts & SECRET_NAME_PARTS) and not (parts & NON_SECRET_NAME_PARTS)


class SecurityASTVisitor(ast.NodeVisitor):
    """Inspects Python AST nodes for common security vulnerabilities and antipatterns."""

    def __init__(self, file_path: str, source_code: str):
        self.file_path = file_path
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.issues: List[CodeIssue] = []

    def _get_line_snippet(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.lines):
            return self.lines[lineno - 1].strip()
        return ""

    def visit_Assign(self, node: ast.Assign):
        """Detects hardcoded secrets, API keys, or tokens in variable assignments."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                # Check for sensitive variable names
                if looks_like_secret_name(target.id):
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        secret_val = node.value.value
                        if len(secret_val) >= 8 and not secret_val.startswith("ENV_"):
                            self.issues.append(CodeIssue(
                                file_path=self.file_path,
                                line_number=node.lineno,
                                rule_id="SEC-002",
                                severity="CRITICAL",
                                title="Hardcoded Secret or API Key",
                                description=(
                                    f"Variable '{target.id}' contains a plaintext hardcoded secret in source code. "
                                    "This risks credential leaks if committed to version control."
                                ),
                                code_snippet=self._get_line_snippet(node.lineno),
                                suggested_fix="Read credentials from environment variables using `os.getenv()` or a secrets manager.",
                                diff_patch=(
                                    f"- {target.id} = \"{secret_val}\"\n"
                                    f"+ import os\n"
                                    f"+ {target.id} = os.getenv(\"{target.id.upper()}\", \"\")"
                                )
                            ))

                # Check for dynamic SQL query assembly in variable assignment
                if isinstance(node.value, ast.JoinedStr):
                    has_sql = False
                    for val in node.value.values:
                        if isinstance(val, ast.Constant) and isinstance(val.value, str):
                            if any(w in val.value.upper() for w in SQL_MARKERS):
                                has_sql = True
                                break
                    # 只看內容，不看變數名：query = f"Hello {name}" 不是 SQL。
                    if has_sql:
                        self.issues.append(CodeIssue(
                            file_path=self.file_path,
                            line_number=node.lineno,
                            rule_id="SEC-001",
                            severity="CRITICAL",
                            title="SQL Injection Vulnerability via Dynamic f-string Construction",
                            description=(
                                f"SQL statement in variable '{target.id}' is assembled using an interpolated f-string. "
                                "This allows SQL injection attacks through malicious user inputs."
                            ),
                            code_snippet=self._get_line_snippet(node.lineno),
                            suggested_fix="Do not format SQL strings with f-strings. Use parameterized queries (?, params) in .execute().",
                            diff_patch=(
                                f"- {self._get_line_snippet(node.lineno)}\n"
                                f"+ query = \"SELECT id, username, balance FROM users WHERE email = ?\""
                            )
                        ))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """Inspects function calls for SQL injections, missing timeouts, and dangerous functions."""
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        # 1. Dangerous functions: eval, exec, os.system
        if func_name in ["eval", "exec"]:
            self.issues.append(CodeIssue(
                file_path=self.file_path,
                line_number=node.lineno,
                rule_id="SEC-003",
                severity="CRITICAL",
                title=f"Use of Dangerous Built-in '{func_name}'",
                description=f"Direct invocation of '{func_name}' allows arbitrary code execution from untrusted inputs.",
                code_snippet=self._get_line_snippet(node.lineno),
                suggested_fix="Refactor logic to use safe parsers like `ast.literal_eval` or typed Pydantic models."
            ))

        # 2. Database query execution checks (SQL injection detection)
        if func_name in ["execute", "executemany", "raw"]:
            if node.args:
                first_arg = node.args[0]
                # Pattern: f"SELECT ... {var}"
                if isinstance(first_arg, ast.JoinedStr):
                    self.issues.append(CodeIssue(
                        file_path=self.file_path,
                        line_number=node.lineno,
                        rule_id="SEC-001",
                        severity="CRITICAL",
                        title="SQL Injection Vulnerability via f-string Formatting",
                        description=(
                            "SQL query constructed using dynamic f-string formatting. "
                            "Untrusted user input can manipulate query logic and dump or delete the database."
                        ),
                        code_snippet=self._get_line_snippet(node.lineno),
                        suggested_fix="Use parameterized queries with placeholders `(?, (param,))` or `%s`.",
                        diff_patch=(
                            "- cursor.execute(f\"SELECT * FROM users WHERE id = '{user_id}'\")\n"
                            "+ cursor.execute(\"SELECT * FROM users WHERE id = ?\", (user_id,))"
                        )
                    ))
                # Pattern: cursor.execute("DROP TABLE ...")
                elif isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str) and any(
                    m in first_arg.value.upper() for m in DESTRUCTIVE_SQL
                ):
                    self.issues.append(CodeIssue(
                        file_path=self.file_path,
                        line_number=node.lineno,
                        rule_id="ARCH-001",
                        severity="CRITICAL",
                        title="Destructive DDL in application code",
                        description="DROP/TRUNCATE executed from application logic bypasses migration review and backups.",
                        code_snippet=self._get_line_snippet(node.lineno),
                        suggested_fix="Move schema changes into reviewed migration scripts (Alembic, Flyway) with a backup step.",
                    ))
                # Pattern: "SELECT ... " + var
                elif isinstance(first_arg, ast.BinOp) and isinstance(first_arg.op, ast.Add):
                    self.issues.append(CodeIssue(
                        file_path=self.file_path,
                        line_number=node.lineno,
                        rule_id="SEC-001",
                        severity="CRITICAL",
                        title="SQL Injection Vulnerability via String Concatenation",
                        description="SQL query assembled using binary string addition (`+`). Vulnerable to SQL injection.",
                        code_snippet=self._get_line_snippet(node.lineno),
                        suggested_fix="Replace string concatenation with parameterized query parameters."
                    ))

        # 3. HTTP Network calls without timeout
        if func_name in ["get", "post", "put", "delete", "request"]:
            is_http = False
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                if node.func.value.id in ["requests", "httpx", "http_client"]:
                    is_http = True

            if is_http:
                has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
                if not has_timeout:
                    self.issues.append(CodeIssue(
                        file_path=self.file_path,
                        line_number=node.lineno,
                        rule_id="PERF-001",
                        severity="HIGH",
                        title="Missing HTTP Request Timeout",
                        description=(
                            f"Call to `{node.func.value.id}.{func_name}()` lacks an explicit `timeout` parameter. "
                            "Slow or unresponsive third-party APIs can cause thread starvation and cascade service outages."
                        ),
                        code_snippet=self._get_line_snippet(node.lineno),
                        suggested_fix="Always specify an explicit timeout, e.g. `timeout=5.0` or `timeout=(3.0, 10.0)`.",
                        diff_patch=(
                            f"- {node.func.value.id}.{func_name}(url)\n"
                            f"+ {node.func.value.id}.{func_name}(url, timeout=5.0)"
                        )
                    ))

        self.generic_visit(node)


def analyze_source_code_ast(file_path: str, source_code: str) -> List[CodeIssue]:
    """Parses Python source code and runs AST security analysis."""
    try:
        tree = ast.parse(source_code, filename=file_path)
    except SyntaxError as e:
        return [
            CodeIssue(
                file_path=file_path,
                line_number=e.lineno or 1,
                rule_id="SYN-001",
                severity="CRITICAL",
                title="Python Syntax Error",
                description=f"Source code contains syntax error: {e.msg}",
                code_snippet=e.text.strip() if e.text else "",
                suggested_fix="Fix code syntax before running static and architecture review."
            )
        ]

    visitor = SecurityASTVisitor(file_path, source_code)
    visitor.visit(tree)
    return visitor.issues

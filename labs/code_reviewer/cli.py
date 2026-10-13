"""
AI Code Reviewer & Architecture Compliance Inspector
Module: cli.py
Command-Line Interface (CLI) runner with rich formatted output,
colorized unified diffs, and CI/CD status code reporting.
"""

import sys
import os
import argparse

# Configure Windows UTF-8 stdout encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

from .reviewer_agent import AICodeReviewerAgent
from .schemas import ReviewReport

console = Console(highlight=False)


def display_report(report: ReviewReport):
    """Renders formatted code review report in the terminal."""
    # 1. Header Banner
    banner_color = "red" if report.verdict == "BLOCKED" else ("yellow" if report.verdict == "WARNING" else "green")
    console.print(Panel(
        f"[bold {banner_color}]AI CODE REVIEW & COMPLIANCE REPORT: {report.verdict}[/bold {banner_color}]\n"
        f"[white]Target:[/] [bold]{report.target_file}[/]  |  "
        f"[white]Lines:[/] {report.total_lines}  |  "
        f"[white]Score:[/] [bold {banner_color}]{report.security_score}/100[/]  |  "
        f"[white]Engine:[/] [cyan]{report.execution_mode}[/]",
        border_style=banner_color
    ))

    # 2. Executive Summary
    console.print(f"\n[bold cyan]Executive Summary:[/bold cyan] {report.summary}\n")

    # 3. Issues Table
    if not report.issues:
        console.print("[bold green]✔ Zero vulnerabilities or architectural anti-patterns detected! Clean code.[/bold green]\n")
        return

    table = Table(title="Detected Vulnerabilities & Policy Violations", show_lines=True)
    table.add_column("Line", style="cyan", justify="right", width=6)
    table.add_column("Rule ID", style="bold magenta", width=10)
    table.add_column("Severity", justify="center", width=10)
    table.add_column("Title & Suggested Fix", style="white")

    severity_styles = {
        "CRITICAL": "[bold red]CRITICAL[/bold red]",
        "HIGH": "[bold yellow]HIGH[/bold yellow]",
        "MEDIUM": "[cyan]MEDIUM[/cyan]",
        "LOW": "[blue]LOW[/blue]",
        "INFO": "[dim]INFO[/dim]"
    }

    for issue in report.issues:
        sev_label = severity_styles.get(issue.severity, issue.severity)
        details = (
            f"[bold]{issue.title}[/bold]\n"
            f"[dim]{issue.description}[/dim]\n"
            f"[yellow]Offending Code:[/] [red]{issue.code_snippet}[/red]\n"
            f"[green]Fix:[/] {issue.suggested_fix}"
        )
        table.add_row(str(issue.line_number), issue.rule_id, sev_label, details)

    console.print(table)

    # 4. Unified Diff Patches
    patches = [i for i in report.issues if i.diff_patch]
    if patches:
        console.print("\n[bold green]━━━ Automated Remediation Diffs (Unified Patch) ━━━[/bold green]")
        for i, patch_issue in enumerate(patches, 1):
            console.print(f"\n[cyan]Patch #{i} (Line {patch_issue.line_number} - {patch_issue.rule_id}):[/cyan]")
            syntax = Syntax(patch_issue.diff_patch, "diff", theme="monokai", line_numbers=False)
            console.print(syntax)

    # 5. Final CI/CD Gate Status
    console.print("")
    if report.verdict == "BLOCKED":
        console.print("[bold red]🚨 CI/CD QUALITY GATE FAILED: Pull Request cannot be merged until CRITICAL issues are resolved.[/bold red]\n")
    elif report.verdict == "WARNING":
        console.print("[bold yellow]⚠️ CI/CD QUALITY GATE WARNING: Please review high-priority suggestions before release.[/bold yellow]\n")
    else:
        console.print("[bold green]🎉 CI/CD QUALITY GATE PASSED: Code meets enterprise security & architecture standards.[/bold green]\n")


def main():
    parser = argparse.ArgumentParser(description="AI Code Reviewer & Architecture Compliance Inspector")
    parser.add_argument(
        "target", 
        nargs="?", 
        default=os.path.join(os.path.dirname(__file__), "samples", "vulnerable_api.py"),
        help="Path to Python file to inspect (defaults to sample vulnerable_api.py)"
    )
    parser.add_argument("--rules", default=None, help="Optional Markdown rules file (## RULE-ID: Title sections)")
    args = parser.parse_args()

    agent = AICodeReviewerAgent(custom_rules_file=args.rules)
    
    try:
        report = agent.review_file(args.target)
        display_report(report)
        sys.exit(1 if report.verdict == "BLOCKED" else 0)
    except Exception as e:
        console.print(f"[bold red]Error running code review:[/] {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()

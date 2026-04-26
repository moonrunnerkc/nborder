from __future__ import annotations

import sys
from pathlib import Path

from nborder.fix.models import FixOutcome
from nborder.reporters.base import Reporter
from nborder.rules.types import Diagnostic, Severity

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_SEVERITY_ANSI: dict[Severity, str] = {
    "error": "\x1b[31m",
    "warning": "\x1b[33m",
    "info": "\x1b[36m",
}
_FIXABLE_ANSI = "\x1b[32m"


class TextReporter(Reporter):
    """Human-readable diagnostic output styled after ruff."""

    def __init__(self, *, color: bool | None = None) -> None:
        """Configure the text reporter.

        Args:
            color: Force color on or off. None auto-detects a TTY on stdout.
        """
        self._color = color if color is not None else sys.stdout.isatty()

    def report(
        self,
        diagnostics: tuple[Diagnostic, ...],
        fix_outcomes: tuple[FixOutcome, ...] | None = None,
    ) -> str:
        report_lines = [_render_diagnostic(diagnostic, self._color) for diagnostic in diagnostics]
        if fix_outcomes is not None:
            report_lines.append(_format_fix_outcomes(fix_outcomes))
        if diagnostics:
            report_lines.append(format_summary(diagnostics))
        return "\n".join(report_lines)


def format_diagnostic(diagnostic: Diagnostic) -> str:
    """Format one diagnostic as plain text.

    Args:
        diagnostic: Finding to format.

    Returns:
        A single-line ruff-style diagnostic without ANSI styling.
    """
    return _render_diagnostic(diagnostic, color=False)


def format_summary(diagnostics: tuple[Diagnostic, ...]) -> str:
    """Format the diagnostic count and fixability summary.

    Args:
        diagnostics: Findings emitted for a check run.

    Returns:
        Summary line describing the count and fixable share.
    """
    diagnostic_count = len(diagnostics)
    fixable_count = sum(1 for diagnostic in diagnostics if diagnostic.fixable)
    noun = "error" if diagnostic_count == 1 else "errors"
    return f"Found {diagnostic_count} {noun}. {fixable_count} fixable with --fix."


def _render_diagnostic(diagnostic: Diagnostic, color: bool) -> str:
    code_text = diagnostic.code
    fixable_text = "[*]" if diagnostic.fixable else ""
    if color:
        severity_color = _SEVERITY_ANSI[diagnostic.severity]
        code_text = f"{_BOLD}{severity_color}{code_text}{_RESET}"
        if fixable_text:
            fixable_text = f"{_BOLD}{_FIXABLE_ANSI}{fixable_text}{_RESET}"
    suffix = f" {fixable_text}" if fixable_text else ""
    return (
        f"{_format_path(diagnostic.notebook_path)}:cell_{diagnostic.cell_index}:"
        f"{diagnostic.line}:{diagnostic.column}: "
        f"{code_text} {diagnostic.message}{suffix}"
    )


def _format_path(notebook_path: Path) -> str:
    try:
        relative_path = notebook_path.resolve().relative_to(Path.cwd().resolve())
        return str(relative_path)
    except ValueError:
        return str(notebook_path)


def _format_fix_outcomes(fix_outcomes: tuple[FixOutcome, ...]) -> str:
    lines = ["Fix outcomes:"]
    for fix_outcome in fix_outcomes:
        lines.append(f"  {fix_outcome.fix_id}: {fix_outcome.status} ({fix_outcome.description})")
    return "\n".join(lines)

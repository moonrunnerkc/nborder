from __future__ import annotations

from nborder.fix.models import FixOutcome
from nborder.reporters.base import Reporter
from nborder.rules.types import Diagnostic


class TextReporter(Reporter):
    """Human-readable diagnostic output styled after ruff."""

    def report(
        self,
        diagnostics: tuple[Diagnostic, ...],
        fix_outcomes: tuple[FixOutcome, ...] | None = None,
    ) -> str:
        report_lines = [format_diagnostic(diagnostic) for diagnostic in diagnostics]
        if fix_outcomes is not None:
            report_lines.append(_format_fix_outcomes(fix_outcomes))
        if diagnostics:
            report_lines.append(format_summary(diagnostics))
        return "\n".join(report_lines)


def format_diagnostic(diagnostic: Diagnostic) -> str:
    """Format one diagnostic for terminal output.

    Args:
        diagnostic: Finding to format.

    Returns:
        A single-line diagnostic with notebook cell, line, column, and rule code.
    """
    cell_number = diagnostic.cell_index + 1
    return (
        f"{diagnostic.notebook_path}:cell_{cell_number}:{diagnostic.line}:{diagnostic.column}: "
        f"{diagnostic.code} {diagnostic.message}"
    )



def format_summary(diagnostics: tuple[Diagnostic, ...]) -> str:
    """Format the diagnostic count and fixability summary.

    Args:
        diagnostics: Findings emitted for a check run.

    Returns:
        Summary line for terminal output.
    """
    diagnostic_count = len(diagnostics)
    fixable_count = sum(1 for diagnostic in diagnostics if diagnostic.fixable)
    noun = "error" if diagnostic_count == 1 else "errors"
    return f"Found {diagnostic_count} {noun}. {fixable_count} fixable with --fix."


def _format_fix_outcomes(fix_outcomes: tuple[FixOutcome, ...]) -> str:
    lines = ["Fix outcomes:"]
    for fix_outcome in fix_outcomes:
        lines.append(f"  {fix_outcome.fix_id}: {fix_outcome.status} ({fix_outcome.description})")
    return "\n".join(lines)

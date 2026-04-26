from __future__ import annotations

from nborder.fix.models import FixOutcome
from nborder.reporters.base import Reporter
from nborder.rules.types import Diagnostic, Severity

_SEVERITY_COMMAND: dict[Severity, str] = {
    "error": "error",
    "warning": "warning",
    "info": "notice",
}


class GithubReporter(Reporter):
    """GitHub Actions workflow command output for inline annotations."""

    def report(
        self,
        diagnostics: tuple[Diagnostic, ...],
        fix_outcomes: tuple[FixOutcome, ...] | None = None,
    ) -> str:
        del fix_outcomes
        return "\n".join(_format_workflow_command(diagnostic) for diagnostic in diagnostics)


def _format_workflow_command(diagnostic: Diagnostic) -> str:
    command_name = _SEVERITY_COMMAND[diagnostic.severity]
    properties = (
        f"file={_escape_property(str(diagnostic.notebook_path))},"
        f"line={diagnostic.line},"
        f"col={diagnostic.column},"
        f"endLine={diagnostic.end_line},"
        f"endColumn={diagnostic.end_column},"
        f"title={_escape_property(diagnostic.code)}"
    )
    return f"::{command_name} {properties}::{_escape_message(diagnostic.message)}"


def _escape_property(value: str) -> str:
    return (
        value.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


def _escape_message(message: str) -> str:
    return message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")

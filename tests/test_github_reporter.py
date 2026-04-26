from __future__ import annotations

from pathlib import Path

from nborder.reporters.github import GithubReporter
from nborder.rules.types import Diagnostic, FixDescriptor, Severity


def _make_diagnostic(
    *,
    severity: Severity = "error",
    code: str = "NB201",
    message: str = "Variable `df` used in cell 0 is only defined in cell 1.",
) -> Diagnostic:
    return Diagnostic(
        code=code,
        severity=severity,
        message=message,
        notebook_path=Path("notebooks/example.ipynb"),
        cell_index=0,
        cell_id="abc123",
        line=7,
        column=5,
        end_line=7,
        end_column=12,
        fixable=True,
        fix_descriptor=FixDescriptor("reorder", [0, 1], "reorder"),
    )


def test_github_reporter_uses_error_command_for_error_severity() -> None:
    rendered = GithubReporter().report((_make_diagnostic(),), None)

    assert rendered.startswith("::error ")
    assert "file=notebooks/example.ipynb" in rendered
    assert "line=7" in rendered
    assert "col=5" in rendered
    assert "endLine=7" in rendered
    assert "endColumn=12" in rendered
    assert "title=NB201" in rendered
    assert rendered.endswith("Variable `df` used in cell 0 is only defined in cell 1.")


def test_github_reporter_maps_warning_to_warning_command() -> None:
    rendered = GithubReporter().report(
        (_make_diagnostic(severity="warning", code="NB103"),),
        None,
    )

    assert rendered.startswith("::warning ")


def test_github_reporter_maps_info_to_notice_command() -> None:
    rendered = GithubReporter().report(
        (_make_diagnostic(severity="info", code="NB102"),),
        None,
    )

    assert rendered.startswith("::notice ")


def test_github_reporter_escapes_newlines_in_message() -> None:
    rendered = GithubReporter().report(
        (_make_diagnostic(message="line one\nline two"),),
        None,
    )

    assert "line one%0Aline two" in rendered
    assert "\n" not in rendered.split("::", 2)[2]


def test_github_reporter_emits_one_line_per_diagnostic() -> None:
    rendered = GithubReporter().report(
        (_make_diagnostic(), _make_diagnostic(code="NB103", severity="warning")),
        None,
    )

    assert rendered.count("\n") == 1

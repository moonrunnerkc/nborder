from __future__ import annotations

from pathlib import Path

from nborder.fix.models import FixOutcome
from nborder.reporters.text import TextReporter, format_diagnostic, format_summary
from nborder.rules.types import Diagnostic, FixDescriptor

FIXTURE_NOTEBOOK = Path("tests/fixtures/phase3/mixed.ipynb").resolve()


def _make_diagnostic(
    *,
    code: str = "NB201",
    severity: str = "error",
    message: str = "Variable `df` used in cell 0 is only defined in cell 1.",
    cell_index: int = 0,
    line: int = 1,
    column: int = 7,
    fixable: bool = True,
) -> Diagnostic:
    return Diagnostic(
        code=code,
        severity=severity,  # type: ignore[arg-type]
        message=message,
        notebook_path=FIXTURE_NOTEBOOK,
        cell_index=cell_index,
        cell_id="mixed-use",
        line=line,
        column=column,
        end_line=line,
        end_column=column + 2,
        fixable=fixable,
        fix_descriptor=FixDescriptor("reorder", [0, 1], "reorder") if fixable else None,
    )


def test_text_reporter_emits_zero_based_cell_index_and_fixable_marker() -> None:
    diagnostic = _make_diagnostic()

    rendered = format_diagnostic(diagnostic)

    assert "cell_0" in rendered
    assert "[*]" in rendered
    assert "NB201" in rendered


def test_text_reporter_omits_fixable_marker_for_unfixable_diagnostic() -> None:
    diagnostic = _make_diagnostic(code="NB102", message="Name `x` is undefined.", fixable=False)

    rendered = format_diagnostic(diagnostic)

    assert "[*]" not in rendered


def test_text_reporter_summary_pluralizes_for_multiple_errors() -> None:
    fixable = _make_diagnostic()
    unfixable = _make_diagnostic(code="NB102", fixable=False)

    summary = format_summary((fixable, unfixable))

    assert summary == "Found 2 errors. 1 fixable with --fix."


def test_text_reporter_appends_fix_outcomes_block_when_provided() -> None:
    diagnostic = _make_diagnostic()
    outcomes = (
        FixOutcome("reorder", "applied", "applied to 2 cells", (0, 1)),
        FixOutcome("seeds", "no-op", "no NB103 seed diagnostics found", ()),
    )

    rendered = TextReporter(color=False).report((diagnostic,), outcomes)

    assert "Fix outcomes:" in rendered
    assert "reorder: applied (applied to 2 cells)" in rendered
    assert "seeds: no-op" in rendered


def test_text_reporter_skips_summary_when_no_diagnostics() -> None:
    rendered = TextReporter(color=False).report((), None)

    assert rendered == ""


def test_text_reporter_color_path_emits_ansi_codes() -> None:
    diagnostic = _make_diagnostic()

    rendered = TextReporter(color=True).report((diagnostic,), None)

    assert "\x1b[" in rendered

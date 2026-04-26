from __future__ import annotations

import json
from pathlib import Path

from nborder.fix.models import FixOutcome
from nborder.reporters.jsonout import JsonReporter
from nborder.rules.types import Diagnostic, FixDescriptor


def _make_diagnostic(*, fixable: bool = True) -> Diagnostic:
    return Diagnostic(
        code="NB201",
        severity="error",
        message="Variable `df` used in cell 0 is only defined in cell 1.",
        notebook_path=Path("notebooks/example.ipynb"),
        cell_index=0,
        cell_id="abc123",
        line=7,
        column=5,
        end_line=7,
        end_column=12,
        fixable=fixable,
        fix_descriptor=FixDescriptor("reorder", [0, 1], "reorder") if fixable else None,
    )


def test_json_reporter_emits_diagnostics_with_documented_fields() -> None:
    diagnostic = _make_diagnostic()

    payload = json.loads(JsonReporter().report((diagnostic,), None))

    assert payload["fix_outcomes"] is None
    assert len(payload["diagnostics"]) == 1
    diagnostic_dict = payload["diagnostics"][0]
    assert diagnostic_dict["code"] == "NB201"
    assert diagnostic_dict["severity"] == "error"
    assert diagnostic_dict["cell_index"] == 0
    assert diagnostic_dict["cell_id"] == "abc123"
    assert diagnostic_dict["line"] == 7
    assert diagnostic_dict["column"] == 5
    assert diagnostic_dict["end_line"] == 7
    assert diagnostic_dict["end_column"] == 12
    assert diagnostic_dict["fixable"] is True
    assert diagnostic_dict["fix_id"] == "reorder"
    assert diagnostic_dict["notebook_path"] == "notebooks/example.ipynb"


def test_json_reporter_emits_fix_outcomes_block_when_provided() -> None:
    diagnostic = _make_diagnostic(fixable=False)
    outcomes = (
        FixOutcome("reorder", "applied", "applied to 2 cells", (0, 1)),
        FixOutcome("seeds", "no-op", "no NB103 seed diagnostics found", ()),
    )

    payload = json.loads(JsonReporter().report((diagnostic,), outcomes))

    assert payload["fix_outcomes"] == [
        {"fix_id": "reorder", "status": "applied", "details": "applied to 2 cells"},
        {"fix_id": "seeds", "status": "no-op", "details": "no NB103 seed diagnostics found"},
    ]


def test_json_reporter_keeps_top_level_shape_for_empty_input() -> None:
    payload = json.loads(JsonReporter().report((), None))

    assert payload == {"diagnostics": [], "fix_outcomes": None}


def test_json_reporter_marks_unfixable_diagnostic_with_null_fix_id() -> None:
    diagnostic = _make_diagnostic(fixable=False)

    payload = json.loads(JsonReporter().report((diagnostic,), None))

    assert payload["diagnostics"][0]["fix_id"] is None
    assert payload["diagnostics"][0]["fixable"] is False

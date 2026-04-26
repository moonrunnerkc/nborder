from __future__ import annotations

import json
from typing import Any

from nborder.fix.models import FixOutcome
from nborder.reporters.base import Reporter
from nborder.rules.types import Diagnostic


class JsonReporter(Reporter):
    """Machine-readable JSON output for CI consumption."""

    def __init__(self, *, indent: int | None = 2) -> None:
        """Configure the JSON reporter.

        Args:
            indent: Indentation level for json.dumps. None produces compact output.
        """
        self._indent = indent

    def report(
        self,
        diagnostics: tuple[Diagnostic, ...],
        fix_outcomes: tuple[FixOutcome, ...] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "diagnostics": [_diagnostic_dict(diagnostic) for diagnostic in diagnostics],
            "fix_outcomes": (
                [_fix_outcome_dict(fix_outcome) for fix_outcome in fix_outcomes]
                if fix_outcomes is not None
                else None
            ),
        }
        return json.dumps(payload, indent=self._indent)


def _diagnostic_dict(diagnostic: Diagnostic) -> dict[str, Any]:
    fix_descriptor = diagnostic.fix_descriptor
    return {
        "notebook_path": str(diagnostic.notebook_path),
        "cell_index": diagnostic.cell_index,
        "cell_id": diagnostic.cell_id,
        "line": diagnostic.line,
        "column": diagnostic.column,
        "end_line": diagnostic.end_line,
        "end_column": diagnostic.end_column,
        "code": diagnostic.code,
        "severity": diagnostic.severity,
        "message": diagnostic.message,
        "fixable": diagnostic.fixable,
        "fix_id": fix_descriptor.fix_id if fix_descriptor is not None else None,
    }


def _fix_outcome_dict(fix_outcome: FixOutcome) -> dict[str, Any]:
    return {
        "fix_id": fix_outcome.fix_id,
        "status": fix_outcome.status,
        "details": fix_outcome.description,
    }

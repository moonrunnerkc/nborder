from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nborder import __version__
from nborder.fix.models import FixOutcome
from nborder.reporters.base import Reporter
from nborder.rules.types import Diagnostic, Severity

_SARIF_VERSION = "2.1.0"
_SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/"
    "sarif-2.1/schema/sarif-schema-2.1.0.json"
)
_HELP_URI_BASE = "https://github.com/moonrunnerkc/nborder/blob/main/docs/rules"

_LEVEL_FROM_SEVERITY: dict[Severity, str] = {
    "error": "error",
    "warning": "warning",
    "info": "note",
}

_RULE_METADATA: dict[str, dict[str, str]] = {
    "NB101": {
        "name": "non-monotonic-execution-counts",
        "short": "Notebook cells were not executed in source order.",
        "full": (
            "Source-order cells with decreasing execution counts indicate the "
            "notebook was run out of order, which makes it unreliable on a "
            "Restart-and-Run-All execution."
        ),
    },
    "NB102": {
        "name": "wont-survive-restart-run-all",
        "short": "Name is used but never defined in the notebook.",
        "full": (
            "A symbol is referenced in source order but no cell in the notebook "
            "defines it. Restart-and-Run-All will fail with NameError."
        ),
    },
    "NB201": {
        "name": "use-before-assign",
        "short": "Symbol is used in a cell before its only definition.",
        "full": (
            "A symbol is referenced in cell N but only defined in cell M with "
            "M > N. Reordering cells topologically resolves the dependency."
        ),
    },
    "NB103": {
        "name": "stochastic-library-without-seed",
        "short": "Stochastic library is used before its random seed is set.",
        "full": (
            "A known random-number-generator library produces stochastic output "
            "before any seed call has run. Inject a library-appropriate seed "
            "near the top of the notebook for reproducibility."
        ),
    },
}


class SarifReporter(Reporter):
    """SARIF 2.1.0 JSON output for static-analysis dashboards."""

    def __init__(self, *, indent: int | None = 2) -> None:
        """Configure the SARIF reporter.

        Args:
            indent: Indentation level for json.dumps. None produces compact output.
        """
        self._indent = indent

    def report(
        self,
        diagnostics: tuple[Diagnostic, ...],
        fix_outcomes: tuple[FixOutcome, ...] | None = None,
    ) -> str:
        del fix_outcomes
        sarif_log = _build_sarif_log(diagnostics)
        return json.dumps(sarif_log, indent=self._indent)


def _build_sarif_log(diagnostics: tuple[Diagnostic, ...]) -> dict[str, Any]:
    return {
        "version": _SARIF_VERSION,
        "$schema": _SARIF_SCHEMA,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "nborder",
                        "version": __version__,
                        "informationUri": "https://github.com/moonrunnerkc/nborder",
                        "rules": _rule_descriptors(),
                    }
                },
                "results": [_result(diagnostic) for diagnostic in diagnostics],
            }
        ],
    }


def _rule_descriptors() -> list[dict[str, Any]]:
    descriptors: list[dict[str, Any]] = []
    for rule_code in ("NB101", "NB102", "NB201", "NB103"):
        rule_metadata = _RULE_METADATA[rule_code]
        descriptors.append(
            {
                "id": rule_code,
                "name": rule_metadata["name"],
                "shortDescription": {"text": rule_metadata["short"]},
                "fullDescription": {"text": rule_metadata["full"]},
                "helpUri": f"{_HELP_URI_BASE}/{rule_code}.md",
            }
        )
    return descriptors


def _result(diagnostic: Diagnostic) -> dict[str, Any]:
    return {
        "ruleId": diagnostic.code,
        "level": _LEVEL_FROM_SEVERITY[diagnostic.severity],
        "message": {"text": diagnostic.message},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": _artifact_uri(diagnostic.notebook_path)},
                    "region": {
                        "startLine": diagnostic.line,
                        "startColumn": diagnostic.column,
                        "endLine": diagnostic.end_line,
                        "endColumn": diagnostic.end_column,
                    },
                }
            }
        ],
    }


def _artifact_uri(notebook_path: Path) -> str:
    return notebook_path.as_posix()

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from nborder.reporters.sarif import SarifReporter
from nborder.rules.types import Diagnostic, FixDescriptor, Severity

SCHEMA_PATH = Path(__file__).parent / "fixtures" / "sarif" / "sarif_schema.json"


def _make_diagnostic(
    *,
    code: str = "NB201",
    severity: Severity = "error",
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


def _load_schema() -> dict[str, object]:
    with SCHEMA_PATH.open(encoding="utf-8") as schema_file:
        return json.load(schema_file)


def test_sarif_reporter_output_validates_against_official_schema() -> None:
    diagnostics = (
        _make_diagnostic(),
        _make_diagnostic(code="NB103", severity="warning", message="Numpy unseeded."),
        _make_diagnostic(code="NB102", severity="info", message="Wildcard import."),
    )

    sarif_log = json.loads(SarifReporter().report(diagnostics, None))

    jsonschema.validate(sarif_log, _load_schema())


def test_sarif_reporter_emits_one_rule_per_known_code() -> None:
    sarif_log = json.loads(SarifReporter().report((), None))

    rules = sarif_log["runs"][0]["tool"]["driver"]["rules"]
    rule_ids = [rule["id"] for rule in rules]
    assert rule_ids == ["NB101", "NB102", "NB201", "NB103"]


def test_sarif_reporter_maps_severity_to_sarif_level() -> None:
    diagnostics = (
        _make_diagnostic(severity="error"),
        _make_diagnostic(severity="warning", code="NB103"),
        _make_diagnostic(severity="info", code="NB102"),
    )

    sarif_log = json.loads(SarifReporter().report(diagnostics, None))
    levels = [result["level"] for result in sarif_log["runs"][0]["results"]]

    assert levels == ["error", "warning", "note"]


def test_sarif_reporter_records_one_physical_location_per_diagnostic() -> None:
    sarif_log = json.loads(SarifReporter().report((_make_diagnostic(),), None))
    physical_location = sarif_log["runs"][0]["results"][0]["locations"][0]["physicalLocation"]

    assert physical_location["artifactLocation"]["uri"] == "notebooks/example.ipynb"
    assert physical_location["region"] == {
        "startLine": 7,
        "startColumn": 5,
        "endLine": 7,
        "endColumn": 12,
    }

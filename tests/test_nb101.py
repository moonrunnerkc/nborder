from __future__ import annotations

from pathlib import Path

from nborder.parser.reader import read_notebook
from nborder.rules.nb101 import check_non_monotonic_execution_counts

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "NB101"


def test_nb101_flags_non_monotonic_execution_counts() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "non_monotonic.ipynb")

    diagnostics = check_non_monotonic_execution_counts(notebook)

    assert len(diagnostics) == 1
    assert diagnostics[0].code == "NB101"
    assert diagnostics[0].cell_index == 1


def test_nb101_allows_monotonic_execution_counts_with_nulls() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "monotonic_with_nulls.ipynb")

    diagnostics = check_non_monotonic_execution_counts(notebook)

    assert diagnostics == ()


def test_nb101_fixed_fixture_round_trips_cleanly() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "fixed.ipynb")

    diagnostics = check_non_monotonic_execution_counts(notebook)

    assert diagnostics == ()

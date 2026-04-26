from __future__ import annotations

from pathlib import Path

from nborder.cli import _check_notebook
from nborder.config import Config
from nborder.parser.reader import read_notebook

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def test_nb101_noqa_suppresses_execution_count_diagnostic() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "suppression" / "NB101.ipynb")

    diagnostics = _check_notebook(notebook, Config(), include_levels=frozenset({"error", "info"}))

    assert all(diagnostic.code != "NB101" for diagnostic in diagnostics)


def test_nb102_noqa_suppresses_undefined_name_diagnostic() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "suppression" / "NB102.ipynb")

    diagnostics = _check_notebook(notebook, Config(), include_levels=frozenset({"error", "info"}))

    assert all(diagnostic.code != "NB102" for diagnostic in diagnostics)


def test_nb201_noqa_suppresses_use_before_assign_diagnostic() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "suppression" / "NB201.ipynb")

    diagnostics = _check_notebook(notebook, Config(), include_levels=frozenset({"error", "info"}))

    assert all(diagnostic.code != "NB201" for diagnostic in diagnostics)


def test_nb103_noqa_suppresses_unseeded_random_diagnostic() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "suppression" / "NB103.ipynb")

    diagnostics = _check_notebook(notebook, Config(), include_levels=frozenset({"error", "info"}))

    assert all(diagnostic.code != "NB103" for diagnostic in diagnostics)


def test_cell_level_noqa_suppresses_all_nborder_diagnostics() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "suppression" / "all_codes.ipynb")

    diagnostics = _check_notebook(notebook, Config(), include_levels=frozenset({"error", "info"}))

    assert diagnostics == ()

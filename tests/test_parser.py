from __future__ import annotations

from pathlib import Path

from nborder.parser.reader import read_notebook

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def test_parser_preserves_nbformat_minor_on_v45_notebook() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "roundtrip" / "v45_clean.ipynb")

    assert notebook.nbformat_minor == 5


def test_parser_preserves_papermill_tags() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "roundtrip" / "v45_clean.ipynb")

    assert "parameters" in notebook.cells[0].tags


def test_parser_records_magic_bindings_from_code_cells() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "roundtrip" / "v44_clean.ipynb")

    assert notebook.cells[0].magics[2].kind == "shell_assignment"
    assert notebook.cells[0].magics[2].binding == "files"

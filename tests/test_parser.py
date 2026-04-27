from __future__ import annotations

from pathlib import Path

from nbformat.notebooknode import NotebookNode

from nborder.parser.reader import _cell_source, read_notebook

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


def test_cell_source_joins_list_source_values() -> None:
    cell_node = NotebookNode(source=["alpha = 1\n", "beta = 2\n"])

    assert _cell_source(cell_node) == "alpha = 1\nbeta = 2\n"


def test_cell_source_stringifies_unusual_source_values() -> None:
    cell_node = NotebookNode(source=42)

    assert _cell_source(cell_node) == "42"

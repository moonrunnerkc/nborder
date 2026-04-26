from __future__ import annotations

from pathlib import Path
from typing import cast

import libcst as cst
import nbformat
from nbformat.notebooknode import NotebookNode

from nborder.parser.magics import strip_magics
from nborder.parser.models import Cell, CellKind, Notebook


class NotebookParseError(Exception):
    """Raised when a notebook cell cannot be parsed as Python."""



def read_notebook(path: Path) -> Notebook:
    """Read a notebook into nborder's typed cell model.

    Args:
        path: Notebook file to read.

    Returns:
        Parsed notebook with original bytes preserved for stable writing.

    Raises:
        NotebookParseError: A code cell still contains invalid Python after magic stripping.
    """
    raw_bytes = path.read_bytes()
    notebook_node = cast(
        NotebookNode,
        nbformat.reads(raw_bytes.decode("utf-8"), as_version=4),  # type: ignore[no-untyped-call]
    )
    cells = tuple(
        _parse_cell(cell_node, index) for index, cell_node in enumerate(notebook_node.cells)
    )
    return Notebook(
        path=path,
        raw_bytes=raw_bytes,
        node=notebook_node,
        nbformat_minor=cast(int, notebook_node.nbformat_minor),
        cells=cells,
    )



def _parse_cell(cell_node: NotebookNode, index: int) -> Cell:
    cell_kind = cast(CellKind, cell_node.cell_type)
    source = _cell_source(cell_node)
    tags = frozenset(str(tag) for tag in cell_node.get("metadata", {}).get("tags", ()))
    cell_id = cast(str | None, cell_node.get("id"))

    if cell_kind != "code":
        return Cell(
            index=index,
            cell_id=cell_id,
            kind=cell_kind,
            source=source,
            stripped_source=source,
            tags=tags,
            execution_count=None,
            magics=(),
            cst_module=None,
        )

    magic_strip = strip_magics(source)
    try:
        cst_module = cst.parse_module(magic_strip.stripped_source)
    except cst.ParserSyntaxError as parser_error:
        cell_number = index + 1
        raise NotebookParseError(
            f"Failed to parse cell {cell_number}: {parser_error}. "
            "Run nborder check with a Python notebook or remove unsupported syntax."
        ) from parser_error

    return Cell(
        index=index,
        cell_id=cell_id,
        kind="code",
        source=source,
        stripped_source=magic_strip.stripped_source,
        tags=tags,
        execution_count=cast(int | None, cell_node.get("execution_count")),
        magics=magic_strip.magics,
        cst_module=cst_module,
    )



def _cell_source(cell_node: NotebookNode) -> str:
    source_value = cell_node.get("source", "")
    if isinstance(source_value, str):
        return source_value
    if isinstance(source_value, list):
        return "".join(str(source_line) for source_line in source_value)
    return str(source_value)

from __future__ import annotations

import copy
from pathlib import Path
from typing import cast

import nbformat
from nbformat.notebooknode import NotebookNode

from nborder.parser.models import Notebook


def write_notebook(
    notebook: Notebook,
    path: Path | None = None,
    *,
    cell_order: tuple[int, ...] | None = None,
    clear_execution_counts: bool = False,
) -> None:
    """Write a notebook, preserving raw bytes when no mutation is requested.

    Args:
        notebook: Parsed notebook to write.
        path: Destination path. Defaults to the source path.
        cell_order: Optional source cell index order for mutation writes.
        clear_execution_counts: Whether to clear code-cell execution counts.
    """
    destination = path if path is not None else notebook.path
    if cell_order is None and not clear_execution_counts:
        destination.write_bytes(notebook.raw_bytes)
        return
    destination.write_bytes(
        serialize_notebook(
            notebook,
            cell_order=cell_order,
            clear_execution_counts=clear_execution_counts,
        )
    )


def serialize_notebook(
    notebook: Notebook,
    *,
    cell_order: tuple[int, ...] | None = None,
    clear_execution_counts: bool = False,
) -> bytes:
    """Serialize a possibly modified notebook with stable formatting controls.

    Args:
        notebook: Parsed notebook to serialize.
        cell_order: Optional source cell index order for the cells array.
        clear_execution_counts: Whether to clear code-cell execution counts.

    Returns:
        UTF-8 JSON bytes with the original trailing newline convention.
    """
    if cell_order is None and not clear_execution_counts:
        return notebook.raw_bytes

    notebook_node = _modified_node(notebook, cell_order, clear_execution_counts)
    serialized_text = cast(
        str,
        nbformat.writes(notebook_node, version=nbformat.NO_CONVERT, indent=1),  # type: ignore[no-untyped-call]
    )
    serialized_text = _preserve_trailing_newline(notebook.raw_bytes, serialized_text)
    return serialized_text.encode("utf-8")


def _modified_node(
    notebook: Notebook,
    cell_order: tuple[int, ...] | None,
    clear_execution_counts: bool,
) -> NotebookNode:
    notebook_node = copy.deepcopy(notebook.node)
    notebook_node.nbformat_minor = notebook.nbformat_minor
    if cell_order is not None:
        cells_by_index = {cell.index: notebook_node.cells[cell.index] for cell in notebook.cells}
        notebook_node.cells = [cells_by_index[cell_index] for cell_index in cell_order]
    if clear_execution_counts:
        for cell_node in notebook_node.cells:
            if cell_node.get("cell_type") == "code":
                cell_node.execution_count = None
    return notebook_node


def _preserve_trailing_newline(raw_bytes: bytes, serialized_text: str) -> str:
    original_had_newline = raw_bytes.endswith(b"\n")
    serialized_has_newline = serialized_text.endswith("\n")
    if original_had_newline and not serialized_has_newline:
        return f"{serialized_text}\n"
    if not original_had_newline and serialized_has_newline:
        return serialized_text.rstrip("\n")
    return serialized_text

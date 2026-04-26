from __future__ import annotations

from nborder.parser.models import Cell, Notebook
from nborder.rules.types import Diagnostic


def filter_suppressed_diagnostics(
    notebook: Notebook,
    diagnostics: tuple[Diagnostic, ...],
) -> tuple[Diagnostic, ...]:
    """Remove diagnostics suppressed by nborder noqa pragmas.

    Args:
        notebook: Parsed notebook containing diagnostic cells.
        diagnostics: Diagnostics emitted by rules.

    Returns:
        Diagnostics that are not suppressed by cell-local pragmas.
    """
    suppressions_by_cell = {
        cell.index: _suppressed_codes(cell) for cell in notebook.cells if _has_noqa(cell.source)
    }
    return tuple(
        diagnostic
        for diagnostic in diagnostics
        if not _is_suppressed(diagnostic, suppressions_by_cell.get(diagnostic.cell_index, ()))
    )


def _is_suppressed(diagnostic: Diagnostic, suppressed_codes: tuple[str, ...] | None) -> bool:
    if suppressed_codes is None:
        return False
    return "ALL" in suppressed_codes or diagnostic.code in suppressed_codes


def _suppressed_codes(cell: Cell) -> tuple[str, ...]:
    suppressed_codes: list[str] = []
    for source_line in cell.source.splitlines():
        marker_index = source_line.find("# nborder: noqa")
        if marker_index == -1:
            continue
        pragma = source_line[marker_index:].removeprefix("# nborder: noqa").strip()
        if not pragma:
            suppressed_codes.append("ALL")
            continue
        if not pragma.startswith(":"):
            continue
        codes = tuple(code.strip() for code in pragma.removeprefix(":").split(","))
        suppressed_codes.extend(code for code in codes if code)
    return tuple(suppressed_codes)


def _has_noqa(source: str) -> bool:
    return "# nborder: noqa" in source
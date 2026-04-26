from __future__ import annotations

from nborder.graph.models import DataflowGraph, SymbolUse
from nborder.parser.models import Notebook
from nborder.rules.types import Diagnostic, FixDescriptor
from nborder.rules.unresolved import ClassifiedUse


def check_use_before_assign(
    notebook: Notebook,
    graph: DataflowGraph,
    classified_uses: tuple[ClassifiedUse, ...],
) -> tuple[Diagnostic, ...]:
    """Emit NB201 diagnostics for uses defined later in source order.

    Args:
        notebook: Parsed notebook the graph came from.
        graph: Dataflow graph built for the notebook.
        classified_uses: Unresolved uses classified in a single pass.

    Returns:
        Diagnostics for fixable use-before-assign references.
    """
    diagnostics: list[Diagnostic] = []
    for classified_use in classified_uses:
        if classified_use.kind != "nb201" or classified_use.defining_cell is None:
            continue
        symbol_use = classified_use.symbol
        defining_cell = classified_use.defining_cell
        use_cell = symbol_use.cell_index
        diagnostics.append(
            Diagnostic(
                code="NB201",
                severity="error",
                message=(
                    f"Variable `{symbol_use.name}` used in cell {use_cell} is only defined "
                    f"in cell {defining_cell}. The notebook will fail on Restart-and-Run-All."
                ),
                notebook_path=notebook.path,
                cell_index=use_cell,
                cell_id=graph.cells[use_cell].cell_id,
                line=symbol_use.line,
                column=symbol_use.column,
                end_line=symbol_use.line,
                end_column=_end_column(symbol_use),
                fixable=True,
                fix_descriptor=FixDescriptor(
                    fix_id="reorder",
                    target_cells=[use_cell, defining_cell],
                    description=(
                        f"Reorder cells so cell {defining_cell} runs before cell {use_cell}"
                    ),
                ),
            )
        )
    return tuple(diagnostics)


def _end_column(symbol_use: SymbolUse) -> int:
    return symbol_use.column + len(symbol_use.name)

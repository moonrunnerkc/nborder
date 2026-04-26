from __future__ import annotations

from nborder.graph.models import DataflowGraph, SymbolUse
from nborder.parser.models import Notebook
from nborder.rules.types import Diagnostic
from nborder.rules.unresolved import ClassifiedUse


def check_restart_run_all(
    notebook: Notebook,
    graph: DataflowGraph,
    classified_uses: tuple[ClassifiedUse, ...],
    *,
    include_wildcard_info: bool = True,
) -> tuple[Diagnostic, ...]:
    """Emit NB102 diagnostics for names never defined in the notebook.

    Args:
        notebook: Parsed notebook the graph came from.
        graph: Dataflow graph built for the notebook.
        classified_uses: Unresolved uses classified in a single pass.
        include_wildcard_info: Whether to include info diagnostics for wildcard imports.

    Returns:
        Diagnostics for undefined names and optional wildcard-covered names.
    """
    diagnostics: list[Diagnostic] = []
    for classified_use in classified_uses:
        if classified_use.kind == "nb102":
            diagnostics.append(_undefined_name_diagnostic(notebook, graph, classified_use.symbol))
            continue
        if classified_use.kind == "wildcard" and include_wildcard_info:
            diagnostics.append(_wildcard_info_diagnostic(notebook, graph, classified_use))
    return tuple(diagnostics)


def _undefined_name_diagnostic(
    notebook: Notebook,
    graph: DataflowGraph,
    symbol_use: SymbolUse,
) -> Diagnostic:
    use_cell = symbol_use.cell_index
    return Diagnostic(
        code="NB102",
        severity="error",
        message=(
            f"Name `{symbol_use.name}` is used in cell {use_cell} "
            "but never defined in the notebook."
        ),
        notebook_path=notebook.path,
        cell_index=use_cell,
        cell_id=graph.cells[use_cell].cell_id,
        line=symbol_use.line,
        column=symbol_use.column,
        end_line=symbol_use.line,
        end_column=_end_column(symbol_use),
        fixable=False,
        fix_descriptor=None,
    )


def _wildcard_info_diagnostic(
    notebook: Notebook,
    graph: DataflowGraph,
    classified_use: ClassifiedUse,
) -> Diagnostic:
    symbol_use = classified_use.symbol
    use_cell = symbol_use.cell_index
    modules = ", ".join(classified_use.wildcard_modules)
    return Diagnostic(
        code="NB102",
        severity="info",
        message=(
            f"Possibly defined by wildcard import from {modules}: "
            f"Name `{symbol_use.name}` is used in cell {use_cell} "
            "but never defined in the notebook."
        ),
        notebook_path=notebook.path,
        cell_index=use_cell,
        cell_id=graph.cells[use_cell].cell_id,
        line=symbol_use.line,
        column=symbol_use.column,
        end_line=symbol_use.line,
        end_column=_end_column(symbol_use),
        fixable=False,
        fix_descriptor=None,
    )


def _end_column(symbol_use: SymbolUse) -> int:
    return symbol_use.column + len(symbol_use.name)

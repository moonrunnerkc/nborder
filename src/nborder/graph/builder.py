from __future__ import annotations

import builtins

from nborder.graph.extractor import extract_cell_symbols
from nborder.graph.models import (
    CellIndex,
    CellSymbols,
    DataflowGraph,
    Edge,
    SymbolDef,
    UnresolvedUse,
)
from nborder.parser.models import Notebook

_PARAMETER_TAGS = frozenset({"parameters", "injected-parameters"})
_SKIP_TAG = "nborder:skip"
_ALWAYS_DEFINED_NAMES = frozenset(name for name in dir(builtins) if not name.startswith("__"))


def build_dataflow_graph(notebook: Notebook) -> DataflowGraph:
    """Build the cross-cell symbol dependency graph for a notebook.

    Args:
        notebook: Parsed notebook to analyze.

    Returns:
        Dataflow graph with definitions, dependency edges, and unresolved uses.
    """
    symbols_by_cell = _extract_symbols(notebook)
    symbol_to_defining_cells = _build_symbol_index(symbols_by_cell)
    adjacency, unresolved_uses = _resolve_symbols(notebook, symbols_by_cell)
    wildcard_import_cells = frozenset(
        cell_index
        for cell_index, cell_symbols in symbols_by_cell.items()
        if cell_symbols.has_wildcard_import
    )
    return DataflowGraph(
        cells=notebook.cells,
        symbol_to_defining_cells=symbol_to_defining_cells,
        adjacency=adjacency,
        unresolved_uses=unresolved_uses,
        symbols_by_cell=symbols_by_cell,
        wildcard_import_cells=wildcard_import_cells,
    )


def _extract_symbols(notebook: Notebook) -> dict[CellIndex, CellSymbols]:
    symbols_by_cell: dict[CellIndex, CellSymbols] = {}
    for cell in notebook.cells:
        if _SKIP_TAG in cell.tags:
            symbols_by_cell[cell.index] = CellSymbols(cell.index, (), (), (), False)
            continue
        symbols_by_cell[cell.index] = extract_cell_symbols(cell)
    return symbols_by_cell


def _build_symbol_index(
    symbols_by_cell: dict[CellIndex, CellSymbols],
) -> dict[str, list[CellIndex]]:
    symbol_to_defining_cells: dict[str, list[CellIndex]] = {}
    for cell_index in sorted(symbols_by_cell):
        seen_cell_symbols: set[str] = set()
        for definition in symbols_by_cell[cell_index].definitions:
            if definition.name in seen_cell_symbols:
                continue
            symbol_to_defining_cells.setdefault(definition.name, []).append(cell_index)
            seen_cell_symbols.add(definition.name)
    return symbol_to_defining_cells


def _resolve_symbols(
    notebook: Notebook,
    symbols_by_cell: dict[CellIndex, CellSymbols],
) -> tuple[dict[CellIndex, list[Edge]], list[UnresolvedUse]]:
    adjacency: dict[CellIndex, list[Edge]] = {cell.index: [] for cell in notebook.cells}
    unresolved_uses: list[UnresolvedUse] = []
    parameter_definitions = _parameter_definitions(notebook, symbols_by_cell)
    prior_definitions = {
        symbol_name: definition.cell_index
        for symbol_name, definition in parameter_definitions.items()
    }

    for cell in notebook.cells:
        cell_symbols = symbols_by_cell[cell.index]
        for symbol_use in cell_symbols.uses:
            if symbol_use.name in _ALWAYS_DEFINED_NAMES:
                continue
            provider_cell = prior_definitions.get(symbol_use.name)
            if provider_cell == symbol_use.cell_index:
                provider_cell = None
            if provider_cell is None:
                unresolved_uses.append(
                    UnresolvedUse(symbol_use, has_wildcard_import=cell_symbols.has_wildcard_import)
                )
                continue
            adjacency[cell.index].append(Edge(cell.index, provider_cell, symbol_use.name))

        for definition in cell_symbols.definitions:
            prior_definitions[definition.name] = definition.cell_index

    return adjacency, unresolved_uses


def _parameter_definitions(
    notebook: Notebook,
    symbols_by_cell: dict[CellIndex, CellSymbols],
) -> dict[str, SymbolDef]:
    definitions: dict[str, SymbolDef] = {}
    for cell in notebook.cells:
        if not cell.tags.intersection(_PARAMETER_TAGS):
            continue
        for definition in symbols_by_cell[cell.index].definitions:
            definitions[definition.name] = definition
    return definitions


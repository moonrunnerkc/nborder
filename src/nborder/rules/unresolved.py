from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nborder.graph.models import CellIndex, DataflowGraph, ImportBinding, SymbolUse

ClassificationKind = Literal["nb201", "nb102", "wildcard"]


@dataclass(frozen=True, slots=True)
class ClassifiedUse:
    """An unresolved symbol use assigned to the rule that owns it."""

    kind: ClassificationKind
    symbol: SymbolUse
    defining_cell: CellIndex | None
    wildcard_modules: tuple[str, ...]


def classify_unresolved_uses(graph: DataflowGraph) -> tuple[ClassifiedUse, ...]:
    """Classify unresolved graph uses for NB201 and NB102.

    Args:
        graph: Dataflow graph built once for the notebook.

    Returns:
        Unresolved symbol uses partitioned by rule ownership.
    """
    classified_uses: list[ClassifiedUse] = []
    wildcard_modules_by_cell = _wildcard_modules_by_cell(graph)

    for unresolved_use in graph.unresolved_uses:
        symbol_use = unresolved_use.symbol
        wildcard_modules = wildcard_modules_by_cell.get(symbol_use.cell_index, ())
        later_definition_cell = _later_definition_cell(graph, symbol_use)
        if (
            unresolved_use.has_wildcard_import
            and wildcard_modules
            and later_definition_cell == symbol_use.cell_index
        ):
            classified_uses.append(ClassifiedUse("wildcard", symbol_use, None, wildcard_modules))
            continue
        if later_definition_cell is not None:
            classified_uses.append(
                ClassifiedUse("nb201", symbol_use, later_definition_cell, ())
            )
            continue

        if unresolved_use.has_wildcard_import and wildcard_modules:
            classified_uses.append(ClassifiedUse("wildcard", symbol_use, None, wildcard_modules))
            continue

        classified_uses.append(ClassifiedUse("nb102", symbol_use, None, ()))

    return tuple(classified_uses)


def _later_definition_cell(graph: DataflowGraph, symbol_use: SymbolUse) -> CellIndex | None:
    definition_cells = graph.symbol_to_defining_cells.get(symbol_use.name, [])
    candidate_cells = [
        cell_index for cell_index in definition_cells if cell_index >= symbol_use.cell_index
    ]
    if not candidate_cells:
        return None
    return min(candidate_cells)


def _wildcard_modules_by_cell(graph: DataflowGraph) -> dict[CellIndex, tuple[str, ...]]:
    modules_by_cell: dict[CellIndex, tuple[str, ...]] = {}
    for cell_index, cell_symbols in graph.symbols_by_cell.items():
        wildcard_imports = tuple(
            import_binding.module
            for import_binding in cell_symbols.imports
            if _is_wildcard_import(import_binding)
        )
        if wildcard_imports:
            modules_by_cell[cell_index] = wildcard_imports
    return modules_by_cell


def _is_wildcard_import(import_binding: ImportBinding) -> bool:
    return import_binding.kind == "wildcard"

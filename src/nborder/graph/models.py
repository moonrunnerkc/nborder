from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nborder.parser.models import Cell

CellIndex = int
SymbolDefKind = Literal["assignment", "function", "class", "import", "magic", "walrus"]
ImportKind = Literal["import", "from", "wildcard"]


@dataclass(frozen=True, slots=True)
class SymbolDef:
    """A symbol binding visible at notebook cell scope."""

    name: str
    cell_index: CellIndex
    line: int
    column: int
    kind: SymbolDefKind


@dataclass(frozen=True, slots=True)
class SymbolUse:
    """A symbol reference that may depend on a prior cell."""

    name: str
    cell_index: CellIndex
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class ImportBinding:
    """Import metadata collected during symbol extraction."""

    module: str
    imported_name: str | None
    bound_name: str | None
    cell_index: CellIndex
    line: int
    column: int
    kind: ImportKind


@dataclass(frozen=True, slots=True)
class CellSymbols:
    """Symbols extracted from one notebook cell."""

    cell_index: CellIndex
    definitions: tuple[SymbolDef, ...]
    uses: tuple[SymbolUse, ...]
    imports: tuple[ImportBinding, ...]
    has_wildcard_import: bool = False


@dataclass(frozen=True, slots=True)
class Edge:
    """A dependency from one cell to the cell that provides a symbol."""

    source_cell: CellIndex
    target_cell: CellIndex
    symbol: str


@dataclass(frozen=True, slots=True)
class UnresolvedUse:
    """A symbol reference that did not resolve to an earlier definition."""

    symbol: SymbolUse
    has_wildcard_import: bool = False


@dataclass(frozen=True, slots=True)
class DataflowGraph:
    """Cross-cell symbol dependency graph for a notebook."""

    cells: tuple[Cell, ...]
    symbol_to_defining_cells: dict[str, list[CellIndex]]
    adjacency: dict[CellIndex, list[Edge]]
    unresolved_uses: list[UnresolvedUse]
    symbols_by_cell: dict[CellIndex, CellSymbols]
    wildcard_import_cells: frozenset[CellIndex]

    def topological_sort(self) -> list[CellIndex] | None:
        """Return cell order with dependencies before dependents.

        Returns:
            Ordered cell indexes, or None when the graph contains a cycle.
        """
        cell_indexes = [cell.index for cell in self.cells]
        indegrees = dict.fromkeys(cell_indexes, 0)
        dependents_by_cell = {cell_index: set[CellIndex]() for cell_index in cell_indexes}

        for dependency_edges in self.adjacency.values():
            for dependency_edge in dependency_edges:
                dependent_cell = dependency_edge.source_cell
                provider_cell = dependency_edge.target_cell
                if dependent_cell == provider_cell:
                    continue
                if dependent_cell not in dependents_by_cell[provider_cell]:
                    dependents_by_cell[provider_cell].add(dependent_cell)
                    indegrees[dependent_cell] += 1

        ready_cells = sorted(cell_index for cell_index, degree in indegrees.items() if degree == 0)
        ordered_cells: list[CellIndex] = []
        while ready_cells:
            current_cell = ready_cells.pop(0)
            ordered_cells.append(current_cell)
            for dependent_cell in sorted(dependents_by_cell[current_cell]):
                indegrees[dependent_cell] -= 1
                if indegrees[dependent_cell] == 0:
                    ready_cells.append(dependent_cell)
                    ready_cells.sort()

        if len(ordered_cells) != len(cell_indexes):
            return None
        return ordered_cells

    def detect_cycle(self) -> list[CellIndex]:
        """Return cells participating in a dependency cycle.

        Returns:
            Cell indexes for one detected cycle, or an empty list for a DAG.
        """
        dependency_cells: dict[CellIndex, set[CellIndex]] = {
            cell.index: set() for cell in self.cells
        }
        for source_cell, dependency_edges in self.adjacency.items():
            dependency_cells.setdefault(source_cell, set())
            for dependency_edge in dependency_edges:
                if dependency_edge.target_cell != source_cell:
                    dependency_cells[source_cell].add(dependency_edge.target_cell)

        visited_cells: set[CellIndex] = set()
        active_cells: list[CellIndex] = []

        def visit_cell(cell_index: CellIndex) -> list[CellIndex]:
            if cell_index in active_cells:
                return active_cells[active_cells.index(cell_index) :]
            if cell_index in visited_cells:
                return []
            active_cells.append(cell_index)
            for dependency_cell in sorted(dependency_cells[cell_index]):
                cycle_cells = visit_cell(dependency_cell)
                if cycle_cells:
                    return cycle_cells
            active_cells.pop()
            visited_cells.add(cell_index)
            return []

        for cell in self.cells:
            cycle_cells = visit_cell(cell.index)
            if cycle_cells:
                return cycle_cells
        return []
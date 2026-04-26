from __future__ import annotations

from nborder.config import SeedConfig
from nborder.fix.models import FixOutcome
from nborder.fix.seeds import plan_seed_injection
from nborder.graph.models import DataflowGraph, Edge
from nborder.parser.models import Notebook
from nborder.rules.types import Diagnostic


def plan_fix_pipeline(
    notebook: Notebook,
    graph: DataflowGraph,
    diagnostics: tuple[Diagnostic, ...],
    enabled_fixes: frozenset[str],
    seed_config: SeedConfig | None = None,
) -> tuple[tuple[int, ...] | None, str | None, bool, tuple[FixOutcome, ...]]:
    """Plan enabled fix stages for a notebook.

    Args:
        notebook: Parsed notebook to fix.
        graph: Dataflow graph for the notebook.
        diagnostics: Diagnostics emitted before fixes.
        enabled_fixes: Fix identifiers enabled for this run.

    Returns:
        Cell order, seed cell source, execution-count clearing flag, and per-stage outcomes.
    """
    outcomes: list[FixOutcome] = []
    cell_order: tuple[int, ...] | None = None
    seed_cell_source: str | None = None
    clear_execution_counts = False
    effective_seed_config = seed_config if seed_config is not None else SeedConfig()

    if "reorder" in enabled_fixes:
        reorder_outcome = _plan_reorder(notebook, graph, diagnostics)
        outcomes.append(reorder_outcome)
        if reorder_outcome.status == "applied":
            cell_order = reorder_outcome.cell_order
            clear_execution_counts = True

    if "seeds" in enabled_fixes:
        seeds_outcome, seed_cell_source = plan_seed_injection(
            graph,
            diagnostics,
            effective_seed_config,
        )
        outcomes.append(seeds_outcome)

    if "clear-counts" in enabled_fixes:
        clear_counts_outcome = _plan_clear_counts(notebook, diagnostics, clear_execution_counts)
        outcomes.append(clear_counts_outcome)
        if clear_counts_outcome.status == "applied":
            clear_execution_counts = True

    return cell_order, seed_cell_source, clear_execution_counts, tuple(outcomes)


def _plan_reorder(
    notebook: Notebook,
    graph: DataflowGraph,
    diagnostics: tuple[Diagnostic, ...],
) -> FixOutcome:
    reorder_diagnostics = tuple(
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.fix_descriptor is not None and diagnostic.fix_descriptor.fix_id == "reorder"
    )
    if not reorder_diagnostics:
        return FixOutcome("reorder", "no-op", "no NB201 reorder diagnostics found", ())

    cycle_cells = graph.detect_cycle()
    dependency_edges = _dependency_edges(graph, reorder_diagnostics)
    if cycle_cells:
        cycle_edges = _cycle_edges(dependency_edges, tuple(cycle_cells))
        return FixOutcome(
            "reorder",
            "bailed",
            _cycle_message(cycle_edges),
            tuple(cycle_cells),
        )

    augmented_cycle_cells = _detect_cycle(notebook, dependency_edges)
    if augmented_cycle_cells:
        cycle_edges = _cycle_edges(dependency_edges, tuple(augmented_cycle_cells))
        return FixOutcome(
            "reorder",
            "bailed",
            _cycle_message(cycle_edges),
            tuple(augmented_cycle_cells),
        )

    topological_order = _topological_sort(notebook, dependency_edges)
    if topological_order is None:
        return FixOutcome(
            "reorder",
            "bailed",
            (
                "Cycle detected. Automatic reordering cannot resolve circular dependencies; "
                "restructure the notebook manually."
            ),
            (),
        )

    proposed_order = tuple(topological_order)
    current_order = tuple(cell.index for cell in notebook.cells)
    if proposed_order == current_order:
        return FixOutcome("reorder", "no-op", "notebook already satisfies dependency order", ())

    touched_cells = tuple(
        cell_index
        for position, cell_index in enumerate(proposed_order)
        if position != cell_index
    )
    return FixOutcome(
        "reorder",
        "applied",
        f"reordered {len(touched_cells)} cells and cleared execution counts",
        touched_cells,
        cell_order=proposed_order,
        clear_execution_counts=True,
    )


def _plan_clear_counts(
    notebook: Notebook,
    diagnostics: tuple[Diagnostic, ...],
    already_cleared: bool,
) -> FixOutcome:
    if already_cleared:
        return FixOutcome(
            "clear-counts",
            "no-op",
            "execution counts already cleared by reorder",
            (),
        )

    has_nb101 = any(diagnostic.code == "NB101" for diagnostic in diagnostics)
    if not has_nb101:
        return FixOutcome("clear-counts", "no-op", "no NB101 execution-count diagnostics found", ())

    affected_cells = tuple(
        cell.index
        for cell in notebook.cells
        if cell.kind == "code" and cell.execution_count is not None
    )
    if not affected_cells:
        return FixOutcome("clear-counts", "no-op", "execution counts are already clear", ())

    return FixOutcome(
        "clear-counts",
        "applied",
        f"applied to {len(affected_cells)} cells",
        affected_cells,
        clear_execution_counts=True,
    )


def _dependency_edges(
    graph: DataflowGraph,
    reorder_diagnostics: tuple[Diagnostic, ...],
) -> tuple[Edge, ...]:
    dependency_edges = [
        dependency_edge
        for graph_edges in graph.adjacency.values()
        for dependency_edge in graph_edges
        if dependency_edge.source_cell != dependency_edge.target_cell
    ]
    for diagnostic in reorder_diagnostics:
        fix_descriptor = diagnostic.fix_descriptor
        if fix_descriptor is None or len(fix_descriptor.target_cells) != 2:
            continue
        use_cell, defining_cell = fix_descriptor.target_cells
        dependency_edges.append(Edge(use_cell, defining_cell, _symbol_name(diagnostic.message)))
    return tuple(dependency_edges)


def _topological_sort(
    notebook: Notebook,
    dependency_edges: tuple[Edge, ...],
) -> tuple[int, ...] | None:
    cell_indexes = [cell.index for cell in notebook.cells]
    indegrees = dict.fromkeys(cell_indexes, 0)
    dependents_by_cell = {cell_index: set[int]() for cell_index in cell_indexes}

    for dependency_edge in dependency_edges:
        dependent_cell = dependency_edge.source_cell
        provider_cell = dependency_edge.target_cell
        if dependent_cell not in dependents_by_cell[provider_cell]:
            dependents_by_cell[provider_cell].add(dependent_cell)
            indegrees[dependent_cell] += 1

    ready_cells = sorted(cell_index for cell_index, degree in indegrees.items() if degree == 0)
    ordered_cells: list[int] = []
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
    return tuple(ordered_cells)


def _detect_cycle(notebook: Notebook, dependency_edges: tuple[Edge, ...]) -> tuple[int, ...]:
    dependency_cells: dict[int, set[int]] = {cell.index: set() for cell in notebook.cells}
    for dependency_edge in dependency_edges:
        dependency_cells[dependency_edge.source_cell].add(dependency_edge.target_cell)

    visited_cells: set[int] = set()
    active_cells: list[int] = []

    def visit_cell(cell_index: int) -> tuple[int, ...]:
        if cell_index in active_cells:
            return tuple(active_cells[active_cells.index(cell_index) :])
        if cell_index in visited_cells:
            return ()
        active_cells.append(cell_index)
        for dependency_cell in sorted(dependency_cells[cell_index]):
            cycle_cells = visit_cell(dependency_cell)
            if cycle_cells:
                return cycle_cells
        active_cells.pop()
        visited_cells.add(cell_index)
        return ()

    for cell in notebook.cells:
        cycle_cells = visit_cell(cell.index)
        if cycle_cells:
            return cycle_cells
    return ()


def _cycle_edges(
    dependency_edges: tuple[Edge, ...],
    cycle_cells: tuple[int, ...],
) -> tuple[Edge, ...]:
    cycle_cell_set = set(cycle_cells)
    ordered_edges: list[Edge] = []
    for source_cell in cycle_cells:
        candidate_edges = [
            dependency_edge
            for dependency_edge in dependency_edges
            if dependency_edge.source_cell == source_cell
            if dependency_edge.target_cell in cycle_cell_set
        ]
        if candidate_edges:
            ordered_edges.append(sorted(candidate_edges, key=lambda edge: edge.target_cell)[0])
    return tuple(ordered_edges)


def _symbol_name(message: str) -> str:
    marker = "`"
    if marker not in message:
        return "unknown"
    return message.split(marker, 2)[1]


def _cycle_message(cycle_edges: tuple[Edge, ...]) -> str:
    if not cycle_edges:
        return (
            "Cycle detected. Automatic reordering cannot resolve circular dependencies; "
            "restructure the notebook manually."
        )
    edge_sentences = " ".join(
        f"Cell {edge.target_cell} defines `{edge.symbol}` used by cell {edge.source_cell}."
        for edge in cycle_edges
    )
    return (
        f"Cycle detected. {edge_sentences} Automatic reordering cannot resolve "
        "circular dependencies; "
        "restructure the notebook manually."
    )

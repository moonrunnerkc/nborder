from __future__ import annotations

from nborder.config import SeedConfig
from nborder.fix.models import FixOutcome
from nborder.graph.models import DataflowGraph, ImportBinding
from nborder.parser.models import Notebook
from nborder.rules.seed_registry import SEED_PROBES
from nborder.rules.types import Diagnostic

_PARAMETER_TAGS = frozenset({"parameters", "injected-parameters"})

_CANONICAL_ALIAS: dict[str, str] = {
    "numpy": "np",
    "random": "random",
    "torch": "torch",
    "tensorflow": "tf",
}


def plan_seed_injection(
    notebook: Notebook,
    graph: DataflowGraph,
    diagnostics: tuple[Diagnostic, ...],
    seed_config: SeedConfig,
    cell_order: tuple[int, ...] | None = None,
) -> tuple[FixOutcome, str | None]:
    """Plan a single seed cell for fixable NB103 diagnostics.

    Args:
        notebook: Parsed notebook the graph came from.
        graph: Dataflow graph for the notebook being fixed.
        diagnostics: Diagnostics emitted before fixes.
        seed_config: Effective seed configuration.
        cell_order: Final cell order produced by an earlier reorder stage, if any.

    Returns:
        The seeds stage outcome and optional new seed cell source.
    """
    seed_libraries = _seed_libraries(diagnostics)
    if not seed_libraries:
        return FixOutcome("seeds", "no-op", "no NB103 seed diagnostics found", ()), None

    seed_insert_index = len(_cells_before_seed_insertion(notebook, cell_order))
    seed_lines = _seed_lines(seed_libraries, notebook, graph, seed_config.value, cell_order)
    if not seed_lines:
        return FixOutcome("seeds", "no-op", "no fixable NB103 seed diagnostics found", ()), None

    description = _seed_description(seed_libraries, seed_insert_index)
    first_affected_cell = min(
        cell_index
        for diagnostic in diagnostics
        if diagnostic.fix_descriptor is not None
        if diagnostic.fix_descriptor.fix_id == "seeds"
        for cell_index in diagnostic.fix_descriptor.target_cells
    )
    return (
        FixOutcome("seeds", "applied", description, (first_affected_cell,)),
        "\n".join(seed_lines) + "\n",
    )


def _seed_libraries(diagnostics: tuple[Diagnostic, ...]) -> tuple[str, ...]:
    libraries: list[str] = []
    for probe in SEED_PROBES:
        for diagnostic in diagnostics:
            fix_descriptor = diagnostic.fix_descriptor
            if fix_descriptor is None or fix_descriptor.fix_id != "seeds":
                continue
            if fix_descriptor.description == probe.library and probe.injection_template is not None:
                libraries.append(probe.library)
                break
    return tuple(libraries)


def _seed_lines(
    libraries: tuple[str, ...],
    notebook: Notebook,
    graph: DataflowGraph,
    seed_value: int,
    cell_order: tuple[int, ...] | None,
) -> tuple[str, ...]:
    pre_seed_cells = _cells_before_seed_insertion(notebook, cell_order)
    other_cells = tuple(
        cell.index for cell in notebook.cells if cell.index not in pre_seed_cells
    )
    seed_lines: list[str] = []
    for library in libraries:
        canonical_alias = _CANONICAL_ALIAS[library]
        alias, already_imported = _resolve_library_alias(
            library,
            canonical_alias,
            graph,
            pre_seed_cells,
            other_cells,
        )
        if not already_imported:
            seed_lines.append(_import_line(library, alias))
        seed_lines.extend(_seed_call_lines(library, alias, seed_value, graph))
    return tuple(seed_lines)


def _cells_before_seed_insertion(
    notebook: Notebook,
    cell_order: tuple[int, ...] | None,
) -> tuple[int, ...]:
    ordered_indexes = (
        cell_order if cell_order is not None else tuple(cell.index for cell in notebook.cells)
    )
    last_parameters_position = -1
    for position, cell_index in enumerate(ordered_indexes):
        if notebook.cells[cell_index].tags.intersection(_PARAMETER_TAGS):
            last_parameters_position = position
    if last_parameters_position < 0:
        return ()
    return tuple(ordered_indexes[: last_parameters_position + 1])


def _resolve_library_alias(
    library: str,
    canonical_alias: str,
    graph: DataflowGraph,
    pre_seed_cells: tuple[int, ...],
    other_cells: tuple[int, ...],
) -> tuple[str, bool]:
    pre_seed_alias = _find_module_alias(library, graph, pre_seed_cells)
    if pre_seed_alias is not None:
        return pre_seed_alias, True
    later_alias = _find_module_alias(library, graph, other_cells)
    if later_alias is not None:
        return later_alias, False
    return canonical_alias, False


def _find_module_alias(
    library: str,
    graph: DataflowGraph,
    cell_indexes: tuple[int, ...],
) -> str | None:
    for cell_index in cell_indexes:
        for import_binding in graph.symbols_by_cell[cell_index].imports:
            alias = _alias_for_library(import_binding, library)
            if alias is not None:
                return alias
    return None


def _alias_for_library(import_binding: ImportBinding, library: str) -> str | None:
    if import_binding.kind != "import":
        return None
    if import_binding.module != library:
        return None
    if import_binding.bound_name is None:
        return None
    return import_binding.bound_name


def _import_line(library: str, alias: str) -> str:
    if alias == library:
        return f"import {library}"
    return f"import {library} as {alias}"


def _seed_call_lines(
    library: str,
    alias: str,
    seed_value: int,
    graph: DataflowGraph,
) -> tuple[str, ...]:
    if library == "numpy":
        return (f"rng = {alias}.random.default_rng({seed_value})",)
    if library == "random":
        return (f"{alias}.seed({seed_value})",)
    if library == "torch":
        torch_lines = [f"{alias}.manual_seed({seed_value})"]
        if _torch_cuda_imported(graph):
            torch_lines.append(f"{alias}.cuda.manual_seed_all({seed_value})")
        return tuple(torch_lines)
    if library == "tensorflow":
        return (f"{alias}.random.set_seed({seed_value})",)
    return ()


def _torch_cuda_imported(graph: DataflowGraph) -> bool:
    return any(
        import_binding.module == "torch.cuda" or import_binding.module.startswith("torch.cuda.")
        for cell_symbols in graph.symbols_by_cell.values()
        for import_binding in cell_symbols.imports
    )


def _seed_description(libraries: tuple[str, ...], seed_insert_index: int) -> str:
    library_names = ", ".join(libraries)
    seed_word = "seed" if len(libraries) == 1 else "seeds"
    return f"{library_names} {seed_word} injected at cell {seed_insert_index}"

from __future__ import annotations

from nborder.config import SeedConfig
from nborder.fix.models import FixOutcome
from nborder.graph.models import DataflowGraph
from nborder.rules.seed_registry import SEED_PROBES
from nborder.rules.types import Diagnostic


def plan_seed_injection(
    graph: DataflowGraph,
    diagnostics: tuple[Diagnostic, ...],
    seed_config: SeedConfig,
) -> tuple[FixOutcome, str | None]:
    """Plan a single seed cell for fixable NB103 diagnostics.

    Args:
        graph: Dataflow graph for the notebook being fixed.
        diagnostics: Diagnostics emitted before fixes.
        seed_config: Effective seed configuration.

    Returns:
        The seeds stage outcome and optional new seed cell source.
    """
    seed_libraries = _seed_libraries(diagnostics)
    if not seed_libraries:
        return FixOutcome("seeds", "no-op", "no NB103 seed diagnostics found", ()), None

    seed_lines = _seed_lines(seed_libraries, graph, seed_config.value)
    if not seed_lines:
        return FixOutcome("seeds", "no-op", "no fixable NB103 seed diagnostics found", ()), None

    description = _seed_description(seed_libraries)
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
    graph: DataflowGraph,
    seed_value: int,
) -> tuple[str, ...]:
    seed_lines: list[str] = []
    for library in libraries:
        if library == "numpy":
            seed_lines.append("import numpy as np")
            seed_lines.append(f"rng = np.random.default_rng({seed_value})")
            continue
        if library == "random":
            seed_lines.append("import random")
            seed_lines.append(f"random.seed({seed_value})")
            continue
        if library == "torch":
            seed_lines.append("import torch")
            seed_lines.append(f"torch.manual_seed({seed_value})")
            if _torch_cuda_imported(graph):
                seed_lines.append(f"torch.cuda.manual_seed_all({seed_value})")
            continue
        if library == "tensorflow":
            seed_lines.append("import tensorflow as tf")
            seed_lines.append(f"tf.random.set_seed({seed_value})")
    return tuple(seed_lines)


def _torch_cuda_imported(graph: DataflowGraph) -> bool:
    return any(
        import_binding.module == "torch.cuda" or import_binding.module.startswith("torch.cuda.")
        for cell_symbols in graph.symbols_by_cell.values()
        for import_binding in cell_symbols.imports
    )


def _seed_description(libraries: tuple[str, ...]) -> str:
    library_names = ", ".join(libraries)
    seed_word = "seed" if len(libraries) == 1 else "seeds"
    return f"{library_names} {seed_word} injected at cell 1"

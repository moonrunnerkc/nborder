"""Public diagnostic-production surface, separate from CLI argument plumbing."""

from __future__ import annotations

from nborder.config import Config
from nborder.graph.builder import build_dataflow_graph
from nborder.parser.models import Notebook
from nborder.rules.nb101 import check_non_monotonic_execution_counts
from nborder.rules.nb102 import check_restart_run_all
from nborder.rules.nb103 import check_unseeded_stochastic_calls
from nborder.rules.nb201 import check_use_before_assign
from nborder.rules.suppression import filter_suppressed_diagnostics
from nborder.rules.types import Diagnostic, Severity
from nborder.rules.unresolved import classify_unresolved_uses


def check_notebook(
    notebook: Notebook,
    config: Config,
    *,
    include_levels: frozenset[Severity],
) -> tuple[Diagnostic, ...]:
    """Return diagnostics for one parsed notebook."""
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)
    include_info = "info" in include_levels
    diagnostics = [
        *check_non_monotonic_execution_counts(notebook),
        *check_use_before_assign(notebook, graph, classified_uses),
        *check_unseeded_stochastic_calls(notebook, graph, config.seeds),
        *check_restart_run_all(
            notebook,
            graph,
            classified_uses,
            include_wildcard_info=include_info,
        ),
    ]
    return filter_suppressed_diagnostics(notebook, tuple(diagnostics))


def filter_visible_diagnostics(
    diagnostics: tuple[Diagnostic, ...],
    *,
    include_levels: frozenset[Severity],
) -> tuple[Diagnostic, ...]:
    """Return diagnostics whose severity is included in the active level set."""
    return tuple(diagnostic for diagnostic in diagnostics if diagnostic.severity in include_levels)


def filter_selected_diagnostics(
    diagnostics: tuple[Diagnostic, ...],
    *,
    selected_codes: frozenset[str] | None,
) -> tuple[Diagnostic, ...]:
    """Return diagnostics whose rule code is in the active selection set.

    Args:
        diagnostics: Diagnostics produced for a notebook.
        selected_codes: Rule codes to keep; ``None`` disables selection.

    Returns:
        Diagnostics gated by ``--select``; unchanged when no selection is active.
    """
    if selected_codes is None:
        return diagnostics
    return tuple(diagnostic for diagnostic in diagnostics if diagnostic.code in selected_codes)
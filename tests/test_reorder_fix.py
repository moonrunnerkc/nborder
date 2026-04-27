from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from nborder.fix import pipeline as fix_pipeline
from nborder.fix.pipeline import plan_fix_pipeline
from nborder.graph.builder import build_dataflow_graph
from nborder.graph.models import Edge
from nborder.parser.reader import read_notebook
from nborder.rules.nb101 import check_non_monotonic_execution_counts
from nborder.rules.nb201 import check_use_before_assign
from nborder.rules.types import Diagnostic, FixDescriptor
from nborder.rules.unresolved import classify_unresolved_uses

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def test_reorder_fix_plans_dependency_first_order_for_dag() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "phase3" / "reorder_dag.ipynb")
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)
    diagnostics = check_use_before_assign(notebook, graph, classified_uses)

    cell_order, seed_cell_source, clear_counts, outcomes = plan_fix_pipeline(
        notebook,
        graph,
        diagnostics,
        frozenset({"reorder"}),
    )

    assert cell_order == (1, 0, 2)
    assert seed_cell_source is None
    assert clear_counts is True
    assert outcomes[0].status == "applied"


def test_reorder_fix_bails_on_cycle_with_edge_details() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "phase3" / "reorder_cycle.ipynb")
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)
    diagnostics = check_use_before_assign(notebook, graph, classified_uses)

    cell_order, seed_cell_source, clear_counts, outcomes = plan_fix_pipeline(
        notebook,
        graph,
        diagnostics,
        frozenset({"reorder"}),
    )

    assert cell_order is None
    assert seed_cell_source is None
    assert clear_counts is False
    assert outcomes[0].status == "bailed"
    assert "Cell 1 defines `y` used by cell 0." in outcomes[0].description
    assert "Cell 0 defines `x` used by cell 1." in outcomes[0].description


def test_clear_counts_runs_after_reorder_bails() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "phase3" / "reorder_cycle.ipynb")
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)
    diagnostics = (
        *check_non_monotonic_execution_counts(notebook),
        *check_use_before_assign(notebook, graph, classified_uses),
    )

    cell_order, seed_cell_source, clear_counts, outcomes = plan_fix_pipeline(
        notebook,
        graph,
        diagnostics,
        frozenset({"reorder", "clear-counts"}),
    )

    assert cell_order is None
    assert seed_cell_source is None
    assert clear_counts is True
    assert [(outcome.fix_id, outcome.status) for outcome in outcomes] == [
        ("reorder", "bailed"),
        ("clear-counts", "applied"),
    ]


def test_clear_counts_is_no_op_after_reorder_applies() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "phase3" / "reorder_dag.ipynb")
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)
    diagnostics = (
        *check_non_monotonic_execution_counts(notebook),
        *check_use_before_assign(notebook, graph, classified_uses),
    )

    cell_order, seed_cell_source, clear_counts, outcomes = plan_fix_pipeline(
        notebook,
        graph,
        diagnostics,
        frozenset({"reorder", "clear-counts"}),
    )

    assert cell_order == (1, 0, 2)
    assert seed_cell_source is None
    assert clear_counts is True
    assert [(outcome.fix_id, outcome.status) for outcome in outcomes] == [
        ("reorder", "applied"),
        ("clear-counts", "no-op"),
    ]


def test_reorder_is_no_op_when_no_reorder_diagnostics_exist() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "roundtrip" / "v45_clean.ipynb")
    graph = build_dataflow_graph(notebook)

    cell_order, seed_cell_source, clear_counts, outcomes = plan_fix_pipeline(
        notebook,
        graph,
        (),
        frozenset({"reorder"}),
    )

    assert cell_order is None
    assert seed_cell_source is None
    assert clear_counts is False
    assert outcomes[0].description == "no NB201 reorder diagnostics found"


def test_clear_counts_is_no_op_without_nb101_diagnostics() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "roundtrip" / "v45_clean.ipynb")
    graph = build_dataflow_graph(notebook)

    cell_order, seed_cell_source, clear_counts, outcomes = plan_fix_pipeline(
        notebook,
        graph,
        (),
        frozenset({"clear-counts"}),
    )

    assert cell_order is None
    assert seed_cell_source is None
    assert clear_counts is False
    assert outcomes[0].description == "no NB101 execution-count diagnostics found"


def test_clear_counts_is_no_op_when_nb101_cells_are_already_clear() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "roundtrip" / "v45_clean.ipynb")
    notebook = replace(
        notebook,
        cells=tuple(replace(cell, execution_count=None) for cell in notebook.cells),
    )
    diagnostic = Diagnostic(
        code="NB101",
        severity="error",
        message="execution counts are out of order",
        notebook_path=notebook.path,
        cell_index=0,
        cell_id=notebook.cells[0].cell_id,
        line=1,
        column=1,
        end_line=1,
        end_column=1,
    )

    outcome = fix_pipeline._plan_clear_counts(notebook, (diagnostic,), already_cleared=False)

    assert outcome.status == "no-op"
    assert outcome.description == "execution counts are already clear"


def test_pipeline_helpers_handle_unusual_reorder_edges() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "roundtrip" / "v45_clean.ipynb")
    graph = build_dataflow_graph(notebook)
    invalid_descriptor = FixDescriptor("reorder", [0], "missing provider")
    diagnostic = Diagnostic(
        code="NB201",
        severity="error",
        message="Variable name missing markers",
        notebook_path=notebook.path,
        cell_index=0,
        cell_id=notebook.cells[0].cell_id,
        line=1,
        column=1,
        end_line=1,
        end_column=1,
        fixable=True,
        fix_descriptor=invalid_descriptor,
    )

    assert fix_pipeline._dependency_edges(graph, (diagnostic,)) == ()
    assert fix_pipeline._symbol_name("Variable name missing markers") == "unknown"
    assert fix_pipeline._cycle_message(()) == (
        "Cycle detected. Automatic reordering cannot resolve circular dependencies; "
        "restructure the notebook manually."
    )
    assert fix_pipeline._topological_sort(notebook, (Edge(0, 1, "x"), Edge(1, 0, "y"))) is None

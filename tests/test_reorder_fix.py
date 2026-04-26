from __future__ import annotations

from pathlib import Path

from nborder.fix.pipeline import plan_fix_pipeline
from nborder.graph.builder import build_dataflow_graph
from nborder.parser.reader import read_notebook
from nborder.rules.nb101 import check_non_monotonic_execution_counts
from nborder.rules.nb201 import check_use_before_assign
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

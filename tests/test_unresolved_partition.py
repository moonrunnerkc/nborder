from __future__ import annotations

from pathlib import Path

from nborder.graph.builder import build_dataflow_graph
from nborder.parser.reader import read_notebook
from nborder.rules.unresolved import classify_unresolved_uses

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def test_partition_classifies_later_definition_as_nb201() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "NB201" / "use_df_later_def.ipynb")
    graph = build_dataflow_graph(notebook)

    classified_uses = classify_unresolved_uses(graph)
    classified_summary = [
        (classified.kind, classified.symbol.name, classified.defining_cell)
        for classified in classified_uses
    ]

    assert classified_summary == [("nb201", "df", 1)]


def test_partition_classifies_never_defined_name_as_nb102() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "NB102" / "undefined_name.ipynb")
    graph = build_dataflow_graph(notebook)

    classified_uses = classify_unresolved_uses(graph)

    assert [(classified.kind, classified.symbol.name) for classified in classified_uses] == [
        ("nb102", "some_undefined_name")
    ]


def test_partition_keeps_mixed_uses_separate() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "phase3" / "mixed.ipynb")
    graph = build_dataflow_graph(notebook)

    classified_uses = classify_unresolved_uses(graph)

    assert [(classified.kind, classified.symbol.name) for classified in classified_uses] == [
        ("nb201", "df"),
        ("nb102", "totally_undefined"),
    ]


def test_partition_classifies_wildcard_cell_as_wildcard() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "phase3" / "wildcard.ipynb")
    graph = build_dataflow_graph(notebook)

    classified_uses = classify_unresolved_uses(graph)

    assert classified_uses[0].kind == "wildcard"
    assert classified_uses[0].symbol.name == "array"
    assert classified_uses[0].wildcard_modules == ("numpy",)

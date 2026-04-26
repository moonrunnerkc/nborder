from __future__ import annotations

import libcst as cst

from nborder.graph.cst_helpers import dotted_name, param_default_values, target_names


def test_target_names_extracts_starred_target_name() -> None:
    assignment = cst.ensure_type(
        cst.parse_statement("first, *rest = values"),
        cst.SimpleStatementLine,
    )
    assign_node = cst.ensure_type(assignment.body[0], cst.Assign)
    tuple_target = assign_node.targets[0].target

    assert target_names(tuple_target) == ("first", "rest")
    assert target_names(cst.StarredElement(cst.Name("tail"))) == ("tail",)


def test_dotted_name_returns_empty_string_for_unsupported_node() -> None:
    assert dotted_name(cst.Integer("1")) == ""


def test_param_default_values_yields_regular_and_keyword_only_defaults() -> None:
    function_node = cst.ensure_type(
        cst.parse_statement("def run(first=default_first, *, second=default_second): pass"),
        cst.FunctionDef,
    )

    defaults = tuple(
        cst.ensure_type(default_value, cst.Name).value
        for default_value in param_default_values(function_node.params)
    )

    assert defaults == ("default_first", "default_second")

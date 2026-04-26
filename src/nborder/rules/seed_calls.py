from __future__ import annotations

from dataclasses import dataclass

import libcst as cst
from libcst.metadata import CodePosition, MetadataWrapper, PositionProvider

from nborder.graph.cst_helpers import dotted_name
from nborder.parser.models import Cell


@dataclass(frozen=True, slots=True)
class CallEvent:
    """A function call in a notebook cell."""

    cell_index: int
    name: str
    line: int
    column: int
    arguments: tuple[str, ...]
    keyword_values: dict[str, str]


def call_events(cell: Cell) -> tuple[CallEvent, ...]:
    """Return function call events from one notebook cell.

    Args:
        cell: Parsed notebook cell to inspect.

    Returns:
        Function calls in source order.
    """
    if cell.kind != "code" or cell.cst_module is None:
        return ()
    wrapper = MetadataWrapper(cell.cst_module, unsafe_skip_copy=True)
    visitor = _CallEventVisitor(cell.index)
    wrapper.visit(visitor)
    return tuple(sorted(visitor.events, key=lambda event: (event.line, event.column)))


class _CallEventVisitor(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, cell_index: int) -> None:
        self.cell_index = cell_index
        self.events: list[CallEvent] = []

    def visit_Call(self, cst_node: cst.Call) -> bool:
        call_name = dotted_name(cst_node.func)
        if not call_name:
            return True
        position = self._position(cst_node.func)
        self.events.append(
            CallEvent(
                self.cell_index,
                call_name,
                position.line,
                position.column + 1,
                tuple(
                    _argument_value(argument)
                    for argument in cst_node.args
                    if argument.keyword is None
                ),
                {
                    argument.keyword.value: _argument_value(argument)
                    for argument in cst_node.args
                    if argument.keyword is not None
                },
            )
        )
        return True

    def _position(self, cst_node: cst.CSTNode) -> CodePosition:
        return self.get_metadata(PositionProvider, cst_node).start


def _argument_value(argument: cst.Arg) -> str:
    if isinstance(argument.value, cst.Name):
        return argument.value.value
    if isinstance(argument.value, cst.Integer):
        return argument.value.value
    if isinstance(argument.value, cst.SimpleString):
        return argument.value.value
    return "expr"
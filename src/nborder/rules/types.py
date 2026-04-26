from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True, slots=True)
class FixDescriptor:
    """Auto-fix metadata attached to a diagnostic."""

    fix_id: str
    target_cells: list[int]
    description: str


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Finding emitted by an nborder rule."""

    code: str
    severity: Severity
    message: str
    notebook_path: Path
    cell_index: int
    cell_id: str | None
    line: int
    column: int
    end_line: int
    end_column: int
    fixable: bool = False
    fix_descriptor: FixDescriptor | None = None

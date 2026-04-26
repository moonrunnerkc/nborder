from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import libcst as cst
from nbformat.notebooknode import NotebookNode

CellKind = Literal["code", "markdown", "raw"]
MagicKind = Literal["line", "cell", "shell", "shell_assignment", "help", "auto_call"]


@dataclass(frozen=True, slots=True)
class Magic:
    """IPython syntax stripped before Python parsing."""

    kind: MagicKind
    name: str
    source: str
    line_number: int
    binding: str | None = None


@dataclass(frozen=True, slots=True)
class Cell:
    """Notebook cell with original source and parsed Python state."""

    index: int
    cell_id: str | None
    kind: CellKind
    source: str
    stripped_source: str
    tags: frozenset[str]
    execution_count: int | None
    magics: tuple[Magic, ...]
    cst_module: cst.Module | None


@dataclass(frozen=True, slots=True)
class Notebook:
    """Parsed notebook plus the original bytes needed for stable writing."""

    path: Path
    raw_bytes: bytes
    node: NotebookNode
    nbformat_minor: int
    cells: tuple[Cell, ...]

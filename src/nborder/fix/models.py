from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FixStatus = Literal["applied", "bailed", "no-op"]


@dataclass(frozen=True, slots=True)
class FixOutcome:
    """Outcome emitted by one fix pipeline stage."""

    fix_id: str
    status: FixStatus
    description: str
    affected_cells: tuple[int, ...]
    cell_order: tuple[int, ...] | None = None
    clear_execution_counts: bool = False

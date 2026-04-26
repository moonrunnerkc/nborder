from __future__ import annotations

from abc import ABC, abstractmethod

from nborder.fix.models import FixOutcome
from nborder.rules.types import Diagnostic


class Reporter(ABC):
    """Base class for diagnostic output reporters."""

    @abstractmethod
    def report(
        self,
        diagnostics: tuple[Diagnostic, ...],
        fix_outcomes: tuple[FixOutcome, ...] | None = None,
    ) -> str:
        """Format diagnostics and optional fix outcomes into a single string.

        Args:
            diagnostics: Findings emitted for the run.
            fix_outcomes: Pipeline outcomes when --fix was requested, otherwise None.

        Returns:
            Reporter-specific output, ready to write to stdout.
        """

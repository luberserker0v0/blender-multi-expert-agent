"""Decision engine abstractions."""

from typing import Protocol

from ai_3d_modeling_agent.schemas.actions import Action
from ai_3d_modeling_agent.schemas.gap_report import GapReport


class DecisionEngine(Protocol):
    def decide(self, gap_report: GapReport) -> Action:
        """Choose the next action for the current gap report."""

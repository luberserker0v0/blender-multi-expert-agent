"""Multi-expert pipeline package.

Sub-packages:
    artifacts — typed dataclass stubs for each pipeline phase.
    core — core data models and types for the multi-expert pipeline.
"""

from __future__ import annotations

from . import artifacts
from . import core

__all__ = [
    "artifacts",
    "core",
]

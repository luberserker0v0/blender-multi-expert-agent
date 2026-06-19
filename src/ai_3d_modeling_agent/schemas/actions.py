"""Action schema models for the MVP."""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Action:
    action_type: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""

"""Shared local model runtime abstractions."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Protocol, Tuple


class LocalModelHandle(Protocol):
    """Opaque handle returned by a local model backend."""


class LocalModelBackend(Protocol):
    def load(self, config: "LocalModelConfig") -> LocalModelHandle:
        """Load a local model according to the given config."""


@dataclass
class LocalModelConfig:
    model_path: Path
    runtime: str
    allowed_suffixes: Tuple[str, ...]
    n_threads: Optional[int] = None
    extra_options: Dict[str, Any] = field(default_factory=dict)


class LocalModelLoader:
    def __init__(self, backend: LocalModelBackend) -> None:
        self.backend = backend

    def load(self, config: LocalModelConfig) -> LocalModelHandle:
        self._validate_path(config.model_path, config.allowed_suffixes)
        return self.backend.load(config)

    @staticmethod
    def _validate_path(model_path: Path, allowed_suffixes: Iterable[str]) -> None:
        suffixes = tuple(suffix.lower() for suffix in allowed_suffixes)
        if model_path.suffix.lower() not in suffixes:
            raise ValueError(
                f"Model path must point to one of the supported formats: {', '.join(suffixes)}"
            )
        if not model_path.exists():
            raise FileNotFoundError(f"Local model not found: {model_path}")

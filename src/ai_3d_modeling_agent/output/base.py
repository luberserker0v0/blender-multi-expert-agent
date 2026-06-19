"""Streaming output abstractions for user-facing agent messages."""

import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, TextIO


class AgentOutput(Protocol):
    def emit(self, text: str) -> None:
        """Emit one user-visible message chunk."""


class NullAgentOutput:
    def emit(self, text: str) -> None:
        """Ignore output."""


class ConsoleStreamingOutput:
    def __init__(
        self,
        stream: Optional[TextIO] = None,
        chunk_size: int = 12,
        delay_seconds: float = 0.0,
    ) -> None:
        self.stream = stream or sys.stdout
        self.chunk_size = max(1, chunk_size)
        self.delay_seconds = max(0.0, delay_seconds)

    def emit(self, text: str) -> None:
        for index in range(0, len(text), self.chunk_size):
            chunk = text[index : index + self.chunk_size]
            self.stream.write(chunk)
            self.stream.flush()
            if self.delay_seconds > 0:
                time.sleep(self.delay_seconds)
        self.stream.write("\n")
        self.stream.flush()


@dataclass
class MemoryStreamingOutput:
    messages: List[str] = field(default_factory=list)

    def emit(self, text: str) -> None:
        self.messages.append(text)

"""Background flush manager — periodically flushes BufferedWriter instances."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .buffered_writer import BufferedWriter


class FlushManager:
    """Background daemon thread that periodically flushes registered buffers.

    Parameters
    ----------
    interval:
        Seconds between flush cycles.
    """

    def __init__(self, interval: float = 5.0) -> None:
        self._buffers: list[BufferedWriter] = []
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def register(self, buffer: BufferedWriter) -> None:
        """Register a buffer to be flushed periodically."""
        self._buffers.append(buffer)

    def start(self) -> None:
        """Start the background flush thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the background thread and perform a final flush."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 1)
        for buf in self._buffers:
            buf.flush()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._interval)
            for buf in self._buffers:
                buf.maybe_flush()

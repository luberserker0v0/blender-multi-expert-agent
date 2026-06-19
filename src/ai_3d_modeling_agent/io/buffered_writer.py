"""通用 buffered file writer — 記憶體 buffer + 批次 flush。

支援三種 flush 策略：
- on_event: 每 N 個 events flush 一次（flush_threshold）
- on_interval: 每 N 秒 flush 一次（flush_interval）
- manual: 只在呼叫 flush() 時寫入
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


class BufferedWriter:
    """Buffered JSONL writer — append to memory, flush to disk in batches.

    Thread-safe.  Each record is serialized as a single JSON line.

    Parameters
    ----------
    file_path:
        Path to the JSONL file.  Created on first flush (parent dirs too).
    flush_interval:
        Seconds between automatic flushes via ``maybe_flush()``.
        ``None`` disables interval-based flushing.
    flush_threshold:
        Flush automatically when the buffer reaches this many records.
    """

    def __init__(
        self,
        file_path: str | Path,
        *,
        flush_interval: float | None = 5.0,
        flush_threshold: int = 50,
    ) -> None:
        self._path = Path(file_path)
        self._buffer: list[str] = []
        self._lock = threading.Lock()
        self._flush_interval = flush_interval
        self._flush_threshold = flush_threshold
        self._last_flush = time.monotonic()
        self._pending = False

    def append(self, record: dict[str, Any]) -> None:
        """Append a JSON record to the in-memory buffer.

        If the buffer reaches ``flush_threshold``, it is flushed to disk
        automatically.
        """
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self._buffer.append(line)
            self._pending = True
            if len(self._buffer) >= self._flush_threshold:
                self._flush_locked()

    def flush(self) -> None:
        """Force-flush all buffered records to disk."""
        with self._lock:
            self._flush_locked()

    def maybe_flush(self) -> None:
        """Flush if the interval has elapsed.

        Intended to be called from a background thread or timer.
        Does nothing if no records are pending.
        """
        with self._lock:
            if not self._pending:
                return
            now = time.monotonic()
            if (
                self._flush_interval is not None
                and (now - self._last_flush) >= self._flush_interval
            ):
                self._flush_locked()

    def _flush_locked(self) -> None:
        """Write buffer to file.  Caller must hold ``self._lock``."""
        if not self._buffer:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            for line in self._buffer:
                f.write(line + "\n")
        self._buffer.clear()
        self._last_flush = time.monotonic()
        self._pending = False

    @property
    def path(self) -> Path:
        """Return the target file path."""
        return self._path

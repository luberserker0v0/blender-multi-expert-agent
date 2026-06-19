"""Unit tests for BufferedWriter and FlushManager."""

import json
import tempfile
import threading
import time
from pathlib import Path

from ai_3d_modeling_agent.io.buffered_writer import BufferedWriter
from ai_3d_modeling_agent.io.flush_manager import FlushManager


class TestBufferedWriter:
    """Tests for BufferedWriter."""

    def test_append_and_flush(self):
        """Append records and flush to disk."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "test.jsonl"
            writer = BufferedWriter(path, flush_interval=60.0, flush_threshold=100)

            writer.append({"event": "start", "phase": "design"})
            writer.append({"event": "spoke", "phase": "design", "speaker": "designer"})
            writer.flush()

            assert path.exists()
            lines = path.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 2

            e1 = json.loads(lines[0])
            assert e1["event"] == "start"
            assert e1["phase"] == "design"

            e2 = json.loads(lines[1])
            assert e2["event"] == "spoke"
            assert e2["speaker"] == "designer"

    def test_auto_flush_on_threshold(self):
        """Flush automatically when threshold is reached."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "test.jsonl"
            writer = BufferedWriter(path, flush_interval=60.0, flush_threshold=3)

            writer.append({"n": 1})
            writer.append({"n": 2})
            assert not path.exists()  # not yet flushed

            writer.append({"n": 3})  # triggers flush
            assert path.exists()

            lines = path.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 3

    def test_maybe_flush_on_interval(self):
        """maybe_flush writes when interval has elapsed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "test.jsonl"
            writer = BufferedWriter(path, flush_interval=0.1, flush_threshold=100)

            writer.append({"n": 1})
            assert not path.exists()

            time.sleep(0.15)
            writer.maybe_flush()
            assert path.exists()

    def test_append_is_thread_safe(self):
        """Concurrent appends do not lose data."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "test.jsonl"
            writer = BufferedWriter(path, flush_interval=60.0, flush_threshold=1000)

            def writer_worker(n):
                for i in range(50):
                    writer.append({"thread": n, "i": i})

            threads = [threading.Thread(target=writer_worker, args=(i,)) for i in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            writer.flush()

            lines = path.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 200  # 4 threads * 50 records

    def test_empty_flush_is_noop(self):
        """Flush with no records does not create file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "test.jsonl"
            writer = BufferedWriter(path)
            writer.flush()
            assert not path.exists()

    def test_creates_parent_directories(self):
        """Flush creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sub" / "dir" / "test.jsonl"
            writer = BufferedWriter(path)
            writer.append({"n": 1})
            writer.flush()
            assert path.exists()


class TestFlushManager:
    """Tests for FlushManager."""

    def test_periodic_flush(self):
        """FlushManager periodically flushes registered buffers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "test.jsonl"
            writer = BufferedWriter(path, flush_interval=0.1, flush_threshold=100)

            mgr = FlushManager(interval=0.1)
            mgr.register(writer)

            writer.append({"n": 1})
            assert not path.exists()

            mgr.start()
            time.sleep(0.25)
            mgr.stop()

            assert path.exists()
            lines = path.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 1

    def test_stop_flushes_remaining(self):
        """FlushManager.stop() flushes any remaining buffered records."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "test.jsonl"
            writer = BufferedWriter(path, flush_interval=60.0, flush_threshold=100)

            mgr = FlushManager(interval=60.0)
            mgr.register(writer)

            writer.append({"n": 1})
            assert not path.exists()

            mgr.start()
            mgr.stop()

            assert path.exists()
            lines = path.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 1

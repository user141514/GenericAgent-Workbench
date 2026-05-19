"""Tests for AgentOutputChannel and QueueOutputChannel."""

import queue
import time
import pytest
from core.protocol.channel import AgentOutputChannel, QueueOutputChannel
from core.protocol.events import AgentOutputEvent


class TestQueueOutputChannel:
    """Tests for the local queue-backed channel."""

    def test_put_and_get(self):
        ch = QueueOutputChannel()
        ev = AgentOutputEvent(kind="chunk", text="hello")
        ch.put(ev)
        result = ch.get(timeout=1.0)
        assert result is not None
        assert result.text == "hello"

    def test_get_nowait_empty(self):
        ch = QueueOutputChannel()
        assert ch.get_nowait() is None

    def test_get_nowait_has_item(self):
        ch = QueueOutputChannel()
        ch.put(AgentOutputEvent(kind="chunk", text="x"))
        result = ch.get_nowait()
        assert result is not None
        assert result.text == "x"

    def test_get_timeout_returns_none(self):
        ch = QueueOutputChannel()
        result = ch.get(timeout=0.05)
        assert result is None

    def test_multiple_events_in_order(self):
        ch = QueueOutputChannel()
        events = [
            AgentOutputEvent(kind="chunk", text="a"),
            AgentOutputEvent(kind="chunk", text="b"),
            AgentOutputEvent(kind="done", text="c"),
        ]
        for ev in events:
            ch.put(ev)
        results = [ch.get(timeout=1.0) for _ in range(3)]
        assert [r.text for r in results] == ["a", "b", "c"]

    def test_close_prevents_put(self):
        ch = QueueOutputChannel()
        ch.close()
        ch.put(AgentOutputEvent(kind="chunk", text="should not appear"))
        # Sentinel from close() is first; then nothing else
        assert ch.get_nowait() is None  # the sentinel
        assert ch.get_nowait() is None  # no more items

    def test_close_returns_none_on_get(self):
        ch = QueueOutputChannel()
        ch.close()
        assert ch.get() is None

    def test_closed_property(self):
        ch = QueueOutputChannel()
        assert not ch.closed
        ch.close()
        assert ch.closed

    def test_len_reflects_queue_size(self):
        ch = QueueOutputChannel()
        assert len(ch) == 0
        ch.put(AgentOutputEvent(kind="chunk", text="x"))
        assert len(ch) == 1

    def test_iter_yields_until_terminal(self):
        ch = QueueOutputChannel()
        ch.put(AgentOutputEvent(kind="chunk", text="a"))
        ch.put(AgentOutputEvent(kind="chunk", text="b"))
        ch.put(AgentOutputEvent(kind="done", text="c"))
        results = list(ch)
        assert len(results) == 3
        assert results[-1].kind == "done"


class TestFromLegacyQueue:
    """Tests for wrapping legacy raw-dict queues."""

    def test_bridge_converts_legacy_items(self):
        legacy_q = queue.Queue()
        legacy_q.put({"next": "chunk1", "source": "user", "turn": 1})
        legacy_q.put({"next": "chunk2", "source": "user", "turn": 1})
        legacy_q.put({"done": "final", "source": "user", "turn": 1})

        ch = QueueOutputChannel.from_legacy_queue(legacy_q)
        # Give the bridge thread time to process all items
        time.sleep(0.5)

        results = []
        deadline = time.time() + 2.0
        while time.time() < deadline:
            ev = ch.get(timeout=0.3)
            if ev is None:
                if ch.closed:
                    break
                continue
            results.append(ev)
            if ev.is_terminal():
                break

        assert len(results) >= 2  # at minimum chunk + done
        assert results[-1].kind == "done"
        assert results[-1].text == "final"

    def test_bridge_stops_on_terminal(self):
        legacy_q = queue.Queue()
        legacy_q.put({"done": "immediate", "source": "user", "turn": 1})

        ch = QueueOutputChannel.from_legacy_queue(legacy_q)
        time.sleep(0.5)

        ev = ch.get(timeout=1.0)
        assert ev is not None, "should have received the done event"
        assert ev.kind == "done"
        assert ch.closed

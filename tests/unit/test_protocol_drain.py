"""Tests for AgentOutputDrainer — shared queue-draining utility."""

import queue
import time
import pytest
from core.protocol.channel import QueueOutputChannel
from core.protocol.drain import AgentOutputDrainer
from core.protocol.events import AgentOutputEvent


class TestAgentOutputDrainer:
    """Tests for the drainer with typed events."""

    @staticmethod
    def _make_channel():
        return QueueOutputChannel()

    def test_collect_chunks(self):
        ch = self._make_channel()
        ch.put(AgentOutputEvent(kind="chunk", text="hello"))
        ch.put(AgentOutputEvent(kind="chunk", text="hello world"))
        ch.put(AgentOutputEvent(kind="done", text="hello world final"))

        d = AgentOutputDrainer(ch)
        latest = d.collect(max_items=10)
        assert latest is not None
        assert d.is_done
        assert d.full_text == "hello world final"

    def test_collect_tracks_turn(self):
        ch = self._make_channel()
        ch.put(AgentOutputEvent(kind="chunk", text="a", turn=3))
        d = AgentOutputDrainer(ch)
        d.collect()
        assert d.current_turn == 3

    def test_collect_stopped(self):
        ch = self._make_channel()
        ch.put(AgentOutputEvent(kind="chunk", text="partial"))
        ch.put(AgentOutputEvent(kind="stopped", text="partial"))
        d = AgentOutputDrainer(ch)
        d.collect()
        assert d.is_stopped
        assert not d.is_done
        assert d.is_terminal

    def test_collect_error(self):
        ch = self._make_channel()
        ch.put(AgentOutputEvent(kind="error", error="boom", text="partial"))
        d = AgentOutputDrainer(ch)
        d.collect()
        assert d.is_error
        assert d.error_msg == "boom"
        assert d.is_terminal

    def test_collect_metadata_preserved(self):
        ch = self._make_channel()
        ch.put(AgentOutputEvent(kind="done", text="done",
                                metadata={"shortcut_type": "read_shortcut"}))
        d = AgentOutputDrainer(ch)
        d.collect()
        assert d.metadata["shortcut_type"] == "read_shortcut"

    def test_collect_returns_none_when_empty(self):
        ch = self._make_channel()
        d = AgentOutputDrainer(ch)
        assert d.collect() is None

    def test_collect_respects_max_items(self):
        ch = self._make_channel()
        for i in range(5):
            ch.put(AgentOutputEvent(kind="chunk", text=f"chunk{i}"))
        d = AgentOutputDrainer(ch)
        d.collect(max_items=3)
        # Should only have drained 3 items; 2 remain
        assert len(d.recent_events) == 3

    def test_drain_all_blocks_until_terminal(self):
        ch = self._make_channel()
        ch.put(AgentOutputEvent(kind="chunk", text="a"))
        ch.put(AgentOutputEvent(kind="chunk", text="b"))
        ch.put(AgentOutputEvent(kind="done", text="c"))
        d = AgentOutputDrainer(ch)
        events = d.drain_all()
        assert len(events) == 3
        assert events[-1].kind == "done"


class TestFromLegacyQueueDrainer:
    """Backward compatibility: drainer from raw queue.Queue."""

    def test_drain_legacy_queue(self):
        legacy_q = queue.Queue()
        legacy_q.put({"next": "chunk1", "turn": 1})
        legacy_q.put({"next": "chunk2", "turn": 1})
        legacy_q.put({"done": "final", "turn": 1})

        d = AgentOutputDrainer.from_legacy_queue(legacy_q)
        time.sleep(0.5)  # allow bridge thread to process

        d.collect(max_items=10)
        assert d.is_done
        assert d.full_text == "final"


class TestFormatter:
    """Tests for AgentOutputFormatter classes."""

    def test_null_formatter_emits_nothing(self):
        from core.protocol.formatter import NullFormatter
        f = NullFormatter()
        assert f.format_turn_start(1) == ""
        assert f.format_turn_end(1) == ""
        assert f.format_tool_call("read", {"path": "/x"}) == ""
        assert f.format_tool_result("read", "ok") == ""
        assert f.format_error("boom") == ""

    def test_verbose_formatter_emits_markers(self):
        from core.protocol.formatter import VerboseFormatter
        f = VerboseFormatter()
        result = f.format_turn_start(3)
        assert "Turn 3" in result
        assert "LLM Running" in result

    def test_verbose_tool_call_formatting(self):
        from core.protocol.formatter import VerboseFormatter
        f = VerboseFormatter()
        result = f.format_tool_call("file_read", {"path": "/tmp/x.txt"})
        assert "file_read" in result
        assert "/tmp/x.txt" in result

    def test_verbose_formatter_outputs_full_json(self):
        from core.protocol.formatter import VerboseFormatter
        f = VerboseFormatter()
        args = {"path": "/tmp/test.txt", "content": "hello"}
        result = f.format_tool_call("file_read", args)
        assert "file_read" in result
        assert "/tmp/test.txt" in result
        assert "````" in result  # markdown code block wrapper

    def test_compact_formatter_truncates_args(self):
        from core.protocol.formatter import CompactFormatter
        f = CompactFormatter()
        args = {f"key{i}": f"value{i}" for i in range(10)}
        result = f.format_tool_call("big_tool", args)
        assert "..." in result  # compact formatter truncates


class TestNavigationDetection:
    """web_execute_js navigation short-circuit detection."""

    def test_detect_location_href_assignment(self):
        from core.ga import _is_navigation_script
        assert _is_navigation_script("window.location.href = 'https://bing.com'")
        assert _is_navigation_script("location.href = 'https://google.com'")

    def test_detect_location_assign(self):
        from core.ga import _is_navigation_script
        assert _is_navigation_script("window.location.assign('https://x.com')")

    def test_detect_location_replace(self):
        from core.ga import _is_navigation_script
        assert _is_navigation_script("window.location.replace('https://y.com')")

    def test_detect_location_bare_assignment(self):
        from core.ga import _is_navigation_script
        assert _is_navigation_script("location = 'https://z.com'")

    def test_normal_js_not_detected_as_navigation(self):
        from core.ga import _is_navigation_script
        assert not _is_navigation_script("document.title")
        assert not _is_navigation_script("document.querySelector('.btn').click()")
        assert not _is_navigation_script("window.scrollTo(0, 100)")
        assert not _is_navigation_script("console.log(location.href)")  # read, not write


class TestDrainerFilters:
    """Phase 6a: stop_requested + task_id filtering."""

    @staticmethod
    def _make_channel():
        from core.protocol.channel import QueueOutputChannel
        return QueueOutputChannel()

    def test_stop_requested_skips_chunks(self):
        """When stop_requested=True, collect() skips chunk events."""
        from core.protocol.drain import AgentOutputDrainer
        from core.protocol.events import AgentOutputEvent

        ch = self._make_channel()
        ch.put(AgentOutputEvent(kind="chunk", text="should be skipped"))
        ch.put(AgentOutputEvent(kind="chunk", text="also skipped"))
        ch.put(AgentOutputEvent(kind="stopped", text="stopped text"))

        d = AgentOutputDrainer(ch, stop_requested=True)
        d.collect(max_items=10)
        # Stopped event IS terminal, so it gets through
        assert d.is_stopped
        assert d.full_text == "stopped text"

    def test_stop_requested_accepts_done(self):
        """When stop_requested=True, done events are still processed."""
        from core.protocol.drain import AgentOutputDrainer
        from core.protocol.events import AgentOutputEvent

        ch = self._make_channel()
        ch.put(AgentOutputEvent(kind="chunk", text="skip"))
        ch.put(AgentOutputEvent(kind="done", text="final"))

        d = AgentOutputDrainer(ch, stop_requested=True)
        d.collect(max_items=10)
        assert d.is_done
        assert d.full_text == "final"

    def test_stop_requested_false_behaves_normally(self):
        """When stop_requested=False, all events are processed."""
        from core.protocol.drain import AgentOutputDrainer
        from core.protocol.events import AgentOutputEvent

        ch = self._make_channel()
        ch.put(AgentOutputEvent(kind="chunk", text="hello"))
        ch.put(AgentOutputEvent(kind="done", text="hello"))

        d = AgentOutputDrainer(ch, stop_requested=False)
        d.collect(max_items=10)
        assert d.full_text == "hello"

    def test_task_id_filters_out_non_matching(self):
        """Events with different task_id are skipped."""
        from core.protocol.drain import AgentOutputDrainer
        from core.protocol.events import AgentOutputEvent

        ch = self._make_channel()
        ch.put(AgentOutputEvent(kind="chunk", text="old", task_id="old_task"))
        ch.put(AgentOutputEvent(kind="chunk", text="new", task_id="new_task"))
        ch.put(AgentOutputEvent(kind="done", text="final", task_id="new_task"))

        d = AgentOutputDrainer(ch, task_id="new_task")
        d.collect(max_items=10)
        assert d.full_text == "final"
        # The "old" chunk was filtered, so full_text was never set to "old"

    def test_task_id_empty_accepts_all(self):
        """When task_id is empty, all events pass through."""
        from core.protocol.drain import AgentOutputDrainer
        from core.protocol.events import AgentOutputEvent

        ch = self._make_channel()
        ch.put(AgentOutputEvent(kind="chunk", text="any", task_id="anything"))
        ch.put(AgentOutputEvent(kind="done", text="done"))

        d = AgentOutputDrainer(ch, task_id="")
        d.collect(max_items=10)
        assert d.is_done

    def test_stop_requested_setter_updates_filter(self):
        """stop_requested property can be toggled between collect() calls."""
        from core.protocol.drain import AgentOutputDrainer
        from core.protocol.events import AgentOutputEvent

        ch = self._make_channel()
        ch.put(AgentOutputEvent(kind="chunk", text="before stop"))

        d = AgentOutputDrainer(ch, stop_requested=False)
        d.collect(max_items=10)
        assert d.full_text == "before stop"

        # Now set stop_requested
        d.stop_requested = True
        ch.put(AgentOutputEvent(kind="chunk", text="after stop"))
        ch.put(AgentOutputEvent(kind="done", text="final"))

        d.collect(max_items=10)
        # The chunk "after stop" skipped; only done applied
        assert d.full_text == "final"


class TestFormatterBackwardCompat:
    """Regression: formatter=None + verbose must not crash (agent_loop.py:373)."""

    @staticmethod
    def _init_formatter(formatter, verbose):
        if formatter is None:
            if verbose:
                from core.protocol.formatter import VerboseFormatter
                return VerboseFormatter()
            else:
                from core.protocol.formatter import CompactFormatter
                return CompactFormatter()
        return formatter

    def test_formatter_none_verbose_true(self):
        f = self._init_formatter(None, verbose=True)
        assert f is not None
        assert f.is_verbose()

    def test_formatter_none_verbose_false(self):
        f = self._init_formatter(None, verbose=False)
        assert f is not None
        assert not f.is_verbose()

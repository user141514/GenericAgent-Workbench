"""Unit tests for core.hook_bus (HookBus, HookEvent, HookResult)."""

from __future__ import annotations

import pytest
from core.hook_bus import HookBus, HookEvent, HookResult, VALID_EVENTS


class TestHookBusConstruction:
    def test_singleton_is_stable(self):
        a = HookBus.global_instance()
        b = HookBus.global_instance()
        assert a is b

    def test_reset_global(self):
        HookBus.reset_global_instance()
        a = HookBus.global_instance()
        HookBus.reset_global_instance()
        b = HookBus.global_instance()
        assert a is not b

    def test_all_valid_events_pre_populated(self):
        bus = HookBus()
        for evt in VALID_EVENTS:
            assert bus.handler_count(evt) == 0


class TestRegistration:
    def test_on_adds_handler(self):
        bus = HookBus()
        def h(e): pass
        bus.on("tool.pre_execute", h)
        assert bus.handler_count("tool.pre_execute") == 1

    def test_on_unknown_event_works(self):
        bus = HookBus()
        def h(e): pass
        bus.on("my.custom.event", h)
        assert bus.handler_count("my.custom.event") == 1

    def test_priority_ordering(self):
        bus = HookBus()
        order: list[int] = []
        bus.on("turn.start", lambda e: order.append(1) or None, priority=1)
        bus.on("turn.start", lambda e: order.append(3) or None, priority=3)
        bus.on("turn.start", lambda e: order.append(2) or None, priority=2)
        bus.emit("turn.start")
        assert order == [3, 2, 1]  # highest priority first

    def test_remove_handler(self):
        bus = HookBus()
        def h(e): return None
        bus.on("turn.end", h)
        assert bus.handler_count("turn.end") == 1
        assert bus.remove("turn.end", h) is True
        assert bus.handler_count("turn.end") == 0
        assert bus.remove("turn.end", h) is False


class TestEmission:
    def test_emit_no_handlers_returns_empty(self):
        bus = HookBus()
        results = bus.emit("session.start")
        assert results == []

    def test_emit_calls_handler(self):
        bus = HookBus()
        called: list[HookEvent] = []
        def h(e):
            called.append(e)
            return None
        bus.on("turn.start", h)
        results = bus.emit("turn.start", {"turn": 5})
        assert len(called) == 1
        assert called[0].name == "turn.start"
        assert called[0].payload == {"turn": 5}
        assert results == []

    def test_emit_returns_results(self):
        bus = HookBus()
        def h(e):
            return HookResult(additional_context={"key": "val"})
        bus.on("turn.start", h)
        results = bus.emit("turn.start")
        assert len(results) == 1
        assert results[0].additional_context == {"key": "val"}

    def test_emit_payload_is_copied(self):
        bus = HookBus()
        seen_keys: set = set()
        def h(e):
            nonlocal seen_keys
            seen_keys = set(e.payload.keys())
            e.payload["mutated"] = True  # mutates the COPY, not original
        bus.on("turn.start", h)
        original = {"key": "original"}
        bus.emit("turn.start", original)
        assert original == {"key": "original"}  # original unchanged
        assert "key" in seen_keys  # handler received the key from original


class TestToolGlobMatching:
    def test_glob_matches(self):
        bus = HookBus()
        called: list[str] = []
        bus.on("tool.pre_execute", lambda e: called.append(e.payload["tool_name"]) or None,
               tool_glob="file_*")
        bus.emit("tool.pre_execute", {"tool_name": "file_read"})
        bus.emit("tool.pre_execute", {"tool_name": "file_write"})
        bus.emit("tool.pre_execute", {"tool_name": "code_run"})
        assert called == ["file_read", "file_write"]

    def test_glob_no_match_skips(self):
        bus = HookBus()
        called: list[str] = []
        bus.on("tool.post_execute", lambda e: called.append("hit") or None,
               tool_glob="web_*")
        bus.emit("tool.post_execute", {"tool_name": "file_read"})
        assert called == []

    def test_no_glob_matches_all(self):
        bus = HookBus()
        count = [0]
        bus.on("tool.pre_execute", lambda e: count.__setitem__(0, count[0] + 1) or None)
        bus.emit("tool.pre_execute", {"tool_name": "file_read"})
        bus.emit("tool.pre_execute", {"tool_name": "code_run"})
        bus.emit("tool.pre_execute", {"tool_name": "web_search"})
        assert count[0] == 3


class TestBlock:
    def test_block_stops_remaining_handlers(self):
        bus = HookBus()
        later_called = False
        bus.on("tool.pre_execute",
               lambda e: HookResult(block=True, block_reason="forbidden"), priority=10)
        bus.on("tool.pre_execute",
               lambda e: setattr(sys.modules[__name__], 'later_called', True) or None)
        results = bus.emit("tool.pre_execute", {"tool_name": "shell"})
        assert len(results) == 1
        assert results[0].block is True
        assert results[0].block_reason == "forbidden"

    def test_emit_blocked_convenience(self):
        bus = HookBus()
        bus.on("tool.pre_execute",
               lambda e: HookResult(block=True, block_reason="nope"))
        blocked, reason = bus.emit_blocked("tool.pre_execute", {"tool_name": "rm"})
        assert blocked is True
        assert reason == "nope"

    def test_emit_blocked_not_blocked(self):
        bus = HookBus()
        blocked, reason = bus.emit_blocked("session.start")
        assert blocked is False
        assert reason == ""


class TestErrorHandling:
    def test_handler_exception_is_caught(self):
        bus = HookBus()
        later_called = [False]
        def bad(e):
            raise RuntimeError("boom")
        def good(e):
            later_called[0] = True
        bus.on("turn.start", bad)
        bus.on("turn.start", good)
        results = bus.emit("turn.start")
        assert later_called[0] is True  # good handler still ran
        assert len(results) == 0  # bad handler returned None (exception)

    def test_handler_exception_with_block_before(self):
        bus = HookBus()
        def block_first(e):
            return HookResult(block=True)
        def will_raise(e):
            raise RuntimeError("should not run")
        bus.on("tool.pre_execute", block_first, priority=10)
        bus.on("tool.pre_execute", will_raise, priority=5)
        results = bus.emit("tool.pre_execute", {"tool_name": "rm"})
        assert len(results) == 1  # only the block result
        assert results[0].block is True


class TestIntrospection:
    def test_handler_count_per_event(self):
        bus = HookBus()
        bus.on("session.start", lambda e: None)
        bus.on("session.start", lambda e: None)
        bus.on("session.end", lambda e: None)
        assert bus.handler_count("session.start") == 2
        assert bus.handler_count("session.end") == 1
        assert bus.handler_count("turn.start") == 0

    def test_handler_count_total(self):
        bus = HookBus()
        bus.on("session.start", lambda e: None)
        bus.on("turn.start", lambda e: None)
        assert bus.handler_count() == 2

    def test_clear_event(self):
        bus = HookBus()
        bus.on("turn.start", lambda e: None)
        bus.clear("turn.start")
        assert bus.handler_count("turn.start") == 0

    def test_clear_all(self):
        bus = HookBus()
        bus.on("session.start", lambda e: None)
        bus.on("turn.end", lambda e: None)
        bus.clear()
        assert bus.handler_count() == 0

    def test_list_registrations(self):
        bus = HookBus()
        bus.on("turn.start", lambda e: None, tool_glob="file_*",
               priority=5, source="test")
        regs = bus.list_registrations()
        turn_regs = [r for r in regs if r["event"] == "turn.start"]
        assert len(turn_regs) == 1
        assert turn_regs[0]["tool_glob"] == "file_*"
        assert turn_regs[0]["priority"] == 5


class TestHookResult:
    def test_defaults(self):
        r = HookResult()
        assert r.additional_context is None
        assert r.block is False
        assert r.modify is None
        assert r.block_reason == ""


class TestSourceTagging:
    def test_source_is_passed_to_event(self):
        bus = HookBus()
        seen_source = [""]
        bus.on("session.start", lambda e: (
            seen_source.__setitem__(0, e.source) or None
        ))
        bus.emit("session.start", source="agentmain.py")
        assert seen_source[0] == "agentmain.py"

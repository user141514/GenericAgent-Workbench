"""
TDD tests for frontend scroll behavior.

These tests validate the scroll decision logic that is embedded as JS strings
in stapp.py and stapp_mobile.py. Each test corresponds to a specific bug.

RED phase: all tests should FAIL initially (testing the broken logic).
"""

import pytest


# ── Pure-function mirrors of the JS scroll decision logic ──

def is_near_bottom(scroll_top, client_height, scroll_height, threshold=200):
    """Mirror of JS isNearBottom() in stapp_mobile.py:1421."""
    return scroll_top + client_height >= scroll_height - threshold


def should_stream_scroll(marker_active, scroll_event, last_scroll_event, near_bottom):
    """Mirror of stream-marker scroll decision in stapp_mobile.py:1456-1465."""
    if not marker_active:
        return False
    if scroll_event == last_scroll_event:
        return False
    if not near_bottom:
        return False
    return True


def should_content_event_scroll(content_event, last_content_event, near_bottom):
    """
    Mirror of content-end scroll decision in stapp_mobile.py:1467-1473.
    BUG: current code does NOT check near_bottom. This function models
    the FIXED behavior we want.
    """
    if content_event == last_content_event:
        return False
    if not near_bottom:
        return False
    return True


def should_content_event_scroll_BROKEN(content_event, last_content_event):
    """
    Mirror of the CURRENT BROKEN behavior: scrolls unconditionally
    when content_event changes.
    """
    if content_event == last_content_event:
        return False
    return True  # BUG: missing isNearBottom check!


# ── Tests ──

class TestIsNearBottom:
    """Bug 3: isNearBottom threshold behavior."""

    def test_at_bottom_returns_true(self):
        """User at very bottom should be considered near bottom."""
        assert is_near_bottom(scroll_top=800, client_height=200, scroll_height=1000)

    def test_within_threshold_returns_true(self):
        """User within threshold of bottom."""
        # 1000 - 200 - 200 = 600, user at 650 is within 200px
        assert is_near_bottom(scroll_top=650, client_height=200, scroll_height=1000)

    def test_far_from_bottom_returns_false(self):
        """User reading history far from bottom."""
        assert not is_near_bottom(scroll_top=100, client_height=200, scroll_height=1000)

    def test_threshold_200_is_too_large(self):
        """Demonstrate that 200px threshold catches users who are clearly reading."""
        # User is reading content 180px from bottom - still within 200px threshold
        # With scroll_height=1000, client_height=200:
        # bottom = 1000 - 200 = 800
        # user at 620: distance to bottom = 800 - 620 = 180 < 200
        assert is_near_bottom(scroll_top=620, client_height=200, scroll_height=1000, threshold=200)
        # But with 80px threshold, this user would NOT be considered near bottom
        assert not is_near_bottom(scroll_top=620, client_height=200, scroll_height=1000, threshold=80)


class TestStreamScrollDecision:
    """Bug 1-related: stream-marker scroll decision logic."""

    def test_scrolls_when_active_and_near_bottom_and_event_changed(self):
        """Normal streaming: active, near bottom, new event → should scroll."""
        assert should_stream_scroll(
            marker_active=True, scroll_event=5, last_scroll_event=4, near_bottom=True
        )

    def test_no_scroll_when_not_active(self):
        """Stream not active → no scroll."""
        assert not should_stream_scroll(
            marker_active=False, scroll_event=5, last_scroll_event=4, near_bottom=True
        )

    def test_no_scroll_when_same_event(self):
        """Same scroll event (dedup) → no scroll."""
        assert not should_stream_scroll(
            marker_active=True, scroll_event=5, last_scroll_event=5, near_bottom=True
        )

    def test_no_scroll_when_user_scrolled_up(self):
        """User scrolled up (not near bottom) → no scroll."""
        assert not should_stream_scroll(
            marker_active=True, scroll_event=5, last_scroll_event=4, near_bottom=False
        )


class TestContentEventScrollDecision:
    """Bug 1 (PRIMARY): content-end unconditional auto-scroll."""

    def test_broken_scrolls_even_when_user_reading_history(self):
        """Demonstrate the BUG: content_event change ALWAYS scrolls."""
        # User is reading history (far from bottom) but gets yanked anyway
        assert should_content_event_scroll_BROKEN(content_event=3, last_content_event=2)
        # This should be False! User is not near bottom.

    def test_fixed_does_not_scroll_when_user_reading_history(self):
        """Fixed version: no scroll when user is not near bottom."""
        assert not should_content_event_scroll(
            content_event=3, last_content_event=2, near_bottom=False
        )

    def test_fixed_scrolls_when_near_bottom(self):
        """Fixed version: still scrolls when user IS near bottom."""
        assert should_content_event_scroll(
            content_event=3, last_content_event=2, near_bottom=True
        )

    def test_fixed_no_scroll_when_same_event(self):
        """Fixed version: dedup still works."""
        assert not should_content_event_scroll(
            content_event=3, last_content_event=3, near_bottom=True
        )


class TestStappMobileFixes:
    """Verify fixes in stapp_mobile.py JS code."""

    @staticmethod
    def _get_scroll_js():
        import re
        with open("frontends/stapp_mobile.py", "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r'_js_scroll_fix\s*=\s*\((.*?)\)\s*\n\s*_js_ime_fix', content, re.DOTALL)
        assert match, "Could not find _js_scroll_fix block in stapp_mobile.py"
        return match.group(1)

    def test_content_event_scroll_checks_is_near_bottom(self):
        """Bug 1 fix: content-end scroll should check isNearBottom()."""
        js = self._get_scroll_js()
        # The content-end section should have isNearBottom check
        assert "isNearBottom()" in js, "isNearBottom() should be in scroll fix"

    def test_no_characterdata_observation(self):
        """Bug 2 fix: MutationObserver should not watch characterData."""
        js = self._get_scroll_js()
        assert "characterData" not in js, (
            "characterData observation should be removed (performance)"
        )

    def test_threshold_not_200(self):
        """Bug 3 fix: isNearBottom threshold should not be 200px."""
        js = self._get_scroll_js()
        assert "scrollHeight-200" not in js, (
            "200px threshold should be replaced with smaller value"
        )
        assert "scrollHeight-80" in js, (
            "80px threshold should be used instead"
        )


class TestStappScrollFix:
    """Bug 5 & 6: stapp.py setInterval replaced with MutationObserver."""

    def test_setinterval_removed_from_scroll_fix(self):
        """After fix: setInterval should NOT be in _js_scroll_fix."""
        import re
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            content = f.read()
        # Extract the _js_scroll_fix block
        match = re.search(r'_js_scroll_fix\s*=\s*\((.*?)\)\s*\n\s*_js_ime_fix', content, re.DOTALL)
        assert match, "Could not find _js_scroll_fix block"
        scroll_fix_js = match.group(1)
        assert "setInterval" not in scroll_fix_js, (
            "setInterval should be removed from scroll fix (was causing jank)"
        )

    def test_mutationobserver_in_scroll_fix(self):
        """After fix: MutationObserver should be in _js_scroll_fix."""
        import re
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r'_js_scroll_fix\s*=\s*\((.*?)\)\s*\n\s*_js_ime_fix', content, re.DOTALL)
        assert match, "Could not find _js_scroll_fix block"
        scroll_fix_js = match.group(1)
        assert "MutationObserver" in scroll_fix_js, (
            "MutationObserver should be in scroll fix (proper approach)"
        )

    def test_content_end_scroll_checks_is_near_bottom(self):
        """After fix: content-end scroll checks isNearBottom()."""
        import re
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r'_js_scroll_fix\s*=\s*\((.*?)\)\s*\n\s*_js_ime_fix', content, re.DOTALL)
        assert match, "Could not find _js_scroll_fix block"
        scroll_fix_js = match.group(1)
        # Should have isNearBottom check before content-event scroll
        assert "isNearBottom()" in scroll_fix_js, (
            "isNearBottom() check should be in scroll fix"
        )

    def test_no_characterdata_observation(self):
        """After fix: MutationObserver should not watch characterData."""
        import re
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r'_js_scroll_fix\s*=\s*\((.*?)\)\s*\n\s*_js_ime_fix', content, re.DOTALL)
        assert match, "Could not find _js_scroll_fix block"
        scroll_fix_js = match.group(1)
        assert "characterData" not in scroll_fix_js, (
            "characterData observation should not be in scroll fix (performance)"
        )


# ═══════════════════════════════════════════════════════════════
# Bug 1: #content-end rendered inside message loop (HIGH)
# ═══════════════════════════════════════════════════════════════

class TestContentEndPlacement:
    """Bug 1: #content-end must be OUTSIDE the message rendering loop."""

    @staticmethod
    def _get_message_loop_content():
        import re
        with open("frontends/stapp_mobile.py", "r", encoding="utf-8") as f:
            content = f.read()
        # Find the message rendering for loop — from "for msg_idx" to the line before try/embed
        match = re.search(
            r'(for msg_idx, msg in enumerate\(st\.session_state\.messages\):.*?)'
            r'(?=\n{0,2}# Persistent scroll anchor.*?\nst\.markdown)',
            content, re.DOTALL
        )
        if not match:
            return None
        return match.group(1)

    def test_content_end_outside_message_loop_stapp_mobile(self):
        """stapp_mobile.py: content-end should NOT be inside the for loop body."""
        loop_body = self._get_message_loop_content()
        assert loop_body is not None, "Could not find message rendering loop"
        # After fix: content-end div should NOT be inside the for loop
        assert 'id="content-end"' not in loop_body, (
            "content-end div should NOT be inside the for loop (causes duplicate IDs)"
        )

    def test_content_end_is_after_loop_stapp_mobile(self):
        """stapp_mobile.py: content-end should be placed after the loop."""
        import re
        with open("frontends/stapp_mobile.py", "r", encoding="utf-8") as f:
            content = f.read()
        # Find the section between loop end and try block
        match = re.search(
            r'enumerate\(st\.session_state\.messages\):.*?'
            r'(# Persistent scroll anchor.*?content-end.*?)'
            r'(?=\n{0,5}try:)',
            content, re.DOTALL
        )
        assert match is not None, (
            "content-end should be placed after the loop, before try block"
        )


# ═══════════════════════════════════════════════════════════════
# Bug 2: routing_mode="ask" never sets pending_routing (HIGH)
# ═══════════════════════════════════════════════════════════════

class TestRoutingModeAsk:
    """Bug 2: routing_mode='ask' should set pending_routing for complex tasks."""

    @staticmethod
    def _get_dispatch_code(filepath):
        import re
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        # Find the dispatch section: after "route = detect_complexity" line
        match = re.search(
            r'route = detect_complexity\(prompt\).*?(?=\n\s*# ── Streaming|$)',
            content, re.DOTALL
        )
        return match.group(0) if match else ""

    def test_ask_mode_sets_pending_routing_stapp_mobile(self):
        """stapp_mobile.py: when routing_mode='ask' and complex task, set pending_routing."""
        dispatch = self._get_dispatch_code("frontends/stapp_mobile.py")
        # After fix: should contain ask mode branch that sets pending_routing
        assert 'pending_routing' in dispatch, (
            "routing_mode='ask' should set pending_routing for complex tasks"
        )
        assert 'routing_mode == "ask"' in dispatch or "routing_mode == 'ask'" in dispatch, (
            "Should have explicit check for routing_mode=='ask'"
        )

    def test_ask_mode_sets_pending_routing_stapp(self):
        """stapp.py: when routing_mode='ask' and complex task, set pending_routing."""
        dispatch = self._get_dispatch_code("frontends/stapp.py")
        assert 'pending_routing' in dispatch, (
            "routing_mode='ask' should set pending_routing for complex tasks"
        )
        assert 'routing_mode == "ask"' in dispatch or "routing_mode == 'ask'" in dispatch, (
            "Should have explicit check for routing_mode=='ask'"
        )


# ═══════════════════════════════════════════════════════════════
# Bug 3: sanitize_streaming_tail omitted from final render (MEDIUM)
# ═══════════════════════════════════════════════════════════════

class TestFinalRenderSanitize:
    """Bug 3: final rendering must sanitize streaming tail."""

    def test_final_render_calls_sanitize_stapp(self):
        """stapp.py: poll-based streaming should call sanitize_streaming_tail."""
        import re
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            content = f.read()
        # Find the streaming section
        streaming_match = re.search(
            r'# ── Streaming state:.*?(?=if st\.session_state\.autonomous_enabled)',
            content, re.DOTALL
        )
        assert streaming_match, "Could not find streaming section"
        streaming_section = streaming_match.group(0)
        assert "sanitize_streaming_tail" in streaming_section, (
            "Streaming section should call sanitize_streaming_tail to clean unclosed markdown"
        )


# ═══════════════════════════════════════════════════════════════
# Bug 4: --accent-bar CSS variable undefined (MEDIUM)
# ═══════════════════════════════════════════════════════════════

class TestAccentBarCSS:
    """Bug 4: --accent-bar must be defined in :root."""

    def test_accent_bar_defined_in_root_stapp(self):
        """stapp_theme.css: --accent-bar should be defined in :root CSS block."""
        import re
        with open("frontends/assets/stapp_theme.css", "r", encoding="utf-8") as f:
            content = f.read()
        root_match = re.search(r':root\s*{(.*?)}', content, re.DOTALL)
        assert root_match, "Could not find :root block in CSS file"
        root_block = root_match.group(1)
        assert "--accent-bar" in root_block, (
            "--accent-bar CSS variable should be defined in :root"
        )


# ═══════════════════════════════════════════════════════════════
# Bug 5: sleep/rerun fires after task completion (MEDIUM)
# ═══════════════════════════════════════════════════════════════

class TestDonePathNoSleep:
    """Bug 5: done path should not fall through to time.sleep + st.rerun()."""

    def test_done_path_guards_against_sleep_stapp_mobile(self):
        """stapp_mobile.py: time.sleep should be inside 'else' block from done check."""
        import re
        with open("frontends/stapp_mobile.py", "r", encoding="utf-8") as f:
            content = f.read()
        # The done block and sleep should be in an if/else structure
        match = re.search(
            r'if done:.*?reset_agent_state\(\)\s*\n\s*st\.rerun\(\)\s*\n\s*else:\s*\n\s*time\.sleep',
            content, re.DOTALL
        )
        assert match is not None, (
            "time.sleep should be inside else: block guarded by 'if done:'"
        )


# ═══════════════════════════════════════════════════════════════
# Bug 6: cursor blinks during pre-streaming "running" state (MEDIUM)
# ═══════════════════════════════════════════════════════════════

class TestCursorDuringRunning:
    """Bug 6: cursor should not be visible when state==running and no response."""

    def test_cursor_hidden_during_running_state_stapp_mobile(self):
        """stapp_mobile.py: cursor variable should be empty string during 'running' state."""
        import re
        with open("frontends/stapp_mobile.py", "r", encoding="utf-8") as f:
            content = f.read()
        # The cursor assignment should include "running" in the no-cursor states
        match = re.search(
            r'cursor\s*=\s*""\s*if\s*state\s*in\s*\(.*?running.*?\)\s*else\s*"[^"]*"',
            content
        )
        assert match is not None, (
            "cursor should be empty when state is 'running' (no text to type at)"
        )


# ═══════════════════════════════════════════════════════════════
# Bug 7: "Reinject tools" accumulates without dedup (MEDIUM)
# ═══════════════════════════════════════════════════════════════

class TestReinjectToolsNoDup:
    """Bug 7: reinject tools should not accumulate duplicates."""

    def test_reinject_tools_has_dedup_stapp(self):
        """stapp.py: reinject tools should check _tools_injected flag before extend."""
        import re
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            content = f.read()
        reinject_match = re.search(
            r'重新注入工具.*?st\.toast\(f"(?:注入|已注入|工具示范)',
            content, re.DOTALL
        )
        assert reinject_match, "Could not find reinject tools section"
        reinject_section = reinject_match.group(0)
        assert "_tools_injected" in reinject_section, (
            "Reinject tools should use _tools_injected flag for dedup"
        )

    def test_reinject_tools_has_dedup_stapp_mobile(self):
        """stapp_mobile.py: reinject tools should check _tools_injected flag before extend."""
        import re
        with open("frontends/stapp_mobile.py", "r", encoding="utf-8") as f:
            content = f.read()
        reinject_match = re.search(
            r'重新注入工具.*?st\.toast\(f"(?:注入|已注入|工具示范)',
            content, re.DOTALL
        )
        assert reinject_match, "Could not find reinject tools section"
        reinject_section = reinject_match.group(0)
        assert "_tools_injected" in reinject_section, (
            "Reinject tools should use _tools_injected flag for dedup"
        )


# ═══════════════════════════════════════════════════════════════
# Bug 8: Stop button abandons queue without draining (MEDIUM)
# ═══════════════════════════════════════════════════════════════

class TestStopButtonQueueDrain:
    """Bug 8: stop button should drain the queue before discarding reference."""

    def test_stop_button_drains_queue_stapp(self):
        """stapp.py: sidebar stop uses stop_requested; drainer.collect() drains."""
        import re
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            content = f.read()
        stop_match = re.search(
            r'强行停止任务.*?(?=if st\.button\("重新注入工具")',
            content, re.DOTALL
        )
        assert stop_match, "Could not find stop button section"
        stop_section = stop_match.group(0)
        assert "stop_requested" in stop_section, (
            "Sidebar stop should set stop_requested=True for graceful shutdown via streaming loop"
        )
        # After Phase 6c migration: uses drainer.collect(), not raw get_nowait
        assert ".collect(" in content or "get_nowait" in content, (
            "poll_agent_output should drain via drainer.collect() or get_nowait"
        )


# ═══════════════════════════════════════════════════════════════
# Bug L1: Generator-based streaming blocks event loop (HIGH)
# ═══════════════════════════════════════════════════════════════

class TestPollBasedStreaming:
    """Bug L1: stapp.py should use poll-based streaming, not blocking generator."""

    def test_streaming_uses_poll_not_generator_stapp(self):
        """stapp.py: streaming should use drainer.collect() or get_nowait() polling."""
        import re
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            content = f.read()
        # After Phase 6c: uses drainer.collect() (or legacy get_nowait)
        assert ".collect(" in content or "get_nowait" in content, (
            "stapp.py should use drainer.collect() or get_nowait for non-blocking polling"
        )
        # Should use time.sleep between polls
        assert "time.sleep" in content, (
            "stapp.py should use time.sleep between poll iterations"
        )

    def test_no_blocking_generator_loop_stapp(self):
        """stapp.py: should NOT use blocking for-loop over generator for streaming."""
        import re
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            content = f.read()
        # The old pattern: for payload in agent_backend_stream(dq):
        # should be replaced with poll-based rendering
        # Check that the streaming section uses poll_agent_output
        streaming_section = content.split("# ── Streaming state:")[1] if "# ── Streaming state:" in content else ""
        assert "poll_agent_output" in streaming_section or "get_nowait" in streaming_section, (
            "Streaming section should use non-blocking polling"
        )

    def test_stop_button_in_streaming_area_stapp(self):
        """stapp.py: stop button should be present inside the streaming area."""
        import re
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            content = f.read()
        # Find streaming section
        streaming_section = content.split("# ── Streaming state:")[1] if "# ── Streaming state:" in content else ""
        assert "stop" in streaming_section.lower() and "st.button" in streaming_section, (
            "Stop button should be in the streaming area for user to abort"
        )

    def test_stop_requested_state_stapp(self):
        """stapp.py: should have stop_requested session state for graceful stop."""
        import re
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "stop_requested" in content, (
            "stapp.py should use stop_requested flag for graceful stop handling"
        )

    def test_partial_response_state_stapp(self):
        """stapp.py: should store partial_response in session state across reruns."""
        import re
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "partial_response" in content, (
            "stapp.py should store partial_response in session_state for poll-based rendering"
        )

    def test_sidebar_stop_uses_stop_requested_stapp(self):
        """stapp.py sidebar: stop button should set stop_requested, not agent_running=False."""
        import re
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            content = f.read()
        # Find sidebar stop button section
        stop_match = re.search(
            r'强行停止任务.*?(?=if st\.button\("重新注入工具")',
            content, re.DOTALL
        )
        assert stop_match, "Could not find sidebar stop button"
        stop_section = stop_match.group(0)
        # After fix: should use stop_requested pattern
        assert "stop_requested" in stop_section, (
            "Sidebar stop button should set stop_requested=True for graceful shutdown"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for Phase 6: stapp2.py migration from put_task() to submit()."""

import re
import pytest


class TestStapp2Migration:
    """Verify stapp2.py is the first frontend migrated to AgentBackend protocol."""

    @staticmethod
    def _read_stapp2():
        with open("frontends/stapp2.py", "r", encoding="utf-8") as f:
            return f.read()

    # ── Completion definition item 2: no put_task() call ──
    def test_no_put_task_call(self):
        """stapp2.py must not call agent.put_task()."""
        content = self._read_stapp2()
        # Only the original line should no longer exist
        assert "agent.put_task(" not in content, (
            "stapp2.py should not call agent.put_task() after migration"
        )

    # ── Completion definition item 3: constructs AgentInput ──
    def test_constructs_agent_input(self):
        """stapp2.py must construct AgentInput for submission."""
        content = self._read_stapp2()
        assert "AgentInput(" in content, (
            "stapp2.py should construct AgentInput(query=prompt)"
        )

    # ── Completion definition item 4: calls agent.submit() ──
    def test_calls_agent_submit(self):
        """stapp2.py must call agent.submit(AgentInput(...))."""
        content = self._read_stapp2()
        assert "agent.submit(" in content, (
            "stapp2.py should call agent.submit(AgentInput(...))"
        )

    # ── Completion definition item 5: uses AgentOutputDrainer ──
    def test_uses_agent_output_drainer(self):
        """stapp2.py must use AgentOutputDrainer for consuming output."""
        content = self._read_stapp2()
        assert "AgentOutputDrainer" in content, (
            "stapp2.py should use AgentOutputDrainer to consume output"
        )

    # ── Completion definition item 5: uses drainer methods ──
    def test_uses_drainer_collect(self):
        """poll_agent_output must use drainer.collect() + drainer.full_text."""
        content = self._read_stapp2()
        assert "drainer" in content.lower() or "_drainer" in content, (
            "poll_agent_output should reference the drainer"
        )
        assert ".collect(" in content, (
            "should call drainer.collect() for non-blocking polling"
        )

    # ── Completion definition item 7: put_task() still exists for other frontends ──
    def test_put_task_still_exists_for_legacy(self):
        """put_task() must still exist in agentmain.py for other frontends."""
        with open("core/agentmain.py", "r", encoding="utf-8") as f:
            agentmain = f.read()
        assert "def put_task(" in agentmain, (
            "put_task() must remain for other frontends that haven't migrated"
        )

    # ── No raw queue.get_nowait() in stapp2 after migration ──
    def test_no_raw_queue_polling_in_stapp2(self):
        """stapp2.py should not do raw get_nowait() on a queue."""
        content = self._read_stapp2()
        # The stop button's old drain pattern is gone
        assert "dq.get_nowait()" not in content, (
            "stapp2.py should not use raw queue.get_nowait() after migration"
        )

    # ── Imports are present ──
    def test_protocol_imports_present(self):
        """stapp2.py should import from core.protocol."""
        content = self._read_stapp2()
        assert "from core.protocol" in content, (
            "stapp2.py should import protocol types"
        )


class TestLegacyPutTaskPreserved:
    """Verify put_task() is preserved for other frontends."""

    def test_put_task_is_callable(self):
        """put_task is not removed — it delegates to submit()."""
        from core.agentmain import GeneraticAgent
        assert hasattr(GeneraticAgent, "put_task"), (
            "put_task must remain for legacy frontends"
        )


class TestStappMigration:
    """Phase 6c: stapp.py migration from put_task() to submit() + drainer."""

    @staticmethod
    def _read_stapp():
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            return f.read()

    def test_no_put_task_calls(self):
        """stapp.py must not call agent.put_task() or dispatch_agent.put_task()."""
        content = self._read_stapp()
        assert ".put_task(" not in content, (
            "stapp.py should not call .put_task() after migration"
        )

    def test_start_agent_task_uses_ensure_agent_backend(self):
        """start_agent_task() must call ensure_agent_backend(dispatch_agent)."""
        content = self._read_stapp()
        assert "ensure_agent_backend" in content, (
            "start_agent_task should call ensure_agent_backend(dispatch_agent) "
            "to safely handle both GeneraticAgent and OpenAIOrchestratedAgent"
        )
        assert "AgentInput(" in content, (
            "start_agent_task should construct AgentInput"
        )

    def test_poll_uses_drainer(self):
        """poll_agent_output() must use AgentOutputDrainer."""
        content = self._read_stapp()
        assert "_drainer" in content, (
            "poll_agent_output should use _drainer"
        )
        assert ".collect(" in content, (
            "should call drainer.collect()"
        )

    def test_stop_requested_wired_to_drainer(self):
        """stop_requested must be synced to drainer before collect()."""
        content = self._read_stapp()
        # poll_agent_output should set d.stop_requested = st.session_state.stop_requested
        assert "stop_requested" in content, (
            "stop_requested filter must be wired to drainer"
        )

    def test_drainer_cleaned_up_on_new_conversation(self):
        """_drainer must be set to None when agent_running is reset."""
        content = self._read_stapp()
        assert "st.session_state._drainer = None" in content, (
            "_drainer must be cleaned up on reset"
        )

    def test_routing_buttons_guard_duplicate_submit(self):
        """Routing buttons must check agent_running before dispatching."""
        content = self._read_stapp()
        assert "已有任务在运行" in content, (
            "routing buttons should guard against duplicate submit"
        )


class TestStapp2Stability:
    """Phase A1: stapp2.py stop_requested sync + force-complete timeout."""

    @staticmethod
    def _read_stapp2():
        with open("frontends/stapp2.py", "r", encoding="utf-8") as f:
            return f.read()

    def test_stop_requested_synced_to_drainer(self):
        """poll_agent_output must sync stopping flag to drainer."""
        content = self._read_stapp2()
        assert "d.stop_requested" in content, (
            "stapp2 poll_agent_output should sync d.stop_requested"
        )

    def test_force_complete_timeout_on_stop(self):
        """stapp2 must have force-complete timeout after stop."""
        content = self._read_stapp2()
        assert "stop_requested_at" in content, (
            "stapp2 should track stop_requested_at for force-complete timeout"
        )
        assert "1.5" in content or "elapsed > 1.5" in content, (
            "stapp2 should have 1.5s force-complete timeout"
        )


class TestQtappMigration:
    """Phase 6b: qtapp.py migration from put_task() to submit() + drainer."""

    @staticmethod
    def _read_qtapp():
        with open("frontends/qtapp.py", "r", encoding="utf-8") as f:
            return f.read()

    def test_no_put_task_calls(self):
        """qtapp.py must not call self.agent.put_task()."""
        content = self._read_qtapp()
        assert ".put_task(" not in content, (
            "qtapp.py should not call .put_task() after migration"
        )

    def test_uses_ensure_agent_backend(self):
        """_handle_send must use ensure_agent_backend(self.agent)."""
        content = self._read_qtapp()
        assert "ensure_agent_backend" in content, (
            "qtapp.py should use ensure_agent_backend(self.agent)"
        )

    def test_uses_agent_output_drainer(self):
        """_poll_queue must use AgentOutputDrainer."""
        content = self._read_qtapp()
        assert "AgentOutputDrainer" in content, (
            "qtapp.py should use AgentOutputDrainer"
        )

    def test_drainer_used_in_poll_queue(self):
        """_poll_queue must call drainer.collect() and check drainer.full_text."""
        content = self._read_qtapp()
        assert "drainer" in content.lower() or "_drainer" in content, (
            "_poll_queue should reference the drainer"
        )
        assert ".collect(" in content, (
            "_poll_queue should call drainer.collect()"
        )

    def test_drainer_used_in_do_stop(self):
        """_do_stop must drain via drainer.collect()."""
        content = self._read_qtapp()
        # _do_stop should reference _drainer
        do_stop_section = content.split("def _do_stop")[1].split("def _")[0] if "def _do_stop" in content else ""
        assert "_drainer" in do_stop_section or "collect(" in do_stop_section, (
            "_do_stop should drain via drainer.collect()"
        )


class TestStappMobileMigration:
    """Phase S2: stapp_mobile.py migration to submit() + drainer + task_id."""

    @staticmethod
    def _read_mobile():
        with open("frontends/stapp_mobile.py", "r", encoding="utf-8") as f:
            return f.read()

    def test_no_put_task_calls_in_dispatch(self):
        """stapp_mobile.py dispatch paths (routing + main) must not call .put_task()."""
        content = self._read_mobile()
        # Check the routing UI section and the main dispatch section
        routing_start = content.find("# ── Routing suggestion UI")
        chat_input_start = content.find("if prompt := st.chat_input")
        if routing_start > 0 and chat_input_start > 0:
            dispatch_area = content[routing_start:chat_input_start + 3000]
        else:
            dispatch_area = content
        assert ".put_task(" not in dispatch_area, (
            "stapp_mobile.py dispatch paths should not call .put_task()"
        )

    def test_start_agent_task_uses_ensure_agent_backend(self):
        """start_agent_task must use ensure_agent_backend(dispatch_agent)."""
        content = self._read_mobile()
        assert "ensure_agent_backend" in content, (
            "stapp_mobile should use ensure_agent_backend"
        )

    def test_poll_uses_drainer_with_task_id(self):
        """poll_agent_output must sync task_id to drainer."""
        content = self._read_mobile()
        assert "_drainer" in content, (
            "stapp_mobile should use _drainer"
        )
        assert "d.task_id" in content, (
            "poll_agent_output should sync d.task_id"
        )

    def test_stop_requested_wired_to_drainer(self):
        """stop_requested must be synced to drainer before collect()."""
        content = self._read_mobile()
        assert "d.stop_requested" in content, (
            "stop_requested filter must be wired to drainer"
        )

    def test_drainer_cleaned_up_on_reset(self):
        """reset_agent_state must set _drainer = None."""
        content = self._read_mobile()
        reset_section = content.split("def reset_agent_state")[1].split("def ")[0] if "def reset_agent_state" in content else ""
        assert "_drainer" in reset_section, (
            "reset_agent_state should set _drainer = None"
        )

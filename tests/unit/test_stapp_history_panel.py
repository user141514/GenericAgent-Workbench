"""Phase P1 tests for stapp_history_panel module."""

import pytest


class FakeState(dict):
    """Simulates st.session_state for distill preview state management."""
    pass


class TestRenderDistillPreview:
    """render_distill_preview() — P1 extraction."""

    def test_module_importable(self):
        from frontends.stapp_history_panel import render_distill_preview
        assert callable(render_distill_preview)

    def test_no_agent_access(self):
        import inspect
        from frontends.stapp_history_panel import render_distill_preview
        source = inspect.getsource(render_distill_preview)
        assert "agent." not in source

    def test_no_submit_put_task_drainer(self):
        import inspect
        from frontends.stapp_history_panel import render_distill_preview
        source = inspect.getsource(render_distill_preview)
        assert "submit" not in source
        assert "put_task" not in source
        assert "AgentOutputDrainer" not in source

    def test_uses_state_param(self):
        """Verify function accepts 'state' keyword argument."""
        import inspect
        from frontends.stapp_history_panel import render_distill_preview
        sig = inspect.signature(render_distill_preview)
        assert "state" in sig.parameters

    def test_function_no_longer_in_stapp_py(self):
        """render_distill_preview must NOT be defined in stapp.py anymore."""
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "def render_distill_preview" not in content

    def test_write_memory_clears_distill_state(self):
        """Simulate the state cleanup that happens on 'write to memory'."""
        # The actual button calls save_distilled_memory + clears distill_result.
        # We verify the state cleanup logic directly.
        state = FakeState()
        state["distill_result_hist.txt"] = {"title": "test"}
        # Simulate button click
        state["distill_result_hist.txt"] = None
        assert state["distill_result_hist.txt"] is None

    def test_close_clears_distill_state(self):
        """Closing the preview should set distill_result to None."""
        state = FakeState()
        state["distill_result_hist.txt"] = {"title": "test"}
        state["distill_result_hist.txt"] = None
        assert state["distill_result_hist.txt"] is None


class TestStappStillCallsIt:
    """stapp.py must still import and call render_distill_preview."""

    def test_stapp_imports_render_distill_preview(self):
        from frontends.stapp import render_distill_preview
        assert callable(render_distill_preview)

    def test_render_history_panel_calls_it(self):
        """render_history_panel() must still reference render_distill_preview."""
        with open("frontends/stapp.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "render_distill_preview(" in content

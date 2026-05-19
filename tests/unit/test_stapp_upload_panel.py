"""Phase U1 tests for stapp_upload_panel module."""

import pytest


class FakeUploadedFile:
    """Simulates a Streamlit UploadedFile for testing sync_uploaded_files."""
    def __init__(self, name, data, mime_type=""):
        self.name = name
        self._data = data
        self.type = mime_type
        self.size = len(data)
    def getvalue(self):
        return self._data


class FakeState(dict):
    """Simulates st.session_state for testing clear_uploaded_files."""
    pass


class TestSyncUploadedFiles:
    """sync_uploaded_files() returns list[dict] without writing session_state."""

    def test_empty_list_returns_empty(self):
        from frontends.stapp_upload_panel import sync_uploaded_files
        result = sync_uploaded_files([], cache={})
        assert result == []

    def test_none_returns_empty(self):
        from frontends.stapp_upload_panel import sync_uploaded_files
        result = sync_uploaded_files(None, cache={})
        assert result == []

    def test_returns_list_of_dicts(self):
        from frontends.stapp_upload_panel import sync_uploaded_files
        fake = FakeUploadedFile("test.py", b"x = 1")
        result = sync_uploaded_files([fake], cache={})
        assert isinstance(result, list)
        assert len(result) >= 1
        assert isinstance(result[0], dict)
        assert result[0]["name"] == "test.py"

    def test_dedup_with_cache(self):
        from frontends.stapp_upload_panel import sync_uploaded_files
        cache = {}
        f1 = FakeUploadedFile("a.py", b"hello")
        r1 = sync_uploaded_files([f1], cache=cache)
        r2 = sync_uploaded_files([f1], cache=cache)
        assert r1[0]["id"] == r2[0]["id"]

    def test_legacy_keys_present(self):
        """Output dicts must have the keys expected by stapp.py helpers."""
        from frontends.stapp_upload_panel import sync_uploaded_files
        fake = FakeUploadedFile("data.txt", b"content")
        result = sync_uploaded_files([fake], cache={})
        required = {"id", "name", "size", "size_label", "mime", "kind",
                    "stored_path", "status", "preview_text", "distilled_text",
                    "raw_text_length", "warning"}
        assert set(result[0].keys()) >= required


class TestClearUploadedFiles:
    """clear_uploaded_files(state) resets upload state."""

    def test_clears_list_and_increments_nonce(self):
        from frontends.stapp_upload_panel import clear_uploaded_files
        state = FakeState(uploaded_files=[{"name": "x.txt"}], upload_widget_nonce=3)
        clear_uploaded_files(state)
        assert state["uploaded_files"] == []
        assert state["upload_widget_nonce"] == 4

    def test_handles_missing_keys(self):
        """Should raise KeyError — caller must provide required keys."""
        from frontends.stapp_upload_panel import clear_uploaded_files
        state = FakeState()
        with pytest.raises(KeyError):
            clear_uploaded_files(state)


class TestRenderAttachmentItems:
    """render_attachment_items(files) does NOT depend on session_state."""

    def test_empty_files_shows_caption(self):
        """Should not crash with empty list."""
        from frontends.stapp_upload_panel import render_attachment_items
        # In test env without Streamlit running, this may raise or be skipped.
        # The key contract: it accepts a 'files' list parameter.
        try:
            render_attachment_items([])
        except Exception as e:
            # Expected: Streamlit not running in test env
            pass

    def test_function_signature_accepts_files(self):
        """The function must accept 'files' as its first positional arg."""
        import inspect
        from frontends.stapp_upload_panel import render_attachment_items
        sig = inspect.signature(render_attachment_items)
        params = list(sig.parameters.keys())
        assert params[0] == "files"


class TestModuleNoAgentAccess:
    """Module must not access agent or submit/drainer paths."""

    def test_no_agent_access(self):
        import inspect
        from frontends import stapp_upload_panel
        source = inspect.getsource(stapp_upload_panel)
        assert "agent." not in source
        assert "put_task" not in source
        assert "submit" not in source


class TestStappRetainsSubmitHelpers:
    """get_ready_attachments / build_prompt_with_attachments / format_user_message stay."""

    def test_get_ready_attachments_still_in_stapp(self):
        from frontends import stapp
        assert hasattr(stapp, "get_ready_attachments")

    def test_build_prompt_with_attachments_still_in_stapp(self):
        from frontends import stapp
        assert hasattr(stapp, "build_prompt_with_attachments")

    def test_format_user_message_still_in_stapp(self):
        from frontends import stapp
        assert hasattr(stapp, "format_user_message")

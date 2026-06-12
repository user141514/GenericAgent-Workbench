"""
Protocol compatibility tests — Claude/OpenAI/DeepSeek auto-detection.

Tests model capability detection, backend inference, and protocol negotiation.
"""

from __future__ import annotations

import pytest

from core.llm_capabilities import detect_model_profile, get_model_capabilities


class TestModelDetection:
    """Verify model → protocol auto-detection."""

    CLAUDE_MODELS = [
        ("claude-4", "claude"),
        ("claude-opus-4-6", "claude"),
        ("claude-sonnet-4-5-20251001", "claude"),
        ("claude-3.5-sonnet", "claude"),
        ("claude-3-opus", "claude"),
    ]

    @pytest.mark.parametrize("model,expected_protocol", CLAUDE_MODELS)
    def test_claude_models_detected(self, model, expected_protocol):
        profile = detect_model_profile(model)
        assert profile.protocol == expected_protocol
        assert profile.supports_thinking is True
        assert profile.supports_prompt_caching is True
        assert profile.supports_tools is True

    DEEPSEEK_MODELS = [
        "deepseek-v4-pro",
        "deepseek-chat",
        "deepseek-v3",
        "deepseek-r1",
    ]

    @pytest.mark.parametrize("model", DEEPSEEK_MODELS)
    def test_deepseek_models_detected(self, model):
        profile = detect_model_profile(model)
        assert profile.model_family == "deepseek"
        assert profile.supports_thinking is True
        assert profile.supports_tools is True

    GPT_MODELS = [
        ("gpt-4o", "openai"),
        ("gpt-4-turbo", "openai"),
        ("o1", "openai"),
        ("o4-mini", "openai"),
    ]

    @pytest.mark.parametrize("model,expected_protocol", GPT_MODELS)
    def test_gpt_models_detected(self, model, expected_protocol):
        profile = detect_model_profile(model)
        assert profile.protocol == expected_protocol

    def test_unknown_model_uses_fallback(self):
        profile = detect_model_profile("some-unknown-model-123")
        assert profile.model_family == "unknown"
        assert profile.protocol == "openai"
        assert profile.supports_tools is True

    def test_claude_endpoint_detected_by_url(self):
        profile = detect_model_profile("unknown-model", base_url="https://api.anthropic.com")
        assert profile.protocol == "claude"

    def test_claude_protocol_via_messages_url(self):
        profile = detect_model_profile("unknown", base_url="https://example.com/v1/messages")
        assert profile.protocol == "claude"


class TestCapabilityDict:
    """Verify get_model_capabilities() returns a complete capabilities dict."""

    def test_claude_capabilities_dict(self):
        caps = get_model_capabilities("claude-4")
        assert caps["protocol"] == "claude"
        assert caps["supports_vision"] is True
        assert caps["supports_thinking"] is True
        assert caps["supports_extended_thinking"] is True
        assert caps["supports_prompt_caching"] is True
        assert caps["supports_tools"] is True
        assert caps["context_window"] >= 100000
        assert caps["max_tokens"] >= 4096

    def test_gpt_capabilities_dict(self):
        caps = get_model_capabilities("gpt-4o")
        assert caps["protocol"] == "openai"
        assert caps["supports_tools"] is True
        assert caps["context_window"] >= 32000

    def test_unknown_capabilities_dict(self):
        caps = get_model_capabilities("unknown-xyz")
        assert caps["protocol"] in ("openai", "claude")
        assert "model_family" in caps
        assert "max_tokens" in caps


class TestBackendInference:
    """Verify the _infer_backend_kind function (in openai_agentmain.py)."""

    def test_native_claude_detected_by_name(self):
        from core.openai_agentmain import _infer_backend_kind
        assert _infer_backend_kind("my-native-claude", None, None) == "native_claude"

    def test_native_claude_detected_by_model(self):
        from core.openai_agentmain import _infer_backend_kind
        assert _infer_backend_kind("test", None, "claude-4") == "native_claude"

    def test_native_oai_detected(self):
        from core.openai_agentmain import _infer_backend_kind
        assert _infer_backend_kind("openai-backend", None, None) == "native_oai"
        assert _infer_backend_kind("test", "https://api.openai.com/v1", None) == "native_oai"
        assert _infer_backend_kind("test", None, "gpt-4o") == "native_oai"

    def test_deepseek_defaults_to_oai(self):
        from core.openai_agentmain import _infer_backend_kind
        result = _infer_backend_kind("test", None, "deepseek-chat")
        assert result == "native_oai"

    def test_unknown_returns_none(self):
        from core.openai_agentmain import _infer_backend_kind
        assert _infer_backend_kind("random-name", "https://random.url", "random-model") is None


class TestStreamArtifactCleanup:
    def test_latest_turn_marker_uses_last_marker(self):
        from core.openai_agentmain import _latest_turn_marker

        text = (
            "**LLM Running (Turn 1) ...**\n\nA\n"
            "**LLM Running (Turn 4) ...**\n\nB"
        )

        assert _latest_turn_marker(text) == 4

    def test_preserves_delta_boundary_spaces(self):
        from core.openai_agentmain import _strip_stream_artifacts

        chunks = [
            _strip_stream_artifacts("I'll "),
            _strip_stream_artifacts("systematically "),
            _strip_stream_artifacts("explore "),
            _strip_stream_artifacts("your project."),
        ]

        assert "".join(chunks) == "I'll systematically explore your project."

    def test_removes_transport_tags_without_stripping_text(self):
        from core.openai_agentmain import _strip_stream_artifacts

        assert _strip_stream_artifacts(" hello <assistant>world</assistant> ") == " hello world "

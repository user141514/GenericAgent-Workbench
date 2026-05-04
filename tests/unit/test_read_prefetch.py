"""Unit tests for read_prefetch detection + safe reading (P2-1)."""

import os
import tempfile
from pathlib import Path

import pytest

from core.runtime.read_prefetch import (
    READ_PREFETCH_ENV_VAR,
    _is_binary_content,
    _is_sensitive_path,
    build_read_prefetch_context,
    detect_read_prefetch,
    is_read_prefetch_enabled,
    safe_read_prefetch_content,
)


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal project tree for file-targeting tests."""
    (tmp_path / "core").mkdir(exist_ok=True)
    (tmp_path / "core" / "router_rules.py").write_text("# router rules module\n\ndef match():\n    pass\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Project\n\nSome docs.\n", encoding="utf-8")
    (tmp_path / "large_file.py").write_text("\n".join(f"# line {i}" for i in range(300)) + "\n", encoding="utf-8")
    # Sensitive paths
    (tmp_path / ".env").write_text("SECRET=xxx", encoding="utf-8")
    (tmp_path / "mykey.py").write_text("key = 'test'", encoding="utf-8")
    (tmp_path / "secrets").mkdir(exist_ok=True)
    (tmp_path / "secrets" / "token.txt").write_text("secret", encoding="utf-8")
    return tmp_path


# ── Detection tests ───────────────────────────────────────────────


def test_detect_analysis_query_with_explicit_file(tmp_project):
    """Explicit file-view analysis query should trigger prefetch."""
    decision = detect_read_prefetch(
        "分析 core/router_rules.py 的路由逻辑", project_root=tmp_project
    )
    assert decision.should_prefetch is True
    assert decision.target_file == "core/router_rules.py"
    assert decision.reason == "analysis_single_file_prefetch_candidate"
    assert decision.confidence > 0.8


def test_detect_normal_chat_no_prefetch(tmp_project):
    """Normal chat query should NOT trigger prefetch."""
    decision = detect_read_prefetch("你好，今天天气怎么样", project_root=tmp_project)
    assert decision.should_prefetch is False
    assert decision.reason == "not_analysis_request"


def test_detect_action_request_no_prefetch(tmp_project):
    """Modification request should NOT trigger prefetch (blocked action)."""
    decision = detect_read_prefetch(
        "修改 core/router_rules.py 的函数", project_root=tmp_project
    )
    assert decision.should_prefetch is False
    assert "action_request_not_supported" in decision.reason


def test_detect_file_not_found(tmp_project):
    """Non-existent file should not trigger prefetch."""
    decision = detect_read_prefetch(
        "分析 nonexistent_file.py 的逻辑", project_root=tmp_project
    )
    assert decision.should_prefetch is False


# ── Sensitive path detection ──────────────────────────────────────


def test_sensitive_dotenv():
    assert _is_sensitive_path(".env") is True
    assert _is_sensitive_path("subdir/.env.local") is True
    assert _is_sensitive_path(".env.production") is True


def test_sensitive_mykey():
    assert _is_sensitive_path("mykey.py") is True
    assert _is_sensitive_path("mykey.json") is True


def test_sensitive_secrets_dir():
    assert _is_sensitive_path("secrets/token.txt") is True


def test_sensitive_credentials():
    assert _is_sensitive_path("credentials.json") is True


def test_sensitive_git_dir():
    assert _is_sensitive_path(".git/config") is True


def test_non_sensitive_normal_file():
    assert _is_sensitive_path("core/router_rules.py") is False
    assert _is_sensitive_path("README.md") is False
    assert _is_sensitive_path("frontends/stapp.py") is False


# ── Binary detection ──────────────────────────────────────────────


def test_binary_null_bytes():
    assert _is_binary_content(b"hello\x00world") is True


def test_binary_low_text_ratio():
    # 90% non-printable bytes
    data = bytes([0x80] * 900 + [ord("a")] * 100)
    assert _is_binary_content(data) is True


def test_text_content_not_binary():
    assert _is_binary_content(b"def hello():\n    print('world')\n") is False


def test_utf8_chinese_not_binary():
    assert _is_binary_content("分析代码结构\n".encode("utf-8")) is False


# ── Safe read tests ───────────────────────────────────────────────


def test_safe_read_normal_file(tmp_project):
    content, status, meta = safe_read_prefetch_content(
        "core/router_rules.py", tmp_project
    )
    assert status == "ok"
    assert content is not None
    assert "router rules" in content.lower()
    assert meta["truncated"] is False


def test_safe_read_sensitive_skipped(tmp_project):
    content, status, meta = safe_read_prefetch_content(".env", tmp_project)
    assert status == "sensitive_path"
    assert content is None


def test_safe_read_missing_file(tmp_project):
    content, status, meta = safe_read_prefetch_content("nonexistent.py", tmp_project)
    assert status == "file_not_found"
    assert content is None


def test_safe_read_large_file_truncated(tmp_project):
    content, status, meta = safe_read_prefetch_content(
        "large_file.py", tmp_project, max_lines=50, max_chars=4000
    )
    assert status == "ok"
    assert content is not None
    assert meta["truncated"] is True


def test_safe_read_path_escape_blocked(tmp_project):
    content, status, meta = safe_read_prefetch_content(
        "../../etc/passwd", tmp_project
    )
    assert status == "path_escape"
    assert content is None


# ── Context builder tests ────────────────────────────────────────


def test_build_context():
    ctx = build_read_prefetch_context(
        "def hello(): pass\n", "test.py", "test_reason", 0.95, truncated=False
    )
    assert "[READ PREFETCH CONTEXT]" in ctx
    assert "source_file: test.py" in ctx
    assert "reason: test_reason" in ctx
    assert "confidence: 0.95" in ctx
    assert "def hello(): pass" in ctx
    assert "```" in ctx
    assert "truncated" not in ctx


def test_build_context_truncated():
    ctx = build_read_prefetch_context(
        "line1\n", "big.py", "test", 0.80, truncated=True
    )
    assert "truncated: true" in ctx


# ── Env var switch tests ─────────────────────────────────────────


def test_read_prefetch_disabled_by_default(monkeypatch):
    monkeypatch.delenv(READ_PREFETCH_ENV_VAR, raising=False)
    assert is_read_prefetch_enabled() is False


def test_read_prefetch_enabled_via_env(monkeypatch):
    monkeypatch.setenv(READ_PREFETCH_ENV_VAR, "1")
    assert is_read_prefetch_enabled() is True


def test_read_prefetch_not_enabled_with_other_values(monkeypatch):
    monkeypatch.setenv(READ_PREFETCH_ENV_VAR, "0")
    assert is_read_prefetch_enabled() is False
    monkeypatch.setenv(READ_PREFETCH_ENV_VAR, "true")
    assert is_read_prefetch_enabled() is False

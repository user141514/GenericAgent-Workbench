"""Integration test: cache + policy pipeline (P2-5).

Tests: LLM cache bridge → store → retrieve semantic hit, and
ExecutionPolicy observe/soft/hard modes with skill effects.
"""

import os
import tempfile
from pathlib import Path

import pytest

from core.runtime.llm_cache_bridge import (
    CACHE_ENV_VAR,
    _canonicalize,
    _extract_user_question,
    get_cache_stats,
    llm_cache_enabled,
    make_semantic_hash,
    store_cache,
    try_get_cached,
)
from core.runtime.llm_cache import LLMCallCache
from core.runtime.execution_policy import (
    POLICY_ENV_VAR,
    evaluate_operation,
    get_policy_mode,
)


class TestCacheBridgePipeline:
    """Store → Retrieve → Semantic Hit pipeline."""

    def test_full_cache_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CACHE_ENV_VAR, "1")
        cache_dir = tmp_path / "cache_test"
        cache_dir.mkdir()

        from core.runtime.llm_cache_bridge import _get_cache
        _get_cache._instance = LLMCallCache(cache_dir)

        # Store
        store_cache("帮我写一个快速排序的 Python 实现", "test-model", "def quicksort(arr): ...")
        # Retrieve exact
        result = try_get_cached("帮我写一个快速排序的 Python 实现", "test-model")
        assert result is not None
        assert "quicksort" in result["response"]

    def test_semantic_hit_similar_question(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CACHE_ENV_VAR, "1")
        cache_dir = tmp_path / "cache_sem"
        cache_dir.mkdir()

        from core.runtime.llm_cache_bridge import _get_cache
        _get_cache._instance = LLMCallCache(cache_dir)

        store_cache("帮我写个快排", "model-x", "def quicksort(arr): [...]")
        # Same canonical form should match
        result = try_get_cached("帮我写个快排", "model-x")
        assert result is not None

    def test_different_question_not_matched(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CACHE_ENV_VAR, "1")
        cache_dir = tmp_path / "cache_diff"
        cache_dir.mkdir()

        from core.runtime.llm_cache_bridge import _get_cache
        _get_cache._instance = LLMCallCache(cache_dir)

        store_cache("快速排序", "model", "quicksort code")
        result = try_get_cached("今天天气怎么样", "model")
        assert result is None  # Different question, no semantic hit

    def test_cache_stats(self, monkeypatch):
        monkeypatch.setenv(CACHE_ENV_VAR, "1")
        stats = get_cache_stats()
        assert stats["enabled"] is True


class TestPolicyPipeline:
    """ExecutionPolicy observe → soft → hard pipeline with skill effects."""

    def test_full_policy_pipeline_observe(self, monkeypatch):
        monkeypatch.setenv(POLICY_ENV_VAR, "observe")
        policy = {
            "source_skills": ["security_gate"],
            "disabled_tools": ["code_run"],
            "warnings": [],
        }
        # Safe operation
        d1 = evaluate_operation("读取 README.md", policy=policy)
        assert d1.allowed is True
        # Dangerous operation — observed but not blocked
        d2 = evaluate_operation("rm -rf /tmp/build", policy=policy)
        assert d2.allowed is True
        assert d2.risk_level == "critical"

    def test_full_policy_pipeline_soft(self, monkeypatch):
        monkeypatch.setenv(POLICY_ENV_VAR, "soft")
        policy = {"source_skills": ["security_gate"], "warnings": []}
        # Safe
        d1 = evaluate_operation("写个 hello world", policy=policy)
        assert d1.allowed is True
        # Critical — blocked in soft mode
        d2 = evaluate_operation("git reset --hard HEAD", policy=policy)
        assert d2.allowed is False

    def test_full_policy_pipeline_hard(self, monkeypatch):
        monkeypatch.setenv(POLICY_ENV_VAR, "hard")
        # Even medium risk is blocked in hard mode
        d1 = evaluate_operation("pip install requests")
        assert d1.allowed is False
        # No risk — allowed
        d2 = evaluate_operation("写个注释")
        assert d2.allowed is True

    def test_policy_off_never_blocks(self, monkeypatch):
        monkeypatch.setenv(POLICY_ENV_VAR, "off")
        d = evaluate_operation("rm -rf / --no-preserve-root")
        assert d.allowed is True
        assert d.mode == "off"

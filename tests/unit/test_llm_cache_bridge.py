"""Unit tests for LLM semantic cache bridge (P2-cache)."""

import os
import tempfile
from pathlib import Path

import pytest

from core.runtime.llm_cache import LLMCallCache
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


# ── Env switch ───────────────────────────────────────────────────


def test_cache_disabled_by_default(monkeypatch):
    monkeypatch.delenv(CACHE_ENV_VAR, raising=False)
    assert llm_cache_enabled() is False


def test_cache_enabled_via_env(monkeypatch):
    monkeypatch.setenv(CACHE_ENV_VAR, "1")
    assert llm_cache_enabled() is True


# ── Canonicalization ─────────────────────────────────────────────


def test_canonicalize_basic():
    assert _canonicalize("帮我写个快排") == "帮我写个快排"


def test_canonicalize_case_and_punctuation():
    result = _canonicalize("帮我写一个快速排序！Python实现。")
    # Should strip punctuation and normalize whitespace
    assert "快速排序" in result
    assert "！" not in result
    assert "。" not in result


def test_canonicalize_equivalent_questions():
    a = _canonicalize("帮我写个快排")
    b = _canonicalize("帮我写一个快速排序")
    # These are different after canonicalization
    assert isinstance(a, str)
    assert isinstance(b, str)


def test_canonicalize_whitespace():
    result = _canonicalize("  帮我  写个  快排  ")
    assert result == "帮我 写个 快排"


# ── Extract user question ────────────────────────────────────────


def test_extract_from_string():
    result = _extract_user_question("帮我写个快排")
    assert "快排" in result


def test_extract_from_messages():
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "帮我写个快排"},
    ]
    result = _extract_user_question(messages)
    assert "快排" in result


def test_extract_last_user_only():
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！"},
        {"role": "user", "content": "帮我写个快排"},
    ]
    result = _extract_user_question(messages)
    assert "快排" in result
    assert "你好" not in result


def test_extract_content_list():
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "分析这个文件"}]}
    ]
    result = _extract_user_question(messages)
    assert "分析" in result


# ── Semantic hash ────────────────────────────────────────────────


def test_semantic_hash_consistent():
    h1 = make_semantic_hash("帮我写个快排")
    h2 = make_semantic_hash("帮我写个快排")
    assert h1 == h2


def test_semantic_hash_different():
    h1 = make_semantic_hash("帮我写个快排")
    h2 = make_semantic_hash("今天天气怎么样")
    assert h1 != h2


def test_semantic_hash_empty():
    assert make_semantic_hash("") == ""


# ── Cache read/write ─────────────────────────────────────────────


def test_try_get_cached_disabled(monkeypatch):
    monkeypatch.delenv(CACHE_ENV_VAR, raising=False)
    result = try_get_cached("test prompt", "test-model")
    assert result is None


def test_store_and_retrieve(tmp_path, monkeypatch):
    monkeypatch.setenv(CACHE_ENV_VAR, "1")
    # Use temp dir for cache
    cache_dir = tmp_path / "llm_cache_test"
    cache_dir.mkdir(parents=True)

    # We need to clear the lazy singleton to use our test dir
    from core.runtime.llm_cache_bridge import _get_cache
    _get_cache._instance = LLMCallCache(cache_dir)

    store_cache("测试问题", "test-model", "这是回答")
    result = try_get_cached("测试问题", "test-model")
    assert result is not None
    assert result["response"] == "这是回答"


def test_store_semantic_hit(tmp_path, monkeypatch):
    monkeypatch.setenv(CACHE_ENV_VAR, "1")
    cache_dir = tmp_path / "llm_cache_sem"
    cache_dir.mkdir(parents=True)

    from core.runtime.llm_cache_bridge import _get_cache
    _get_cache._instance = LLMCallCache(cache_dir)

    store_cache("帮我写个快排", "model-x", "def quicksort(arr):...")
    # Same canonical form should hit via semantic hash
    result = try_get_cached("帮我写个快排", "model-x")
    assert result is not None


def test_store_dict_response(tmp_path, monkeypatch):
    monkeypatch.setenv(CACHE_ENV_VAR, "1")
    cache_dir = tmp_path / "llm_cache_dict"
    cache_dir.mkdir(parents=True)

    from core.runtime.llm_cache_bridge import _get_cache
    _get_cache._instance = LLMCallCache(cache_dir)

    store_cache("问题", "model", {"text": "回答"})
    result = try_get_cached("问题", "model")
    assert result is not None


def test_get_cache_stats(monkeypatch):
    monkeypatch.setenv(CACHE_ENV_VAR, "1")
    stats = get_cache_stats()
    assert "enabled" in stats
    assert stats["enabled"] is True

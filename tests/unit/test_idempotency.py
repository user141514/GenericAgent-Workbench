"""
Idempotency tests (P1 from coding-improve.md §5.3).

Verifies that running the same operation twice produces consistent results.
"""

from __future__ import annotations

import pytest

from core.router_rules import RouterRules, quick_route
from core.runtime.shared_store import SharedArtifactStore


def route(query: str):
    """Wrapper matching RouterRules.match API."""
    return RouterRules.match(query).target


class TestRouterIdempotency:
    """Router rules must return the same result for the same input."""

    QUERIES = [
        ("帮我写一个登录页面", "code"),
        ("审查这段代码的安全性", "review"),
        ("搜索 Python asyncio 的用法", "research"),
        ("你好世界", "chat"),
    ]

    @pytest.mark.parametrize("query,expected", QUERIES)
    def test_route_same_query_twice(self, query, expected):
        """Same query routed twice should give same agent."""
        result1 = route(query)
        result2 = route(query)
        assert result1 == result2, f"non-idempotent: {result1} vs {result2}"

    @pytest.mark.parametrize("query,expected", QUERIES)
    def test_quick_route_same_query_twice(self, query, expected):
        """Same query quick-routed twice should give same agent."""
        result1 = quick_route(query)
        result2 = quick_route(query)
        assert result1 == result2, f"non-idempotent: {result1} vs {result2}"

    def test_route_batch_idempotent(self):
        """Batch processing should be idempotent."""
        results1 = [route(q) for q, _ in self.QUERIES]
        results2 = [route(q) for q, _ in self.QUERIES]
        assert results1 == results2


class TestSharedStoreIdempotency:
    """Shared store operations must be idempotent."""

    def test_write_same_key_overwrite(self):
        """Writing the same key twice overwrites cleanly."""
        store = SharedArtifactStore()
        v1 = store.write("x.py", "content1")
        v2 = store.write("x.py", "content1")
        assert v2 == v1 + 1
        assert store.read("x.py").content == "content1"

    def test_delete_recreate_cycle(self):
        """Delete then recreate should be clean."""
        store = SharedArtifactStore()
        store.write("x.py", "hello")
        store.delete("x.py")
        store.write("x.py", "hello")
        assert store.read("x.py") is not None
        assert store.read("x.py").version == 1

    def test_read_absent_is_stable(self):
        """Reading a missing key twice returns None both times."""
        store = SharedArtifactStore()
        assert store.read("nonexistent") is None
        assert store.read("nonexistent") is None

    def test_list_keys_idempotent(self):
        """Listing keys twice without mutation gives same result."""
        store = SharedArtifactStore()
        store.write("a.py", "1")
        store.write("b.py", "2")
        keys1 = sorted(store.list_keys())
        keys2 = sorted(store.list_keys())
        assert keys1 == keys2 == ["a.py", "b.py"]


class TestBoundaryInputs:
    """Boundary and edge case inputs (P1 from coding-improve.md §5.3)."""

    def test_empty_string(self):
        """Empty string should not crash the router."""
        result = route("")
        assert result is None or isinstance(result, str)

    def test_whitespace_only(self):
        """Whitespace-only input should not crash."""
        for inp in ["   ", "\t", "\n", "  \n\t  "]:
            result = route(inp)
            assert result is None or isinstance(result, str)

    def test_unicode_special_chars(self):
        """Unicode and special characters should not crash."""
        queries = [
            "emoji test 🚀🔥💻",
            "japanese こんにちは世界",
            "math symbols ∑∏∫√∞≈",
            "combined 中文 + 日本語 + 한국어 + English",
        ]
        for q in queries:
            result = route(q)
            assert isinstance(result, str) or result is None

    def test_very_long_query(self):
        """Very long query should not crash or hang."""
        long_query = "帮我写代码 " * 500  # ~3500 chars
        result = route(long_query)
        assert isinstance(result, str) or result is None

    def test_single_char_query(self):
        """Single character query should handle gracefully."""
        for ch in ["a", "1", "?", "。", "！"]:
            result = route(ch)
            assert result is None or isinstance(result, str)

    def test_control_characters(self):
        """Control characters should not crash."""
        result = route("hello\x00world")
        assert result is None or isinstance(result, str)

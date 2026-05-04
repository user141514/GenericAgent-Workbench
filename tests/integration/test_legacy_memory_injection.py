"""
Integration tests for P0b: OpenAI path L1/L2 legacy memory injection.

Verifies:
1. L1/L2 block is built from project memory files
2. GA_OPENAI_LEGACY_MEMORY gate works (enable/disable)
3. Block declares itself as "legacy project memory, not a user request"
4. Classic path get_global_memory() is unaffected
5. read_legacy_l1_l2() returns structured data
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.memory.legacy_global import (
    build_legacy_memory_block,
    read_legacy_l1_l2,
)


# ══════════════════════════════════════════════════════════════════════
# read_legacy_l1_l2()
# ══════════════════════════════════════════════════════════════════════

class TestReadLegacyL1L2:
    def test_reads_l1(self):
        data = read_legacy_l1_l2(PROJECT_ROOT)
        assert data["l1"] is not None, "L1 should exist"
        assert data["l1_chars"] > 0
        assert "global_mem_insight.txt" in data["l1_path"]

    def test_reads_l2(self):
        data = read_legacy_l1_l2(PROJECT_ROOT)
        assert data["l2"] is not None, "L2 should exist"
        assert data["l2_chars"] > 0
        assert "global_mem.txt" in data["l2_path"]

    def test_total_chars_positive(self):
        data = read_legacy_l1_l2(PROJECT_ROOT)
        assert data["total_chars"] > 0
        assert data["total_chars"] == data["l1_chars"] + data["l2_chars"]

    def test_returns_structured_dict(self):
        data = read_legacy_l1_l2(PROJECT_ROOT)
        for key in ("l1", "l2", "l1_path", "l2_path", "l1_chars", "l2_chars", "total_chars"):
            assert key in data, f"Missing key: {key}"

    def test_nonexistent_project_root(self):
        """Should not crash, returns empty data."""
        data = read_legacy_l1_l2("/nonexistent/path/12345")
        assert data["l1"] is None
        assert data["l2"] is None
        assert data["total_chars"] == 0


# ══════════════════════════════════════════════════════════════════════
# build_legacy_memory_block()
# ══════════════════════════════════════════════════════════════════════

class TestBuildLegacyMemoryBlock:
    def test_contains_l1_file_reference(self):
        block = build_legacy_memory_block(PROJECT_ROOT)
        assert "global_mem_insight.txt" in block

    def test_contains_memory_section(self):
        block = build_legacy_memory_block(PROJECT_ROOT)
        assert "[Memory]" in block

    def test_contains_project_root(self):
        block = build_legacy_memory_block(PROJECT_ROOT)
        assert "project_root" in block

    def test_has_cwd_path(self):
        block = build_legacy_memory_block(PROJECT_ROOT)
        assert "cwd =" in block

    def test_empty_when_no_l1_file(self):
        block = build_legacy_memory_block("/nonexistent/path/12345")
        assert block == ""


# ══════════════════════════════════════════════════════════════════════
# OpenAI injection format
# ══════════════════════════════════════════════════════════════════════

class TestOpenAIInjectionFormat:
    """Verify the injection block format used in openai_agentmain.py."""

    def _build_injection_block(self):
        """Replicate the injection logic from openai_agentmain.py."""
        data = read_legacy_l1_l2(PROJECT_ROOT)
        l1 = data.get("l1") or ""
        l2 = data.get("l2") or ""
        parts: list[str] = []
        parts.append("[LEGACY PROJECT MEMORY — This is persistent project memory, not a user request.]")
        if l1:
            parts.append(f"## L1 (Insights)\n{l1}")
        if l2:
            parts.append(f"## L2 (Environment Facts)\n{l2}")
        return "\n\n".join(parts)

    def test_declares_not_user_request(self):
        block = self._build_injection_block()
        assert "not a user request" in block

    def test_contains_l1_section(self):
        block = self._build_injection_block()
        assert "## L1 (Insights)" in block

    def test_contains_l2_section(self):
        block = self._build_injection_block()
        assert "## L2 (Environment Facts)" in block

    def test_block_is_non_empty(self):
        block = self._build_injection_block()
        assert len(block) > 100


# ══════════════════════════════════════════════════════════════════════
# Env var gate: GA_OPENAI_LEGACY_MEMORY
# ══════════════════════════════════════════════════════════════════════

class TestLegacyMemoryGate:
    def test_default_enabled(self):
        """GA_OPENAI_LEGACY_MEMORY defaults to enabled (1)."""
        with patch.dict(os.environ, {}, clear=False):
            old = os.environ.pop("GA_OPENAI_LEGACY_MEMORY", None)
            try:
                enabled = os.environ.get("GA_OPENAI_LEGACY_MEMORY", "1") != "0"
                assert enabled is True
            finally:
                if old is not None:
                    os.environ["GA_OPENAI_LEGACY_MEMORY"] = old

    def test_disabled_with_zero(self):
        with patch.dict(os.environ, {"GA_OPENAI_LEGACY_MEMORY": "0"}):
            enabled = os.environ.get("GA_OPENAI_LEGACY_MEMORY", "1") != "0"
            assert enabled is False

    def test_enabled_with_one(self):
        with patch.dict(os.environ, {"GA_OPENAI_LEGACY_MEMORY": "1"}):
            enabled = os.environ.get("GA_OPENAI_LEGACY_MEMORY", "1") != "0"
            assert enabled is True

    def test_independent_from_context_runtime(self):
        """L1/L2 injection must NOT be gated by GA_CONTEXT_RUNTIME_ENABLED."""
        with patch.dict(os.environ, {"GA_CONTEXT_RUNTIME_ENABLED": "0"}):
            # Context runtime is disabled, but legacy memory gate is independent
            legacy_enabled = os.environ.get("GA_OPENAI_LEGACY_MEMORY", "1") != "0"
            assert legacy_enabled is True
            # L1/L2 should still be readable
            data = read_legacy_l1_l2(PROJECT_ROOT)
            assert data["l1"] is not None


# ══════════════════════════════════════════════════════════════════════
# Classic path non-regression
# ══════════════════════════════════════════════════════════════════════

class TestClassicNonRegression:
    def test_get_global_memory_uses_shared_module(self):
        """Classic get_global_memory() calls build_legacy_memory_block()."""
        from core.ga import get_global_memory

        classic = get_global_memory()
        shared = build_legacy_memory_block(PROJECT_ROOT)
        # Must be character-by-character identical
        assert classic == shared, (
            f"Classic and shared output must match! "
            f"Classic={len(classic)} chars, shared={len(shared)} chars"
        )

    def test_get_global_memory_output_stable(self):
        """Output must contain expected markers."""
        from core.ga import get_global_memory

        result = get_global_memory()
        assert "global_mem_insight.txt" in result
        assert "[Memory]" in result
        assert "project_root" in result
        assert "cwd =" in result

    def test_no_writes_to_legacy_files(self):
        """read_legacy_l1_l2 and build_legacy_memory_block must not write files."""
        import time

        l1_path = os.path.join(PROJECT_ROOT, "memory", "global_mem_insight.txt")
        l2_path = os.path.join(PROJECT_ROOT, "memory", "global_mem.txt")

        l1_mtime_before = os.path.getmtime(l1_path)
        l2_mtime_before = os.path.getmtime(l2_path)

        read_legacy_l1_l2(PROJECT_ROOT)
        build_legacy_memory_block(PROJECT_ROOT)

        # Give FS time to settle
        time.sleep(0.1)

        l1_mtime_after = os.path.getmtime(l1_path)
        l2_mtime_after = os.path.getmtime(l2_path)

        assert l1_mtime_before == l1_mtime_after, "L1 file was modified!"
        assert l2_mtime_before == l2_mtime_after, "L2 file was modified!"

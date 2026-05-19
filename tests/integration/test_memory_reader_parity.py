"""
Parity tests: canonical MemoryReader vs legacy read paths.

Verifies that core.context.memory_reader.MemoryReader returns the same
L1/L2 content as core.memory.legacy_global.read_legacy_l1_l2().

Phase M3 — read-only. No runtime behavior is changed by these tests.

Usage:
    pytest tests/integration/test_memory_reader_parity.py -v
"""

import importlib
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# core/context/memory_reader.py uses `str | None` syntax (PEP 604, Python 3.10+).
# Under Python < 3.10, these modules cannot be imported. The parity tests
# require loading the module, so they must be skipped on older Python versions.
_MIN_PYTHON = (3, 10)
_py_version = sys.version_info[:2]
CAN_LOAD = _py_version >= _MIN_PYTHON

skip_if_py_too_old = pytest.mark.skipif(
    not CAN_LOAD,
    reason=(
        f"Python {'.'.join(map(str, _MIN_PYTHON))}+ required "
        f"(PEP 604 union types). Current: {sys.version}"
    ),
)


# ═══ Safe module loader (bypasses __init__.py chains on Python < 3.10) ═══

def _remove_suffix(s, suffix):
    """Python 3.7 compatible remove_suffix."""
    if s.endswith(suffix):
        return s[: -len(suffix)]
    return s


def _load_module_direct(module_path: str):
    """Load a .py module. Uses normal import on Python >= 3.10, falls back
    to isolated file loading on older Python versions."""
    parts = _remove_suffix(module_path.replace("/", ".").replace("\\", "."), ".py")

    # On Python 3.10+, use normal import (no syntax issues with PEP 604)
    if sys.version_info >= (3, 10):
        import importlib as _il
        return _il.import_module(parts)

    # Legacy path for Python < 3.10: load module file directly with fake stubs
    file_path = PROJECT_ROOT / module_path.replace("/", os.sep)
    if not file_path.exists():
        raise FileNotFoundError(f"Module not found: {file_path}")

    spec = importlib.util.spec_from_file_location(parts, str(file_path))
    mod = importlib.util.module_from_spec(spec)

    # Provide minimal package stubs for relative imports
    if "context" in module_path:
        class _FakeContextModule:
            @staticmethod
            def _context_enabled():
                return os.environ.get("GA_CONTEXT_RUNTIME_ENABLED", "1") == "1"
        # Use setdefault to avoid clobbering real packages
        sys.modules.setdefault("core.context", _FakeContextModule())
        sys.modules.setdefault("core.context.__init__", _FakeContextModule())

    if "memory" in module_path:
        class _FakeMemoryModule:
            pass
        sys.modules.setdefault("core.memory", _FakeMemoryModule())
        sys.modules.setdefault("core.memory.__init__", _FakeMemoryModule())

    sys.modules[parts] = mod
    try:
        spec.loader.exec_module(mod)
    except (ImportError, SyntaxError) as e:
        pytest.skip(f"Cannot import {module_path} (pre-existing env issue): {e}")
    return mod


def _load_legacy_global():
    """Load core/memory/legacy_global.py. Uses normal import on Python >= 3.10."""
    if sys.version_info >= (3, 10):
        import core.memory.legacy_global as mod
        return mod

    # Legacy path for Python < 3.10
    mod_path = str(PROJECT_ROOT / "core" / "memory" / "legacy_global.py")

    class _FakeMemoryModule:
        pass
    sys.modules.setdefault("core.memory", _FakeMemoryModule())
    sys.modules.setdefault("core.memory.__init__", _FakeMemoryModule())

    spec = importlib.util.spec_from_file_location("core.memory.legacy_global", mod_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["core.memory.legacy_global"] = mod
    try:
        spec.loader.exec_module(mod)
    except SyntaxError as e:
        pytest.skip(f"Cannot import legacy_global.py (encoding issue): {e}")
    return mod


# ═══ Fixtures ══════════════════════════════════════════════════════════════

@pytest.fixture
def temp_memory_dir():
    """Create a temporary memory/ directory with known L1/L2 content."""
    with tempfile.TemporaryDirectory() as tmp:
        mem_dir = Path(tmp) / "memory"
        mem_dir.mkdir()

        l1 = "## L1 Insight\n\n- Key insight 1: test\n- Key insight 2: parity check\n"
        l2 = "## L2 Environment\n\n- Python 3.11\n- Project: test-parity\n"

        (mem_dir / "global_mem_insight.txt").write_text(l1, encoding="utf-8")
        (mem_dir / "global_mem.txt").write_text(l2, encoding="utf-8")

        yield str(tmp), l1, l2


# ═══ Read parity ════════════════════════════════════════════════════════════

@skip_if_py_too_old
def test_l1_l2_content_parity(temp_memory_dir):
    """I2: MemoryReader.read_global_memory() returns same L1/L2 as legacy path."""
    tmp, l1_expected, l2_expected = temp_memory_dir

    legacy_mod = _load_legacy_global()
    legacy = legacy_mod.read_legacy_l1_l2(project_root=tmp)

    reader_mod = _load_module_direct("core/context/memory_reader.py")
    reader = reader_mod.MemoryReader(project_root=tmp)
    canonical = reader.read_global_memory()

    assert canonical.get("l1") == legacy.get("l1")
    assert canonical.get("l1") == l1_expected
    assert canonical.get("l2") == legacy.get("l2")
    assert canonical.get("l2") == l2_expected


@skip_if_py_too_old
def test_standalone_wrapper_structure(temp_memory_dir):
    """I2b: Standalone read_global_memory() has correct dict structure."""
    tmp, l1_expected, l2_expected = temp_memory_dir

    reader_mod = _load_module_direct("core/context/memory_reader.py")
    result = reader_mod.read_global_memory(project_root=tmp)

    assert result["global_mem_insight"] == l1_expected
    assert result["global_mem"] == l2_expected
    assert result["total_chars"] == len(l1_expected) + len(l2_expected)

    labels = {s["label"] for s in result["sources"]}
    assert labels == {"L1", "L2"}


@skip_if_py_too_old
def test_memory_reader_blocks_structure(temp_memory_dir):
    """I2c: MemoryReader produces properly structured MemoryBlocks."""
    tmp, _, _ = temp_memory_dir

    reader_mod = _load_module_direct("core/context/memory_reader.py")
    reader = reader_mod.MemoryReader(project_root=tmp)
    blocks = reader.read_global_memory_blocks()

    assert len(blocks) == 2
    assert blocks[0].source == "L1"
    assert blocks[0].source_priority == "primary"
    assert blocks[0].relevance_score == 1.0
    assert blocks[1].source == "L2"
    assert blocks[1].source_priority == "primary"
    assert blocks[1].relevance_score == 0.9


# ═══ Working memory ═════════════════════════════════════════════════════════

@skip_if_py_too_old
def test_working_memory_format():
    """read_working_memory produces correct format."""
    reader_mod = _load_module_direct("core/context/memory_reader.py")
    history = ["[USER]: hello", "[Agent] replied"]
    result = reader_mod.read_working_memory(history)
    assert "[WORKING MEMORY]" in result
    assert "<history>" in result
    assert "[USER]: hello" in result


@skip_if_py_too_old
def test_working_memory_empty():
    """read_working_memory returns empty string for empty history."""
    reader_mod = _load_module_direct("core/context/memory_reader.py")
    assert reader_mod.read_working_memory([]) == ""


@skip_if_py_too_old
def test_working_memory_truncation():
    """read_working_memory respects max_items."""
    reader_mod = _load_module_direct("core/context/memory_reader.py")
    history = [f"[USER]: msg {i:02d}" for i in range(50)]
    result = reader_mod.read_working_memory(history, max_items=5)
    # Only last 5 entries should appear
    for i in range(45):
        assert f"msg {i:02d}" not in result, f"msg {i:02d} should NOT be in truncated result"
    for i in range(45, 50):
        assert f"msg {i:02d}" in result, f"msg {i:02d} should be in truncated result"


# ═══ Scoped query ══════════════════════════════════════════════════════════

@skip_if_py_too_old
def test_scoped_query_respects_budget(temp_memory_dir):
    """scoped_query stays within max_chars."""
    tmp, _, _ = temp_memory_dir
    reader_mod = _load_module_direct("core/context/memory_reader.py")
    reader = reader_mod.MemoryReader(project_root=tmp)
    bundle = reader.scoped_query(user_query="test", max_chars=500)
    assert bundle.total_chars <= 500


@skip_if_py_too_old
def test_scoped_query_primary_only(temp_memory_dir):
    """scoped_query without user_query returns only primary blocks."""
    tmp, _, _ = temp_memory_dir
    reader_mod = _load_module_direct("core/context/memory_reader.py")
    reader = reader_mod.MemoryReader(project_root=tmp)
    bundle = reader.scoped_query(user_query="", max_chars=2000)
    for block in bundle.blocks:
        assert block.source_priority == "primary"


# ═══ Edge cases ════════════════════════════════════════════════════════════

@skip_if_py_too_old
def test_missing_memory_files():
    """MemoryReader handles missing files gracefully."""
    with tempfile.TemporaryDirectory() as tmp:
        reader_mod = _load_module_direct("core/context/memory_reader.py")
        reader = reader_mod.MemoryReader(project_root=tmp)
        result = reader.read_global_memory()
        assert result == {"l1": "", "l2": ""}


@skip_if_py_too_old
def test_legacy_parity_missing_files():
    """Both paths handle missing files identically."""
    with tempfile.TemporaryDirectory() as tmp:
        legacy_mod = _load_legacy_global()
        legacy = legacy_mod.read_legacy_l1_l2(project_root=tmp)

        reader_mod = _load_module_direct("core/context/memory_reader.py")
        canonical = reader_mod.MemoryReader(project_root=tmp).read_global_memory()

        assert (canonical.get("l1") or None) == legacy.get("l1")
        assert (canonical.get("l2") or None) == legacy.get("l2")


# ═══ Source report ═════════════════════════════════════════════════════════

@skip_if_py_too_old
def test_build_memory_source_report():
    """build_memory_source_report returns expected keys."""
    reader_mod = _load_module_direct("core/context/memory_reader.py")
    report = reader_mod.build_memory_source_report()
    for key in ("l1_chars", "l2_chars", "structured_enabled", "total_sources"):
        assert key in report, f"Missing key: {key}"

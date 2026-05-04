"""Unit tests for core/memory/reader.py (P2-2)."""

import os

import pytest

from core.memory.reader import (
    STRUCTURED_MEMORY_ENV_VAR,
    build_memory_source_report,
    read_global_memory,
    read_working_memory,
    search_structured_memory,
    structured_memory_enabled,
)


# ── structured_memory_enabled ─────────────────────────────────────


def test_structured_disabled_by_default(monkeypatch):
    monkeypatch.delenv(STRUCTURED_MEMORY_ENV_VAR, raising=False)
    assert structured_memory_enabled() is False


def test_structured_enabled_via_env(monkeypatch):
    monkeypatch.setenv(STRUCTURED_MEMORY_ENV_VAR, "1")
    assert structured_memory_enabled() is True


# ── read_global_memory ────────────────────────────────────────────


def test_read_global_memory_from_real_project():
    """Read the actual project memory files — they exist on disk."""
    result = read_global_memory()
    assert result["global_mem_insight"] is not None
    assert isinstance(result["sources"], list)
    assert len(result["sources"]) >= 1
    assert result["total_chars"] > 0


def test_read_global_memory_has_l1_l2_labels():
    result = read_global_memory()
    labels = {s["label"] for s in result["sources"]}
    assert "L1" in labels


# ── read_working_memory ────────────────────────────────────────────


def test_read_working_memory_empty():
    assert read_working_memory([]) == ""


def test_read_working_memory_with_items():
    result = read_working_memory(["turn 1", "turn 2"], max_items=2)
    assert "[WORKING MEMORY]" in result
    assert "turn 1" in result
    assert "turn 2" in result


def test_read_working_memory_truncates():
    result = read_working_memory([f"line {i}" for i in range(100)], max_items=5)
    assert "line 0" not in result
    assert "line 95" in result


# ── search_structured_memory ──────────────────────────────────────


def test_search_disabled_by_default():
    result = search_structured_memory("test query")
    assert result["disabled"] is True
    assert result["results"] == []


def test_search_missing_db(monkeypatch):
    monkeypatch.setenv(STRUCTURED_MEMORY_ENV_VAR, "1")
    result = search_structured_memory("test", db_path="/nonexistent/catalog.sqlite")
    assert result["disabled"] is False
    assert result["error"] == "database not found"


# ── build_memory_source_report ────────────────────────────────────


def test_report_has_expected_keys():
    report = build_memory_source_report()
    assert "l1_chars" in report
    assert "l2_chars" in report
    assert "structured_enabled" in report
    assert "total_sources" in report


def test_report_values_are_positive():
    report = build_memory_source_report()
    assert report["total_sources"] >= 1
    assert isinstance(report["l1_chars"], int)

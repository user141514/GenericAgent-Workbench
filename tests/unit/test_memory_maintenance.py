"""Unit tests for autonomous memory maintenance (P3)."""

import re
from pathlib import Path

import pytest

from core.memory.maintenance import (
    _hash_line,
    _entry_age_days,
    build_scoped_memory_context,
    dedup_inbox,
    run_memory_maintenance,
    score_inbox_entries,
)


# ── Dedup tests ────────────────────────────────────────────────────


def test_dedup_empty():
    assert dedup_inbox("/nonexistent/inbox.md") == {"removed": 0, "kept": 0, "report": "inbox not found"}


def test_dedup_no_duplicates(tmp_path):
    inbox = tmp_path / "inbox.md"
    inbox.write_text("## Entry 1\n- question 1\n\n## Entry 2\n- question 2\n", encoding="utf-8")
    result = dedup_inbox(inbox)
    assert result["removed"] == 0
    assert result["kept"] == 2


def test_dedup_removes_duplicates(tmp_path):
    inbox = tmp_path / "inbox.md"
    entry = "## Duplicate Entry\n- Saved At: 2026-05-01\n- question A"
    inbox.write_text(f"{entry}\n\n{entry}\n\n## Unique\n- question B\n", encoding="utf-8")
    result = dedup_inbox(inbox)
    assert result["removed"] == 1
    assert result["kept"] == 2
    content = inbox.read_text(encoding="utf-8")
    assert content.count("## Duplicate") == 1


# ── Scoring tests ──────────────────────────────────────────────────


def test_score_entries_empty(tmp_path):
    inbox = tmp_path / "empty.md"
    inbox.write_text("# Header\n", encoding="utf-8")
    scores = score_inbox_entries(inbox)
    assert scores == []


def test_score_entries_recent_ranks_higher(tmp_path):
    inbox = tmp_path / "scored.md"
    inbox.write_text(
        "## Recent Entry\n"
        "<!-- source: recent.txt -->\n"
        "- Saved At: 2026-05-04\n"
        "- User Questions:\n"
        "  - Q1\n"
        "  - Q2\n"
        "- Files Touched:\n"
        "  - file1.py\n"
        "\n"
        "## Old Entry\n"
        "<!-- source: old.txt -->\n"
        "- Saved At: 2026-01-01\n"
        "- User Questions:\n"
        "  - Q3\n",
        encoding="utf-8",
    )
    scores = score_inbox_entries(inbox)
    assert len(scores) >= 2
    assert scores[0]["score"] > scores[-1]["score"]


def test_score_files_touched_bonus(tmp_path):
    inbox = tmp_path / "files.md"
    inbox.write_text(
        "## Code Heavy\n"
        "<!-- source: code.txt -->\n"
        "- Saved At: 2026-05-04\n"
        "- Files Touched:\n"
        "  - a.py\n  - b.py\n  - c.py\n"
        "  - d.py\n  - e.py\n",
        encoding="utf-8",
    )
    scores = score_inbox_entries(inbox)
    assert len(scores) == 1
    assert scores[0]["score"] >= 3.0  # at least 3 points from 5 file touches


# ── Scoped context tests ──────────────────────────────────────────


def test_build_scoped_context_keyword_match():
    result = build_scoped_memory_context("Python 版本 3.11")
    assert "context" in result
    assert "total_chars" in result


def test_build_scoped_context_no_match():
    result = build_scoped_memory_context("xyzzy_nonexistent_keyword_12345")
    assert result["total_chars"] >= 0


# ── Full maintenance orchestration ──────────────────────────────────


def test_run_memory_maintenance():
    report = run_memory_maintenance()
    assert "ran_at" in report
    assert "tasks" in report
    assert "dedup" in report["tasks"]
    assert "scored_entries" in report["tasks"]


# ── Hash helper ────────────────────────────────────────────────────


def test_hash_deterministic():
    assert _hash_line("hello") == _hash_line("hello")


def test_hash_different():
    assert _hash_line("hello") != _hash_line("world")


# ── Age extraction ─────────────────────────────────────────────────


def test_entry_age_valid():
    age = _entry_age_days("## Test\n- Saved At: 2026-05-04\n")
    assert age is not None
    assert age >= 0


def test_entry_age_missing():
    age = _entry_age_days("## Test\n- No date here\n")
    assert age is None

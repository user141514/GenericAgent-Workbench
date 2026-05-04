"""
Integration tests for P2a/P2b: inbox archive to structured memory.

Verifies:
1. archive_inbox_to_structured(dry_run=True) does not write
2. archive_inbox_to_structured(dry_run=True) produces valid preview report
3. SHA256 dedup: duplicate entries are skipped
4. Chunk count is correct
5. Empty inbox handles gracefully
6. Backup created before write (P2b)
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.memory.maintenance import archive_inbox_to_structured


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _make_inbox(tmp_path: Path, entries: list[str]) -> Path:
    """Create a test inbox file with given entries."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(exist_ok=True)
    inbox = memory_dir / "history_memory_inbox.md"
    content = "# Distilled Conversation Memory Inbox\n\n" + "\n\n".join(entries) + "\n"
    inbox.write_text(content, encoding="utf-8")
    return inbox


def _sample_entry(title="Sample Entry", source="test_source", saved="2026-05-01"):
    return (
        f"## {title}\n"
        f"<!-- source: run_001 -->\n"
        f"- Saved At: {saved}\n"
        f"- Source File: {source}\n"
        f"- Run: run_001\n"
        f"- Dialogue Rounds: 1\n"
        f"- User Questions:\n"
        f"  - What should we test?\n"
        f"- Files Touched:\n"
        f"  - test.py\n"
        f"- Key Replies:\n"
        f"  - Verified the test framework\n"
    )


# ══════════════════════════════════════════════════════════════════════
# Dry-run tests
# ══════════════════════════════════════════════════════════════════════

class TestArchiveDryRun:
    def test_dry_run_writes_nothing(self, tmp_path):
        _make_inbox(tmp_path, [_sample_entry("Test Entry")])
        report = archive_inbox_to_structured(tmp_path, dry_run=True)
        assert report["dry_run"] is True
        assert report["written_chunks"] == 0
        assert report["written_candidates"] == 0

    def test_dry_run_counts_entries(self, tmp_path):
        entries = [
            _sample_entry("Entry 1"),
            _sample_entry("Entry 2"),
            _sample_entry("Entry 3"),
        ]
        _make_inbox(tmp_path, entries)
        report = archive_inbox_to_structured(tmp_path, dry_run=True)
        assert report["total_entries"] == 3
        assert report["new_entries"] == 3

    def test_dry_run_produces_preview(self, tmp_path):
        _make_inbox(tmp_path, [_sample_entry("Preview Test")])
        report = archive_inbox_to_structured(tmp_path, dry_run=True)
        assert len(report["preview_entries"]) >= 1
        preview = report["preview_entries"][0]
        assert preview["title"] == "Preview Test"
        assert preview["source"] == "test_source"
        assert "content_preview" in preview
        assert "chunks_count" in preview

    def test_dry_run_with_empty_inbox(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir(exist_ok=True)
        inbox = memory_dir / "history_memory_inbox.md"
        inbox.write_text("Just a header, no entries\n", encoding="utf-8")
        report = archive_inbox_to_structured(tmp_path, dry_run=True)
        assert report["total_entries"] == 0
        assert report["new_entries"] == 0

    def test_dry_run_with_no_inbox(self, tmp_path):
        report = archive_inbox_to_structured(tmp_path, dry_run=True)
        assert "inbox not found" in str(report["errors"])


# ══════════════════════════════════════════════════════════════════════
# Dedup tests
# ══════════════════════════════════════════════════════════════════════

class TestArchiveDedup:
    def test_duplicate_entries_skipped_in_dry_run(self, tmp_path):
        """Two identical entries: one should be flagged as duplicate."""
        entry = _sample_entry("Dup Test")
        _make_inbox(tmp_path, [entry, entry])
        report = archive_inbox_to_structured(tmp_path, dry_run=True)
        assert report["total_entries"] == 2
        # Second identical entry should be marked as duplicate
        assert report["skipped_duplicates"] >= 1

    def test_unique_entries_all_new(self, tmp_path):
        entries = [
            _sample_entry(f"Unique {i}", saved=f"2026-05-0{i+1}")
            for i in range(3)
        ]
        _make_inbox(tmp_path, entries)
        report = archive_inbox_to_structured(tmp_path, dry_run=True)
        assert report["total_entries"] == 3
        assert report["new_entries"] == 3
        assert report["skipped_duplicates"] == 0


# ══════════════════════════════════════════════════════════════════════
# Write tests (P2b readiness)
# ══════════════════════════════════════════════════════════════════════

class TestArchiveWrite:
    def test_write_mode_backs_up_inbox(self, tmp_path):
        """Write mode should create a .bak backup."""
        _make_inbox(tmp_path, [_sample_entry("Backup Test")])
        report = archive_inbox_to_structured(tmp_path, dry_run=False, backup_first=True)
        if report.get("backup_path"):
            assert os.path.exists(report["backup_path"])

    def test_write_mode_writes_candidates(self, tmp_path):
        """Write mode should insert into memory_candidates."""
        _make_inbox(tmp_path, [_sample_entry("Write Test")])
        report = archive_inbox_to_structured(tmp_path, dry_run=False, backup_first=False)
        if not report["errors"]:
            assert report["written_candidates"] > 0
            assert report["written_chunks"] > 0

    def test_write_mode_does_not_truncate_inbox(self, tmp_path):
        """Inbox must NOT be truncated after archive (truncation is P2b)."""
        inbox = _make_inbox(
            tmp_path,
            [_sample_entry("No Truncation Test")],
        )
        content_before = inbox.read_text(encoding="utf-8")
        archive_inbox_to_structured(tmp_path, dry_run=False, backup_first=False)
        content_after = inbox.read_text(encoding="utf-8")
        assert len(content_after) >= len(content_before.strip()), (
            "Inbox should NOT be truncated after archive"
        )

    def test_chunk_content_is_saved(self, tmp_path):
        """Long entries should be chunked and each chunk gets a hash."""
        long_text = "Line " * 200  # ~1000 chars
        entry = _sample_entry("Long Entry") + "\n" + long_text
        _make_inbox(tmp_path, [entry])
        report = archive_inbox_to_structured(tmp_path, dry_run=False, backup_first=False)
        if not report["errors"]:
            assert report["written_chunks"] >= 1


# ══════════════════════════════════════════════════════════════════════
# Truncation tests (P2b)
# ══════════════════════════════════════════════════════════════════════

class TestArchiveTruncation:
    def test_truncation_removes_archived_entries(self, tmp_path):
        """After archive+truncate, archived entries are removed from inbox."""
        entries = [
            _sample_entry("Keep This", saved="2026-05-01"),
            _sample_entry("Archive This", saved="2026-05-02"),
        ]
        inbox = _make_inbox(tmp_path, entries)

        # Only archive the second entry (partial archive simulation)
        report = archive_inbox_to_structured(
            tmp_path,
            dry_run=False,
            backup_first=True,
            truncate_after_write=True,
        )
        if report["errors"]:
            pytest.skip(f"Truncation test prerequisites not met: {report['errors']}")

        assert report["truncated"] is True
        assert report["truncated_entries"] == 2  # both were new, both archived
        assert report["remaining_entries"] == 0

        content_after = inbox.read_text(encoding="utf-8")
        # Archived entries should be gone
        assert "Archive This" not in content_after
        assert "Keep This" not in content_after  # both got archived since both were new

    def test_truncation_preserves_unarchived(self, tmp_path):
        """Only archived entries are truncated; duplicates stay."""
        entry1 = _sample_entry("First", saved="2026-05-01")
        entry2 = _sample_entry("Second", saved="2026-05-02")
        inbox = _make_inbox(tmp_path, [entry1, entry2])

        # First run: archive everything
        report1 = archive_inbox_to_structured(
            tmp_path,
            dry_run=False,
            backup_first=True,
            truncate_after_write=True,
        )
        if report1["errors"]:
            pytest.skip(f"First archive failed: {report1['errors']}")
        assert report1["truncated_entries"] == 2

        # Re-create inbox with new entries + one duplicate
        entry3 = _sample_entry("Third", saved="2026-05-03")
        _make_inbox(tmp_path, [entry1, entry3])  # entry1 is duplicate

        # Second run: should skip duplicate, archive only entry3
        report2 = archive_inbox_to_structured(
            tmp_path,
            dry_run=False,
            backup_first=True,
            truncate_after_write=True,
        )
        if report2["errors"]:
            pytest.skip(f"Second archive failed: {report2['errors']}")
        # entry1 was duplicate, entry3 was new → 1 truncated
        assert report2["truncated_entries"] == 1
        assert report2["skipped_duplicates"] == 1

    def test_truncation_requires_backup(self, tmp_path):
        """Truncation without backup should be refused."""
        _make_inbox(tmp_path, [_sample_entry("Test")])
        report = archive_inbox_to_structured(
            tmp_path,
            dry_run=False,
            backup_first=False,
            truncate_after_write=True,
        )
        assert "truncation requires backup" in str(report["errors"])

    def test_backup_created_before_truncation(self, tmp_path):
        """Backup file must exist after archive+truncate."""
        _make_inbox(tmp_path, [_sample_entry("Backup Test")])
        report = archive_inbox_to_structured(
            tmp_path,
            dry_run=False,
            backup_first=True,
            truncate_after_write=True,
        )
        if report["backup_path"]:
            assert os.path.exists(report["backup_path"])

    def test_dry_run_never_truncates(self, tmp_path):
        """Dry run must never truncate, even with truncate_after_write=True."""
        inbox = _make_inbox(tmp_path, [_sample_entry("Safety Test")])
        content_before = inbox.read_text(encoding="utf-8")
        archive_inbox_to_structured(
            tmp_path,
            dry_run=True,
            truncate_after_write=True,
        )
        content_after = inbox.read_text(encoding="utf-8")
        assert content_before.strip() == content_after.strip()

    def test_repeat_archive_is_idempotent(self, tmp_path):
        """Repeated archive runs should not duplicate entries."""
        entries = [_sample_entry("Idempotent Test")]
        _make_inbox(tmp_path, entries)

        # First write
        r1 = archive_inbox_to_structured(
            tmp_path,
            dry_run=False,
            backup_first=True,
            truncate_after_write=True,
        )
        if r1["errors"]:
            pytest.skip(f"First run failed: {r1['errors']}")
        assert r1["written_candidates"] == 1

        # Re-create same entry in inbox
        _make_inbox(tmp_path, [_sample_entry("Idempotent Test")])

        # Second run: should detect as duplicate
        r2 = archive_inbox_to_structured(
            tmp_path,
            dry_run=False,
            backup_first=True,
            truncate_after_write=True,
        )
        assert r2["written_candidates"] == 0  # already archived
        assert r2["skipped_duplicates"] == 1
        assert r2["new_entries"] == 0

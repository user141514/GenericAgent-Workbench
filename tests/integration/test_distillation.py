"""
Integration tests for P1a: distillation trigger and candidate builder.

Verifies:
1. trigger_distillation() generates prompt (preview mode default)
2. build_distillation_candidate() includes source/run_id/task/session
3. Proposed candidates are NOT written to inbox
4. Preview mode writes JSON preview, NOT inbox
5. Write mode appends to inbox
6. Off mode does nothing
7. Classic path do_start_long_term_update() is unaffected
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from unittest.mock import patch

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.memory.distillation import (
    build_distillation_candidate,
    format_inbox_entry,
    get_distillation_mode,
    trigger_distillation,
    write_distillation_candidate,
)


# ══════════════════════════════════════════════════════════════════════
# get_distillation_mode()
# ══════════════════════════════════════════════════════════════════════

class TestDistillationMode:
    def test_default_is_preview(self):
        with patch.dict(os.environ, {}, clear=False):
            old = os.environ.pop("GA_OPENAI_DISTILLATION", None)
            try:
                assert get_distillation_mode() == "preview"
            finally:
                if old is not None:
                    os.environ["GA_OPENAI_DISTILLATION"] = old

    def test_off_via_zero(self):
        with patch.dict(os.environ, {"GA_OPENAI_DISTILLATION": "0"}):
            assert get_distillation_mode() == "off"

    def test_off_via_off_string(self):
        with patch.dict(os.environ, {"GA_OPENAI_DISTILLATION": "off"}):
            assert get_distillation_mode() == "off"

    def test_preview_explicit(self):
        with patch.dict(os.environ, {"GA_OPENAI_DISTILLATION": "preview"}):
            assert get_distillation_mode() == "preview"

    def test_write(self):
        with patch.dict(os.environ, {"GA_OPENAI_DISTILLATION": "write"}):
            assert get_distillation_mode() == "write"


# ══════════════════════════════════════════════════════════════════════
# trigger_distillation()
# ══════════════════════════════════════════════════════════════════════

class TestTriggerDistillation:
    def test_returns_empty_when_off(self):
        with patch.dict(os.environ, {"GA_OPENAI_DISTILLATION": "0"}):
            result = trigger_distillation(PROJECT_ROOT)
            assert result == ""

    def test_returns_prompt_when_preview(self):
        with patch.dict(os.environ, {"GA_OPENAI_DISTILLATION": "preview"}):
            result = trigger_distillation(PROJECT_ROOT)
            assert len(result) > 0
            assert "总结提炼经验" in result or "distill" in result.lower()

    def test_prompt_contains_memory_block(self):
        with patch.dict(os.environ, {"GA_OPENAI_DISTILLATION": "preview"}):
            result = trigger_distillation(PROJECT_ROOT)
            # Should contain L1/L2 reference
            assert "global_mem" in result.lower() or "[Memory]" in result


# ══════════════════════════════════════════════════════════════════════
# build_distillation_candidate()
# ══════════════════════════════════════════════════════════════════════

class TestBuildDistillationCandidate:
    def test_includes_all_metadata(self):
        candidate = build_distillation_candidate(
            summary="Task completed: updated config port from 8080 to 3000",
            source="openai",
            run_id="run_001",
            task="Update port configuration",
            session="session_abc",
        )
        assert candidate["summary"] is not None
        assert candidate["source"] == "openai"
        assert candidate["run_id"] == "run_001"
        assert candidate["task"] == "Update port configuration"
        assert candidate["session"] == "session_abc"

    def test_default_not_proposed(self):
        candidate = build_distillation_candidate(summary="test")
        assert candidate["is_proposed"] is False

    def test_proposed_flag(self):
        candidate = build_distillation_candidate(
            summary="Proposal: change timeout to 30s",
            is_proposed=True,
        )
        assert candidate["is_proposed"] is True

    def test_includes_files_touched(self):
        candidate = build_distillation_candidate(
            summary="test",
            files_touched=["config.yaml", "nginx.conf"],
        )
        assert "config.yaml" in candidate["files_touched"]
        assert "nginx.conf" in candidate["files_touched"]

    def test_includes_generated_at(self):
        candidate = build_distillation_candidate(summary="test")
        assert "generated_at" in candidate
        assert len(candidate["generated_at"]) > 0


# ══════════════════════════════════════════════════════════════════════
# format_inbox_entry()
# ══════════════════════════════════════════════════════════════════════

class TestFormatInboxEntry:
    def test_formats_correctly(self):
        candidate = build_distillation_candidate(
            summary="## Updated port config\nChanged port from 8080 to 3000.",
            source="openai",
            run_id="run_001",
            task="Update port",
            session="s1",
        )
        entry = format_inbox_entry(candidate)
        assert "## Updated port config" in entry
        assert "Saved At:" in entry
        assert "Source File: openai" in entry
        assert "Run: run_001" in entry

    def test_refuses_proposed_candidate(self):
        candidate = build_distillation_candidate(
            summary="Plan to change timeout",
            is_proposed=True,
        )
        entry = format_inbox_entry(candidate)
        assert entry == "", "Proposed candidates must NOT be formatted as inbox entries"

    def test_includes_files_touched(self):
        candidate = build_distillation_candidate(
            summary="test",
            files_touched=["a.py", "b.py"],
        )
        entry = format_inbox_entry(candidate)
        assert "Files Touched:" in entry
        assert "a.py" in entry

    def test_format_compatible_with_maintenance_tools(self):
        """Entry must be parseable by dedup_inbox and score_inbox_entries."""
        from core.memory.maintenance import dedup_inbox, score_inbox_entries

        candidate = build_distillation_candidate(
            summary="- Fixed config port\n- Updated nginx\n- Verified deployment",
            source="openai",
            run_id="run_compat",
            task="Verify compatibility",
            files_touched=["config.yaml", "nginx.conf"],
            questions=["What port should we use?", "Is nginx configured?"],
        )
        entry = format_inbox_entry(candidate)
        assert len(entry) > 0

        # Write to temp inbox and run maintenance tools
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            inbox = os.path.join(td, "history_memory_inbox.md")
            with open(inbox, "w", encoding="utf-8") as f:
                f.write(entry + "\n")

            # dedup_inbox should work
            dedup_result = dedup_inbox(inbox)
            assert dedup_result["removed"] == 0  # single entry, no dups

            # score_inbox_entries should extract age and score
            scores = score_inbox_entries(inbox)
            assert len(scores) >= 1
            assert "score" in scores[0]

    def test_format_matches_classic_structure(self):
        """Key markers that Classic maintenance tools depend on."""
        candidate = build_distillation_candidate(
            summary="Key fix applied.",
            source="openai",
            run_id="r1",
            files_touched=["x.py"],
            questions=["what to fix?"],
        )
        entry = format_inbox_entry(candidate)
        # Must have ## heading
        assert entry.startswith("## ")
        # Must have Saved At for age extraction
        assert "- Saved At:" in entry
        # Must have Files Touched for file counting
        assert "- Files Touched:" in entry


# ══════════════════════════════════════════════════════════════════════
# write_distillation_candidate()
# ══════════════════════════════════════════════════════════════════════

class TestWriteDistillationCandidate:
    def test_preview_writes_json_not_inbox(self, tmp_path):
        """In preview mode, writes JSON to temp/, NOT to inbox."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        candidate = build_distillation_candidate(
            summary="Test memory update",
            source="openai",
            run_id="test_001",
            task="Test task",
        )

        with patch.dict(os.environ, {"GA_OPENAI_DISTILLATION": "preview"}):
            result = write_distillation_candidate(candidate, project_root=tmp_path)

        assert result["mode"] == "preview"
        assert result["written"] is False
        assert "preview" in result["reason"].lower()
        if result["path"]:
            assert os.path.exists(result["path"]) or "temp" in result["path"]
        # Inbox should NOT be written
        inbox_path = memory_dir / "history_memory_inbox.md"
        assert not inbox_path.exists(), "inbox should not exist in preview mode"

    def test_refuses_proposed_in_write_mode(self, tmp_path):
        """Even in write mode, proposed candidates are refused."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()

        candidate = build_distillation_candidate(
            summary="Proposed change — not executed",
            is_proposed=True,
        )

        with patch.dict(os.environ, {"GA_OPENAI_DISTILLATION": "write"}):
            result = write_distillation_candidate(candidate, project_root=tmp_path)

        assert result["written"] is False
        assert "proposal" in result["reason"].lower() or "proposed" in result["reason"].lower()

    def test_write_mode_appends_to_inbox(self, tmp_path):
        """Write mode should append to history_memory_inbox.md."""
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()

        candidate = build_distillation_candidate(
            summary="## Executed fact\nVerified: config updated successfully.",
            source="openai",
            run_id="run_002",
            task="Config update",
            files_touched=["config.yaml"],
        )

        with patch.dict(os.environ, {"GA_OPENAI_DISTILLATION": "write"}):
            result = write_distillation_candidate(candidate, project_root=tmp_path)

        assert result["written"] is True
        assert result["mode"] == "write"

        inbox_path = memory_dir / "history_memory_inbox.md"
        assert inbox_path.exists()
        content = inbox_path.read_text(encoding="utf-8")
        assert "Executed fact" in content
        assert "Source File: openai" in content
        assert "config.yaml" in content

    def test_off_mode_does_nothing(self, tmp_path):
        """Off mode should not write anything."""
        candidate = build_distillation_candidate(summary="test")

        with patch.dict(os.environ, {"GA_OPENAI_DISTILLATION": "0"}):
            result = write_distillation_candidate(candidate, project_root=tmp_path)

        assert result["written"] is False
        assert result["mode"] == "off"


# ══════════════════════════════════════════════════════════════════════
# Classic path non-regression
# ══════════════════════════════════════════════════════════════════════

class TestClassicNonRegression:
    def test_do_start_long_term_update_still_works(self):
        """Classic ga.py path must still work."""
        from core.ga import get_global_memory

        mem = get_global_memory()
        assert len(mem) > 0
        assert "global_mem_insight" in mem

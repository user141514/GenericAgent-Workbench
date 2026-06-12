from __future__ import annotations

from types import SimpleNamespace

from core.agent_loop import exhaust
from core.ga import GenericAgentHandler


def test_file_patch_backs_up_previous_content(monkeypatch, tmp_path):
    monkeypatch.setenv("GENERIC_AGENT_TOOL_PATH_GUARD", "0")
    target = tmp_path / "sample.txt"
    target.write_text("alpha\nold block\nomega\n", encoding="utf-8")
    handler = GenericAgentHandler(SimpleNamespace(verbose=False), cwd=str(tmp_path))

    outcome = exhaust(
        handler.do_file_patch(
            {
                "path": str(target),
                "old_content": "old block",
                "new_content": "new block",
            },
            SimpleNamespace(content=""),
        )
    )

    assert outcome.data["status"] == "success"
    assert target.read_text(encoding="utf-8") == "alpha\nnew block\nomega\n"
    backup_path = outcome.data["backup_path"]
    assert backup_path
    with open(backup_path, "r", encoding="utf-8") as backup_file:
        assert backup_file.read() == "alpha\nold block\nomega\n"


def test_file_patch_rejects_mismatched_expected_sha256(monkeypatch, tmp_path):
    monkeypatch.setenv("GENERIC_AGENT_TOOL_PATH_GUARD", "0")
    target = tmp_path / "sample.txt"
    target.write_text("alpha\nold block\nomega\n", encoding="utf-8")
    handler = GenericAgentHandler(SimpleNamespace(verbose=False), cwd=str(tmp_path))

    outcome = exhaust(
        handler.do_file_patch(
            {
                "path": str(target),
                "old_content": "old block",
                "new_content": "new block",
                "expected_sha256": "0" * 64,
            },
            SimpleNamespace(content=""),
        )
    )

    assert outcome.data["status"] == "error"
    assert "expected_sha256 mismatch" in outcome.data["msg"]
    assert target.read_text(encoding="utf-8") == "alpha\nold block\nomega\n"

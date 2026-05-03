"""Minimal self-check for narrow read-task shortcut detection."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from .read_shortcut import detect_read_shortcut


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]

    decision = detect_read_shortcut(
        "\u8bfb\u53d6\u5f53\u524d\u9879\u76ee README \u7684\u7b2c\u4e00\u884c\u6807\u9898\uff0c\u7136\u540e\u53ea\u7528\u4e00\u53e5\u8bdd\u603b\u7ed3\u9879\u76ee\u5b9a\u4f4d\u3002",
        project_root=project_root,
    )
    assert decision.should_shortcut is True
    assert decision.extraction_type == "readme_title_and_positioning"

    decision = detect_read_shortcut(
        "\u8bfb\u53d6 README \u7b2c\u4e00\u884c\u3002",
        project_root=project_root,
    )
    assert decision.should_shortcut is True
    assert decision.extraction_type == "readme_title"

    decision = detect_read_shortcut(
        "\u770b\u770b core/router_rules.py",
        project_root=project_root,
    )
    assert decision.should_shortcut is True
    assert decision.extraction_type == "explicit_file_view:80"
    assert decision.line_count == 80

    decision = detect_read_shortcut(
        "\u67e5\u770b core/agentmain.py",
        project_root=project_root,
    )
    assert decision.should_shortcut is True
    assert decision.extraction_type == "explicit_file_view:80"
    assert decision.line_count == 80

    decision = detect_read_shortcut(
        "\u8bfb\u53d6 core/agentmain.py \u524d 20 \u884c",
        project_root=project_root,
    )
    assert decision.should_shortcut is True
    assert decision.extraction_type == "explicit_file_view:20"
    assert decision.line_count == 20

    decision = detect_read_shortcut(
        "\u6253\u5f00 README.md",
        project_root=project_root,
    )
    assert decision.should_shortcut is True
    assert decision.extraction_type == "explicit_file_view:80"

    decision = detect_read_shortcut(
        "\u5206\u6790 core/agentmain.py \u7684\u6267\u884c\u6d41\u7a0b",
        project_root=project_root,
    )
    assert decision.should_shortcut is False

    decision = detect_read_shortcut(
        "\u67e5\u770b core/router_rules.py \u5e76\u89e3\u91ca\u903b\u8f91",
        project_root=project_root,
    )
    assert decision.should_shortcut is False

    decision = detect_read_shortcut(
        "\u4fee\u6539 core/agentmain.py",
        project_root=project_root,
    )
    assert decision.should_shortcut is False

    decision = detect_read_shortcut(
        "\u4f18\u5316 core/agent_loop.py",
        project_root=project_root,
    )
    assert decision.should_shortcut is False

    decision = detect_read_shortcut(
        "\u8bfb\u53d6 ../secret.txt",
        project_root=project_root,
    )
    assert decision.should_shortcut is False
    assert decision.reason == "path_traversal_not_allowed"

    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        skill_a = temp_root / "a"
        skill_b = temp_root / "b"
        skill_a.mkdir()
        skill_b.mkdir()
        (skill_a / "package.json").write_text('{"name": "a"}\n', encoding="utf-8")
        (skill_b / "package.json").write_text('{"name": "b"}\n', encoding="utf-8")
        decision = detect_read_shortcut(
            "\u663e\u793a package.json",
            project_root=temp_root,
        )
        assert decision.should_shortcut is False
        assert decision.reason == "ambiguous_filename"

    print("demo_read_shortcut: OK")


if __name__ == "__main__":
    main()

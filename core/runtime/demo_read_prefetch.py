"""Minimal self-check for analysis-oriented single-file read_prefetch detection."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from .read_prefetch import detect_read_prefetch


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]

    decision = detect_read_prefetch(
        "\u5206\u6790 core/router_rules.py \u7684\u8def\u7531\u903b\u8f91",
        project_root=project_root,
    )
    assert decision.should_prefetch is True
    assert decision.target_file == "core/router_rules.py"

    decision = detect_read_prefetch(
        "\u89e3\u91ca core/agent_loop.py \u7684 turn loop",
        project_root=project_root,
    )
    assert decision.should_prefetch is True
    assert decision.target_file == "core/agent_loop.py"

    decision = detect_read_prefetch(
        "\u770b\u770b core/openai_agentmain.py \u7684\u6267\u884c\u6d41\u7a0b",
        project_root=project_root,
    )
    assert decision.should_prefetch is True
    assert decision.target_file == "core/openai_agentmain.py"

    decision = detect_read_prefetch(
        "\u770b\u770b core/router_rules.py",
        project_root=project_root,
    )
    assert decision.should_prefetch is False
    assert decision.reason == "not_analysis_request"

    decision = detect_read_prefetch(
        "\u4fee\u6539 core/router_rules.py",
        project_root=project_root,
    )
    assert decision.should_prefetch is False
    assert decision.reason == "action_request_not_supported"

    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        dir_a = temp_root / "a"
        dir_b = temp_root / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "package.json").write_text('{"name": "a"}\n', encoding="utf-8")
        (dir_b / "package.json").write_text('{"name": "b"}\n', encoding="utf-8")
        decision = detect_read_prefetch(
            "\u5206\u6790 package.json",
            project_root=temp_root,
        )
        assert decision.should_prefetch is False
        assert decision.reason == "ambiguous_filename"

    decision = detect_read_prefetch(
        "\u5206\u6790 ../secret.txt",
        project_root=project_root,
    )
    assert decision.should_prefetch is False
    assert decision.reason == "unsafe_path"

    print("demo_read_prefetch: OK")


if __name__ == "__main__":
    main()

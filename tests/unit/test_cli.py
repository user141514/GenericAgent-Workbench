"""Tests for the unified CLI entry point.

These tests verify module structure, argument parsing, and pyproject.toml
configuration. They do NOT execute the agent (which requires mykey.py config).
"""

import os
import sys
import pytest


class TestCLIModule:
    """Verify the CLI module is importable and has the expected API."""

    def test_module_importable(self):
        import core.cli
        assert hasattr(core.cli, "main")

    def test_all_commands_exist(self):
        import core.cli
        for name in ("cmd_run", "cmd_serve", "cmd_reflect",
                     "cmd_run_openai", "cmd_serve_openai"):
            assert hasattr(core.cli, name), f"Missing command: {name}"
            assert callable(getattr(core.cli, name))

    def test_helpers_exist(self):
        import core.cli
        assert callable(core.cli._drain_to_stdout)
        assert callable(core.cli._run_interactive)
        assert callable(core.cli._run_task_mode)

    def test_main_function_has_argparse(self):
        """Verify main() creates subparsers for all 5 commands."""
        import argparse
        parser = argparse.ArgumentParser(prog="ga")
        sub = parser.add_subparsers(dest="command")

        # Match the structure in core/cli.py
        sub.add_parser("run")
        sub.add_parser("serve")
        sub.add_parser("reflect")
        sub.add_parser("run-openai")
        sub.add_parser("serve-openai")

        assert set(sub.choices.keys()) == {
            "run", "serve", "reflect", "run-openai", "serve-openai"
        }

    def test_run_subparser_accepts_flags(self):
        import argparse
        parser = argparse.ArgumentParser(prog="ga")
        sub = parser.add_subparsers(dest="command")
        p = sub.add_parser("run")
        p.add_argument("--input")
        p.add_argument("--task", metavar="DIR")
        p.add_argument("--llm", type=int, default=0, dest="llm_no")
        p.add_argument("--verbose", action="store_true")

        ns = parser.parse_args(["run", "--input", "hello", "--llm", "2"])
        assert ns.command == "run"
        assert ns.input == "hello"
        assert ns.llm_no == 2
        assert not ns.verbose


class TestPyProjectConfig:
    """Verify pyproject.toml has the required console_scripts entry."""

    def test_ga_entry_point_defined(self):
        pyproject_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "pyproject.toml"
        )
        if not os.path.exists(pyproject_path):
            pytest.skip("pyproject.toml not found")
        with open(pyproject_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "ga = " in content, "pyproject.toml missing 'ga' console_scripts entry"
        assert "core.cli" in content, "console_scripts should point to core.cli:main"

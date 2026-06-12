from __future__ import annotations

import importlib.util
from pathlib import Path

from scripts import run_runtime_regression, runtime_regression_runner

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_ROOT = PROJECT_ROOT / "examples" / "demos"


def test_no_demo_modules_in_production_core_dirs():
    demo_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in (PROJECT_ROOT / "core").rglob("demo_*.py")
        if "__pycache__" not in path.parts
    ]

    assert demo_files == []


def test_runtime_regression_demos_live_under_examples_package():
    modules = set(run_runtime_regression.MODULES) | set(runtime_regression_runner.MODULES)

    assert modules
    assert all(module.startswith("examples.demos.") for module in modules)


def test_runtime_regression_demo_modules_are_importable():
    modules = set(run_runtime_regression.MODULES) | set(runtime_regression_runner.MODULES)

    missing = [module for module in sorted(modules) if importlib.util.find_spec(module) is None]
    assert missing == []

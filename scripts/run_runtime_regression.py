"""Run lightweight runtime regression demos."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


MODULES = [
    "core.runtime.demo_tool_contract",
    "core.runtime.demo_read_shortcut",
    "core.runtime.demo_read_prefetch",
    "core.quality.demo_answer_quality_context",
    "core.skills.demo_skill_selector",
    "core.skills.demo_skill_prompt_injector",
    "core.skills.demo_skill_activation",
    "core.memory.demo_write_gate",
    "core.memory.demo_memory_store",
    "core.memory.demo_memory_indexer",
    "core.tools.demo_schema_selector",
    "core.tools.demo_schema_registry",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _module_exists(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        parts = module_name.split(".")
        parts[-1] = parts[-1] + ".py"
        return Path(_repo_root(), *parts).is_file()


def main() -> int:
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    passed = 0
    failed = 0
    skipped = 0

    for module_name in MODULES:
        if not _module_exists(module_name):
            skipped += 1
            print(f"[SKIP] {module_name}")
            continue

        proc = subprocess.run(
            [sys.executable, "-m", module_name],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode == 0:
            passed += 1
            print(f"[PASS] {module_name}")
            continue

        failed += 1
        print(f"[FAIL] {module_name}")
        if proc.stdout.strip():
            print(proc.stdout.rstrip())
        if proc.stderr.strip():
            print(proc.stderr.rstrip())

    print()
    print(f"passed: {passed}")
    print(f"failed: {failed}")
    print(f"skipped: {skipped}")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())

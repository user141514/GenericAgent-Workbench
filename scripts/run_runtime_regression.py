"""Run lightweight runtime regression demos."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

MODULES = [
    "examples.demos.runtime.demo_tool_contract",
    "examples.demos.runtime.demo_read_shortcut",
    "examples.demos.runtime.demo_read_prefetch",
    "examples.demos.quality.demo_answer_quality_context",
    "examples.demos.skills.demo_skill_selector",
    "examples.demos.skills.demo_skill_prompt_injector",
    "examples.demos.skills.demo_skill_activation",
    "examples.demos.memory.demo_write_gate",
    "examples.demos.memory.demo_memory_store",
    "examples.demos.memory.demo_memory_indexer",
    "examples.demos.tools.demo_schema_selector",
    "examples.demos.tools.demo_schema_registry",
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


def _safe_console_text(text: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return str(text).encode(encoding, errors="replace").decode(encoding, errors="replace")


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
            print(_safe_console_text(proc.stdout.rstrip()))
        if proc.stderr.strip():
            print(_safe_console_text(proc.stderr.rstrip()))

    print()
    print(f"passed: {passed}")
    print(f"failed: {failed}")
    print(f"skipped: {skipped}")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Runtime regression runner — smoke-test every demo module under core/.

Usage:
  python scripts/runtime_regression_runner.py

Each demo is invoked via ``sys.executable -m <module>`` in a subprocess.
A module that does not exist is reported as [SKIP].
A module whose subprocess exits 0 is reported as [PASS].
A module whose subprocess exits non-zero is reported as [FAIL] with the
last 1000 characters of stderr.

Exit code is 1 when at least one module fails, 0 otherwise.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

# ── All demo modules, grouped by capability category ──────────────────────
MODULES: list[str] = [
    # ── Runtime Optimization ───────────────────────────────────────────
    "examples.demos.runtime.demo_profiler",
    "examples.demos.runtime.demo_llm_cache",
    "examples.demos.runtime.demo_early_stop",
    "examples.demos.runtime.demo_direct_answer",
    "examples.demos.runtime.demo_read_shortcut",
    "examples.demos.runtime.demo_read_prefetch",
    "examples.demos.runtime.demo_tool_contract",
    "examples.demos.runtime.demo_clarification_gate",
    # ── Quality Guard ───────────────────────────────────────────────────
    "examples.demos.quality.demo_answer_quality_context",
    "examples.demos.quality.demo_problem_framing",
    # ── Skill System ────────────────────────────────────────────────────
    "examples.demos.skills.demo_skill_activation",
    "examples.demos.skills.demo_skill_discovery",
    "examples.demos.skills.demo_skill_effects",
    "examples.demos.skills.demo_skill_manifest",
    "examples.demos.skills.demo_skill_prompt_injector",
    "examples.demos.skills.demo_skill_registry",
    "examples.demos.skills.demo_skill_selector",
    # ── Memory Gate ─────────────────────────────────────────────────────
    "examples.demos.memory.demo_memory_indexer",
    "examples.demos.memory.demo_memory_store",
    "examples.demos.memory.demo_write_gate",
    # ── Tool System ─────────────────────────────────────────────────────
    "examples.demos.tools.demo_schema_selector",
    "examples.demos.tools.demo_schema_registry",
]

STDERR_TAIL_CHARS: int = 1000


# ── helpers ────────────────────────────────────────────────────────────────


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _module_exists(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        # Parent package import may fail on older Pythons
        # (e.g. @dataclass(slots=True) is 3.10+).
        # Fall back to checking whether the .py file exists on disk.
        parts = module_name.split(".")
        parts[-1] = parts[-1] + ".py"
        candidate = Path(_repo_root(), *parts)
        return candidate.is_file()


def _safe_console_text(text: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return str(text).encode(encoding, errors="replace").decode(encoding, errors="replace")


# ── main ───────────────────────────────────────────────────────────────────


def main() -> int:
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    passed: int = 0
    failed: int = 0
    skipped: int = 0

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
            tail = proc.stderr.rstrip()
            if len(tail) > STDERR_TAIL_CHARS:
                tail = "…\n" + tail[-STDERR_TAIL_CHARS:]
            print(_safe_console_text(tail))

    # ── summary ─────────────────────────────────────────────────────────
    print()
    print(f"passed:  {passed}")
    print(f"failed:  {failed}")
    print(f"skipped: {skipped}")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())

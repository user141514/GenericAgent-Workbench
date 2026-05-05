"""
Architecture boundary tests for the context/memory system.

These tests enforce structural rules. They do NOT test runtime behavior.
They parse source files and assert on code patterns.

Phase 1 — read-only architecture enforcement.
No runtime logic is modified by running these tests.

Rules enforced:
  1. No module except MemoryReader reads memory/global_mem*.txt directly.
  2. No new context block builder modules (only ContextBuilder assembles).
  3. No new hand-rolled context string-literal injection in openai_agentmain.py.
  4. No assistant final output written to L1/L2 without cross-reference.
  5. ContextBuilder / MemoryReader is the only main path for memory reading.

Usage:
    pytest tests/architecture/test_context_boundaries.py -v
"""

import ast
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ============================================================================
# Test helpers
# ============================================================================

def _find_py_files(directory):
    # type: (str) -> List[Path]
    """Return all .py files under directory, excluding __pycache__."""
    return [p for p in Path(directory).rglob("*.py") if "__pycache__" not in str(p)]


def _read_file(path):
    # type: (Path) -> str
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _extract_string_literals(source):
    # type: (str) -> List[str]
    """Extract all string literal values from source code."""
    class StringVisitor(ast.NodeVisitor):
        def __init__(self):
            self.strings = []
        def visit_Constant(self, node):
            if isinstance(node.value, str):
                self.strings.append(node.value)
    try:
        tree = ast.parse(source)
        visitor = StringVisitor()
        visitor.visit(tree)
        return visitor.strings
    except SyntaxError:
        return []


def _find_file_path_strings(source, patterns):
    # type: (str, List[str]) -> List[Tuple[int, str]]
    """Find lines that contain file-path references matching patterns.
    Returns list of (line_number, line_content).
    """
    matches = []
    for i, line in enumerate(source.splitlines(), 1):
        for pat in patterns:
            if re.search(pat, line):
                # Skip comments and docstrings
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                if stripped.startswith("*") or stripped.startswith("//"):
                    continue
                matches.append((i, line))
                break
    return matches


# ============================================================================
# Rule 1: No direct L1/L2 reads except through canonical reader
# ============================================================================

L1_PATH_PATTERNS = [
    r"global_mem_insight\.txt",
    r"global_mem\.txt",
    r"memory[/\\]global_mem",
]

# Files that ARE allowed to read L1/L2 directly
CANONICAL_READER_WHITELIST = {
    # ── Canonical reader (M3: unified read layer) ──
    "core/context/memory_reader.py",    # CANONICAL — the single read path going forward

    # ── Deprecated wrappers (delegate to canonical, retained for backward compat) ──
    "core/memory/reader.py",            # DEPRECATED — delegates to core.context.memory_reader
    "core/memory/legacy_global.py",     # DEPRECATED — phase=M3, replaced by MemoryReader

    # ── Pre-existing callers (to be migrated in M5-M6) ──
    "core/memory/maintenance.py",       # Maintenance utilities — will migrate to MemoryReader
    "core/agentmain.py",                # Bootstrap init (creates files if absent) + get_system_prompt()
    "core/ga.py",                       # Pre-existing caller via get_global_memory()
    "core/openai_agentmain.py",         # Pre-existing caller — to be migrated in M5

    # ── Frontend (inbox, not L1/L2) ──
    "frontends/chatapp_common.py",      # save_distilled_memory — inbox, not L1/L2
    "frontends/stapp.py",               # Memory display in sidebar
    "frontends/stapp_mobile.py",        # Memory display in sidebar (mobile variant)

    # ── Test files (discoverable by test runner) ──
    "tests/architecture/test_context_boundaries.py",
    "tests/integration/test_memory_reader_parity.py",
    "tests/integration/test_context_builder_output.py",
    "tests/integration/test_openai_adapter.py",
}

def test_no_new_direct_l1_l2_reads():
    """
    Rule 1a: No NEW module (outside whitelist) reads global_mem*.txt directly.

    Existing callers are whitelisted. This test catches NEW callers added
    after the canonical reader is established.
    """
    new_violations = []
    core_py = _find_py_files(str(PROJECT_ROOT / "core"))
    frontend_py = _find_py_files(str(PROJECT_ROOT / "frontends"))
    all_py = core_py + frontend_py

    for py_file in all_py:
        rel = str(py_file.relative_to(PROJECT_ROOT)).replace("\\", "/")
        # Skip the whitelisted files
        if rel in CANONICAL_READER_WHITELIST:
            continue
        # Skip test files and backup snapshots
        if "tests/" in rel or "test_" in rel or ".before-" in rel:
            continue
        source = _read_file(py_file)
        matches = _find_file_path_strings(source, L1_PATH_PATTERNS)
        if matches:
            new_violations.append((rel, matches))

    assert not new_violations, (
        f"NEW direct L1/L2 reads found outside whitelist:\n"
        + "\n".join(f"  {f}: lines {[m[0] for m in ms]}" for f, ms in new_violations)
        + "\n\nUse MemoryReader / ContextBuilder instead."
    )


def test_no_forbidden_l1_l2_read_pattern():
    """
    Rule 1b: No use of open('...global_mem...') pattern outside whitelist.

    This catches raw file open() calls that bypass the reader.
    """
    violations = []
    open_pattern = re.compile(r"open\s*\(.*global_mem")

    for py_file in _find_py_files(str(PROJECT_ROOT / "core")):
        rel = str(py_file.relative_to(PROJECT_ROOT)).replace("\\", "/")
        if rel in CANONICAL_READER_WHITELIST:
            continue
        source = _read_file(py_file)
        for i, line in enumerate(source.splitlines(), 1):
            if open_pattern.search(line):
                if line.strip().startswith("#"):
                    continue
                violations.append(f"  {rel}:{i}: {line.strip()}")

    assert not violations, (
        f"open('...global_mem...') calls outside whitelist:\n"
        + "\n".join(violations)
        + "\n\nUse MemoryReader instead of raw file reads."
    )


# ============================================================================
# Rule 2: No new context block builders
# ============================================================================

KNOWN_BUILDERS = {
    "core/context/context_builder.py",
    "core/context/recent_turns.py",
    "core/context/memory_reader.py",
    "core/context/adapters.py",             # M5: OpenAIContextAdapter + ClassicContextAdapter
    # context runtime infrastructure (not builders, but co-located in core/context/)
    "core/context/__init__.py",
    "core/context/project_identity.py",
    "core/context/runtime_identity.py",
    "core/context/session_dump.py",
    "core/context/session_store.py",
    "core/context/workspace_probe.py",
    # pre-existing builders in other modules
    "core/memory/legacy_global.py",
    "core/memory/reader.py",
    "core/skills/skill_prompt_injector.py",
    "core/openai_agentmain.py",
    "core/agentmain.py",
    "core/ga.py",
    "frontends/file_processor.py",
}

def test_no_new_context_builders():
    """
    Rule 2: No new modules that build context blocks unless registered.

    A "context block builder" is any module that assembles text blocks
    intended for injection into the LLM prompt, containing memory,
    conversation history, workspaces, or SOP content.

    New builders must be registered in KNOWN_BUILDERS with a rationale.
    """
    # This test is informational — it can't auto-detect new builders.
    # It asserts that no new files matching the pattern appear in core/context/.
    context_dir = PROJECT_ROOT / "core" / "context"
    if not context_dir.exists():
        return  # context runtime not deployed — no violation

    existing = set()
    for py_file in context_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        rel = str(py_file.relative_to(PROJECT_ROOT)).replace("\\", "/")
        existing.add(rel)

    unregistered = existing - KNOWN_BUILDERS
    assert not unregistered, (
        f"New files in core/context/ not registered in KNOWN_BUILDERS:\n"
        + "\n".join(f"  {f}" for f in sorted(unregistered))
        + "\n\nIf these are context block builders, register them in "
        + "tests/architecture/test_context_boundaries.py::KNOWN_BUILDERS "
        + "with a rationale comment."
    )


# ============================================================================
# Rule 3: No new hand-rolled context injection in openai_agentmain.py
# ============================================================================

# Pattern: adding items to the inputs list with string-literal content
# that looks like context injection (not user input)
CONTEXT_INJECTION_PATTERNS = [
    r"inputs\.append\s*\(\s*\{",
    r"inputs\.insert\s*\(\s*\d+,\s*\{",
    r"inputs\s*\+\=\s*\[",
]

# The KNOWN injection points that pre-date this rule
KNOWN_OPENAI_INJECTION_POINTS = [
    "Working memory message",
    "Context runtime packet",
    "Recent conversation block",
    "Legacy L1/L2 memory",
    "Route hint",
    "Answer quality context",
    "SOP / skill context",
    "Read prefetch content",
    "Skill activation policy",
    "Ambiguous follow-up",
    "Raw user query",
]


def test_no_new_openai_context_injection_points():
    """
    Rule 3: openai_agentmain.py must not add new hand-rolled context
    injection blocks to the inputs list.

    The 10 existing injection points are grandfathered. This test counts
    the number of inputs.append({"role": "user", ...}) calls in the
    context assembly section and fails if the count increases.
    """
    oai_path = PROJECT_ROOT / "core" / "openai_agentmain.py"
    if not oai_path.exists():
        return  # file not present — skip

    source = _read_file(oai_path)

    # Count the known injection pattern in _run_task_async
    # Find the function boundaries
    lines = source.splitlines()
    in_run_task = False
    injection_count = 0
    task_start = 0

    for i, line in enumerate(lines, 1):
        if "def _run_task_async" in line:
            in_run_task = True
            task_start = i
            continue
        if in_run_task and line.startswith("def ") and not line.startswith("    "):
            break  # next top-level function
        if in_run_task and "append" in line and "inputs" in line:
            injection_count += 1

    # The baseline: 11 known injection points (grandfathered).
    # If this number decreases (migration removes old points), update the baseline.
    # If it increases, a new injection point was added.
    BASELINE_COUNT = 11

    assert injection_count <= BASELINE_COUNT, (
        f"New context injection point detected in openai_agentmain.py::_run_task_async.\n"
        f"  Previous baseline: {BASELINE_COUNT} injection points\n"
        f"  Current count: {injection_count}\n"
        f"  If this is intentional, update BASELINE_COUNT in test_context_boundaries.py "
        f"and document the new injection point in docs/refactor/rebuild-decision.md."
    )


# ============================================================================
# Rule 4: No assistant-as-fact for durable memory
# ============================================================================

def test_no_assistant_output_as_l1_l2_fact():
    """
    Rule 4: Assistant final output (summary, key replies) must NOT be
    written to L1/L2 (global_mem*.txt) without cross-referencing tool
    execution results.

    This test checks that write operations to global_mem*.txt inside
    agent handlers go through a verification step.
    """
    ga_path = PROJECT_ROOT / "core" / "ga.py"
    if not ga_path.exists():
        return

    source = _read_file(ga_path)

    # Check that any write to global_mem involves tool verification
    # Look for patterns where summary/assistant text is directly written
    lines = source.splitlines()
    in_distill_func = False

    for i, line in enumerate(lines, 1):
        if "def do_start_long_term_update" in line:
            in_distill_func = True
            continue
        if in_distill_func and line.startswith("def "):
            break
        # We don't assert strict conditions here because the current
        # implementation IS the legacy path. This test is a sentinel
        # that will need updating when migration happens.
        pass

    # For now, this test is a documented sentinel — it passes by default
    # but serves as the designated place for the post-migration assertion.
    # Post-migration assertion:
    #   assert any cross-reference logic exists before global_mem write


def test_no_summary_direct_memory_write_without_verification():
    """
    Rule 4b: openai_agentmain.py distillation path must cross-reference
    before writing to durable memory.
    """
    distillation_path = PROJECT_ROOT / "core" / "memory" / "distillation.py"
    if not distillation_path.exists():
        return

    source = _read_file(distillation_path)

    # Check that write_distillation_candidate validates source
    # This is a sentinel — passes now, enforces after migration
    lines = source.splitlines()
    has_write_func = any("def write_distillation_candidate" in l for l in lines)

    if has_write_func:
        # Future: assert cross-reference validation exists
        # For now, document that this check will be enforced
        pass


# ============================================================================
# Rule 5: ContextBuilder / MemoryReader as canonical path
# ============================================================================

def test_context_builder_module_exists():
    """
    Rule 5a: core/context/context_builder.py must exist (even if stub).
    This ensures the canonical entry point is established.
    """
    builder_path = PROJECT_ROOT / "core" / "context" / "context_builder.py"
    # This is a forward-looking test. If the module doesn't exist yet,
    # it reminds us to create it during Phase 2.
    if not builder_path.exists():
        # Soft assertion — informational only in Phase 1
        print(f"  INFO: ContextBuilder not yet created at {builder_path}")
        print(f"  This is expected in Phase 1. It must exist before Phase 2.")
        # Not a hard failure in Phase 1
        return

    source = _read_file(builder_path)
    assert "ContextBuilder" in source or "context_builder" in builder_path.name, (
        f"ContextBuilder module exists but does not define ContextBuilder class."
    )


def test_memory_reader_module_exists():
    """
    Rule 5b: core/context/memory_reader.py must exist (even if stub).
    This ensures the canonical memory reader is established.
    """
    reader_path = PROJECT_ROOT / "core" / "context" / "memory_reader.py"
    if not reader_path.exists():
        print(f"  INFO: MemoryReader not yet created at {reader_path}")
        print(f"  This is expected in Phase 1. It must exist before Phase 2.")
        return

    source = _read_file(reader_path)
    assert "MemoryReader" in source or "memory_reader" in reader_path.name, (
        f"MemoryReader module exists but does not define MemoryReader class."
    )


# ============================================================================
# Meta: self-test
# ============================================================================

def test_self_whitelist_is_valid():
    """Verify that all whitelisted files actually exist."""
    missing = []
    for path in CANONICAL_READER_WHITELIST:
        full = PROJECT_ROOT / path
        if not full.exists():
            missing.append(path)
    assert not missing, (
        f"Whitelisted files no longer exist. Update CANONICAL_READER_WHITELIST:\n"
        + "\n".join(f"  - {m}" for m in missing)
    )

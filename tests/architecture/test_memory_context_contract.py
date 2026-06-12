from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = PROJECT_ROOT / "docs" / "architecture" / "memory_context_contract.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def test_memory_context_contract_document_defines_current_boundaries():
    text = _read(CONTRACT_PATH)

    required = [
        "`core/context/memory_reader.py` owns all L1/L2 text reads",
        "`core/context/context_builder.py` is a pure representation builder",
        "`core/memory/store.py` owns SQLite CRUD",
        "Text L1/L2 remains the canonical prompt input",
        "SQLite structured memory is supplementary evidence",
        "Frontends may display memory, but L1/L2 display must go through",
    ]
    missing = [phrase for phrase in required if phrase not in text]
    assert missing == []


def test_context_builder_does_not_cross_memory_storage_boundary():
    source = _read(PROJECT_ROOT / "core" / "context" / "context_builder.py")

    assert "MemoryStore" not in source
    assert "core.memory.store" not in source
    assert "global_mem_insight.txt" not in source
    assert "global_mem.txt" not in source
    assert "read_global_memory" not in source


def test_memory_reader_is_only_context_module_that_names_l1_l2_files():
    context_dir = PROJECT_ROOT / "core" / "context"
    offenders: list[str] = []

    for path in context_dir.rglob("*.py"):
        if path.name == "memory_reader.py" or "__pycache__" in path.parts:
            continue
        source = _read(path)
        if "global_mem_insight.txt" in source or "global_mem.txt" in source:
            offenders.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))

    assert offenders == []

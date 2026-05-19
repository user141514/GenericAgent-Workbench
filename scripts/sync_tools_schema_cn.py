"""Persist a structurally aligned Chinese tool schema to assets/tools_schema_cn.json."""

from __future__ import annotations

import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from core.tools.schema_registry import write_aligned_localized_schema

    report = write_aligned_localized_schema("zh")
    print("sync_tools_schema_cn: OK")
    print(f"source: {report['source']}")
    print(f"tool_count: {report['tool_count']}")
    print(f"missing_tools: {len(report['missing_tools'])}")
    print(f"missing_tool_descriptions: {len(report['missing_tool_descriptions'])}")
    print(f"missing_param_descriptions: {len(report['missing_param_descriptions'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

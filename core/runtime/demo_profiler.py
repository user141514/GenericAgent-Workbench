"""Minimal demo for RuntimeProfiler."""

from __future__ import annotations

import time
from pathlib import Path

from .profiler import RuntimeProfiler


def main() -> None:
    profiler = RuntimeProfiler()
    profiler.start_run(run_id="demo", name="runtime_demo", metadata={"source": "demo_profiler"})

    with profiler.span("agent_a", kind="agent", metadata={"agent": "demo"}):
        time.sleep(0.01)
        with profiler.span("llm_call", kind="llm", metadata={"model": "demo-model"}):
            time.sleep(0.02)
        with profiler.span("tool_call", kind="tool", metadata={"tool": "demo_tool"}):
            time.sleep(0.015)
        profiler.record_event("agent_note", kind="agent", metadata={"message": "demo event"})

    summary = profiler.end_run()
    print(summary)

    export_path = Path("F:/GAgent-Multi/temp/runtime_profile_demo.json")
    profiler.export_json(export_path)
    print(f"exported: {export_path}")


if __name__ == "__main__":
    main()

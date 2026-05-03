"""Minimal self-check for the local LLM cache helpers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .llm_cache import LLMCallCache, is_cache_safe


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = LLMCallCache(Path(tmpdir) / "llm_cache")
        messages = [{"role": "user", "content": "restore bug happened because report_id route was broken"}]
        tools = [{"name": "summarize_file"}]

        key_a = cache.make_key("glm-5", messages, tools=tools, temperature=0.0, metadata={"cache_type": "file_summary"})
        key_b = cache.make_key("glm-5", messages, tools=tools, temperature=0.0, metadata={"cache_type": "file_summary"})
        key_c = cache.make_key("glm-5", messages, tools=tools, temperature=0.2, metadata={"cache_type": "file_summary"})
        assert key_a == key_b
        assert key_a != key_c

        value = {"text": "summary result", "ok": True}
        cache.set(key_a, value)
        assert cache.get(key_a) == value
        assert cache.get("missing") is None

        long_messages = [{"role": "user", "content": "x" * 700}]
        long_response = {"text": "y" * 700}
        record = cache.audit(
            model="glm-5",
            messages=long_messages,
            response=long_response,
            duration_ms=123.456,
            tools=tools,
            metadata={"cache_type": "file_summary", "task_type": "summary", "temperature": 0.0},
        )
        assert len(record.prompt_preview) <= 500
        assert len(record.response_preview) <= 500
        assert record.prompt_chars >= 700
        assert record.response_chars >= 700
        assert record.message_count == 1
        assert record.user_chars >= 700
        assert record.estimated_prompt_tokens > 0
        assert record.estimated_response_tokens > 0

        lines = cache.records_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        saved = json.loads(lines[0])
        assert saved["prompt_hash"] == record.prompt_hash
        assert saved["prompt_chars"] == record.prompt_chars
        assert saved["estimated_prompt_tokens"] == record.estimated_prompt_tokens

        assert is_cache_safe({"cache_type": "file_summary"}) is True
        assert is_cache_safe({"cache_type": "final_answer"}) is False
        assert is_cache_safe({}) is False

    print("demo_llm_cache: OK")


if __name__ == "__main__":
    main()

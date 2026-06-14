from __future__ import annotations

import threading
import time

import core.llmcore as llmcore


def _clear_lazy_key_globals():
    for name in ("mykeys", "proxies"):
        llmcore.__dict__.pop(name, None)
    if hasattr(llmcore, "_MYKEYS_CACHE"):
        llmcore._MYKEYS_CACHE = None


def test_openai_sse_logs_invalid_chat_json(capsys):
    list(llmcore._parse_openai_sse([b"data: {bad-json", b"data: [DONE]"], "chat_completions"))

    captured = capsys.readouterr()
    assert "[SSE] JSON parse error" in captured.out
    assert "{bad-json" in captured.out


def test_openai_sse_logs_invalid_responses_json(capsys):
    list(llmcore._parse_openai_sse([b"data: {bad-json", b"data: [DONE]"], "responses"))

    captured = capsys.readouterr()
    assert "[SSE] JSON parse error" in captured.out
    assert "{bad-json" in captured.out


def test_lazy_mykeys_load_is_thread_safe(monkeypatch):
    _clear_lazy_key_globals()
    calls = 0
    lock = threading.Lock()

    def fake_load():
        nonlocal calls
        time.sleep(0.01)
        with lock:
            calls += 1
        return {"key1_native_oai_config": {"apikey": "fake"}, "proxy": ""}

    monkeypatch.setattr(llmcore, "_load_mykeys", fake_load)

    errors: list[BaseException] = []
    results: list[object] = []

    def read_keys():
        try:
            results.append(llmcore.mykeys)
        except BaseException as exc:  # pragma: no cover - assertion reports list
            errors.append(exc)

    threads = [threading.Thread(target=read_keys) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert len(results) == 20
    assert calls == 1
    _clear_lazy_key_globals()


def test_sanitize_leading_user_msg_does_not_mutate_original_content():
    nested_content = [
        {"type": "text", "text": "before"},
        {"type": "tool_result", "content": [{"type": "text", "text": "tool output"}]},
    ]
    original = {"role": "user", "content": nested_content}

    sanitized = llmcore._sanitize_leading_user_msg(original)

    assert sanitized is not original
    assert sanitized["content"] == [{"type": "text", "text": "before\ntool output"}]
    assert original["content"] is nested_content
    assert original["content"][1]["type"] == "tool_result"

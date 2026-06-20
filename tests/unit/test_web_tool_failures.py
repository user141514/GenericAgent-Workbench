from __future__ import annotations

from types import SimpleNamespace

from core.agent_loop import exhaust
from core.ga import GenericAgentHandler
from core.runtime.web_tool_errors import (
    classify_web_tool_failure,
    enrich_web_tool_result,
    web_tool_failure_prompt,
)


def test_classifies_api_429_as_rate_limited():
    failure = classify_web_tool_failure(
        "OpenAI API returned HTTP 429: rate limit exceeded",
        tool_name="browser_agent",
    )

    assert failure.category == "rate_limited"
    assert failure.retryable is False
    assert failure.recommended_next_tool == "web_search"
    assert "Do not retry browser_agent" in web_tool_failure_prompt("browser_agent", failure)


def test_classifies_missing_browser_tab_as_browser_unavailable():
    failure = classify_web_tool_failure(
        "No available browser tabs; browser extension is not connected",
        tool_name="web_scan",
    )

    assert failure.category == "browser_unavailable"
    assert failure.retryable is False
    assert failure.recommended_next_tool == "browser_agent"


def test_enriches_failed_browser_agent_result():
    result = enrich_web_tool_result(
        "browser_agent",
        {"success": False, "result": "HTTP 429 too many requests"},
    )

    assert result["error_category"] == "rate_limited"
    assert result["retryable"] is False
    assert "recovery_hint" in result


def test_web_scan_failure_gets_structured_recovery(monkeypatch, tmp_path):
    import core.ga as ga

    monkeypatch.setattr(
        ga,
        "web_scan",
        lambda **kwargs: {
            "status": "error",
            "msg": "No available browser tabs; extension is not connected",
        },
    )
    handler = GenericAgentHandler(SimpleNamespace(verbose=False), cwd=str(tmp_path))

    outcome = exhaust(handler.do_web_scan({}, SimpleNamespace(content="")))

    assert outcome.data["error_category"] == "browser_unavailable"
    assert outcome.data["retryable"] is False
    assert "[WEB TOOL FAILURE]" in outcome.next_prompt


def test_browser_agent_rate_limit_gets_structured_recovery(monkeypatch, tmp_path):
    import core.browser_agent as browser_agent

    monkeypatch.setattr(
        browser_agent,
        "run_browser_agent",
        lambda *args, **kwargs: {
            "success": False,
            "result": "API status 429 rate_limit_exceeded",
            "steps_taken": 0,
        },
    )
    parent = SimpleNamespace(verbose=False, llmclient=SimpleNamespace(backend=SimpleNamespace(cfg={})))
    handler = GenericAgentHandler(parent, cwd=str(tmp_path))

    outcome = exhaust(
        handler.do_browser_agent(
            {"task": "search the web for python docs", "max_steps": 1},
            SimpleNamespace(content=""),
        )
    )

    assert outcome.data["error_category"] == "rate_limited"
    assert outcome.data["recommended_next_tool"] == "web_search"
    assert "[WEB TOOL FAILURE]" in outcome.next_prompt


def test_web_search_success_result(monkeypatch, tmp_path):
    import core.ga as ga

    monkeypatch.setattr(
        ga,
        "web_search",
        lambda **kwargs: {
            "status": "success",
            "query": kwargs["query"],
            "results": [{"title": "Python docs", "url": "https://docs.python.org/"}],
        },
    )
    handler = GenericAgentHandler(SimpleNamespace(verbose=False), cwd=str(tmp_path))

    outcome = exhaust(
        handler.do_web_search({"query": "python docs"}, SimpleNamespace(content=""))
    )

    assert outcome.data["status"] == "success"
    assert outcome.data["results"][0]["url"] == "https://docs.python.org/"


def test_web_search_uses_browser_driver_without_llm(monkeypatch):
    import core.ga as ga

    class FakeDriver:
        def __init__(self):
            self.default_session_id = None
            self.scripts = []

        def get_all_sessions(self):
            return [{"id": "tab-1", "url": "about:blank", "title": "blank"}]

        def execute_js(self, script, timeout=15):
            self.scripts.append(script)
            if "window.location.href =" in script:
                return {"data": "navigating"}
            return {
                "data": {
                    "title": "Search",
                    "url": "https://www.bing.com/search?q=python+docs",
                    "result_count": 1,
                    "results": [
                        {
                            "rank": 1,
                            "title": "Python docs",
                            "url": "https://docs.python.org/",
                            "snippet": "Official documentation",
                        }
                    ],
                }
            }

    fake = FakeDriver()
    monkeypatch.setattr(ga, "driver", fake)
    monkeypatch.setattr(ga, "first_init_driver", lambda: None)

    result = ga.web_search("python docs", max_results=3, timeout=3)

    assert result["status"] == "success"
    assert result["results"][0]["url"] == "https://docs.python.org/"
    assert any("https://www.bing.com/search?q=python+docs" in script for script in fake.scripts)


def test_web_search_github_engine_uses_api_without_browser(monkeypatch):
    import core.ga as ga

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "total_count": 1,
                "items": [
                    {
                        "full_name": "python/cpython",
                        "html_url": "https://github.com/python/cpython",
                        "description": "The Python programming language",
                        "stargazers_count": 64000,
                        "language": "Python",
                        "updated_at": "2026-01-01T00:00:00Z",
                    }
                ],
            }

    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr(ga, "driver", None)
    monkeypatch.setattr(ga, "first_init_driver", lambda: (_ for _ in ()).throw(AssertionError("browser used")))
    monkeypatch.setattr(ga.requests, "get", fake_get)

    result = ga.web_search("python cpython", engine="github", max_results=3, timeout=7)

    assert result["status"] == "success"
    assert result["engine"] == "github"
    assert result["search_url"] == "https://api.github.com/search/repositories"
    assert result["results"][0]["url"] == "https://github.com/python/cpython"
    assert captured["url"] == "https://api.github.com/search/repositories"
    assert captured["kwargs"]["params"]["q"] == "python cpython"
    assert captured["kwargs"]["params"]["per_page"] == 3

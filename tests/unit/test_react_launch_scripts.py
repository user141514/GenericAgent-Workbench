from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _script(name: str) -> str:
    path = ROOT / name
    if not path.exists():
        pytest.skip(f"Local launch script is not present: {name}")
    return path.read_text(encoding="utf-8").lower()


def test_start_react_opens_electron_desktop_shell() -> None:
    content = _script("start_react.bat")

    assert "npm.cmd run electron:dev" in content
    assert 'start "" "http://127.0.0.1:5173"' not in content


def test_start_react_requires_current_api_contract_before_reuse() -> None:
    content = _script("start_react.bat")

    assert "/api/status" in content
    assert "/api/llm-config" in content
    assert "stop_stale_api" in content
    assert "core.api.server" in content


def test_start_react_browser_keeps_explicit_browser_entrypoint() -> None:
    content = _script("start_react_browser.bat")

    assert 'start "" "http://127.0.0.1:5173"' in content
    assert "npm.cmd run electron:dev" not in content


def test_start_desktop_remains_electron_entrypoint() -> None:
    content = _script("start_desktop.bat")

    assert "npm.cmd run electron:dev" in content

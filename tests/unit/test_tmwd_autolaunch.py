from __future__ import annotations

from pathlib import Path

from core import ga


def test_build_tmwd_browser_cmd_loads_extension_and_profile(tmp_path):
    browser = str(tmp_path / "msedge.exe")
    profile = str(tmp_path / "profile")
    extension = str(tmp_path / "tmwd_cdp_bridge")

    cmd = ga._build_tmwd_browser_cmd(browser, profile, extension, "https://example.com")

    assert cmd[0] == browser
    assert f"--user-data-dir={profile}" in cmd
    assert f"--load-extension={extension}" in cmd
    assert "https://example.com" == cmd[-1]


def test_find_tmwd_browser_exe_prefers_env_override(monkeypatch, tmp_path):
    fake_browser = tmp_path / "browser.exe"
    fake_browser.write_text("", encoding="utf-8")
    monkeypatch.setenv("GA_BROWSER_EXE", str(fake_browser))

    assert ga._find_tmwd_browser_exe() == str(fake_browser)


def test_launch_tmwd_browser_respects_disable_flag(monkeypatch):
    monkeypatch.setenv("GENERIC_AGENT_WEB_AUTOLAUNCH", "0")
    monkeypatch.setattr(ga, "_tmwd_browser_proc", None)

    assert ga._launch_tmwd_browser() is False

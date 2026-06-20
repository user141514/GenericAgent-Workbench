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


def test_launch_tmwd_browser_defaults_to_blank_page(monkeypatch, tmp_path):
    browser = tmp_path / "msedge.exe"
    browser.write_text("", encoding="utf-8")
    extension = tmp_path / "assets" / "tmwd_cdp_bridge"
    extension.mkdir(parents=True)
    (extension / "manifest.json").write_text("{}", encoding="utf-8")
    launched = {}

    class FakeProcess:
        def poll(self):
            return None

    def fake_popen(cmd, **kwargs):
        launched["cmd"] = cmd
        launched["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.delenv("GENERIC_AGENT_WEB_AUTOLAUNCH_URL", raising=False)
    monkeypatch.setenv("GENERIC_AGENT_WEB_AUTOLAUNCH", "1")
    monkeypatch.setattr(ga, "_tmwd_browser_proc", None)
    monkeypatch.setattr(ga, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(ga, "_find_tmwd_browser_exe", lambda: str(browser))
    monkeypatch.setattr(ga.subprocess, "Popen", fake_popen)

    assert ga._launch_tmwd_browser() is True
    assert launched["cmd"][-1] == "about:blank"


def test_launch_tmwd_browser_skips_invalid_extension(monkeypatch, tmp_path):
    browser = tmp_path / "msedge.exe"
    browser.write_text("", encoding="utf-8")
    extension = tmp_path / "assets" / "tmwd_cdp_bridge"
    extension.mkdir(parents=True)
    launched = {"called": False}

    def fail_popen(*args, **kwargs):
        launched["called"] = True
        raise AssertionError("browser should not launch without extension manifest")

    monkeypatch.setenv("GENERIC_AGENT_WEB_AUTOLAUNCH", "1")
    monkeypatch.setattr(ga, "_tmwd_browser_proc", None)
    monkeypatch.setattr(ga, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(ga, "_find_tmwd_browser_exe", lambda: str(browser))
    monkeypatch.setattr(ga.subprocess, "Popen", fail_popen)

    assert ga._launch_tmwd_browser() is False
    assert launched["called"] is False

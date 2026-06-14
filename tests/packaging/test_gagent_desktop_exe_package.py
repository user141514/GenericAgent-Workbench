import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "packages" / "gagent-desktop"


def test_electron_builder_packages_backend_and_python_runtime() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    build = manifest["build"]

    assert build["win"]["target"][0]["target"] == "portable"
    assert build["win"]["icon"] == "backend/assets/icons/genericagent.ico"
    resources = {(item["from"], item["to"]) for item in build["extraResources"]}
    assert ("backend", "backend") in resources
    assert ("python-runtime", "python-runtime") in resources


def test_electron_main_can_start_packaged_backend() -> None:
    main = (PACKAGE / "electron" / "main.cjs").read_text(encoding="utf-8")

    assert "ensureBackendRunning" in main
    assert "resolveBackendRoot" in main
    assert "resolvePythonExecutable" in main
    assert "python-runtime" in main
    assert "core.api.server" in main
    assert "/api/status" in main
    assert "/api/llm-config" in main
    assert "httpStatusOk" in main
    assert "app.quit()" in main


def test_windows_runtime_scripts_exist_and_are_parameterized() -> None:
    runtime_script = ROOT / "tools" / "prepare_gagent_desktop_windows_runtime.ps1"
    build_script = ROOT / "tools" / "build_gagent_desktop_windows.ps1"

    assert runtime_script.exists()
    assert build_script.exists()
    runtime_text = runtime_script.read_text(encoding="utf-8")
    build_text = build_script.read_text(encoding="utf-8")
    assert "PythonVersion" in runtime_text
    assert "PipIndexUrl" in runtime_text
    assert "Invoke-Native" in runtime_text
    assert "SkipDependencyInstall" in runtime_text
    assert "requirements-desktop.txt" in runtime_text
    assert "..\\backend" in runtime_text
    assert "python.org/ftp/python" in runtime_text
    assert "electron-builder" not in runtime_text
    assert "dist:win" in build_text


def test_electron_builder_runner_preserves_npm_electron_dependency() -> None:
    runner = PACKAGE / "scripts" / "run-electron-builder.cjs"
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    text = runner.read_text(encoding="utf-8")

    assert runner.exists()
    assert manifest["dependencies"]["electron"]
    assert "manifest.devDependencies.electron" in text
    assert "fs.writeFileSync(packageJsonPath, originalText" in text

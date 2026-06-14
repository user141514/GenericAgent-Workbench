import json
import subprocess
from pathlib import Path

from tools.security_scan import validate_npm_manifest, validate_publish_file_list


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "packages" / "gagent-desktop"


def test_gagent_desktop_manifest_is_publishable_and_whitelisted() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))

    assert manifest.get("private") is not True
    assert manifest["files"] == [
        "backend/**/*",
        "!backend/**/__pycache__/**",
        "!backend/**/*.pyc",
        "!backend/**/*.pyo",
        "bin/**/*",
        "electron/**/*",
        "scripts/**/*",
        "dist/**/*",
        "python-runtime/**/*",
        "!python-runtime/**/__pycache__/**",
        "!python-runtime/**/*.pyc",
        "!python-runtime/**/*.pyo",
        "README.md",
        "package.json",
    ]
    assert validate_npm_manifest(PACKAGE / "package.json") == []


def test_gagent_desktop_cli_dry_run_uses_packaged_backend_by_default() -> None:
    result = subprocess.run(
        [
            "node",
            str(PACKAGE / "bin" / "gagent-desktop.js"),
            "--dry-run",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["ok"] is True
    assert Path(payload["repo"]).resolve() == PACKAGE / "backend"
    assert payload["repoSource"] == "packaged"
    assert payload["hasBackend"] is True
    assert payload["hasReactDist"] is True
    assert payload["usesPackagedBackend"] is True
    assert Path(payload["requirements"]).name == "requirements-desktop.txt"
    assert "python-runtime" in payload["embeddedPython"]
    if payload["hasEmbeddedPython"]:
        assert payload["python"] == payload["embeddedPython"]


def test_gagent_desktop_cli_dry_run_can_override_with_external_repo() -> None:
    result = subprocess.run(
        [
            "node",
            str(PACKAGE / "bin" / "gagent-desktop.js"),
            "--repo",
            str(ROOT),
            "--dry-run",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)

    assert payload["ok"] is True
    assert Path(payload["repo"]).resolve() == ROOT
    assert payload["repoSource"] == "arg"
    assert payload["usesPackagedBackend"] is False


def test_gagent_desktop_cli_health_check_requires_current_api_contract() -> None:
    cli = (PACKAGE / "bin" / "gagent-desktop.js").read_text(encoding="utf-8")

    assert "/api/status" in cli
    assert "/api/llm-config" in cli
    assert "httpStatusOk" in cli


def test_packaged_backend_contains_hot_path_fixes() -> None:
    packaged_llmcore = (PACKAGE / "backend" / "core" / "llmcore.py").read_text(encoding="utf-8")
    packaged_openai_main = (PACKAGE / "backend" / "core" / "openai_agentmain.py").read_text(encoding="utf-8")
    packaged_capabilities = (PACKAGE / "backend" / "core" / "llm_capabilities.py").read_text(encoding="utf-8")

    assert "_COMPRESS_TAG_PATS" in packaged_llmcore
    assert "_COMPRESS_HISTORY_COUNTS" in packaged_llmcore
    assert "_MYKEYS_CACHE_LOCK" in packaged_llmcore
    assert "_log_sse_json_error" in packaged_llmcore
    assert "timeout=max(0.01, min(5, remaining))" in packaged_openai_main
    assert 'model_family="deepseek"' in packaged_capabilities
    assert 'protocol="openai"' in packaged_capabilities


def test_gagent_desktop_readme_documents_backend_strategy() -> None:
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")

    assert "packaged backend" in readme
    assert "does **not** publish the repository root" in readme
    assert "gagent-desktop setup" in readme
    assert "Windows `.exe` Build" in readme


def test_publish_file_list_rejects_local_state_paths() -> None:
    findings = validate_publish_file_list(
        [
            "package.json",
            "dist/index.html",
            "backend/temp/model_responses_openai/leak.json",
            "backend/mykey.py",
            "backend/memory/history_memory_inbox.md",
            "backend/memory/catalog.sqlite",
            "backend/memory/global_mem.txt",
        ]
    )

    assert {finding.rule for finding in findings} == {"denied_publish_file"}

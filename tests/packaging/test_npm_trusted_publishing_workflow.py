import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "packages" / "gagent-desktop"
WORKFLOW = ROOT / ".github" / "workflows" / "publish-npm.yml"


def test_gagent_desktop_package_declares_github_repository_for_trusted_publishing() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))

    assert manifest["repository"] == {
        "type": "git",
        "url": "git+ssh://git@github.com/user141514/GenericAgent-Workbench.git",
        "directory": "packages/gagent-desktop",
    }


def test_npm_trusted_publishing_workflow_builds_complete_windows_package() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "id-token: write" in workflow
    assert "contents: read" in workflow
    assert "runs-on: windows-latest" in workflow
    assert "node-version: '24'" in workflow
    assert "registry-url: 'https://registry.npmjs.org'" in workflow
    assert "package-manager-cache: false" in workflow
    assert "npm ci" in workflow
    assert "npm --prefix frontends/react_app ci" in workflow
    assert "tools\\prepare_gagent_desktop_package.ps1" in workflow
    assert "tools\\prepare_gagent_desktop_windows_runtime.ps1" in workflow
    assert "npm --prefix packages/gagent-desktop run prepublishOnly" in workflow
    assert "npm --prefix packages/gagent-desktop publish --access public" in workflow
    assert "NODE_AUTH_TOKEN" not in workflow
    assert "NPM_TOKEN" not in workflow

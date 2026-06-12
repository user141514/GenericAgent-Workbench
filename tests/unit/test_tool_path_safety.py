from core.runtime.path_safety import (
    TOOL_PATH_GUARD_ENV_VAR,
    resolve_tool_path,
)


def test_rejects_path_escape(monkeypatch, tmp_path):
    monkeypatch.delenv(TOOL_PATH_GUARD_ENV_VAR, raising=False)
    project = tmp_path / "repo"
    work = project / "temp"
    outside = tmp_path / "outside.txt"
    work.mkdir(parents=True)
    outside.write_text("secret", encoding="utf-8")

    result = resolve_tool_path(
        "../../outside.txt",
        base_dir=str(work),
        project_root=str(project),
        mode="read",
    )

    assert not result.allowed
    assert result.reason == "path_escape"


def test_rejects_sensitive_project_file(monkeypatch, tmp_path):
    monkeypatch.delenv(TOOL_PATH_GUARD_ENV_VAR, raising=False)
    project = tmp_path / "repo"
    work = project / "temp"
    work.mkdir(parents=True)
    (project / "mykey.py").write_text("API_KEY='x'", encoding="utf-8")

    result = resolve_tool_path(
        "../mykey.py",
        base_dir=str(work),
        project_root=str(project),
        mode="read",
    )

    assert not result.allowed
    assert result.reason == "sensitive_path"


def test_allows_normal_project_file(monkeypatch, tmp_path):
    monkeypatch.delenv(TOOL_PATH_GUARD_ENV_VAR, raising=False)
    project = tmp_path / "repo"
    work = project / "temp"
    src = project / "core" / "app.py"
    src.parent.mkdir(parents=True)
    work.mkdir(parents=True)
    src.write_text("print('ok')", encoding="utf-8")

    result = resolve_tool_path(
        "../core/app.py",
        base_dir=str(work),
        project_root=str(project),
        mode="read",
    )

    assert result.allowed
    assert result.path == str(src.resolve())

"""Phase 2b: ProjectIdentity unit tests."""
import os
import tempfile
from core.context.project_identity import detect_project, _make_project_id, ProjectIdentity


class TestProjectIdentityEnabled:
    """Tests that require GA_CONTEXT_RUNTIME_ENABLED=1."""

    def setup_method(self):
        os.environ["GA_CONTEXT_RUNTIME_ENABLED"] = "1"

    def teardown_method(self):
        os.environ.pop("GA_CONTEXT_RUNTIME_ENABLED", None)

    def test_project_id_stable(self):
        """Same path produces same project_id."""
        with tempfile.TemporaryDirectory() as tmp:
            pid1 = detect_project(tmp)
            pid2 = detect_project(tmp)
            assert pid1 is not None
            assert pid2 is not None
            assert pid1.project_id == pid2.project_id

    def test_project_id_different_paths(self):
        """Different paths produce different project_id."""
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            pid1 = detect_project(tmp1)
            pid2 = detect_project(tmp2)
            assert pid1 is not None
            assert pid2 is not None
            assert pid1.project_id != pid2.project_id

    def test_project_name_from_basename(self):
        """project_name is the basename of the root."""
        with tempfile.TemporaryDirectory() as tmp:
            pid = detect_project(tmp)
            assert pid is not None
            assert pid.project_name == os.path.basename(tmp)

    def test_key_files_python_detected(self):
        """Detects Python project files."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create Python project files
            open(os.path.join(tmp, "pyproject.toml"), "w").close()
            open(os.path.join(tmp, "requirements.txt"), "w").close()
            pid = detect_project(tmp)
            assert pid is not None
            assert "pyproject.toml" in pid.key_files
            assert "requirements.txt" in pid.key_files
            assert "python" in pid.languages

    def test_key_files_js_detected(self):
        """Detects JavaScript/TypeScript project files."""
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "package.json"), "w").close()
            open(os.path.join(tmp, "tsconfig.json"), "w").close()
            pid = detect_project(tmp)
            assert pid is not None
            assert "package.json" in pid.key_files
            assert "tsconfig.json" in pid.key_files
            assert "typescript" in pid.languages

    def test_key_files_capped(self):
        """key_files list is capped at 20."""
        with tempfile.TemporaryDirectory() as tmp:
            pid = detect_project(tmp)
            assert pid is not None
            assert len(pid.key_files) <= 20

    def test_project_root_from_workspace_snapshot(self):
        """Works with the project root from a workspace probe."""
        # Use the actual project root
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        pid = detect_project(project_root)
        assert pid is not None
        assert pid.project_root == project_root
        assert len(pid.project_name) > 0

    def test_languages_sorted(self):
        """Languages list is sorted."""
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "pyproject.toml"), "w").close()
            open(os.path.join(tmp, "package.json"), "w").close()
            open(os.path.join(tmp, "Cargo.toml"), "w").close()
            pid = detect_project(tmp)
            assert pid is not None
            assert pid.languages == sorted(pid.languages)

    def test_project_root_absolute(self):
        """project_root is always an absolute path."""
        with tempfile.TemporaryDirectory() as tmp:
            pid = detect_project(tmp)
            assert pid is not None
            assert os.path.isabs(pid.project_root)


class TestProjectIdentityDisabled:
    """Tests when GA_CONTEXT_RUNTIME_ENABLED is not '1'."""

    def setup_method(self):
        os.environ.pop("GA_CONTEXT_RUNTIME_ENABLED", None)

    def test_detect_returns_none_when_disabled(self):
        pid = detect_project("/tmp")
        assert pid is None

    def test_detect_returns_none_when_none_root(self):
        """Returns None when project_root is None."""
        os.environ["GA_CONTEXT_RUNTIME_ENABLED"] = "1"
        try:
            pid = detect_project(None)
            assert pid is None
        finally:
            os.environ.pop("GA_CONTEXT_RUNTIME_ENABLED", None)


class TestMakeProjectId:
    """Test _make_project_id directly."""

    def test_deterministic(self):
        a = _make_project_id("/home/user/project")
        b = _make_project_id("/home/user/project")
        assert a == b
        assert len(a) == 12

    def test_case_sensitive(self):
        """Different case produces different ids."""
        a = _make_project_id("/Home/User/Project")
        b = _make_project_id("/home/user/project")
        assert a != b

    def test_hex_chars_only(self):
        pid = _make_project_id("/some/path")
        assert all(c in "0123456789abcdef" for c in pid)

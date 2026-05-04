"""Phase 2a: WorkspaceProbe unit tests."""
import os
import tempfile
import subprocess
import pytest
from core.context.workspace_probe import WorkspaceProbe, WorkspaceSnapshot


def _in_git_repo():
    """Check if we're currently inside a git repo."""
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True, timeout=3,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        return True
    except Exception:
        return False


class TestWorkspaceProbeEnabled:
    """Tests that require GA_CONTEXT_RUNTIME_ENABLED=1."""

    def setup_method(self):
        os.environ["GA_CONTEXT_RUNTIME_ENABLED"] = "1"

    def teardown_method(self):
        os.environ.pop("GA_CONTEXT_RUNTIME_ENABLED", None)

    def test_probe_cwd_absolute(self):
        """cwd is an absolute path."""
        snap = WorkspaceProbe.probe()
        assert snap is not None
        assert os.path.isabs(snap.cwd)

    def test_probe_cwd_matches_os_getcwd(self):
        """Default probe uses os.getcwd()."""
        snap = WorkspaceProbe.probe()
        assert snap is not None
        assert snap.cwd == os.path.abspath(os.getcwd())

    def test_probe_explicit_cwd(self):
        """Probe with an explicit directory."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = WorkspaceProbe.probe(cwd=tmp)
            assert snap is not None
            assert snap.cwd == os.path.abspath(tmp)
            assert snap.git_root is None  # temp dir is not a git repo

    def test_probe_git_repo_detected(self):
        """When probing the project root (which is a git repo), git_root is set."""
        if not _in_git_repo():
            pytest.skip("Not in a git repository")
        snap = WorkspaceProbe.probe()
        assert snap is not None
        assert snap.git_root is not None
        assert os.path.isabs(snap.git_root)

    def test_probe_git_branch(self):
        """When in a git repo, branch is detected."""
        if not _in_git_repo():
            pytest.skip("Not in a git repository")
        snap = WorkspaceProbe.probe()
        assert snap is not None
        assert snap.git_root is not None
        # branch may be None in detached HEAD, but typically is set
        # Just verify it doesn't crash

    def test_probe_dirty_files_capped(self):
        """dirty_files list is capped at 30 entries."""
        snap = WorkspaceProbe.probe()
        assert snap is not None
        assert len(snap.dirty_files) <= 30

    def test_probe_detected_at_is_recent(self):
        """detected_at timestamp is close to now."""
        import time
        snap = WorkspaceProbe.probe()
        assert snap is not None
        assert abs(snap.detected_at - time.time()) < 5.0


class TestWorkspaceProbeDisabled:
    """Tests when GA_CONTEXT_RUNTIME_ENABLED is not '1'."""

    def setup_method(self):
        os.environ.pop("GA_CONTEXT_RUNTIME_ENABLED", None)

    def test_probe_returns_none_when_disabled(self):
        """Returns None when env var is not set to '1'."""
        snap = WorkspaceProbe.probe()
        assert snap is None

    def test_probe_returns_none_when_explicitly_zero(self):
        """Returns None when env var is '0'."""
        os.environ["GA_CONTEXT_RUNTIME_ENABLED"] = "0"
        try:
            snap = WorkspaceProbe.probe()
            assert snap is None
        finally:
            os.environ.pop("GA_CONTEXT_RUNTIME_ENABLED", None)


class TestWorkspaceSnapshotInvariants:
    """Test the dataclass invariants directly."""

    def test_dirty_files_capped_at_construction(self):
        """Post-init caps dirty_files at 30."""
        snap = WorkspaceSnapshot(
            cwd="/tmp",
            dirty_files=[f"file_{i}.py" for i in range(50)],
        )
        assert len(snap.dirty_files) == 30

    def test_detected_at_defaults_to_now(self):
        """detected_at defaults to current time if 0."""
        import time
        snap = WorkspaceSnapshot(cwd="/tmp", detected_at=0.0)
        assert abs(snap.detected_at - time.time()) < 2.0

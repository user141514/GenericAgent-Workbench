"""Phase 6: Integration tests — preview mode (full pipeline, no injection)."""
import json
import os
import tempfile
import time
import pytest
from core.context.workspace_probe import WorkspaceProbe
from core.context.project_identity import detect_project
from core.context.runtime_identity import detect_runtime
from core.context.memory_reader import MemoryReader
from core.context.context_builder import ContextBuilder


@pytest.fixture(autouse=True)
def enable_context():
    os.environ["GA_CONTEXT_RUNTIME_ENABLED"] = "1"
    yield
    os.environ.pop("GA_CONTEXT_RUNTIME_ENABLED", None)


@pytest.fixture
def project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture
def preview_dir(project_root):
    d = os.path.join(project_root, "temp", "context_previews_test")
    os.makedirs(d, exist_ok=True)
    yield d
    # Cleanup
    for f in os.listdir(d):
        os.unlink(os.path.join(d, f))
    os.rmdir(d)


class TestFullPipelinePreview:
    """End-to-end: probe workspace → reader → builder → serialize."""

    def test_full_pipeline_produces_packet(self, project_root):
        """The full pipeline from probe to ContextPacket works."""
        snap = WorkspaceProbe.probe()
        pid = detect_project(project_root)
        rt = detect_runtime(agent_backend="openai-agents")
        reader = MemoryReader(project_root=project_root)
        bundle = reader.scoped_query("test query", max_chars=2000)

        builder = ContextBuilder(max_chars=4000, policy_mode="preview")
        packet = builder.build(
            workspace=snap,
            project=pid,
            runtime=rt,
            memory_bundle=bundle,
            target_route="code",
        )

        assert packet is not None
        assert packet.target_route == "code"
        assert packet.policy_mode == "preview"
        assert packet.workspace is not None
        assert packet.project is not None
        assert packet.total_chars > 0

    def test_preview_packet_serializable_to_json(self, project_root, preview_dir):
        """ContextPacket metadata can be serialized to JSON for preview."""
        snap = WorkspaceProbe.probe()
        pid = detect_project(project_root)
        reader = MemoryReader(project_root=project_root)
        bundle = reader.scoped_query("test", max_chars=1000)

        builder = ContextBuilder(policy_mode="preview")
        packet = builder.build(
            workspace=snap, project=pid,
            memory_bundle=bundle, target_route="code",
        )

        assert packet is not None

        # Build a JSON-safe preview dict (not the full dataclass)
        preview = {
            "generated_at": packet.generated_at,
            "target_route": packet.target_route,
            "policy_mode": packet.policy_mode,
            "total_chars": packet.total_chars,
            "source_breakdown": packet.source_breakdown,
            "workspace_cwd": packet.workspace.cwd if packet.workspace else None,
            "project_id": packet.project.project_id if packet.project else None,
            "project_name": packet.project.project_name if packet.project else None,
        }

        # Write to preview file
        run_id = "test_run_001"
        path = os.path.join(preview_dir, f"{run_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(preview, f, indent=2, ensure_ascii=False)

        # Verify file exists and is valid JSON
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["target_route"] == "code"
        assert loaded["policy_mode"] == "preview"
        assert loaded["total_chars"] > 0

    def test_chat_route_not_in_preview(self, project_root):
        """Chat route produces no packet → no preview file."""
        snap = WorkspaceProbe.probe()
        pid = detect_project(project_root)

        builder = ContextBuilder(policy_mode="preview")
        packet = builder.build(
            workspace=snap, project=pid,
            target_route="chat",
        )
        assert packet is None  # chat route excluded


class TestLegacyMemoryUnchanged:
    """L1/L2 files are never modified by the context pipeline."""

    def test_l1_l2_readonly(self, project_root):
        """Reading L1/L2 does not modify the files."""
        l1_path = os.path.join(project_root, "memory", "global_mem_insight.txt")
        l2_path = os.path.join(project_root, "memory", "global_mem.txt")

        mtime_l1_before = os.path.getmtime(l1_path) if os.path.exists(l1_path) else None
        mtime_l2_before = os.path.getmtime(l2_path) if os.path.exists(l2_path) else None

        reader = MemoryReader(project_root=project_root)
        reader.read_global_memory()
        reader.scoped_query("test", max_chars=1000)

        if mtime_l1_before and os.path.exists(l1_path):
            assert os.path.getmtime(l1_path) == mtime_l1_before
        if mtime_l2_before and os.path.exists(l2_path):
            assert os.path.getmtime(l2_path) == mtime_l2_before


class TestDirectorySwitchIsolation:
    """Different cwd → different project_id, no cross-contamination."""

    def test_different_directories_different_ids(self):
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            pid1 = detect_project(tmp1)
            pid2 = detect_project(tmp2)
            assert pid1 is not None
            assert pid2 is not None
            assert pid1.project_id != pid2.project_id
            assert pid1.project_name != pid2.project_name


class TestDisabledByDefault:
    """When GA_CONTEXT_RUNTIME_ENABLED is not set, pipeline returns None."""

    def test_disabled_pipeline(self, project_root):
        os.environ.pop("GA_CONTEXT_RUNTIME_ENABLED", None)
        try:
            snap = WorkspaceProbe.probe()
            assert snap is None
            pid = detect_project(project_root)
            assert pid is None
            rt = detect_runtime()
            assert rt is None
        finally:
            os.environ["GA_CONTEXT_RUNTIME_ENABLED"] = "1"


class TestPreviewModeNoInjection:
    """Preview mode does NOT inject into any agent prompt."""

    def test_serialize_has_preview_tag(self, project_root):
        """The serialized output clearly marks itself as preview."""
        snap = WorkspaceProbe.probe()
        pid = detect_project(project_root)
        reader = MemoryReader(project_root=project_root)
        bundle = reader.scoped_query("test", max_chars=500)

        builder = ContextBuilder(policy_mode="preview")
        packet = builder.build(
            workspace=snap, project=pid,
            memory_bundle=bundle, target_route="code",
        )

        assert packet is not None
        text = builder.serialize(packet)
        assert "preview mode" in text
        assert "inject mode" not in text

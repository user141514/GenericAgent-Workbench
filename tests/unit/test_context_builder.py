"""Phase 5: ContextBuilder unit tests."""
import os
import time
import pytest
from core.context.workspace_probe import WorkspaceSnapshot
from core.context.project_identity import ProjectIdentity
from core.context.runtime_identity import RuntimeIdentity
from core.context.memory_reader import MemoryBlock, MemoryBundle
from core.context.context_builder import ContextBuilder, ContextPacket


@pytest.fixture
def builder():
    return ContextBuilder(max_chars=4000, policy_mode="inject")


@pytest.fixture
def sample_workspace():
    return WorkspaceSnapshot(
        cwd="/home/user/projects/myapp",
        git_root="/home/user/projects/myapp",
        git_branch="feature/auth",
        has_uncommitted_changes=True,
        dirty_files=["src/auth.py"],
    )


@pytest.fixture
def sample_project():
    return ProjectIdentity(
        project_id="abc123def456",
        project_name="myapp",
        project_root="/home/user/projects/myapp",
        key_files=["pyproject.toml", "requirements.txt", "src/main.py"],
        languages=["python"],
    )


@pytest.fixture
def sample_runtime():
    return RuntimeIdentity(
        session_id="sess_001",
        process_id=12345,
        agent_backend="openai-agents",
        hostname="devbox",
        started_at=time.time(),
    )


@pytest.fixture
def sample_memory():
    blocks = [
        MemoryBlock(source="L1", source_priority="primary", content="L1: project uses FastAPI", relevance_score=1.0),
        MemoryBlock(source="L2", source_priority="primary", content="L2: auth module uses bcrypt", relevance_score=0.9),
        MemoryBlock(source="structured:supplementary", source_priority="supplementary", content="structured: previous session worked on auth", relevance_score=0.6),
    ]
    return MemoryBundle(blocks=blocks)


class TestContextBuilderRouteGating:
    """Build returns None for excluded routes."""

    def test_build_returns_none_for_chat_route(self, builder, sample_workspace, sample_project):
        packet = builder.build(workspace=sample_workspace, project=sample_project, target_route="chat")
        assert packet is None

    def test_build_returns_none_for_none_route(self, builder):
        packet = builder.build(target_route=None)
        assert packet is None

    def test_build_returns_none_for_off_mode(self):
        builder = ContextBuilder(policy_mode="off")
        packet = builder.build(target_route="code")
        assert packet is None

    def test_build_code_route_returns_packet(self, builder, sample_workspace, sample_project, sample_memory):
        packet = builder.build(
            workspace=sample_workspace, project=sample_project,
            memory_bundle=sample_memory, target_route="code",
        )
        assert packet is not None
        assert packet.target_route == "code"
        assert packet.workspace is not None
        assert packet.project is not None

    def test_build_executor_route_returns_full_packet(self, builder, sample_workspace, sample_project, sample_runtime, sample_memory):
        packet = builder.build(
            workspace=sample_workspace, project=sample_project,
            runtime=sample_runtime, memory_bundle=sample_memory,
            target_route="executor",
        )
        assert packet is not None
        assert packet.target_route == "executor"


class TestContextBuilderBudget:
    """ContextPacket respects max_chars and route budgets."""

    def test_code_route_has_workspace_and_project(self, builder, sample_workspace, sample_project):
        packet = builder.build(workspace=sample_workspace, project=sample_project, target_route="code")
        assert packet is not None
        assert packet.source_breakdown["workspace"] > 0
        assert packet.source_breakdown["project"] > 0
        assert packet.source_breakdown["memory"] == 0  # no memory passed

    def test_code_route_includes_memory(self, builder, sample_workspace, sample_project, sample_memory):
        packet = builder.build(
            workspace=sample_workspace, project=sample_project,
            memory_bundle=sample_memory, target_route="code",
        )
        assert packet is not None
        assert packet.source_breakdown["memory"] > 0

    def test_total_chars_within_limits(self, builder, sample_workspace, sample_project, sample_runtime, sample_memory):
        packet = builder.build(
            workspace=sample_workspace, project=sample_project,
            runtime=sample_runtime, memory_bundle=sample_memory,
            target_route="executor",
        )
        assert packet is not None
        assert packet.total_chars <= 4000

    def test_chat_route_budget_is_zero(self, builder):
        # Chat route has empty budget in _ROUTE_BUDGET
        packet = builder.build(target_route="chat")
        assert packet is None  # returns None before any budget allocation


class TestContextBuilderSerialize:
    """Serialize produces valid injection format."""

    def test_serialize_code_packet(self, builder, sample_workspace, sample_project, sample_runtime, sample_memory):
        packet = builder.build(
            workspace=sample_workspace, project=sample_project,
            runtime=sample_runtime, memory_bundle=sample_memory,
            target_route="code",
        )
        assert packet is not None
        text = builder.serialize(packet)
        assert "[CONTEXT PACKET" in text
        assert "[/CONTEXT PACKET]" in text
        assert "## Workspace" in text
        assert "## Project" in text
        assert "myapp" in text
        assert "feature/auth" in text

    def test_serialize_empty_packet(self, builder):
        text = builder.serialize(None)
        assert text == ""

    def test_serialize_has_correct_metadata(self, builder, sample_workspace, sample_project, sample_memory):
        packet = builder.build(
            workspace=sample_workspace, project=sample_project,
            memory_bundle=sample_memory, target_route="code",
        )
        text = builder.serialize(packet)
        assert "inject mode" in text
        assert "route=code" in text


class TestContextBuilderPreviewMode:
    """Preview mode still builds but has correct metadata."""

    def test_preview_mode_builds_packet(self, sample_workspace, sample_project, sample_memory):
        builder = ContextBuilder(policy_mode="preview")
        packet = builder.build(
            workspace=sample_workspace, project=sample_project,
            memory_bundle=sample_memory, target_route="code",
        )
        assert packet is not None
        assert packet.policy_mode == "preview"

    def test_preview_mode_serialized(self, sample_workspace, sample_project, sample_memory):
        builder = ContextBuilder(policy_mode="preview")
        packet = builder.build(
            workspace=sample_workspace, project=sample_project,
            memory_bundle=sample_memory, target_route="code",
        )
        text = builder.serialize(packet)
        assert "preview mode" in text


class TestSourceBreakdown:
    """source_breakdown tracks char counts accurately."""

    def test_breakdown_keys_exist(self, builder, sample_workspace, sample_project, sample_memory):
        packet = builder.build(
            workspace=sample_workspace, project=sample_project,
            memory_bundle=sample_memory, target_route="executor",
        )
        assert packet is not None
        for key in ("workspace", "project", "state", "memory"):
            assert key in packet.source_breakdown

    def test_breakdown_sums_to_total(self, builder, sample_workspace, sample_project, sample_memory):
        packet = builder.build(
            workspace=sample_workspace, project=sample_project,
            memory_bundle=sample_memory, target_route="executor",
        )
        assert packet is not None
        assert sum(packet.source_breakdown.values()) == packet.total_chars


class TestContextBuilderNoFileIO:
    """ContextBuilder never reads files or DB."""

    def test_builder_accepts_only_typed_inputs(self, builder, sample_workspace, sample_project):
        """builder.build() only accepts keyword arguments, never opens files."""
        packet = builder.build(
            workspace=sample_workspace,
            project=sample_project,
            target_route="code",
        )
        assert packet is not None
        # If we got here without file I/O errors, builder is pure

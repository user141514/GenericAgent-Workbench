"""
SharedArtifactStore unit tests — Level 4 blackboard.

Tests CRUD, versioning, thread safety, snapshot, and workspace summary.
"""

from __future__ import annotations

import threading

import pytest

from core.runtime.shared_store import Artifact, SharedArtifactStore


class TestCRUD:
    """Basic create, read, update, delete, list operations."""

    def test_write_and_read(self):
        store = SharedArtifactStore()
        version = store.write("auth.py", "def login(): pass", author="code_agent")
        assert version == 1

        artifact = store.read("auth.py")
        assert artifact is not None
        assert artifact.key == "auth.py"
        assert "def login()" in artifact.content
        assert artifact.author == "code_agent"
        assert artifact.version == 1

    def test_write_overwrite_bumps_version(self):
        store = SharedArtifactStore()
        store.write("auth.py", "v1", author="code_agent")
        v2 = store.write("auth.py", "v2", author="code_agent")
        assert v2 == 2

        artifact = store.read("auth.py")
        assert artifact.version == 2
        assert artifact.content == "v2"

    def test_read_missing_returns_none(self):
        store = SharedArtifactStore()
        assert store.read("nonexistent") is None

    def test_list_sorted_by_key(self):
        store = SharedArtifactStore()
        store.write("c.py", "c", author="x")
        store.write("a.py", "a", author="x")
        store.write("b.py", "b", author="x")

        keys = [a.key for a in store.list()]
        assert keys == ["a.py", "b.py", "c.py"]

    def test_list_keys_lightweight(self):
        store = SharedArtifactStore()
        store.write("x.py", "x", author="a")
        store.write("y.py", "y", author="a")
        assert store.list_keys() == ["x.py", "y.py"]

    def test_delete_existing(self):
        store = SharedArtifactStore()
        store.write("tmp.txt", "data", author="test")
        assert store.delete("tmp.txt") is True
        assert store.read("tmp.txt") is None

    def test_delete_missing(self):
        store = SharedArtifactStore()
        assert store.delete("nope") is False

    def test_len_and_contains(self):
        store = SharedArtifactStore()
        assert len(store) == 0
        store.write("k1", "v1", author="a")
        assert len(store) == 1
        assert "k1" in store
        assert "k2" not in store


class TestVersioning:
    """Version tracking per key."""

    def test_independent_versions(self):
        store = SharedArtifactStore()
        assert store.write("a.py", "a1", author="x") == 1
        assert store.write("b.py", "b1", author="x") == 1
        assert store.write("a.py", "a2", author="x") == 2
        assert store.read("b.py").version == 1
        assert store.read("a.py").version == 2

    def test_version_reset_on_delete_recreate(self):
        store = SharedArtifactStore()
        store.write("a.py", "v1", author="x")  # v1
        store.delete("a.py")
        v = store.write("a.py", "fresh", author="y")  # v1 again
        assert v == 1
        assert store.read("a.py").version == 1
        assert store.read("a.py").author == "y"


class TestThreadSafety:
    """Concurrent writes should not corrupt the store."""

    def test_concurrent_writes(self):
        store = SharedArtifactStore()
        errors = []

        def writer(key_prefix):
            try:
                for i in range(100):
                    store.write(f"{key_prefix}_{i}", f"content_{i}", author="test")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(f"t{tid}",)) for tid in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(store) == 500
        # All keys should be version 1
        for a in store.list():
            assert a.version == 1


class TestSnapshot:
    """Snapshot and workspace summary."""

    def test_snapshot_serializable(self):
        store = SharedArtifactStore()
        store.write("a.py", "hello", author="code")
        snap = store.snapshot()
        assert isinstance(snap, dict)
        assert snap["a.py"]["key"] == "a.py"
        assert snap["a.py"]["content"] == "hello"
        assert snap["a.py"]["author"] == "code"

    def test_workspace_summary_empty(self):
        store = SharedArtifactStore()
        assert "empty" in store.workspace_summary()

    def test_workspace_summary_with_artifacts(self):
        store = SharedArtifactStore()
        store.write("main.py", "print('hello world')", author="code_agent")
        store.write("test_main.py", "import main; def test(): ...", author="code_agent")
        summary = store.workspace_summary()
        assert "main.py" in summary
        assert "test_main.py" in summary
        assert "v1" in summary
        assert "code_agent" in summary


class TestMetadata:
    """Optional metadata on artifacts."""

    def test_metadata_stored(self):
        store = SharedArtifactStore()
        store.write("a.py", "code", author="code_agent", metadata={"lang": "python", "lines": 42})
        a = store.read("a.py")
        assert a.metadata["lang"] == "python"
        assert a.metadata["lines"] == 42

    def test_metadata_defaults_empty(self):
        store = SharedArtifactStore()
        store.write("a.py", "code", author="x")
        assert store.read("a.py").metadata == {}

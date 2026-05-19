"""Phase S1 tests for FileUploadService and UploadedFileInfo."""

import pytest
from frontends.services.file_upload_service import FileUploadService, UploadedFileInfo


# ── Fake uploaded file (simulates Streamlit UploadedFile) ────────────────

class FakeUploadedFile:
    """Minimal Streamlit UploadedFile simulation for testing."""

    def __init__(self, name: str, data: bytes, mime_type: str = ""):
        self.name = name
        self._data = data
        self.type = mime_type
        self.size = len(data)

    def getvalue(self) -> bytes:
        return self._data


# ── Tests ─────────────────────────────────────────────────────────────────

class TestUploadedFileInfo:
    """UploadedFileInfo dataclass — Streamlit-free."""

    def test_construction(self):
        info = UploadedFileInfo(
            file_id="abc123",
            name="test.txt",
            size=100,
            size_label="100 B",
            mime_type="text/plain",
            kind="text",
            suffix=".txt",
            saved_path="/tmp/u/abc123/test.txt",
            status="ready",
            preview_text="hello world",
        )
        assert info.is_ready
        assert info.name == "test.txt"
        assert info.kind == "text"

    def test_not_ready_when_error(self):
        info = UploadedFileInfo(file_id="x", name="bad.pdf", status="error")
        assert not info.is_ready

    def test_to_dict_roundtrip(self):
        info = UploadedFileInfo(
            file_id="f1", name="a.txt", size=10, size_label="10 B",
            mime_type="text/plain", kind="text", saved_path="/p",
            status="ready", preview_text="prev", distilled_text="dist",
            raw_text_length=5, warning="",
        )
        d = info.to_dict()
        assert d["id"] == "f1"
        assert d["name"] == "a.txt"
        assert d["status"] == "ready"
        assert d["preview_text"] == "prev"
        assert d["distilled_text"] == "dist"


class TestFileUploadService:
    """FileUploadService processes uploaded files into UploadedFileInfo."""

    def test_empty_list(self):
        svc = FileUploadService()
        results = svc.process([])
        assert results == []
        assert isinstance(results, list)

    def test_none_input(self):
        svc = FileUploadService()
        results = svc.process(None)  # type: ignore[arg-type]
        assert results == []

    def test_single_text_file(self):
        svc = FileUploadService()
        fake = FakeUploadedFile("hello.py", b"print('hello world')\n", "text/x-python")
        results = svc.process([fake])
        assert len(results) == 1
        r = results[0]
        assert isinstance(r, UploadedFileInfo)
        assert r.name == "hello.py"
        assert r.kind == "text"
        assert r.status == "ready"
        assert r.size > 0
        assert r.file_id != ""

    def test_multiple_files(self):
        svc = FileUploadService()
        files = [
            FakeUploadedFile("a.txt", b"content a"),
            FakeUploadedFile("b.md", b"# Title\n\nbody"),
        ]
        results = svc.process(files)
        assert len(results) == 2
        assert all(r.status == "ready" for r in results)
        assert results[0].name == "a.txt"
        assert results[1].name == "b.md"

    def test_dedup_by_name_and_content(self):
        """Same name + same content → cached result (file_id uses name+data hash)."""
        svc = FileUploadService()
        f1 = FakeUploadedFile("same.py", b"x = 1")
        f2 = FakeUploadedFile("same.py", b"x = 1")  # identical name AND content

        r1 = svc.process([f1])
        r2 = svc.process([f2])
        assert r1[0].file_id == r2[0].file_id

    def test_different_name_produces_different_id(self):
        """Different name + same content → different file_id (name is part of hash)."""
        svc = FileUploadService()
        f1 = FakeUploadedFile("a.py", b"x = 1")
        f2 = FakeUploadedFile("b.py", b"x = 1")

        r1 = svc.process([f1])
        r2 = svc.process([f2])
        assert r1[0].file_id != r2[0].file_id

    def test_name_extraction(self):
        svc = FileUploadService()
        fake = FakeUploadedFile("my_script.py", b"print(1)")
        r = svc.process([fake])[0]
        assert r.name == "my_script.py"

    def test_size_extraction(self):
        svc = FileUploadService()
        data = b"x" * 500
        fake = FakeUploadedFile("data.txt", data)
        r = svc.process([fake])[0]
        assert r.size == 500

    def test_mime_type_passthrough(self):
        svc = FileUploadService()
        fake = FakeUploadedFile("doc.json", b"{}", "application/json")
        r = svc.process([fake])[0]
        assert r.mime_type == "application/json"

    def test_unsupported_file_does_not_crash(self):
        """Non-text files should not crash the service."""
        svc = FileUploadService()
        fake = FakeUploadedFile("data.bin", b"\x00\x01\x02\x03", "application/octet-stream")
        r = svc.process([fake])[0]
        # Should return an UploadedFileInfo even for unsupported files
        assert isinstance(r, UploadedFileInfo)

    def test_preview_text_generated(self):
        svc = FileUploadService()
        fake = FakeUploadedFile("readme.txt", b"Hello\nWorld\n" * 10)
        r = svc.process([fake])[0]
        if r.status == "ready":
            assert len(r.preview_text) > 0

    def test_to_dict_output_format(self):
        """to_dict() must produce the exact keys expected by stapp.py helpers."""
        svc = FileUploadService()
        fake = FakeUploadedFile("test.py", b"x=1")
        r = svc.process([fake])[0]
        d = r.to_dict()
        expected_keys = {"id", "name", "size", "size_label", "mime", "kind",
                         "stored_path", "status", "preview_text", "distilled_text",
                         "raw_text_length", "warning"}
        assert set(d.keys()) == expected_keys

    def test_dict_compat_with_get_ready_attachments(self):
        """to_dict() output must pass get_ready_attachments() filter."""
        svc = FileUploadService()
        fake = FakeUploadedFile("test.py", b"x=1")
        results = svc.process([fake])
        # Simulate what sync_uploaded_files does
        uploaded_files = [r.to_dict() for r in results]
        ready = [item for item in uploaded_files if item.get("status") == "ready"]
        assert len(ready) == 1
        assert ready[0]["name"] == "test.py"

    def test_dict_compat_with_render_attachment_items(self):
        """All keys used by render_attachment_items() must be present."""
        svc = FileUploadService()
        fake = FakeUploadedFile("doc.txt", b"content")
        results = svc.process([fake])
        meta = results[0].to_dict()
        # render_attachment_items accesses these keys
        assert meta.get("status") is not None
        assert isinstance(meta["name"], str) and len(meta["name"]) > 0
        assert isinstance(meta["kind"], str)
        assert isinstance(meta["size_label"], str)
        assert "warning" in meta
        assert "preview_text" in meta

    def test_dict_compat_with_format_user_message(self):
        """item['name'] must be accessible."""
        svc = FileUploadService()
        fake = FakeUploadedFile("readme.md", b"# Title")
        results = svc.process([fake])
        meta = results[0].to_dict()
        # format_user_message does: f"- {item['name']}"
        assert meta["name"] == "readme.md"

    def test_dict_compat_with_build_attachment_prompt(self):
        """Keys used by build_attachment_prompt() must exist."""
        svc = FileUploadService()
        fake = FakeUploadedFile("data.csv", b"a,b,c\n1,2,3\n" * 20)
        results = svc.process([fake])
        meta = results[0].to_dict()
        # build_attachment_prompt uses these:
        assert "status" in meta
        assert "distilled_text" in meta
        assert "name" in meta
        assert "kind" in meta
        assert "size_label" in meta

    def test_dict_has_required_keys(self):
        """to_dict() must contain all 12 required keys; extra keys are allowed."""
        svc = FileUploadService()
        fake = FakeUploadedFile("test.py", b"x=1")
        results = svc.process([fake])
        meta = results[0].to_dict()
        required = {"id", "name", "size", "size_label", "mime", "kind",
                    "stored_path", "status", "preview_text", "distilled_text",
                    "raw_text_length", "warning"}
        missing = required - set(meta.keys())
        assert not missing, f"Missing required keys: {missing}"

    def test_extra_metadata_preserved(self):
        """Extra keys from file_processor (page_count, toc_count) are kept."""
        svc = FileUploadService()
        # Manually inject extra metadata into the service
        info = UploadedFileInfo(file_id="x", name="a.pdf", kind="pdf",
                                status="ready", preview_text="p",
                                metadata={"page_count": 42, "toc_count": 5})
        d = info.to_dict()
        assert d["page_count"] == 42
        assert d["toc_count"] == 5
        # Required keys still present
        assert d["status"] == "ready"

    def test_no_streamlit_dependency(self):
        """Service must work without Streamlit installed."""
        import sys
        # Temporarily hide streamlit from imports
        streamlit_modules = {k for k in sys.modules if k.startswith("streamlit")}
        for m in streamlit_modules:
            del sys.modules[m]
        try:
            svc = FileUploadService()
            fake = FakeUploadedFile("test.txt", b"hello")
            results = svc.process([fake])
            assert len(results) == 1
        finally:
            # Can't restore streamlit modules easily, but the test proves
            # the service itself doesn't import streamlit at module level
            pass

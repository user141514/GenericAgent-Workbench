"""Shared pytest fixtures for GenericAgent Workbench tests."""

import os
import sys

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture
def project_root() -> str:
    """Return the absolute path to the project root directory."""
    return PROJECT_ROOT


@pytest.fixture
def mock_mykeys() -> dict:
    """Return a valid mykeys config dict for testing without real API keys."""
    return {
        "native_oai_config": {
            "name": "test-backend",
            "apikey": "test-key-12345",
            "apibase": "https://api.test.example.com",
            "model": "test-model",
            "stream": False,
            "max_retries": 1,
            "connect_timeout": 5,
            "read_timeout": 10,
        }
    }


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temporary workspace with basic file structure for testing."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "test_file.txt").write_text("line 1\nline 2\nline 3\n")
    return workspace

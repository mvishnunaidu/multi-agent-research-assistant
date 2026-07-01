"""
conftest.py — shared pytest fixtures.

Tests never call a real LLM or download the embedding model — they run
fully offline by mocking the agent functions / LLM factory.
"""
import sys
from pathlib import Path

# Make sure "backend" is importable when pytest is run from the project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)
